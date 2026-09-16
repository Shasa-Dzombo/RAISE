"""Async MCP client wrapper for gmail_mcp_server.py.

Gives llm_orchestrator.py the same method names gmail_client.py had, but
routed through the MCP protocol to the self-hosted server, so the
orchestrator and Claude Code can both drive the exact same Gmail
implementation instead of two separate integrations.
"""

import json
import pathlib
from contextlib import AsyncExitStack

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SERVER_SCRIPT = str(pathlib.Path(__file__).resolve().parent / "gmail_mcp_server.py")


def _unwrap(result):
    if result.isError:
        text = result.content[0].text if result.content else "MCP tool call failed"
        raise RuntimeError(text)
    if result.structuredContent is not None:
        sc = result.structuredContent
        return sc["result"] if set(sc.keys()) == {"result"} else sc
    if result.content:
        return json.loads(result.content[0].text)
    return None


class MCPGmailClient:
    """Async context manager: `async with MCPGmailClient() as gmail: ...`

    Uses a single AsyncExitStack (rather than manually pairing two separate
    __aenter__/__aexit__ calls) so the stdio transport and the client
    session -- both of which spawn their own anyio task groups internally --
    unwind in the same task that opened them, avoiding cross-task
    cancel-scope errors on exit.
    """

    def __init__(self):
        self._stack = AsyncExitStack()

    async def __aenter__(self):
        params = StdioServerParameters(command="python", args=[SERVER_SCRIPT])
        read, write = await self._stack.enter_async_context(stdio_client(params))
        self.session = await self._stack.enter_async_context(ClientSession(read, write))
        await self.session.initialize()
        return self

    async def __aexit__(self, *exc):
        await self._stack.aclose()

    async def _call(self, tool_name, **kwargs):
        result = await self.session.call_tool(tool_name, kwargs)
        return _unwrap(result)

    async def get_or_create_label_id(self, name):
        return await self._call("get_or_create_label_id", name=name)

    async def search_threads(self, query, max_results=20):
        return await self._call("search_threads", query=query, max_results=max_results)

    async def get_thread(self, thread_id):
        return await self._call("get_thread", thread_id=thread_id)

    async def create_draft(self, to, subject, body, reply_to_message_id=None, thread_id=None):
        return await self._call(
            "create_draft", to=to, subject=subject, body=body,
            reply_to_message_id=reply_to_message_id, thread_id=thread_id,
        )

    async def label_thread(self, thread_id, label_ids):
        return await self._call("label_thread", thread_id=thread_id, label_ids=label_ids)
