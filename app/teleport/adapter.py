from __future__ import annotations
import subprocess
from app.teleport.commands import validate as _validate_command


class TeleportError(Exception):
    pass


def _sanitize_error(stderr: str) -> str:
    import re
    clean = re.sub(r"\x1b\[[0-9;]*m", "", stderr)
    s = clean.lower()
    if "reverse tunnel" in s or "no tunnel connection" in s:
        return "Teleport agent disconnected"
    if "node not found" in s or "no such host" in s:
        return "Node not found in cluster"
    if "connection refused" in s or "dial tcp" in s:
        return "Connection refused"
    if "permission denied" in s:
        return "Permission denied"
    first_line = clean.strip().splitlines()[0] if clean.strip() else "Unknown error"
    return first_line[:80]


class SessionExpiredError(TeleportError):
    pass


class TeleportAdapter:
    def __init__(self, connection_timeout: int = 10, command_timeout: int = 30):
        self._conn_timeout = connection_timeout
        self._cmd_timeout = command_timeout

    def status(self) -> dict:
        result = self._run(["tsh", "status"], timeout=10, raise_on_error=False)
        active = result.returncode == 0
        return {"active": active, "output": result.stdout, "error": result.stderr}

    def ssh(self, host: str, login: str, command: str, timeout: int | None = None) -> str:
        _validate_command(command)
        effective_timeout = timeout or self._cmd_timeout
        target = f"{login}@{host}"
        args = ["tsh", "ssh", target, command]
        result = self._run(args, timeout=effective_timeout, raise_on_error=False)

        if result.returncode != 0:
            stderr = result.stderr.lower()
            if any(kw in stderr for kw in ("expired", "not logged in", "no credentials")):
                raise SessionExpiredError(result.stderr.strip())
            raise TeleportError(_sanitize_error(result.stderr))

        return result.stdout

    def list_nodes(self) -> list[str]:
        result = self._run(["tsh", "ls", "--format=text"], timeout=15, raise_on_error=False)
        if result.returncode != 0:
            return []
        lines = result.stdout.strip().splitlines()
        return [line.split()[0] for line in lines if line and not line.startswith("Node")]

    @staticmethod
    def _run(args: list[str], timeout: int, raise_on_error: bool = True) -> subprocess.CompletedProcess:
        try:
            return subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            if raise_on_error:
                raise TeleportError(f"Command timed out after {timeout}s")
            proc = subprocess.CompletedProcess(args, returncode=124)
            proc.stdout = ""
            proc.stderr = f"Timeout after {timeout}s"
            return proc
        except FileNotFoundError:
            if raise_on_error:
                raise TeleportError("tsh not found in PATH")
            proc = subprocess.CompletedProcess(args, returncode=127)
            proc.stdout = ""
            proc.stderr = "tsh not found in PATH"
            return proc
