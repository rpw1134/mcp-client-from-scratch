# Session Persistence Implementation Plan

## Current Architecture Overview

Your MCP client currently:
- Uses FastAPI with dependency injection for client management
- Supports both HTTP and STDIO MCP server connections
- Routes user messages through OpenAI to determine tool selection
- Maintains in-memory state per client instance (current_id, waiting_requests, tools)
- Uses a singleton pattern for STDIO client management
- **No conversation history tracking** - each request is stateless
- **No multi-server session management** - currently hardcoded to single test server

## Key Challenge: Session Context

The primary issue is in `make_llm_request.py:8-34` - the AI_request function sends only:
1. System prompt with available tools
2. User's current message

**Missing**: Historical conversation context across multiple turns.

---

## Research & Decision Points

### 1. **Storage Backend Selection**

**Decision Criteria:**
- Volume: How many concurrent sessions? Messages per session?
- Latency requirements: Real-time chat needs fast reads/writes
- Query patterns: Simple key-value lookups or complex queries?
- Infrastructure: Preference for managed vs self-hosted?

**Options to Research:**

#### A. **Redis (Recommended Starting Point)**
**Pros:**
- Sub-millisecond latency for session reads
- Built-in TTL for automatic session expiration
- Simple key-value model matches session needs
- Excellent for temporary conversation state

**Cons:**
- Primarily in-memory (costs scale with data size)
- Less suitable for long-term analytics
- Persistence is secondary feature

**Research:**
- Redis JSON module for storing structured session data
- TTL strategies (e.g., 30-min idle timeout, 24-hour max)
- Connection pooling with `redis-py` or `aioredis`
- Fallback strategy if Redis is unavailable

**When to use:** Low-to-medium scale, fast prototyping, sessions are ephemeral

---

#### B. **PostgreSQL**
**Pros:**
- ACID compliance for reliability
- Native JSON/JSONB support for flexible message storage
- Good for analytics queries (e.g., "show me all sessions using tool X")
- You likely already have it in your stack

**Cons:**
- Higher latency than Redis (~5-50ms vs <1ms)
- Requires schema management and migrations
- More operational overhead

**Research:**
- Schema design: `sessions` table with JSONB `messages` column
- Indexing strategies (GIN indexes on JSONB for tool usage queries)
- Connection pooling with SQLAlchemy/asyncpg
- Partitioning strategies for scaling (if needed)

**When to use:** You need durable storage, analytics, or already have Postgres infrastructure

---

#### C. **Hybrid Approach (Redis + PostgreSQL)**
**Architecture:**
- Redis: Active session cache (hot path)
- PostgreSQL: Persistent storage (cold path)

**Flow:**
1. Check Redis for session
2. If miss, load from Postgres → cache in Redis
3. Write to both (or async write to Postgres)

**Research:**
- Write-through vs write-behind caching patterns
- Consistency guarantees (eventual vs strong)
- Cache invalidation strategies

**When to use:** High scale with both performance and durability requirements

---

### 2. **Multi-Server Identifier Strategy**

**Current State:** No unique server identifiers; hardcoded test server in dependencies.

**Requirements:**
- Each MCP server needs a unique, stable ID
- Sessions must track which server(s) were used
- Tool namespacing to avoid collisions (e.g., two servers with "add" tool)

**Research Areas:**

#### A. **Server Registration & Identification**
- **UUID vs Human-Readable IDs**:
  - UUIDs: Guaranteed unique, less readable
  - Slugs: `filesystem-server`, `email-server` (require uniqueness validation)
- **Server Registry Table/Config:**
  ```python
  # Example schema
  {
    "server_id": "uuid-or-slug",
    "name": "Filesystem Server",
    "type": "stdio",  # or "http"
    "connection_config": {...},
    "tools": [...],  # cached tool list
    "metadata": {...}
  }
  ```
- **Dynamic vs Static Registration:**
  - Static: Define all servers in config file (simpler)
  - Dynamic: API endpoint to register new servers (more flexible)

#### B. **Tool Namespacing**
**Problem:** Multiple servers may expose tools with same name.

**Solutions to Research:**
- **Prefixing:** `filesystem_server.read_file`, `email_server.read_file`
- **Explicit Server Selection:** User/AI specifies which server to use
- **Automatic Resolution:** Route based on tool signature/context

**Recommendation:** Start with prefixing - simplest and most explicit.

#### C. **Session-Server Relationship**
**Options:**
1. **1:1 Sessions** - One session per server (simpler, isolated)
2. **1:N Sessions** - One session can use multiple servers (complex, powerful)

**Research:**
- How does the AI choose between servers with overlapping capabilities?
- Should session store active server list or discover dynamically?
- Routing logic: deterministic vs AI-driven

---

### 3. **Session Data Model**

**Core Fields to Research:**

```python
{
  "session_id": "uuid",
  "created_at": "timestamp",
  "updated_at": "timestamp",
  "expires_at": "timestamp",  # For TTL
  "user_id": "optional-user-identifier",

  # Server context
  "active_servers": ["server_id_1", "server_id_2"],

  # Conversation history
  "messages": [
    {
      "role": "user|assistant|system",
      "content": "...",
      "timestamp": "...",
      "tool_calls": [...],  # If AI requested tools
      "tool_results": [...]  # Results from MCP servers
    }
  ],

  # Metadata
  "metadata": {
    "total_tokens": 0,
    "tool_usage_count": {},
    "last_active_server": "server_id"
  }
}
```

**Research Questions:**
- **Message History Limits:**
  - Store last N messages?
  - Sliding window by token count?
  - Summarization for old messages?
- **Token Counting:** How to track OpenAI token usage per session?
- **Pruning Strategy:** Auto-delete old sessions? Archive to cold storage?

---

### 4. **API Design Changes**

**Current:** `/tests/request` takes a `ChatRequest` with just `message`.

**Proposed:** Add session management endpoints.

**Research:**

#### A. **Session Lifecycle Endpoints**
```
POST   /sessions                    # Create new session
GET    /sessions/{session_id}       # Retrieve session state
DELETE /sessions/{session_id}       # End session
POST   /sessions/{session_id}/messages  # Send message in session
```

#### B. **Server Selection**
```
POST /sessions/{session_id}/servers/{server_id}  # Activate server for session
GET  /sessions/{session_id}/tools                # List available tools
```

#### C. **Backward Compatibility**
- Keep `/tests/request` for single-turn requests?
- Or deprecate in favor of session-based flow?

---

### 5. **Conversation History Management**

**Integration Point:** `make_llm_request.py` needs refactoring.

**Current:**
```python
messages=[
  {"role": "system", "content": system_prompt},
  {"role": "user", "content": message}
]
```

**Needed:**
```python
messages=[
  {"role": "system", "content": system_prompt},
  # ... load historical messages from session ...
  {"role": "user", "content": "previous user message"},
  {"role": "assistant", "content": "previous AI response"},
  {"role": "user", "content": current_message}
]
```

**Research:**
- **Message Filtering:** Should all messages go to OpenAI? Or filter by relevance?
- **System Prompt Updates:** If available tools change mid-session, update system prompt?
- **Token Limits:** OpenAI has context windows - how to handle overflow?
  - Truncate oldest messages
  - Summarize older context
  - Split into multiple sessions

---

## Recommended Implementation Phases

### Phase 1: Redis-Based MVP (Fastest Path)
**Goal:** Proof-of-concept with minimal infrastructure.

**Steps:**
1. Add `redis` and `aioredis` dependencies
2. Create `SessionManager` class with:
   - `create_session()` → returns session_id
   - `get_session(session_id)` → returns messages
   - `append_message(session_id, message)` → stores new message
3. Modify `/tests/request` to accept optional `session_id`
4. Update `AI_request()` to load conversation history from Redis
5. Set 1-hour TTL on sessions

**Validation:**
- Test multi-turn conversations maintain context
- Verify sessions expire after TTL

---

### Phase 2: Multi-Server Support
**Goal:** Allow sessions to interact with multiple MCP servers.

**Steps:**
1. Create `servers.json` config with server definitions
2. Add `server_id` field to tools in `MCPClient.tools` dict
3. Update system prompt to include server namespacing
4. Implement server selection logic in request handler
5. Store active servers in session data

**Validation:**
- Session uses tools from Server A, then Server B
- Tool name collisions handled correctly

---

### Phase 3: PostgreSQL Persistence (Optional)
**Goal:** Durable storage for analytics and long-term sessions.

**Steps:**
1. Add SQLAlchemy models for `sessions` and `servers`
2. Implement write-through caching (Redis → Postgres)
3. Add session query endpoints (e.g., `/sessions?user_id=X`)
4. Migration scripts for schema updates

**Validation:**
- Redis failure doesn't lose data
- Can query historical tool usage patterns

---

## Open Questions to Resolve

1. **User Authentication:** Are sessions tied to authenticated users, or anonymous?
2. **Concurrent Server Access:** Can a single message trigger tools from multiple servers?
3. **Error Handling:** If a server dies mid-session, how to recover?
4. **Scaling:** Horizontal scaling needs distributed Redis (Redis Cluster) or sticky sessions.
5. **Observability:** How to trace a request across session → AI → MCP server?

---

## Next Steps

1. **Choose Storage Backend** (Recommend: Start with Redis)
2. **Design Session Schema** (Use JSON example above as template)
3. **Implement SessionManager** (CRUD operations)
4. **Refactor AI_request** (Add history loading)
5. **Add Session Endpoints** (REST API)
6. **Test Multi-Turn Conversations** (Validate context retention)
7. **Add Server Registry** (Static config file first)
8. **Implement Tool Namespacing** (Prefix with server_id)

---

## Code Structure Recommendations

```
src/mcp_client_scratch/
├── classes/
│   ├── MCPClient.py          # (existing)
│   └── SessionManager.py     # NEW: Redis/Postgres session ops
├── routers/
│   ├── sessions.py           # NEW: Session CRUD endpoints
│   └── servers.py            # NEW: Server management endpoints
├── schemas/
│   ├── session.py            # NEW: Session pydantic models
│   └── server.py             # NEW: Server config models
├── config/
│   └── servers.json          # NEW: Server registry
└── utils/
    └── session_utils.py      # NEW: History formatting, pruning
```

---

## Estimated Effort

- **Redis MVP (Phase 1):** 1-2 days
- **Multi-Server (Phase 2):** 2-3 days
- **Postgres Persistence (Phase 3):** 2-4 days

**Total:** 1-2 weeks for full implementation
