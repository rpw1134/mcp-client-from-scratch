import chromadb
from typing import List
import json
import uuid

class VectorStore:
    """Manages vector storage and semantic search for tool embeddings."""

    def __init__(self, openai_client):
        """Initialize vector store with ChromaDB client and OpenAI client.

        Args:
            openai_client: OpenAI client instance for creating embeddings
        """
        self.openai_client = openai_client
        self._vector_store = chromadb.Client() # temporary vector store, cleans up on application exit
        self._collection: chromadb.Collection = self._vector_store.create_collection(name="mcp_client_tools")

    async def embed_tool(self, tool: dict) -> None:
        """Embed a single tool into the vector store.

        Args:
            tool: Tool dictionary with 'name', 'description', and 'inputSchema' keys
        """
        tool_text: str = f"""
        Tool Name: {tool['name']}
        Tool Description: {tool['description']}
        Tool Parameters: {json.dumps(tool['inputSchema'])}
        """
        embedding: List[float] = await self.openai_client.create_embedding(tool_text)
        self._collection.add(
            ids=[str(uuid.uuid4())],
            embeddings=[embedding],
            metadatas=[tool],
        )

    async def batch_embed_tools(self, tools: dict[str, dict]) -> None:
        """Embed multiple tools into the vector store in batch.

        Args:
            tools: Dictionary of tool dictionaries
        """
        tools_list = list(tools.values())

        # Create text representations for all tools
        tool_texts = [
            f"""Tool Name: {tool.get('name', 'Unknown')}
Tool Description: {tool.get('description', 'No description')}
Tool Parameters: {json.dumps(tool.get('inputSchema', {}))}"""
            for tool in tools_list
        ]

        # Create embeddings in a single batch request
        tool_embeddings: List[List[float]] = await self.openai_client.create_embeddings_batch(tool_texts)

        # Add all embeddings to the collection
        self._collection.add(
            ids=[str(uuid.uuid4()) for _ in tools_list],
            embeddings=[*tool_embeddings],
            metadatas=[{
                "name": tool.get('name', 'Unknown'),
                "description": tool.get('description', 'No description'),
                "inputSchema": json.dumps(tool.get('inputSchema',{}))
            } for tool in tools_list],
        )

    async def query_similar_tools(self, query: str, n_results: int = 10) -> List:
        """Query for similar tools using semantic search.

        Args:
            query: Query string to search for similar tools
            n_results: Number of results to return

        Returns:
            List of similar tool dictionaries
        """
        query_embedding: List[float] = await self.openai_client.create_embedding(query)
        results = self._collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results,
        )
        return results['metadatas'][0] if results['metadatas'] else []