"""
PULSE DevOps Agent — Platform Utilities

WHY this file exists:
  The original RIFT project used Linux-style shell commands like:
      cmd = f"cd {repo_path} && pylint --output-format=json ."
  This BREAKS on Windows because:
    1. Windows PowerShell uses semicolons, not &&
    2. Path separators are backslashes
    3. /dev/null doesn't exist on Windows

  This module provides cross-platform wrappers for all subprocess operations.
  Never call subprocess.run() directly — always use run_command() from here.

Usage:
    from utils.platform_utils import run_command, get_python_executable

    result = await run_command(["pylint", "--output-format=json", "."], cwd=repo_path)
    print(result.stdout)
"""

import asyncio
import os
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from utils.logger import get_logger

logger = get_logger(__name__)

# Detect OS once
IS_WINDOWS = platform.system() == "Windows"
IS_LINUX = platform.system() == "Linux"
IS_MAC = platform.system() == "Darwin"


@dataclass
class CommandResult:
    """Result of a subprocess command"""
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool = False

    @property
    def success(self) -> bool:
        return self.returncode == 0


async def run_command(
    args: List[str],
    cwd: Optional[str] = None,
    timeout: int = 60,
    env: Optional[dict] = None,
) -> CommandResult:
    """
    Run a subprocess command cross-platform (Windows + Linux + Mac).

    Args:
        args:    Command as list, e.g. ["pylint", "--output-format=json", "."]
        cwd:     Working directory for the command
        timeout: Timeout in seconds (default 60)
        env:     Additional environment variables

    Returns:
        CommandResult with stdout, stderr, returncode

    Example:
        result = await run_command(["pylint", "."], cwd="/tmp/myrepo")
        if result.success:
            print(result.stdout)
    """
    # Merge environment
    process_env = os.environ.copy()
    if env:
        process_env.update(env)

    logger.debug("Running command", args=args, cwd=cwd)

    try:
        process = await asyncio.create_subprocess_exec(
            *args,
            cwd=cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=process_env,
        )

        stdout, stderr = await asyncio.wait_for(
            process.communicate(),
            timeout=timeout
        )

        return CommandResult(
            returncode=process.returncode,
            stdout=stdout.decode("utf-8", errors="replace"),
            stderr=stderr.decode("utf-8", errors="replace"),
        )

    except asyncio.TimeoutError:
        logger.warning("Command timed out", args=args, timeout=timeout)
        try:
            process.kill()
        except Exception:
            pass
        return CommandResult(returncode=-1, stdout="", stderr="Timed out", timed_out=True)

    except FileNotFoundError:
        # Tool not installed
        tool_name = args[0] if args else "unknown"
        logger.warning("Tool not found", tool=tool_name)
        return CommandResult(
            returncode=-1,
            stdout="",
            stderr=f"Tool not found: {tool_name}. Install it with: pip install {tool_name}"
        )

    except Exception as e:
        logger.error("Command failed", error=str(e), args=args)
        return CommandResult(returncode=-1, stdout="", stderr=str(e))


def get_python_executable() -> str:
    """
    Get the Python executable path.
    Important: In a venv, this points to the venv Python, not system Python.
    """
    return sys.executable


def is_tool_available(tool_name: str) -> bool:
    """
    Check if a CLI tool is installed and on PATH.

    Args:
        tool_name: e.g. "pylint", "flake8", "git"

    Returns:
        True if tool is available

    Example:
        if is_tool_available("pylint"):
            # run pylint
    """
    # System PATH check
    if shutil.which(tool_name) is not None:
        return True
        
    # Virtual Environment robust check
    try:
        from pathlib import Path
        import sys
        venv_bin = Path(sys.executable).parent
        win_exe = venv_bin / f"{tool_name}.exe"
        unix_exe = venv_bin / tool_name
        if win_exe.exists() or unix_exe.exists():
            return True
    except Exception:
        pass
        
    return False


def normalize_path(path: str) -> str:
    """
    Normalize a file path for the current OS.
    Converts forward/back slashes to the OS default.
    """
    return str(Path(path))


def get_relative_path(file_path: str, base_path: str) -> str:
    """
    Get relative path from base, cross-platform.

    Example:
        get_relative_path("/tmp/repo/src/main.py", "/tmp/repo")
        # Returns: "src/main.py" (always forward slashes)
    """
    try:
        rel = os.path.relpath(file_path, base_path)
        # Always use forward slashes in output (consistent across OS)
        return rel.replace("\\", "/")
    except ValueError:
        # On Windows, different drives cause ValueError
        return file_path


def get_available_tools() -> dict:
    """
    Check which analysis tools are available on this system.
    Called at startup to report tool availability.

    Returns:
        Dict of tool_name → bool
    """
    tools = ["pylint", "flake8", "mypy", "bandit", "git"]
    return {tool: is_tool_available(tool) for tool in tools}
