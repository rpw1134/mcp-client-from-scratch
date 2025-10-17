# HTTPS MCP Client Implementation Plan

## Overview
This plan outlines the implementation of the `HTTPMCPClient` class to support HTTP/HTTPS-based MCP server communication.

## Key Architecture: Two-Stream Model

HTTP MCP servers use **TWO distinct communication channels**:

### 1. Persistent Notification Stream (GET → SSE)
- **Purpose:** Receive server-initiated notifications and potentially responses
- **Established:** Once during initialization via GET request
- **Kept open:** For entire session lifetime (with reconnection on disconnect)
- **Analog to STDIO:** Like continuously reading from stdout in background
- **Handles:**
  - Server notifications (no request ID)
  - Optionally: Responses to requests (with request ID)

### 2. Temporary Request/Response Streams (POST → Various)
- **Purpose:** Send requests and receive their responses
- **Established:** Per request
- **Closed:** After response completes
- **Response Types:**
  - Complete JSON (one chunk)
  - Chunked JSON (multiple chunks, accumulated)
  - SSE stream (multiple events for this request)
- **Analog to STDIO:** Like write to stdin + read specific response from stdout

### Critical Insight
Unlike STDIO where there's ONE bidirectional channel (stdin/stdout), HTTP uses:
- **One persistent READ channel** (GET SSE for notifications)
- **Multiple temporary REQUEST channels** (POST for commands)

## Architecture Analysis: STDIO Client Analogs

### Key STDIO Components and HTTP Equivalents

| STDIO Component | HTTP Equivalent | Notes |
|----------------|-----------------|-------|
| `Process` class | `httpx.AsyncClient` with connection pooling | Persistent HTTP client instead of subprocess |
| `write_stdin()` | `client.post()` or `client.stream()` | Send JSON-RPC requests via HTTP POST |
| `read_stdout()` | `response.aiter_bytes()` / `response.aiter_lines()` | Stream response data |
| `read_stdout_nowait()` | Non-blocking async iteration | Continuous reading from stream |
| `_continuous_read()` | Background task reading **persistent SSE notification stream** | Keep connection alive for server-initiated messages |
| `waiting_requests` dict | Same pattern | Match request IDs to futures for request/response pairing |
| Subprocess lifecycle | HTTP session lifecycle | Client creation, maintenance, cleanup |

## HTTP/SSE Two-Stream Model

**Critical Understanding:** HTTP MCP servers use TWO distinct communication patterns:

### 1. Persistent SSE Stream (Notification Channel)
- **Purpose:** Receive server-initiated notifications (analog to STDIO stdout notifications)
- **Lifecycle:** Established once during initialization, kept open for session duration
- **Method:** GET request to SSE endpoint
- **Pattern:** Long-lived streaming response that continuously sends events
- **Handles:** Notifications without request IDs, server-initiated messages

### 2. Request/Response Streams (Command Channel)
- **Purpose:** Send requests and receive responses (analog to STDIO request/response)
- **Lifecycle:** Created per request, closed after response completes
- **Method:** POST request with JSON-RPC payload
- **Pattern:** Each request may return:
  - **Complete JSON response** (single chunk)
  - **Chunked JSON response** (multiple chunks, assembled into one JSON)
  - **SSE stream** (multiple events, may return multiple JSON-RPC messages)
- **Handles:** Responses with request IDs matching `waiting_requests`

## Core Implementation Requirements

### 1. Connection Management

#### 1.1 Persistent HTTP Client
```python
class HTTPMCPClient(BaseMCPClient):
    def __init__(self, name: str, url: str) -> None:
        super().__init__()
        self.url = url
        self.name = name
        self.client: Optional[httpx.AsyncClient] = None
        self.notification_stream: Optional[httpx.Response] = None  # Persistent SSE for notifications
        self.notification_task: Optional[asyncio.Task] = None      # Background reader for notifications
```

**Key Considerations:**
- Create a persistent `httpx.AsyncClient` instance during `initialize_connection()`
- Configure connection pooling: `limits=httpx.Limits(max_connections=10, max_keepalive_connections=5)`
- Set appropriate timeouts: `timeout=httpx.Timeout(10.0, read=None)` (no read timeout for SSE)
- Store client as instance variable for reuse across all requests
- Implement proper cleanup in a `close()` or `__aexit__()` method

#### 1.2 Dual Stream Strategy

**Two Separate Concerns:**

##### A. Persistent Notification Stream (GET)
**Purpose:** Receive server-initiated notifications throughout session lifetime.

**Implementation:**
```python
async def _establish_notification_stream(self) -> None:
    """Establish persistent SSE stream for notifications."""
    backoff = 1.0
    max_backoff = 60.0

    while True:
        try:
            # Make GET request to SSE endpoint
            # Note: Cannot use context manager here - we need to keep stream open
            response = await self.client.__aenter__().stream(
                "GET",
                f"{self.url}/sse",  # Or just self.url if same endpoint
                headers={"Accept": "text/event-stream"},
                timeout=httpx.Timeout(10.0, read=None)  # No read timeout
            ).__aenter__()

            self.notification_stream = response
            backoff = 1.0  # Reset backoff on successful connection

            print("Notification stream established")
            await self._continuous_read_notifications()

        except (httpx.HTTPError, asyncio.CancelledError) as e:
            print(f"Notification stream lost: {e}. Reconnecting in {backoff}s...")
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, max_backoff)
        except Exception as e:
            print(f"Unexpected error in notification stream: {e}")
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, max_backoff)

async def _continuous_read_notifications(self) -> None:
    """Continuously read from persistent notification stream."""
    if not self.notification_stream:
        raise RuntimeError("Notification stream not established")

    try:
        async for line in self.notification_stream.aiter_lines():
            if not line or line.strip() == "":
                continue

            if line.startswith("data:"):
                data = line[len("data:"):].strip()

                try:
                    message = json.loads(data)

                    # Check if this is a response to a pending request
                    if "id" in message and message["id"] in self.waiting_requests:
                        print(f"Response received via notification stream for ID: {message['id']}")
                        future = self.waiting_requests[message["id"]]
                        if not future.done():
                            future.set_result(message)
                    else:
                        # True server notification (no request ID or not in waiting_requests)
                        print(f"Server Notification: {message}")
                        # TODO: Implement notification handler callback

                except json.JSONDecodeError:
                    print(f"Non-JSON notification data: {data}")

    except Exception as e:
        print(f"Error reading notifications: {e}")
        raise  # Re-raise to trigger reconnection
```

##### B. Temporary Request/Response Streams (POST)
**Purpose:** Send individual requests and receive their specific responses.

**Key Insight:** Each POST request creates a NEW stream that may return:
1. Complete JSON (one chunk, parse and done)
2. Chunked JSON (multiple chunks, accumulate until complete)
3. SSE stream (multiple events, parse each event)

**Implementation:**
```python
async def _send_post_request(self, payload: dict) -> dict:
    """Send POST request and handle streaming response."""
    try:
        async with self.client.stream(
            "POST",
            self.url,
            json=payload,
            headers=INIT_HEADERS
        ) as response:
            response.raise_for_status()

            content_type = response.headers.get("Content-Type", "").split(";")[0].strip()

            # Route to appropriate parser
            match content_type:
                case "text/event-stream":
                    return await self._parse_temporary_sse_stream(response)
                case "application/json":
                    # Could be complete or chunked
                    return await self._parse_json_or_chunked(response)
                case _:
                    # Unknown type, try to parse as JSON
                    return await self._parse_json_or_chunked(response)

    except httpx.HTTPError as e:
        return {"error": f"HTTP error: {e}"}
    except Exception as e:
        return {"error": f"Request failed: {e}"}
```

### 2. Response Type Handling

#### 2.1 Content-Type Detection
Implement a response type detector:

```python
async def _handle_response(self, response: httpx.Response) -> dict:
    """Route response to appropriate parser based on Content-Type."""
    content_type = response.headers.get("Content-Type", "").split(";")[0].strip()

    match content_type:
        case "text/event-stream":
            return await self._parse_sse_response(response)
        case "application/json":
            return await self._parse_json_response(response)
        case _:
            # Could be chunked JSON without proper Content-Type
            return await self._parse_chunked_json_response(response)
```

#### 2.2 Complete JSON Response Handling
**Simplest case:** Server sends entire JSON in one response.

```python
async def _parse_json_response(self, response: httpx.Response) -> dict:
    """Parse complete JSON response."""
    try:
        return await response.aread_json()
    except json.JSONDecodeError as e:
        return {"error": f"Invalid JSON response: {e}"}
```

#### 2.3 Chunked JSON Response Handling
**Challenge:** Server streams JSON in multiple chunks. Must accumulate and detect completion.

**Strategy:**
1. Read chunks using `response.aiter_bytes()` or `response.aiter_text()`
2. Accumulate chunks in a buffer
3. Attempt JSON parsing after each chunk
4. Return when valid, complete JSON is detected

**Implementation:**
```python
async def _parse_chunked_json_response(self, response: httpx.Response) -> dict:
    """Parse JSON response that may arrive in chunks."""
    buffer = ""

    async for chunk in response.aiter_text():
        buffer += chunk

        # Try to parse accumulated buffer
        try:
            parsed = json.loads(buffer)
            # Validate it's a complete JSON-RPC message
            if self._is_valid_jsonrpc(parsed):
                return parsed
        except json.JSONDecodeError:
            # Not yet complete, continue accumulating
            continue

    # Stream ended
    if buffer.strip():
        # Attempt final parse
        try:
            return json.loads(buffer)
        except json.JSONDecodeError:
            return {"error": "Incomplete JSON received"}

    return {"error": "Empty response"}

def _is_valid_jsonrpc(self, obj: dict) -> bool:
    """Validate JSON-RPC message structure."""
    return ("jsonrpc" in obj and
            ("result" in obj or "error" in obj) and
            "id" in obj)
```

**Optimization:** Use bracket counting to detect completion instead of parsing attempts:
```python
def _is_json_complete(self, text: str) -> bool:
    """Check if JSON object is syntactically complete using bracket counting."""
    depth = 0
    in_string = False
    escape_next = False

    for char in text.strip():
        if escape_next:
            escape_next = False
            continue
        if char == '\\':
            escape_next = True
            continue
        if char == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if char == '{':
            depth += 1
        elif char == '}':
            depth -= 1
            if depth == 0:
                return True  # Complete JSON object

    return False
```

#### 2.4 SSE Response Handling

**CRITICAL DISTINCTION:** There are TWO types of SSE streams:

##### A. Persistent Notification SSE Stream (from GET request)
- Established once during initialization
- Kept open for entire session
- Handled in `_continuous_read_notifications()` (see section 1.2.A)
- Receives ALL notifications and potentially responses if server uses SSE for everything

##### B. Temporary POST SSE Streams
- Created per POST request
- May contain multiple events for that specific request
- Closed after request completes
- Need to read ALL events from stream, not just first one

**Temporary SSE Stream Parser:**
```python
async def _parse_temporary_sse_stream(self, response: httpx.Response) -> dict:
    """Parse SSE stream from a POST request response.

    This is a TEMPORARY stream for this specific request.
    It may contain multiple events that are all part of the response.
    """
    messages = []
    primary_response = None

    try:
        async for line in response.aiter_lines():
            if not line or line.strip() == "":
                continue

            if line.startswith("data:"):
                data = line[len("data:"):].strip()

                try:
                    message = json.loads(data)

                    # If this has an ID matching our request, it's the primary response
                    if "id" in message and "jsonrpc" in message:
                        if primary_response is None:
                            primary_response = message
                        else:
                            # Multiple responses? Store all
                            messages.append(message)
                    else:
                        # Informational event or partial data
                        messages.append(message)

                except json.JSONDecodeError:
                    print(f"Non-JSON SSE data in POST stream: {data}")
                    continue

            elif line.startswith("event:"):
                event_type = line[len("event:"):].strip()
                print(f"SSE Event Type: {event_type}")
                # Could use event type to determine how to handle next data

        # Return the primary response if found
        if primary_response:
            return primary_response

        # If no primary response but we got messages, return first one
        if messages:
            return messages[0]

        return {"error": "No valid JSON-RPC message in SSE stream"}

    except Exception as e:
        return {"error": f"Error parsing SSE stream: {e}"}
```

**Note:** Some servers may return responses EITHER via:
- The POST response stream directly, OR
- Via the persistent notification stream

If using persistent notification stream for responses, the POST may just return acknowledgment.

### 3. Request/Response Matching

**Updated pattern for two-stream model:**

```python
async def send_request(self, payload: dict) -> dict:
    """Send JSON-RPC request and await response.

    Responses may come from:
    1. Direct POST response (most common)
    2. Persistent notification stream (if server configured that way)
    """
    if not self.client:
        return {"error": "Client not initialized"}

    curr_id = self.current_id
    self.current_id += 1

    request_payload = payload.copy()
    request_payload["id"] = curr_id

    try:
        # Create future for response
        # (May be fulfilled by POST response OR notification stream)
        self.waiting_requests[curr_id] = asyncio.Future()

        # Send POST request with streaming enabled
        result = await self._send_post_request(request_payload)

        # If POST returned a response directly, fulfill the future
        if "id" in result and result["id"] == curr_id:
            if not self.waiting_requests[curr_id].done():
                self.waiting_requests[curr_id].set_result(result)

        # Wait for response (either from POST or notification stream)
        # Note: If response came from POST, future is already fulfilled
        # If server uses notification stream for responses, wait here
        result = await asyncio.wait_for(
            self.waiting_requests[curr_id],
            timeout=10.0
        )

        del self.waiting_requests[curr_id]
        return result

    except asyncio.TimeoutError:
        if curr_id in self.waiting_requests:
            del self.waiting_requests[curr_id]
        return {"error": f"Request {curr_id} timed out"}
    except httpx.HTTPError as e:
        if curr_id in self.waiting_requests:
            del self.waiting_requests[curr_id]
        return {"error": f"HTTP error: {e}"}
    except Exception as e:
        if curr_id in self.waiting_requests:
            del self.waiting_requests[curr_id]
        return {"error": f"Request failed: {e}"}
```

**Alternative: If server ALWAYS uses notification stream for responses**

Some servers may send an immediate ACK via POST and deliver actual response via notification stream:

```python
async def send_request(self, payload: dict) -> dict:
    """Send JSON-RPC request, response comes via notification stream."""
    if not self.client:
        return {"error": "Client not initialized"}

    curr_id = self.current_id
    self.current_id += 1

    request_payload = payload.copy()
    request_payload["id"] = curr_id

    try:
        # Create future BEFORE sending request
        self.waiting_requests[curr_id] = asyncio.Future()

        # Send request (don't await response parsing)
        response = await self.client.post(
            self.url,
            json=request_payload,
            headers=INIT_HEADERS
        )
        response.raise_for_status()

        # ACK received, actual response will come via notification stream
        # Wait for notification stream to fulfill the future
        result = await asyncio.wait_for(
            self.waiting_requests[curr_id],
            timeout=10.0
        )

        del self.waiting_requests[curr_id]
        return result

    except asyncio.TimeoutError:
        if curr_id in self.waiting_requests:
            del self.waiting_requests[curr_id]
        return {"error": f"Request {curr_id} timed out"}
    except Exception as e:
        if curr_id in self.waiting_requests:
            del self.waiting_requests[curr_id]
        return {"error": f"Request failed: {e}"}
```

### 4. Connection Lifecycle

#### 4.1 Initialization
```python
async def initialize_connection(self) -> dict:
    """Initialize HTTP client and establish connections."""
    try:
        # Create persistent HTTP client
        self.client = httpx.AsyncClient(
            headers=INIT_HEADERS,
            timeout=httpx.Timeout(10.0, read=None),
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5)
        )

        # Send initialization POST request
        result = await self._send_post_request(INIT_PAYLOAD)

        if "error" in result:
            await self.close()
            return result

        # Increment ID counter
        self.current_id += 1

        # Start persistent notification stream in background
        self.notification_task = asyncio.create_task(
            self._establish_notification_stream()
        )

        # Send initialized notification if required by protocol
        # await self.send_notification("notifications/initialized", {"status": "ready"})

        print(f"HTTP MCP client initialized for {self.name}")
        return result

    except httpx.HTTPError as e:
        await self.close()
        return {"error": f"Failed to initialize: {e}"}
    except Exception as e:
        await self.close()
        return {"error": f"Unexpected error: {e}"}
```

**Alternative Initialization (if GET is used for init):**

If the MCP spec requires GET for the initial SSE connection:

```python
async def initialize_connection(self) -> dict:
    """Initialize with GET request to establish SSE notification stream."""
    try:
        # Create persistent HTTP client
        self.client = httpx.AsyncClient(
            headers=INIT_HEADERS,
            timeout=httpx.Timeout(10.0, read=None),
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5)
        )

        # Establish SSE stream with GET
        # This will be the main notification channel
        self.notification_task = asyncio.create_task(
            self._establish_notification_stream()
        )

        # Wait a bit for stream to establish
        await asyncio.sleep(0.5)

        # Send initialization via POST
        result = await self._send_post_request(INIT_PAYLOAD)

        if "error" in result:
            await self.close()
            return result

        self.current_id += 1
        print(f"HTTP MCP client initialized for {self.name}")
        return result

    except Exception as e:
        await self.close()
        return {"error": f"Initialization failed: {e}"}
```

#### 4.2 Cleanup
```python
async def close(self) -> None:
    """Clean up HTTP client and background tasks."""
    print(f"Closing HTTP MCP client for {self.name}")

    # Cancel notification stream task
    if self.notification_task and not self.notification_task.done():
        self.notification_task.cancel()
        try:
            await self.notification_task
        except asyncio.CancelledError:
            pass
        self.notification_task = None

    # Close notification stream
    if self.notification_stream:
        try:
            await self.notification_stream.aclose()
        except Exception as e:
            print(f"Error closing notification stream: {e}")
        self.notification_stream = None

    # Close HTTP client
    if self.client:
        try:
            await self.client.aclose()
        except Exception as e:
            print(f"Error closing HTTP client: {e}")
        self.client = None

    # Clear pending requests
    for request_id, future in self.waiting_requests.items():
        if not future.done():
            future.set_exception(RuntimeError("Client closed"))
    self.waiting_requests.clear()

    print(f"HTTP MCP client closed for {self.name}")
```

### 5. Error Handling and Resilience

#### 5.1 Timeout Configuration
- **Connection timeout:** 10 seconds for establishing connection
- **Read timeout:** None (infinite) for SSE streams, 30 seconds for regular requests
- **Request timeout:** 10 seconds at application level (asyncio.wait_for)

#### 5.2 Retry Logic
```python
async def _send_request_with_retry(
    self,
    payload: dict,
    max_retries: int = 3
) -> dict:
    """Send request with exponential backoff retry."""
    backoff = 1.0

    for attempt in range(max_retries):
        try:
            return await self.send_request(payload)
        except httpx.HTTPError as e:
            if attempt == max_retries - 1:
                return {"error": f"Max retries exceeded: {e}"}

            await asyncio.sleep(backoff)
            backoff *= 2
```

#### 5.3 Connection Health Monitoring
```python
async def _health_check(self) -> bool:
    """Check if HTTP client is healthy."""
    if not self.client or self.client.is_closed:
        return False

    try:
        # Send ping or health check request
        response = await self.client.get(
            f"{self.url}/health",
            timeout=5.0
        )
        return response.status_code == 200
    except httpx.HTTPError:
        return False
```

### 6. Special Considerations

#### 6.1 Notifications (Server-Initiated Messages)
HTTP doesn't support server-initiated messages unless using SSE or WebSocket.

**Options:**
1. **SSE Stream:** Server can send notifications via SSE events
2. **Polling:** Periodically poll for notifications (not recommended)
3. **Long-polling:** Keep a request open until server has a message

**Recommended:** If SSE is available, handle notifications in `_continuous_sse_read()`

#### 6.2 Concurrent Requests
Unlike STDIO (sequential), HTTP can handle concurrent requests:

```python
# Multiple requests can be in-flight simultaneously
tasks = [
    client.send_request(payload1),
    client.send_request(payload2),
    client.send_request(payload3)
]
results = await asyncio.gather(*tasks)
```

**Note:** Ensure `current_id` increment is thread-safe:
```python
import threading

class HTTPMCPClient(BaseMCPClient):
    def __init__(self, ...):
        ...
        self._id_lock = threading.Lock()

    def _get_next_id(self) -> int:
        with self._id_lock:
            curr_id = self.current_id
            self.current_id += 1
            return curr_id
```

Or use async-safe counter:
```python
def _get_next_id(self) -> int:
    curr_id = self.current_id
    self.current_id += 1
    return curr_id
# Safe because asyncio is single-threaded per event loop
```

#### 6.3 Session Management
For authenticated endpoints:
```python
self.client = httpx.AsyncClient(
    headers={
        **INIT_HEADERS,
        "Authorization": f"Bearer {token}"
    }
)
```

## Implementation Checklist

### Phase 1: Basic Request/Response
- [ ] Create persistent `httpx.AsyncClient` in `__init__` or `initialize_connection()`
- [ ] Implement `_handle_response()` with content-type routing
- [ ] Implement `_parse_json_response()` for complete JSON
- [ ] Implement `send_request()` with request/response matching
- [ ] Implement `get_tools()` using `send_request()`
- [ ] Add proper error handling and timeouts
- [ ] Implement `close()` cleanup method

### Phase 2: Chunked JSON Support
- [ ] Implement `_parse_chunked_json_response()` with buffer accumulation
- [ ] Add JSON completion detection (bracket counting or parse attempts)
- [ ] Test with servers that send chunked responses
- [ ] Handle edge cases (empty chunks, malformed JSON)

### Phase 3: SSE Support
- [ ] Refactor `parse_sse()` into class method `_parse_sse_response()`
- [ ] Implement `_continuous_sse_read()` for background SSE processing
- [ ] Start background task in `initialize_connection()` for SSE mode
- [ ] Handle SSE reconnection with exponential backoff
- [ ] Implement notification handling for server-initiated messages
- [ ] Add SSE event filtering (event types, IDs)

### Phase 4: Resilience & Optimization
- [ ] Add retry logic with exponential backoff
- [ ] Implement connection health monitoring
- [ ] Add connection pooling configuration
- [ ] Implement concurrent request handling
- [ ] Add comprehensive logging
- [ ] Write unit tests for each response type
- [ ] Integration tests with real MCP servers

### Phase 5: Advanced Features
- [ ] Support for authenticated endpoints
- [ ] Request cancellation support
- [ ] Metrics collection (request counts, latencies)
- [ ] Graceful degradation (fallback to polling if SSE fails)
- [ ] WebSocket support (future enhancement)

## Testing Strategy

### Unit Tests
1. Mock `httpx.AsyncClient` responses
2. Test each response type parser independently
3. Test request/response matching logic
4. Test error handling paths

### Integration Tests
1. Test against real MCP servers (stdio-based servers with HTTP proxy)
2. Test chunked JSON with controlled chunk sizes
3. Test SSE with simulated server notifications
4. Test connection failure and recovery
5. Test concurrent request handling

### Edge Cases to Test
- Empty responses
- Malformed JSON
- Incomplete chunked JSON
- SSE connection drops mid-stream
- Very large responses
- Very slow responses (timeout handling)
- Interleaved SSE events and responses

## Migration Path from Current Implementation

1. **Keep current `initialize_connection()` logic** but enhance it:
   - Create persistent client instead of new client per request
   - Store the client and stream references
   - Start background tasks for SSE

2. **Implement `send_request()` and `get_tools()`** using the patterns from STDIO client

3. **Refactor `_continuous_read()`** to handle SSE stream instead of stdout

4. **Add `close()` method** for cleanup (analog to `_kill_process()`)

## Open Questions / Design Decisions

1. **SSE Endpoint:** Do MCP servers use the same URL for init and SSE, or separate endpoints?
   - *Recommendation:* Check MCP spec; likely same endpoint with different request types

2. **Notification Handling:** How should we expose server notifications to callers?
   - *Options:* Callback function, queue, event emitter
   - *Recommendation:* Add `on_notification` callback parameter to `__init__`

3. **Multiple Concurrent Connections:** Should we support multiple SSE streams?
   - *Recommendation:* No, one persistent stream per client instance

4. **Protocol Negotiation:** How to determine if server supports SSE vs request/response?
   - *Recommendation:* Send initialization with `Accept: application/json, text/event-stream` and handle based on response

## Architecture Diagrams

### Flow Diagram: Two-Stream Model

```
┌─────────────────────────────────────────────────────────────────┐
│                      HTTPMCPClient                               │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌────────────────────────────────────────────────────────┐    │
│  │  Persistent Notification Stream (Background Task)      │    │
│  │  ────────────────────────────────────────────────      │    │
│  │                                                         │    │
│  │  GET /sse  ─────────────────────►  Server              │    │
│  │             (kept open forever)                         │    │
│  │                                                         │    │
│  │  ◄────────── SSE: data: {...}  ◄────  Notification     │    │
│  │  ◄────────── SSE: data: {...}  ◄────  Notification     │    │
│  │  ◄────────── SSE: data: {...}  ◄────  Response (maybe) │    │
│  │         │                                               │    │
│  │         └──► _continuous_read_notifications()          │    │
│  │                    │                                    │    │
│  │                    ├─► Has ID? → Fulfill future        │    │
│  │                    └─► No ID?  → Handle notification   │    │
│  └────────────────────────────────────────────────────────┘    │
│                                                                  │
│  ┌────────────────────────────────────────────────────────┐    │
│  │  Request/Response Streams (Per-Request)                │    │
│  │  ──────────────────────────────────────                │    │
│  │                                                         │    │
│  │  1. Create future in waiting_requests[id]              │    │
│  │                                                         │    │
│  │  2. POST /endpoint ──────────────►  Server             │    │
│  │         Body: {jsonrpc, id, method, params}            │    │
│  │                                                         │    │
│  │  3. Response arrives:                                  │    │
│  │                                                         │    │
│  │     Option A: Complete JSON                            │    │
│  │     ◄────────── {jsonrpc, id, result}                  │    │
│  │                     │                                   │    │
│  │                     └──► Parse → Fulfill future        │    │
│  │                                                         │    │
│  │     Option B: Chunked JSON                             │    │
│  │     ◄────── chunk1 ◄─── chunk2 ◄─── chunk3            │    │
│  │                     │                                   │    │
│  │                     └──► Accumulate → Parse → Fulfill  │    │
│  │                                                         │    │
│  │     Option C: SSE Stream (temporary)                   │    │
│  │     ◄─── data: {...} ◄─── data: {...}                 │    │
│  │                     │                                   │    │
│  │                     └──► Parse events → Fulfill        │    │
│  │                                                         │    │
│  │  4. await future to get result                         │    │
│  │                                                         │    │
│  └────────────────────────────────────────────────────────┘    │
│                                                                  │
│  waiting_requests: {id → Future}                                │
│  ├─ Fulfilled by: POST response OR notification stream          │
│  └─ Enables request/response matching                           │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Comparison: STDIO vs HTTP

```
┌─────────────────────────────────┬──────────────────────────────────┐
│         STDIO Client             │          HTTP Client             │
├─────────────────────────────────┼──────────────────────────────────┤
│                                  │                                  │
│  Start subprocess                │  Create httpx.AsyncClient       │
│                                  │                                  │
│  Write to stdin:                 │  POST request:                  │
│    {id: 1, method: "init"}       │    {id: 1, method: "init"}      │
│                                  │                                  │
│  Read from stdout:               │  Read POST response:            │
│    {id: 1, result: {...}}        │    {id: 1, result: {...}}       │
│                                  │                                  │
│  Background: _continuous_read()  │  Background: GET SSE stream     │
│    Loop: readline()              │    Loop: aiter_lines()          │
│    ├─ Has ID? Fulfill future     │    ├─ Has ID? Fulfill future    │
│    └─ No ID? Notification        │    └─ No ID? Notification       │
│                                  │                                  │
│  Write request:                  │  POST request:                  │
│    {id: 2, method: "tools"}      │    {id: 2, method: "tools"}     │
│                                  │                                  │
│  Response via stdout             │  Response via:                  │
│    (continuous_read catches it)  │    a) POST response directly    │
│                                  │    b) SSE notification stream   │
│                                  │                                  │
│  ONE channel (stdin/stdout)      │  TWO channels (POST + GET SSE)  │
│                                  │                                  │
└─────────────────────────────────┴──────────────────────────────────┘
```

## References

- MCP Protocol Specification: (add link if available)
- httpx Streaming Documentation: https://www.python-httpx.org/quickstart/#streaming-responses
- SSE Specification: https://html.spec.whatwg.org/multipage/server-sent-events.html
- JSON-RPC 2.0 Specification: https://www.jsonrpc.org/specification

## Notes

- Current implementation (lines 268-302) has good foundation for SSE detection
- Need to extract and enhance chunked JSON handling
- Connection pooling will significantly improve performance for request/response mode
- **Key difference from STDIO:** HTTP uses separate persistent notification stream (GET SSE) plus per-request POST streams
- The persistent SSE stream must be kept open in background task, similar to `_continuous_read()` in STDIO client
- POST responses may be complete JSON, chunked JSON, or temporary SSE streams - all need separate handling
- `waiting_requests` futures can be fulfilled from EITHER POST response OR notification stream
