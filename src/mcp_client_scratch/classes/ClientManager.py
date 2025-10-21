from typing import Dict, List, Optional, Union
import json
import os
import re
import logging
from redis import Redis
from typing import cast
from .MCPClient import BaseMCPClient, STDIOMCPClient, HTTPMCPClient

logger = logging.getLogger("uvicorn.error")


class ClientManager:
    """Manages MCP server configurations and their client connections.

    Handles both static servers (from config file) and dynamic servers (from Redis).
    Creates and manages client instances for each server, tracking their status.
    """

    DYNAMIC_SERVERS_KEY = "servers"

    def __init__(self, config_data: dict, redis_client: Redis):
        """Initialize ClientManager with configuration data and Redis persistence.

        Args:
            config_data: Dictionary containing server configurations
                Expected format:
                {
                    "mcpServers": {
                        "server_name": {
                            "command": "npx",
                            "args": ["-y", "@package/name"],
                            "env": {"KEY": "value"},  # optional
                            "wkdir": "/path/to/dir"   # optional
                        }
                        OR
                        "server_name": {
                            "url": "http://localhost:3000"
                        }
                    }
                }
            redis_client: Redis client for persistence
        """
        self.redis_client = redis_client

        # Load static servers from config file (exist only in memory)
        self._static_servers = config_data.get("mcpServers", {})

        # Load dynamic servers from Redis and append to in-memory dict
        self._dynamic_servers = self._load_dynamic_servers()

        # Combined set for easy operations
        self._servers = {**self._static_servers, **self._dynamic_servers}

        # Client instances: name -> BaseMCPClient | Exception
        self._clients: Dict[str, Union[BaseMCPClient, Exception]] = {}

    def _load_dynamic_servers(self) -> Dict[str, dict]:
        """Load dynamically added servers from Redis.

        Returns:
            Dictionary of dynamic servers
        """
        data = self.redis_client.get(self.DYNAMIC_SERVERS_KEY)
        if data:
            return json.loads(cast(str, data))
        return {}

    def _save_dynamic_servers(self, dynamic_servers: Dict[str, dict]) -> None:
        """Save dynamic servers to Redis.

        Args:
            dynamic_servers: Dictionary of dynamic servers to persist
        """
        self.redis_client.set(self.DYNAMIC_SERVERS_KEY, json.dumps(dynamic_servers))

    def _resolve_env_vars(self, config: dict) -> dict:
        """Resolve environment variable placeholders in server config.

        Supports ${ENV_VAR} and ${input:name} syntax.
        ${input:name} is treated as ${NAME} (uppercase).

        Args:
            config: Server configuration dict

        Returns:
            Config with resolved environment variables
        """
        resolved_config = config.copy()

        def resolve_string(value: str) -> str:
            """Resolve env vars in a string."""
            # Replace ${input:name} with ${NAME}
            value = re.sub(r'\$\{input:(\w+)\}', lambda m: f"${{{m.group(1).upper()}}}", value)
            # Replace ${ENV_VAR} with actual env var value
            value = re.sub(r'\$\{(\w+)\}', lambda m: os.getenv(m.group(1), ''), value)
            return value

        # Resolve env vars in the args list
        if "args" in resolved_config and isinstance(resolved_config["args"], list):
            resolved_config["args"] = [
                resolve_string(arg) if isinstance(arg, str) else arg
                for arg in resolved_config["args"]
            ]

        # Resolve env vars in the env dict
        if "env" in resolved_config and isinstance(resolved_config["env"], dict):
            resolved_env = {}
            for key, value in resolved_config["env"].items():
                if isinstance(value, str):
                    value = resolve_string(value)
                resolved_env[key] = value
            resolved_config["env"] = resolved_env
            
        if "headers" in resolved_config and isinstance(resolved_config["headers"], dict):
            resolved_headers = {}
            for key, value in resolved_config["headers"].items():
                if isinstance(value, str):
                    value = resolve_string(value)
                resolved_headers[key] = value
            resolved_config["headers"] = resolved_headers

        return resolved_config

    def _create_client(self, name: str, config: dict) -> BaseMCPClient:
        """Create a client instance based on server configuration.

        Args:
            name: Server name
            config: Resolved server configuration

        Returns:
            STDIOMCPClient or HTTPMCPClient instance

        Raises:
            ValueError: If config is invalid or missing required fields
        """
        # Determine client type based on config
        if "command" in config:
            # STDIO client
            if "args" not in config:
                raise ValueError(f"STDIO server '{name}' must have 'args' field")

            return STDIOMCPClient(
                name=name,
                command=config["command"],
                args=config["args"],
                wkdir=config.get("wkdir", "./"),
                env=config.get("env", {})
            )
        elif "url" in config:
            # HTTP client
            return HTTPMCPClient(name=name, url=config["url"], headers=config.get("headers", {}))
        else:
            raise ValueError(f"Server '{name}' must have either 'command' or 'url' field")

    async def initialize_clients(self) -> None:
        """Initialize all client connections eagerly.

        Creates client instances for all configured servers and attempts to connect.
        Stores successful clients and error objects for failed connections.
        """
        for name, config in self._servers.items():
            logger.info(f"Initializing client: {name}")
            try:
                # Resolve env vars and create client
                resolved_config = self._resolve_env_vars(config)
                client = self._create_client(name, resolved_config)

                # Initialize connection
                await client.initialize_connection()

                # Get tools
                await client.get_tools()

                # Store successful client
                self._clients[name] = client
                logger.info(f"✓ Client {name} initialized successfully")

            except Exception as e:
                # Store error for this client
                self._clients[name] = e
                logger.error(f"✗ Failed to initialize client {name}: {e}")

    def get_client(self, name: str) -> Optional[BaseMCPClient]:
        """Get an initialized client by name.

        Args:
            name: Server name

        Returns:
            Client instance if successfully initialized, None if failed or not found
        """
        client = self._clients.get(name)
        if isinstance(client, BaseMCPClient):
            return client
        return None

    def get_running_clients(self) -> Dict[str, BaseMCPClient]:
        """Get all successfully initialized and running clients.

        Returns:
            Dictionary mapping server names to client instances
        """
        return {
            name: client
            for name, client in self._clients.items()
            if isinstance(client, BaseMCPClient)
        }

    def get_failed_clients(self) -> Dict[str, Exception]:
        """Get all clients that failed to initialize.

        Returns:
            Dictionary mapping server names to their initialization errors
        """
        return {
            name: client
            for name, client in self._clients.items()
            if isinstance(client, Exception)
        }
        
    def get_clients(self) -> Dict[str, Union[BaseMCPClient, Exception]]:
        """Get all clients (running and failed).

        Returns:
            Dictionary mapping server names to client instances or errors
        """
        return self._clients.copy()

    def get_client_status(self) -> Dict[str, dict]:
        """Get status of all clients (running and failed).

        Returns:
            Dictionary with client statuses:
            {
                "server_name": {
                    "status": "running" | "failed",
                    "error": "error message" (only if failed)
                }
            }
        """
        status = {}
        for name, client in self._clients.items():
            if isinstance(client, BaseMCPClient):
                status[name] = {"status": "running"}
            else:
                status[name] = {
                    "status": "failed",
                    "error": str(client)
                }
        return status

    async def cleanup_clients(self) -> None:
        """Shutdown all active client connections.

        Terminates STDIO processes and closes HTTP connections.
        """
        for name, client in self._clients.items():
            if isinstance(client, BaseMCPClient):
                try:
                    if isinstance(client, STDIOMCPClient):
                        await client.kill_process()
                        logger.info(f"✓ Client {name} terminated")
                    if isinstance(client, HTTPMCPClient):
                        await client.close_connection()
                        logger.info(f"✓ Client {name} HTTP connection closed")
                except Exception as e:
                    logger.error(f"✗ Failed to cleanup client {name}: {e}")

        self._clients.clear()

    def get_server(self, name: str) -> Optional[dict]:
        """Get configuration for a specific server with resolved env vars.

        Args:
            name: Server name

        Returns:
            Server configuration dict or None if not found
        """
        config = self._servers.get(name)
        if config:
            return self._resolve_env_vars(config)
        return None

    def get_all_servers(self) -> Dict[str, dict]:
        """Get all server configurations (static + dynamic) with resolved env vars.

        Returns:
            Dictionary of all server configurations
        """
        resolved_servers = {}
        for name, config in self._servers.items():
            resolved_servers[name] = self._resolve_env_vars(config)
        return resolved_servers

    def get_static_servers(self) -> Dict[str, dict]:
        """Get all static server configurations from config file with resolved env vars.

        Returns:
            Dictionary of static server configurations
        """
        resolved_static = {}
        for name, config in self._static_servers.items():
            resolved_static[name] = self._resolve_env_vars(config)
        return resolved_static

    def get_dynamic_servers(self) -> Dict[str, dict]:
        """Get all dynamically added server configurations from Redis with resolved env vars.

        Returns:
            Dictionary of dynamic server configurations
        """
        resolved_dynamic = {}
        for name, config in self._dynamic_servers.items():
            resolved_dynamic[name] = self._resolve_env_vars(config)
        return resolved_dynamic

    async def add_server(self, name: str, config: dict) -> Union[BaseMCPClient, Exception]:
        """Add a dynamic server configuration and initialize its client.

        Args:
            name: Server name
            config: Server configuration dict with keys:
                - command: str (for STDIO) OR url: str (for HTTP)
                - args: List[str] (required for STDIO)
                - env: Dict[str, str] (optional for STDIO)
                - wkdir: str (optional for STDIO)

        Returns:
            Initialized client instance or Exception if failed

        Raises:
            ValueError: If config is invalid
        """
        # Validate config has either command or url
        if "command" not in config and "url" not in config:
            raise ValueError("Server config must have either 'command' or 'url' field")

        if "command" in config and "args" not in config:
            raise ValueError("STDIO server config must have 'args' field")

        # Load current dynamic servers from Redis
        dynamic_servers = self._load_dynamic_servers()

        # Add new server to dynamic servers
        dynamic_servers[name] = config

        # Save updated dynamic servers back to Redis
        self._save_dynamic_servers(dynamic_servers)

        # Update in-memory servers dicts
        self._dynamic_servers[name] = config
        self._servers[name] = config

        # Initialize client
        try:
            resolved_config = self._resolve_env_vars(config)
            client = self._create_client(name, resolved_config)
            await client.initialize_connection()
            await client.get_tools()

            self._clients[name] = client
            logger.info(f"✓ Dynamically added client {name} initialized successfully")
            return client

        except Exception as e:
            self._clients[name] = e
            logger.error(f"✗ Failed to initialize dynamically added client {name}: {e}")
            return e

    async def remove_server(self, name: str) -> bool:
        """Remove a dynamically added server configuration and cleanup its client.

        Only removes servers from the dynamic servers dict in Redis.

        Args:
            name: Server name to remove

        Returns:
            True if server was removed, False if not found in dynamic servers

        Raises:
            ValueError: If trying to remove a static (config file) server
        """
        # Load current dynamic servers
        dynamic_servers = self._load_dynamic_servers()

        # Check if server exists in dynamic servers
        if name not in dynamic_servers:
            raise ValueError(f"Cannot remove server '{name}' - it's either from config file or doesn't exist in dynamic servers")

        # Cleanup client if it exists
        if name in self._clients:
            client = self._clients[name]
            if isinstance(client, STDIOMCPClient):
                try:
                    await client.kill_process()
                except Exception as e:
                    logger.error(f"Error cleaning up client {name}: {e}")
            del self._clients[name]

        # Remove from dynamic servers
        del dynamic_servers[name]

        # Save updated dynamic servers back to Redis
        self._save_dynamic_servers(dynamic_servers)

        # Remove from in-memory dicts
        if name in self._dynamic_servers:
            del self._dynamic_servers[name]
        if name in self._servers:
            del self._servers[name]
            return True
        return False

    def list_server_names(self) -> List[str]:
        """Get list of all configured server names (static + dynamic).

        Returns:
            List of server names
        """
        return list(self._servers.keys())
