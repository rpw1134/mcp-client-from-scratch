import chromadb
from typing import List
import json
import uuid
from .OpenAIClient import OpenAIClient
from ..utils.tools import hash_tool
import time
import logging

logger = logging.getLogger("uvicorn.error")
class VectorStore:
    """Manages vector storage and semantic search for tool embeddings."""
    
    #TODO: delete tools from store if client is failed/removed. Need to detect a failed client and remove all tools. 

    def __init__(self, openai_client: OpenAIClient, persist_directory: str = ""):
        """Initialize vector store with ChromaDB client and OpenAI client.

        Args:
            openai_client: OpenAI client instance for creating embeddings
        """
        self.openai_client = openai_client
        if persist_directory=="":
            self._vector_store = chromadb.Client() # temporary vector store, cleans up on application exit
        else:
            self._vector_store = chromadb.PersistentClient(path=persist_directory)
        self._collection: chromadb.Collection = self._vector_store.get_or_create_collection(name="mcp_client_tools")

    async def embed_tool(self, tool: dict) -> None:
        """Embed a single tool into the vector store.

        Args:
            tool: Tool dictionary with 'name', 'description', and 'inputSchema' keys
        """
        tool_text: str = f"""
        Tool Name: {tool['name']}
        Tool Description: {tool['description']}
        Tool InputSchema: {json.dumps(tool['inputSchema'])}
        """

        embedding: List[float] = await self.openai_client.create_embedding(tool_text)
        self._collection.add(
            ids=[tool.get('name', 'unknown')+tool.get('source', 'unknown')],
            embeddings=[embedding],
            metadatas=[{
                "name": tool.get('name', 'Unknown'),
                "description": tool.get('description', 'No description'),
                "inputSchema": json.dumps(tool.get('inputSchema',{})),
                "source": tool.get('source', 'unknown'),
                "hash": hash_tool(tool)
            }],
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
                Tool InputSchema: {json.dumps(tool.get('inputSchema', {}))}"""
            for tool in tools_list
        ]

        # Create embeddings in a single batch request
        tool_embeddings: List[List[float]] = await self.openai_client.create_embeddings_batch(tool_texts)

        # Add all embeddings to the collection
        self._collection.add(
            ids=[tool.get('name', 'unknown')+tool.get('source', 'unknown') for tool in tools_list],
            embeddings=[*tool_embeddings],
            metadatas=[{
                "name": tool.get('name', 'Unknown'),
                "description": tool.get('description', 'No description'),
                "inputSchema": json.dumps(tool.get('inputSchema',{})),
                "source": tool.get('source', 'unknown'),
                "hash": hash_tool(tool)
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
    
    async def get_tool_hashes(self) -> dict:
        """Retrieve all tool hashes stored in the vector store.

        Returns:
            List of tool hashes
        """
        all_items = self._collection.get()
        if not all_items['metadatas']:
            return {}
        return {
            str(metadata.get("name", "ERROR"))+":"+str(metadata.get("source", "ERROR")): metadata.get("hash", "")
            for metadata in all_items['metadatas']
        }
        
    async def sync_tools(self, tools: dict[str, dict]) -> None:
        """Sync the vector store with the provided tools.

        Args:
            tools: Dictionary of tool dictionaries
        """
        existing_hashes = await self.get_tool_hashes()
        logger.debug(f"Existing tools in vector store: {list(existing_hashes.keys())})")
        tools_to_embed = {} 
        for tool in tools.values():
            tool_key = str(tool.get("name", "ERROR"))+":"+str(tool.get("source", "ERROR"))
            tool_hash = hash_tool(tool) if tool_key != "ERROR:ERROR" else ""
            if existing_hashes.get(tool_key) != tool_hash:
                tools_to_embed[tool.get("name", "unnamed")] = tool
        if tools_to_embed:
            await self.batch_embed_tools(tools_to_embed)
        else:
            logger.info("Vector store is already up to date; no new tools to embed.")
            
            
    async def clear_store(self) -> None:
        """Clear all data from the vector store."""
        self._vector_store.delete_collection(name="mcp_client_tools")
        self._collection = self._vector_store.get_or_create_collection(name="mcp_client_tools")
        
    
    
    