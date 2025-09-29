import asyncio
from typing import Optional

class Process():
    
    def __init__(self, command, wkdir=""):
        self.command = command
        self.wkdir = wkdir
        self.process = None
        self.pid = -1
        
    async def start(self):
        # starts the process
        self.process = await asyncio.create_subprocess_exec(
            *self.command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=self.wkdir
        )
        if not self.process:
            raise RuntimeError("Failed to start process")
        self.pid = self.process.pid
    
    async def read_stdout(self, timeout: Optional[float] = 0.2)->str:
        # throws timeout error to be handled by caller
        if self.process and self.process.stdout:
            if timeout is not None:
                line = await asyncio.wait_for(self.process.stdout.readline(), timeout=timeout)
            else:
                line = await self.process.stdout.readline()
            return line.decode().strip()
        return ""
    
    async def read_stderr(self, timeout: Optional[float] = 0.2)->str:
        # throws timeout error to be handled by caller
        if self.process and self.process.stderr:
            if timeout is not None:
                line = await asyncio.wait_for(self.process.stderr.readline(), timeout=timeout)
            else:
                line = await self.process.stderr.readline()
            return line.decode().strip()
        return ""

    async def write_stdin(self, input_str: str):
        # throws runtime error to be handled by caller
        if self.process and self.process.stdin:
            self.process.stdin.write(input_str.encode() + b'\n')
            await self.process.stdin.drain()
            if self.process.stdin.is_closing():
                raise RuntimeError("stdin is closed")
    
    async def read_startup_notifications(self):
        # reads all startup messages from stdout and stderr
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
            
    async def read_stdout_nowait(self)->str:
        # non-blocking read for continuous readers
        if self.process and self.process.stdout:
            line = await self.process.stdout.readline()
            return line.decode().strip() if line else ""
        return ""

    async def read_stderr_nowait(self)->str:
        # non-blocking read for continuous readers
        if self.process and self.process.stderr:
            line = await self.process.stderr.readline()
            return line.decode().strip() if line else ""
        return ""

    def is_running(self) -> bool:
        # check if process is running
        return self.process is not None and self.process.returncode is None

    async def terminate(self):
        # if process is available, terminate it
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
    
        
    
            