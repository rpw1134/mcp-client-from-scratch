import asyncio
from typing import Optional

class Process():
    """Manages an asyncio subprocess for STDIO-based MCP communication."""

    def __init__(self, command: list[str], wkdir: str = "", env : dict= {}) -> None:
        """Initialize the Process.

        Args:
            command: List of command and arguments to execute
            wkdir: Working directory for the subprocess
        """
        self.command = command
        self.wkdir = wkdir
        self.process: Optional[asyncio.subprocess.Process] = None
        self.pid: int = -1
        self.env = env if env else None
        
        
    async def start(self) -> None:
        """Start the subprocess with STDIO pipes."""
        self.process = await asyncio.create_subprocess_exec(
            *self.command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=self.wkdir
            , env=self.env if self.env else None
        )
        if not self.process:
            raise RuntimeError("Failed to start process")
        self.pid = self.process.pid
    
    async def read_stdout(self, timeout: Optional[float] = 0.2) -> str:
        """Read a line from stdout with optional timeout.

        Args:
            timeout: Timeout in seconds, None for no timeout

        Returns:
            Decoded and stripped line from stdout

        Raises:
            asyncio.TimeoutError: If timeout is exceeded
        """
        if self.process and self.process.stdout:
            if timeout is not None:
                line = await asyncio.wait_for(self.process.stdout.readline(), timeout=timeout)
            else:
                line = await self.process.stdout.readline()
            return line.decode().strip()
        return ""
    
    async def read_stderr(self, timeout: Optional[float] = 0.2) -> str:
        """Read a line from stderr with optional timeout.

        Args:
            timeout: Timeout in seconds, None for no timeout

        Returns:
            Decoded and stripped line from stderr

        Raises:
            asyncio.TimeoutError: If timeout is exceeded
        """
        if self.process and self.process.stderr:
            if timeout is not None:
                line = await asyncio.wait_for(self.process.stderr.readline(), timeout=timeout)
            else:
                line = await self.process.stderr.readline()
            return line.decode().strip()
        return ""

    async def write_stdin(self, input_str: str) -> None:
        """Write a line to stdin.

        Args:
            input_str: String to write to stdin

        Raises:
            RuntimeError: If stdin is closed
        """
        if self.process and self.process.stdin:
            self.process.stdin.write(input_str.encode() + b'\n')
            await self.process.stdin.drain()
            if self.process.stdin.is_closing():
                raise RuntimeError("stdin is closed")
    
    async def read_startup_notifications(self) -> None:
        """Clear initial buffers by reading all startup messages from stdout and stderr."""
        while True:
            try:
                await self.read_stdout(timeout=0.2)
            except asyncio.TimeoutError:
                break
        while True:
            try:
                await self.read_stderr(timeout=0.2)
            except asyncio.TimeoutError:
                break
            
    async def read_stdout_nowait(self) -> str:
        """Non-blocking read from stdout for continuous readers."""
        if self.process and self.process.stdout:
            line = await self.process.stdout.readline()
            return line.decode().strip() if line else ""
        return ""

    async def read_stderr_nowait(self) -> str:
        """Non-blocking read from stderr for continuous readers."""
        if self.process and self.process.stderr:
            line = await self.process.stderr.readline()
            return line.decode().strip() if line else ""
        return ""

    def is_running(self) -> bool:
        """Check if process is running."""
        return self.process is not None and self.process.returncode is None

    async def terminate(self) -> int:
        """Terminate the subprocess.

        Returns:
            The return code of the terminated process

        Raises:
            RuntimeError: If no subprocess exists to terminate
        """
        return_val = -1
        if self.process:
            self.process.terminate()
            return_val = await self.process.wait()
            print(f"Subprocess with PID {self.pid} terminated with return code {return_val}.")
            self.process = None
            self.pid = -1
        else:
            raise RuntimeError("No subprocess to terminate.")
        return return_val
    
        
    
            