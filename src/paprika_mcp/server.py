"""MCP server for Paprika recipe manager."""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any, cast

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Prompt, TextContent, Tool

from .prompts import PROMPTS
from .tools import TOOLS
from .utils import PaprikaAPIError, reset_remote

logger = logging.getLogger(__name__)

# Create server instance
app = Server("paprika")


@app.list_prompts()
async def list_prompts():
    """List available prompts."""
    return [Prompt(**prompt["definition"]) for prompt in PROMPTS.values()]


@app.get_prompt()
async def get_prompt(name: str, arguments: dict[str, Any] | None = None):
    """Get prompt content."""
    if name in PROMPTS:
        handler = cast(
            Callable[[dict[str, Any]], Awaitable[Any]], PROMPTS[name]["handler"]
        )
        return await handler(arguments or {})
    raise ValueError(f"Unknown prompt: {name}")


@app.list_tools()
async def list_tools():
    """List available tools."""
    return [Tool(**tool["definition"]) for tool in TOOLS.values()]


@app.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]):
    """Handle tool calls.

    Failures are logged in full server-side but summarized for the client, so
    raw API/login response bodies never reach the transcript.
    """
    if name not in TOOLS:
        raise ValueError(f"Unknown tool: {name}")

    handler = cast(
        Callable[[dict[str, Any]], Awaitable[list[TextContent]]],
        TOOLS[name]["handler"],
    )
    try:
        return await handler(arguments)
    except ValueError as e:
        # Configuration / bad-input errors: the message is written for the user.
        logger.error(f"Error in {name}: {e}", exc_info=True)
        return [TextContent(type="text", text=f"Error: {e}")]
    except PaprikaAPIError as e:
        logger.error(f"Paprika API error in {name}: {e}", exc_info=True)
        return [
            TextContent(
                type="text",
                text=(
                    f"Error: the Paprika API call for '{name}' failed. This is a "
                    "connectivity or service problem, not an empty result — do not "
                    "treat it as 'no data'. Try again shortly."
                ),
            )
        ]
    except Exception as e:
        logger.error(f"Unexpected error in {name}: {e}", exc_info=True)
        # An auth failure may mean a stale cached token; force re-login next call.
        if "401" in str(e) or "auth" in str(e).lower():
            reset_remote()
            return [
                TextContent(
                    type="text",
                    text=(
                        f"Error: authentication with Paprika failed while running "
                        f"'{name}'. Credentials will be refreshed on the next call; "
                        "if this repeats, check PAPRIKA_EMAIL / PAPRIKA_PASSWORD."
                    ),
                )
            ]
        return [
            TextContent(
                type="text",
                text=(
                    f"Error: '{name}' failed unexpectedly "
                    f"({type(e).__name__}). Details are in the server log."
                ),
            )
        ]


async def main():
    """Run the MCP server using stdio transport."""
    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options(),
        )


def run():
    """Entry point for the server."""
    asyncio.run(main())


if __name__ == "__main__":
    run()
