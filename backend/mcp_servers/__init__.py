"""
GramSetu MCP Servers - Model Context Protocol tool servers.

Each server exposes tools that the LangGraph agent can call
to perform browser automation, document fetching, audit logging,
and messaging.
"""

from backend.mcp_servers.browser_mcp import mcp as browser_mcp
from backend.mcp_servers.audit_mcp import mcp as audit_mcp
from backend.mcp_servers.digilocker_mcp import mcp as digilocker_mcp
from backend.mcp_servers.whatsapp_mcp import mcp as whatsapp_mcp

__all__ = ["browser_mcp", "audit_mcp", "digilocker_mcp", "whatsapp_mcp"]
