"""
Common utilities for GDB tools.

Provides decorators and helper functions used across all tool modules.
"""

from collections.abc import Callable
from functools import wraps
from typing import Any

from session import (
    SessionNotFoundError,
    SessionNotActiveError,
    SessionNotInitializedError,
)
from mi import CommandTimeoutError, CommandError
from parsing import format_tool_response


TIMEOUT_WARNING = (
    "Session may be stuck after timeout. "
    "If commands hang, use gdb_stop to end this session and gdb_start for a fresh one."
)


def tool_handler(func: Callable) -> Callable:
    """
    Decorator that standardizes error handling for tools.
    
    Catches common exceptions and returns properly formatted error responses.
    On timeout, adds a warning about potential session issues.
    """
    @wraps(func)
    async def wrapper(*args, **kwargs) -> dict[str, Any]:
        try:
            return await func(*args, **kwargs)
        except SessionNotFoundError as e:
            return format_tool_response(
                status="failed",
                error=str(e)
            )
        except SessionNotActiveError as e:
            return format_tool_response(
                status="failed",
                error=str(e)
            )
        except SessionNotInitializedError as e:
            return format_tool_response(
                status="failed",
                error=str(e)
            )
        except CommandTimeoutError as e:
            return format_tool_response(
                status="failed",
                error=f"Command timed out: {e}",
                warning=TIMEOUT_WARNING
            )
        except CommandError as e:
            return format_tool_response(
                status="failed",
                error=str(e)
            )
        except FileNotFoundError as e:
            return format_tool_response(
                status="failed",
                error=str(e)
            )
        except ValueError as e:
            return format_tool_response(
                status="failed",
                error=str(e)
            )
        except Exception as e:
            return format_tool_response(
                status="failed",
                error=f"Unexpected error: {type(e).__name__}: {e}"
            )
    return wrapper
