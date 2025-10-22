import os
import logging
from typing import Optional, List, cast
from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionMessageParam
import chromadb
import json
import uuid

logger = logging.getLogger("uvicorn.error")


class OpenAIClient:
    """Client for OpenAI API operations.

    Provides centralized access to OpenAI services including:
    - Chat completions
    - Embeddings
    - Async operations with connection pooling
    """

    def __init__(self, api_key: Optional[str] = None):
        """Initialize OpenAI client with API key.

        Args:
            api_key: OpenAI API key. If not provided, reads from OPEN_AI_API_KEY env var

        Raises:
            ValueError: If API key not provided and not found in environment
        """
        if api_key is None:
            api_key = os.getenv("OPEN_AI_API_KEY")
        if not api_key:
            raise ValueError("OPEN_AI_API_KEY not provided and not set in environment")
        self._client = AsyncOpenAI(api_key=api_key)
        self._vector_store = chromadb.Client() # temporary vector store, cleans up on application exit
        self._collection: chromadb.Collection = self._vector_store.create_collection(name="mcp_client_tools")

    @property
    def client(self) -> AsyncOpenAI:
        """Get the underlying AsyncOpenAI client."""
        return self._client

    async def chat_completion(
        self,
        messages: List[ChatCompletionMessageParam],
        model: str = "gpt-4o-mini",
        max_tokens: Optional[int] = None,
        temperature: float = 1.0,
        **kwargs
    ) -> str:
        """Create a chat completion.

        Args:
            messages: List of message objects with role and content
            model: OpenAI model to use
            max_tokens: Maximum tokens in completion
            temperature: Sampling temperature (0-2)
            **kwargs: Additional parameters for chat.completions.create

        Returns:
            The completion text content

        Raises:
            Exception: If API request fails
        """
        try:
            response = await self.client.chat.completions.create(
                model=model,
                messages=messages,
                max_completion_tokens=max_tokens,
                temperature=temperature,
                **kwargs
            )
            return response.choices[0].message.content or ""
        except Exception as e:
            logger.error(f"Chat completion failed: {e}", exc_info=True)
            raise

    async def create_embedding(
        self,
        text: str,
        model: str = "text-embedding-3-small"
    ) -> List[float]:
        """Create an embedding for the given text.

        Args:
            text: Text to embed
            model: Embedding model to use

        Returns:
            List of floats representing the embedding vector

        Raises:
            Exception: If API request fails
        """
        try:
            response = await self.client.embeddings.create(
                input=text,
                model=model
            )
            return response.data[0].embedding
        except Exception as e:
            logger.error(f"Embedding creation failed: {e}", exc_info=True)
            raise

    async def create_embeddings_batch(
        self,
        texts: List[str],
        model: str = "text-embedding-3-small"
    ) -> List[List[float]]:
        """Create embeddings for multiple texts in a single request.

        Args:
            texts: List of texts to embed
            model: Embedding model to use

        Returns:
            List of embedding vectors

        Raises:
            Exception: If API request fails
        """
        try:
            response = await self.client.embeddings.create(
                input=texts,
                model=model
            )
            return [item.embedding for item in response.data]
        except Exception as e:
            logger.error(f"Batch embedding creation failed: {e}", exc_info=True)
            raise

    async def tool_selection_request(
        self,
        messages: List[ChatCompletionMessageParam],
        system_prompt: str,
        model: str = "gpt-4o-mini",
        max_tokens: int = 10000
    ) -> str:
        """Make a chat completion request for tool selection.

        This is a specialized method for the AI agent to select which tool to use
        based on conversation history and available tools.

        Args:
            messages: Conversation history messages
            system_prompt: System prompt describing available tools
            model: OpenAI model to use
            max_tokens: Maximum tokens in completion

        Returns:
            The completion text (expected to be JSON tool selection)

        Raises:
            Exception: If API request fails
        """
        full_messages: List[ChatCompletionMessageParam] = [
            {"role": "system", "content": system_prompt},
            *messages
        ]

        return await self.chat_completion(
            messages=full_messages,
            model=model,
            max_tokens=max_tokens
        )

    async def close(self):
        """Close the OpenAI client connection."""
        await self._client.close()

    async def embed_tool(self, tool: dict) -> None:
        """Embed a single tool into the vector store.

        Args:
            tool: Tool dictionary with 'name', 'description', and 'parameters' keys
        """
        tool_text: str = f"""
        Tool Name: {tool['name']}
        Tool Description: {tool['description']}
        Tool Parameters: {json.dumps(tool['inputSchema'])}
        """
        embedding: List[float] = await self.create_embedding(tool_text)
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
        tool_embeddings: List[List[float]] = await self.create_embeddings_batch(tool_texts)

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
        query_embedding: List[float] = await self.create_embedding(query)
        results = self._collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results,
        )
        return results['metadatas'][0] if results['metadatas'] else []