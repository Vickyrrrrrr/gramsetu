"""
============================================================
mcp_tool_router.py — Claude Opus-Style MCP Tool Router
============================================================

Architecture inspired by how Claude 4.7 uses MCP:
  1. ALL MCP servers register their tools with full JSON schemas
  2. The LLM receives the tool catalog in its system prompt
  3. The LLM autonomously decides WHICH tool to call and WHEN
  4. Results feed back into the LLM context for multi-step chains
  5. Each tool call is validated before execution

Pattern:
  User: "Fill my ration card form"
  → LLM sees: [browser.fill_form, digilocker.fetch_user_data, audit.validate_field...]
  → LLM decides: call digilocker.fetch_user_data first
  → Get data → LLM decides: call audit.validate_field on each field
  → Get validation → LLM decides: call browser.fill_form
  → Done
"""

import asyncio
import inspect
import json
from typing import Callable, Optional
from dataclasses import dataclass, field


@dataclass
class MCPTool:
    """A single tool registered from an MCP server."""
    name: str
    description: str
    server: str
    func: Optional[Callable] = None     # direct function (register_direct)
    is_fastmcp: bool = False            # True if using FastMCP's call_tool
    input_schema: dict = field(default_factory=dict)
    is_async: bool = True

    def to_prompt(self) -> str:
        params = ", ".join(
            f"{k}: {v.get('type', 'string')}" 
            for k, v in self.input_schema.get("properties", {}).items()
        )
        return f"  {self.server}.{self.name}({params}) — {self.description}"

    def to_llm_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": f"{self.server}__{self.name}",
                "description": self.description,
                "parameters": self.input_schema
            }
        }


class MCPToolRouter:
    """
    Central registry + executor for all MCP tools.
    The LangGraph agent uses this to present tool options to the LLM
    and execute the selected tool.
    """

    def __init__(self):
        self._tools: dict[str, MCPTool] = {}
        self._servers: dict[str, object] = {}           # FastMCP server instances
        self._direct_funcs: dict[str, Callable] = {}    # For register_direct

    def register_server(self, name: str, server: object):
        """Register a FastMCP server — reads @mcp.tool() decorated functions."""
        self._servers[name] = server
        tools = []

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # We're inside an async context — create a new loop on another thread
                import concurrent.futures
                def _sync_list():
                    inner_loop = asyncio.new_event_loop()
                    try:
                        return inner_loop.run_until_complete(server.list_tools())
                    finally:
                        inner_loop.close()

                with concurrent.futures.ThreadPoolExecutor() as executor:
                    tools = executor.submit(_sync_list).result(timeout=10)
            else:
                tools = loop.run_until_complete(server.list_tools())
        except RuntimeError:
            # No event loop exists yet
            tools = asyncio.run(server.list_tools())
        except Exception as e:
            print(f"[MCP Router] list_tools failed for {name}: {e}")
            tools = []

        if isinstance(tools, list):
            for tool in tools:
                tool_name = getattr(tool, "name", "")
                tool_desc = getattr(tool, "description", "")
                tool_schema = getattr(tool, "inputSchema", {}) or {}
                key = f"{name}__{tool_name}"
                self._tools[key] = MCPTool(
                    name=tool_name, description=tool_desc, server=name,
                    is_fastmcp=True, input_schema=tool_schema,
                )
            print(f"[MCP Router] {name}: {len(tools)} tools from @mcp.tool() decorators")

    def _register_tool(self, server_name: str, tool_info: dict):
        """Register a single tool from structured info."""
        name = tool_info.get("name", "unknown")
        desc = tool_info.get("description", "")
        schema = tool_info.get("inputSchema", {})
        key = f"{server_name}__{name}"
        self._tools[key] = MCPTool(
            name=name,
            description=desc,
            server=server_name,
            func=getattr(self._servers.get(server_name), "call_tool", None),
            input_schema=schema,
        )

    def register_direct(self, server: str, name: str, description: str,
                        func: Callable, input_schema: dict = None):
        """Register a tool directly by function (kept for compatibility)."""
        if input_schema is None:
            input_schema = self._infer_schema(func)
        key = f"{server}__{name}"
        self._direct_funcs[key] = func
        self._tools[key] = MCPTool(
            name=name, description=description,
            server=server, func=func,
            input_schema=input_schema,
            is_async=inspect.iscoroutinefunction(func),
        )

    def _infer_schema(self, func: Callable) -> dict:
        """Basic schema inference from function signature."""
        sig = inspect.signature(func)
        properties = {}
        required = []
        for pname, param in sig.parameters.items():
            if pname in ("self", "cls"):
                continue
            ptype = "string"
            annotation = param.annotation
            if annotation != inspect.Parameter.empty:
                if annotation is int:
                    ptype = "integer"
                elif annotation is float:
                    ptype = "number"
                elif annotation is bool:
                    ptype = "boolean"
                elif annotation is dict:
                    ptype = "object"
            properties[pname] = {"type": ptype, "description": f"Parameter: {pname}"}
            if param.default is inspect.Parameter.empty:
                required.append(pname)
        return {"type": "object", "properties": properties, "required": required}

    def get_tool_catalog(self) -> list[dict]:
        """Get all tools as LLM-compatible function schemas."""
        return [t.to_llm_schema() for t in self._tools.values()]

    def get_tool_prompt(self) -> str:
        """Get all tools as a human-readable prompt string."""
        lines = ["## Available Tools\n"]
        by_server = {}
        for t in self._tools.values():
            by_server.setdefault(t.server, []).append(t)

        for server, tools in sorted(by_server.items()):
            lines.append(f"\n### {server.upper()} MCP")
            for t in tools:
                lines.append(t.to_prompt())
        return "\n".join(lines)

    def get_tool(self, server: str, name: str) -> Optional[MCPTool]:
        return self._tools.get(f"{server}__{name}")

    async def execute(self, server: str, name: str, **kwargs) -> dict:
        """Execute a tool — uses FastMCP call_tool for @mcp.tool() functions."""
        tool = self.get_tool(server, name)
        if not tool:
            return {"error": f"Tool not found: {server}.{name}"}

        try:
            if tool.is_fastmcp and server in self._servers:
                result = await self._servers[server].call_tool(name, kwargs)
                # FastMCP returns (list/tuple of TextContent, optional structured content dict)
                blocks = []
                structured = None

                def _scan(item):
                    nonlocal structured
                    if isinstance(item, (list, tuple)):
                        for sub in item:
                            _scan(sub)
                    elif isinstance(item, dict):
                        # Try to determine if this is a tool result dict
                        if structured is None or 'found' in item or 'valid' in item or 'sent' in item or 'configured' in item:
                            structured = item
                        # It might be a {'result': '...'} wrapper
                        elif 'result' in item and len(item) == 1:
                            structured = item
                    elif hasattr(item, 'text'):
                        blocks.append(item)

                _scan(result)

                # Return structured content if available (better than parsing text blocks)
                if structured:
                    if 'result' in structured and len(structured) == 1:
                        inner = structured['result']
                        return inner if isinstance(inner, dict) else {"result": inner}
                    return structured

                # Parse text content blocks as last resort
                for block in blocks:
                    text = getattr(block, 'text', None)
                    if text and isinstance(text, str):
                        try:
                            parsed = json.loads(text)
                            return parsed if isinstance(parsed, dict) else {"result": parsed}
                        except (json.JSONDecodeError, TypeError):
                            return {"result": text}

                return {"result": str(result)}
            elif tool.func:
                # Direct function call (legacy register_direct path)
                result = tool.func(**kwargs)
                if inspect.isawaitable(result):
                    result = await result
                return result if isinstance(result, dict) else {"result": result}
            else:
                return {"error": f"No execution path for {server}.{name}"}
        except Exception as e:
            return {"error": str(e), "tool": f"{server}.{name}"}


# ── Global singleton ─────────────────────────────────────────
_router: Optional[MCPToolRouter] = None


def get_router() -> MCPToolRouter:
    global _router
    if _router is None:
        _router = MCPToolRouter()
        _initialize_tools(_router)
    return _router


def _initialize_tools(router: MCPToolRouter):
    """Register all MCP tools via @mcp.tool() decorators (FastMCP)."""

    # ── Browser MCP (9 tools from @mcp.tool decorators) ─────
    from backend.mcp_servers.browser_mcp import mcp as browser_mcp
    router.register_server("browser", browser_mcp)

    # ── Audit MCP (5 tools from @mcp.tool decorators) ────────
    from backend.mcp_servers.audit_mcp import mcp as audit_mcp
    router.register_server("audit", audit_mcp)

    # ── DigiLocker MCP (5 tools from @mcp.tool decorators) ───
    from backend.mcp_servers.digilocker_mcp import mcp as digilocker_mcp
    router.register_server("digilocker", digilocker_mcp)

    # ── WhatsApp MCP (5 tools from @mcp.tool decorators) ─────
    from backend.mcp_servers.whatsapp_mcp import mcp as whatsapp_mcp
    router.register_server("whatsapp", whatsapp_mcp)

    # Legacy tools removed.
