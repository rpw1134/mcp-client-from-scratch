from typing import Dict, List, Optional
import json
from redis import Redis
from typing import cast


class ServerConfig:
    """Server configuration manager for MCP servers.

    SERVERS = STATIC_SERVERS (from config file) + DYNAMIC_SERVERS (from Redis)
    Dynamic servers are persisted to Redis under the "servers" key.
    """

    DYNAMIC_SERVERS_KEY = "servers"

    def __init__(self, config_data: dict, redis_client: Redis):
        """Initialize ServerConfig with configuration data and Redis persistence.

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
                    }
                }
            redis_client: Redis client for persistence
        """
        self.redis_client = redis_client
        self._servers: Dict[str, dict] = {}

        # Load static servers from config file (exist only in memory)
        file_servers = config_data.get("mcpServers", {})
        for name, cfg in file_servers.items():
            if "command" in cfg and "args" in cfg:
                self._servers[name] = cfg

        # Load dynamic servers from Redis and append to in-memory dict
        dynamic_servers = self._load_dynamic_servers()
        self._servers.update(dynamic_servers)
        print(f"Loaded {len(self._servers)} servers ({len(file_servers)} static, {len(dynamic_servers)} dynamic)")
        print("Servers:", list(self._servers.keys()))

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

    def get_server(self, name: str) -> Optional[dict]:
        """Get configuration for a specific server.

        Args:
            name: Server name

        Returns:
            Server configuration dict or None if not found
        """
        return self._servers.get(name)

    def get_all_servers(self) -> Dict[str, dict]:
        """Get all server configurations (static + dynamic).

        Returns:
            Dictionary of all server configurations
        """
        return self._servers.copy()

    def add_server(self, name: str, config: dict) -> None:
        """Add a dynamic server configuration.

        Appends the server to both Redis and in-memory SERVERS dict.

        Args:
            name: Server name
            config: Server configuration dict with keys:
                - command: str (required)
                - args: List[str] (required)
                - env: Dict[str, str] (optional)
                - wkdir: str (optional)

        Raises:
            ValueError: If config is missing required fields
        """
        if "command" not in config or "args" not in config:
            raise ValueError("Server config must have 'command' and 'args' fields")

        # Load current dynamic servers from Redis
        dynamic_servers = self._load_dynamic_servers()

        # Add new server to dynamic servers
        dynamic_servers[name] = config

        # Save updated dynamic servers back to Redis
        self._save_dynamic_servers(dynamic_servers)

        # Update in-memory servers dict
        self._servers[name] = config

    def remove_server(self, name: str) -> bool:
        """Remove a dynamically added server configuration.

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

        # Remove from dynamic servers
        del dynamic_servers[name]

        # Save updated dynamic servers back to Redis
        self._save_dynamic_servers(dynamic_servers)

        # Remove from in-memory dict
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
