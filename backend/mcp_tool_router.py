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

import json
import inspect
from typing import Any, Callable, Optional
from dataclasses import dataclass, field


@dataclass
class MCPTool:
    """A single tool registered from an MCP server."""
    name: str
    description: str
    server: str                 # e.g. "browser", "audit", "digilocker"
    func: Callable              # The async function to call
    input_schema: dict = field(default_factory=dict)
    is_async: bool = True

    def to_llm_schema(self) -> dict:
        """Convert to OpenAI-compatible function schema for the LLM."""
        return {
            "type": "function",
            "function": {
                "name": f"{self.server}__{self.name}",
                "description": self.description,
                "parameters": self.input_schema,
            },
        }

    def to_prompt(self) -> str:
        """Human-readable description for non-function-calling LLMs."""
        params = ", ".join(
            f"{k}: {v.get('type', 'string')}" 
            for k, v in self.input_schema.get("properties", {}).items()
        )
        return f"  {self.server}.{self.name}({params}) — {self.description}"


class MCPToolRouter:
    """
    Central registry + executor for all MCP tools.
    The LangGraph agent uses this to present tool options to the LLM
    and execute the selected tool.
    """

    def __init__(self):
        self._tools: dict[str, MCPTool] = {}
        self._servers: dict[str, object] = {}

    def register_server(self, name: str, server: object):
        """Register an MCP server instance and all its tools."""
        self._servers[name] = server

        if hasattr(server, "list_tools"):
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    import concurrent.futures
                    future = asyncio.run_coroutine_threadsafe(server.list_tools(), loop)
                    tools = future.result(timeout=5)
                else:
                    tools = asyncio.run(server.list_tools())
            except Exception:
                tools = []

            if isinstance(tools, list):
                for tool in tools:
                    self._register_tool(name, tool)

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
        """Register a tool directly by function (bypass list_tools)."""
        if input_schema is None:
            input_schema = self._infer_schema(func)
        key = f"{server}__{name}"
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
        """Execute a tool by server and name."""
        tool = self.get_tool(server, name)
        if not tool:
            return {"error": f"Tool not found: {server}.{name}"}

        try:
            if hasattr(tool.func, "__self__"):
                result = tool.func(**kwargs)
            else:
                result = tool.func(**kwargs)

            if inspect.isawaitable(result):
                result = await result

            if isinstance(result, dict):
                return result
            return {"result": result}
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
    """Register all MCP tools with the router."""

    # ── Browser tools ─────────────────────────────────────────
    from backend.agents.form_fill_agent import run_form_fill_agent
    from backend.agents.portal_registry import get_portal_info

    async def browser_navigate(session_id: str, url: str) -> dict:
        """Navigate the browser to a specific URL."""
        from backend.mcp_servers.browser_mcp import navigate
        return await navigate(session_id, url)

    async def browser_fill_form(session_id: str, form_data: dict, form_type: str) -> dict:
        """Fill an entire form on the current portal page. Use form_type='generic' for unknown forms."""
        from backend.mcp_servers.browser_mcp import fill_form
        return await fill_form(session_id, form_data, form_type)

    async def browser_fill_field(session_id: str, field_label: str, value: str) -> dict:
        """Fill a single form field by its visible label text."""
        from backend.mcp_servers.browser_mcp import fill_field
        return await fill_field(session_id, field_label, value)

    async def browser_take_screenshot(session_id: str) -> dict:
        """Capture the current browser page."""
        from backend.mcp_servers.browser_mcp import take_screenshot
        return await take_screenshot(session_id)

    async def browser_click_button(session_id: str, button_label: str) -> dict:
        """Click a button on the page by its text."""
        from backend.mcp_servers.browser_mcp import click_button
        return await click_button(session_id, button_label)

    async def browser_detect_otp(session_id: str) -> dict:
        """Check if the current page has an OTP verification field."""
        from backend.mcp_servers.browser_mcp import detect_otp
        return await detect_otp(session_id)

    async def browser_navigate_and_fill(session_id: str, portal_url: str,
                                        form_data: dict, form_type: str) -> dict:
        """Navigate to a portal AND fill the form — complete operation."""
        nav = await browser_navigate(session_id, portal_url)
        if nav.get("error"):
            return nav
        return await browser_fill_form(session_id, form_data, form_type)

    router.register_direct("browser", "navigate", "Navigate browser to a URL", browser_navigate)
    router.register_direct("browser", "fill_form", "Fill all form fields on the current page", browser_fill_form)
    router.register_direct("browser", "fill_field", "Fill a single form field by its label", browser_fill_field)
    router.register_direct("browser", "take_screenshot", "Capture screenshot of the current page", browser_take_screenshot)
    router.register_direct("browser", "click_button", "Click a button by its label text", browser_click_button)
    router.register_direct("browser", "detect_otp", "Check if OTP field is on page", browser_detect_otp)
    router.register_direct("browser", "navigate_and_fill", "Navigate to a portal and fill the entire form", browser_navigate_and_fill)

    # ── Audit tools ────────────────────────────────────────────
    from backend.mcp_servers.audit_mcp import validate_field as _audit_validate, _redact_text

    async def audit_validate_field(field_name: str, value: str, form_type: str = "generic") -> dict:
        """Validate a form field value. Checks Aadhaar, PAN, mobile, IFSC, PIN, DOB, email."""
        return _audit_validate(field_name, value, form_type)

    async def audit_redact_pii(text: str) -> str:
        """Strip all PII from text before logging/displaying."""
        return _redact_text(text)

    async def audit_verify_identity(user_id: str, aadhaar: str, face_photo: str = "") -> dict:
        """Verify user identity via Aadhaar checksum + optional face match."""
        from backend.identity_verifier import verify_identity
        return await verify_identity(user_id, aadhaar, face_photo)

    router.register_direct("audit", "validate_field", "Validate a form field (Aadhaar, PAN, mobile, IFSC, etc.)", audit_validate_field)
    router.register_direct("audit", "redact_pii", "Strip PII from text", audit_redact_pii)
    router.register_direct("audit", "verify_identity", "Verify user identity with Aadhaar + face", audit_verify_identity)

    # ── DigiLocker tools ───────────────────────────────────────
    async def digilocker_fetch_data(user_id: str) -> dict:
        """Fetch registered user data from the secure store."""
        from backend.mcp_servers.digilocker_mcp import fetch_user_data
        return fetch_user_data(user_id)

    async def digilocker_extract_fields(form_type: str, user_context: str) -> dict:
        """Use LLM to extract structured form fields from user conversation text."""
        from backend.digilocker_client import extract_with_llm
        return await extract_with_llm(user_context, form_type)

    async def digilocker_register_user(user_id: str, data: dict) -> dict:
        """Register user data in the secure store."""
        from backend.mcp_servers.digilocker_mcp import register_user_data
        return register_user_data(user_id, data)

    router.register_direct("digilocker", "fetch_data", "Get user's stored identity data", digilocker_fetch_data)
    router.register_direct("digilocker", "extract_fields", "Extract structured form fields from free text", digilocker_extract_fields)
    router.register_direct("digilocker", "register_user", "Save user's data for future use", digilocker_register_user)

    # ── WhatsApp tools ─────────────────────────────────────────
    async def whatsapp_send(phone: str, message: str) -> dict:
        """Send a WhatsApp text message."""
        from backend.mcp_servers.whatsapp_mcp import send_message
        return send_message(phone, message)

    async def whatsapp_send_voice(phone: str, text: str, language: str = "hi") -> dict:
        """Send a voice note via WhatsApp using Sarvam TTS."""
        from backend.mcp_servers.whatsapp_mcp import send_voice
        return send_voice(phone, text, language)

    async def whatsapp_get_session(phone: str) -> dict:
        """Get WhatsApp user's current session state."""
        from backend.mcp_servers.whatsapp_mcp import get_user_session
        return get_user_session(phone)

    async def whatsapp_trigger_form(phone: str, form_type: str, user_data: dict = None) -> dict:
        """Initiate form filling for a WhatsApp user."""
        from backend.mcp_servers.whatsapp_mcp import trigger_form_fill
        return trigger_form_fill(phone, form_type, user_data or {})

    async def whatsapp_check_connection() -> dict:
        """Check WhatsApp gateway connectivity."""
        from backend.mcp_servers.whatsapp_mcp import check_connection
        return check_connection()

    async def whatsapp_send_image(phone: str, image_b64: str, caption: str = "") -> dict:
        """Send an image (screenshot/receipt) via WhatsApp."""
        from backend.mcp_servers.whatsapp_mcp import send_image
        return send_image(phone, image_b64, caption)

    router.register_direct("whatsapp", "send_message", "Send WhatsApp text message", whatsapp_send)
    router.register_direct("whatsapp", "send_voice", "Send WhatsApp voice note (TTS)", whatsapp_send_voice)
    router.register_direct("whatsapp", "get_session", "Get WhatsApp user session state", whatsapp_get_session)
    router.register_direct("whatsapp", "trigger_form", "Start form filling for a WhatsApp user", whatsapp_trigger_form)
    router.register_direct("whatsapp", "check_connection", "Check WhatsApp gateway status", whatsapp_check_connection)
    router.register_direct("whatsapp", "send_image", "Send image/document via WhatsApp", whatsapp_send_image)
