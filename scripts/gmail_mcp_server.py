"""Self-hosted Gmail MCP server -- unifies the Gmail integration so both
Claude (via Claude Code's MCP config) and the open-weights orchestrator
(via mcp_client.py) drive the exact same implementation, instead of the
two separate paths (Anthropic's hosted connector vs. gmail_client.py
called in-process) that existed before this.

Wraps gmail_client.py's functions as MCP tools. Deliberately exposes no
send/reply tool -- gmail_client.py has no such function to wrap, so this
server cannot be made to send mail no matter what a client asks for.

Usage (stdio transport, the standard for local MCP servers):
    python scripts/gmail_mcp_server.py

Claude Code config (project .mcp.json):
    {"mcpServers": {"raise-gmail": {"command": "python",
        "args": ["scripts/gmail_mcp_server.py"], "cwd": "<repo root>"}}}
"""

import pathlib
import sys

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import gmail_client  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

mcp = FastMCP(
    "raise-gmail",
    instructions=(
        "Gmail access for RAISE, scoped to reading, labeling, and drafting only. "
        "There is no send or reply tool -- it does not exist on this server, "
        "not merely disallowed by instruction. A person must send from Gmail directly."
    ),
)


@mcp.tool()
def list_labels() -> list[dict]:
    """List all Gmail labels with their ids."""
    return gmail_client.list_labels()


@mcp.tool()
def get_or_create_label_id(name: str) -> str:
    """Get the id of a label by display name, creating it if it does not exist yet."""
    return gmail_client.get_or_create_label_id(name)


@mcp.tool()
def search_threads(query: str, max_results: int = 20) -> list[dict]:
    """Search Gmail threads. query uses standard Gmail search syntax (e.g. 'label:X -label:Y')."""
    return gmail_client.search_threads(query, max_results)


@mcp.tool()
def get_thread(thread_id: str) -> dict:
    """Fetch a thread's messages (sender, date, plaintext body). Draft messages are excluded."""
    return gmail_client.get_thread(thread_id)


@mcp.tool()
def create_draft(to: str, subject: str, body: str, reply_to_message_id: str | None = None, thread_id: str | None = None, attachment_path: str | None = None) -> dict:
    """Create a Gmail draft. Never sends. reply_to_message_id/thread_id thread it as a reply. attachment_path attaches one local file (e.g. the public deck)."""
    return gmail_client.create_draft(to, subject, body, reply_to_message_id, thread_id, attachment_path)


@mcp.tool()
def label_thread(thread_id: str, label_ids: list[str]) -> dict:
    """Add label(s) to a thread by label id (use list_labels/get_or_create_label_id first)."""
    return gmail_client.label_thread(thread_id, label_ids)


if __name__ == "__main__":
    mcp.run(transport="stdio")
