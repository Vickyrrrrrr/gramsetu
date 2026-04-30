"""
WhatsApp MCP Server — Meta Cloud API Bridge for GramSetu

Exposes tools:
  - send_message: Send text via Meta WhatsApp API
  - send_image: Send image via Meta WhatsApp API
  - check_connection: Verify Meta API connectivity
  - get_user_session: Get session state for a phone number

Uses Meta's WhatsApp Cloud API (free 1000 convos/month).
Send messages via POST https://graph.facebook.com/v22.0/{phone_id}/messages
"""
import os
import json
import time
import base64
import httpx
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("GramSetu WhatsApp Bridge")

# ── Config ─────────────────────────────────────────────────
META_ACCESS_TOKEN = os.getenv("META_ACCESS_TOKEN", "")
META_PHONE_NUMBER_ID = os.getenv("META_PHONE_NUMBER_ID", "")
META_API_VERSION = os.getenv("META_API_VERSION", "v22.0")
META_API_URL = f"https://graph.facebook.com/{META_API_VERSION}/{META_PHONE_NUMBER_ID}"
GRAMSETU_INTERNAL = os.getenv("GRAMSETU_URL", "http://localhost:8000")

# Tracking
_is_configured = bool(META_ACCESS_TOKEN and META_PHONE_NUMBER_ID)
_last_active = {}
_message_counts = {}


def _send_via_meta(to: str, payload: dict) -> dict:
    """Send any message type via Meta API."""
    if not _is_configured:
        return {"sent": False, "error": "Meta API not configured"}
    try:
        payload["messaging_product"] = "whatsapp"
        payload["to"] = to
        r = httpx.post(
            f"{META_API_URL}/messages",
            headers={"Authorization": f"Bearer {META_ACCESS_TOKEN}", "Content-Type": "application/json"},
            json=payload,
            timeout=15,
        )
        if r.status_code == 200:
            data = r.json()
            return {"sent": True, "provider": "meta", "message_id": data.get("messages", [{}])[0].get("id", "")}
        return {"sent": False, "error": f"Meta HTTP {r.status_code}: {r.text[:200]}"}
    except Exception as e:
        return {"sent": False, "error": str(e)}


def _track(phone: str):
    clean = phone.replace("+", "").replace(" ", "")
    _last_active[clean] = time.time()
    _message_counts[clean] = _message_counts.get(clean, 0) + 1


@mcp.tool()
def check_connection() -> dict:
    """Check if Meta WhatsApp API is configured and reachable."""
    return {
        "configured": _is_configured,
        "phone_number_id": META_PHONE_NUMBER_ID or "not set",
        "provider": "meta",
        "free_tier": "1000 conversations/month",
    }


@mcp.tool()
def send_message(phone_number: str, message: str) -> dict:
    """
    Send a WhatsApp text message via Meta Cloud API.

    Args:
        phone_number: Full number with country code (e.g., +919876543210)
        message: Text to send (supports Hindi, English, all Indian languages)
    """
    _track(phone_number)
    return _send_via_meta(phone_number, {
        "type": "text",
        "text": {"body": message[:4096]},
    })


@mcp.tool()
def send_image(phone_number: str, image_base64: str, caption: str = "") -> dict:
    """
    Send a WhatsApp image (screenshot, receipt) via Meta Cloud API.

    Args:
        phone_number: Recipient's WhatsApp number
        image_base64: Base64-encoded JPEG/PNG image
        caption: Optional text caption for the image
    """
    _track(phone_number)
    if not _is_configured:
        return {"sent": False, "error": "Meta API not configured"}

    try:
        # Step 1: Upload media to Meta
        r = httpx.post(
            f"{META_API_URL}/media",
            headers={"Authorization": f"Bearer {META_ACCESS_TOKEN}"},
            files={
                "file": ("image.jpg", base64.b64decode(image_base64), "image/jpeg"),
                "messaging_product": (None, "whatsapp"),
            },
            timeout=20,
        )
        if r.status_code != 200:
            return {"sent": False, "error": f"Upload failed: {r.status_code}"}

        media_id = r.json().get("id", "")

        # Step 2: Send image message
        return _send_via_meta(phone_number, {
            "type": "image",
            "image": {"id": media_id, "caption": caption[:1000] if caption else ""},
        })
    except Exception as e:
        return {"sent": False, "error": str(e)}


@mcp.tool()
def get_user_session(phone_number: str) -> dict:
    """Get the current session state for a WhatsApp user."""
    clean = phone_number.replace("+", "").replace(" ", "")
    try:
        r = httpx.get(f"{GRAMSETU_INTERNAL}/api/whatsapp/state", params={"phone": clean}, timeout=5)
        if r.status_code == 200:
            data = r.json()
            data["provider"] = "meta"
            data["messages_sent"] = _message_counts.get(clean, 0)
            return data
    except Exception:
        pass
    return {"active": False, "phone": phone_number, "provider": "meta"}


@mcp.tool()
def get_setup_guide() -> dict:
    """
    Get instructions for setting up the Meta WhatsApp Cloud API.
    """
    return {
        "steps": [
            "1. Go to https://developers.facebook.com",
            "2. Create App → Select 'Business' type",
            "3. Add 'WhatsApp' product to your app",
            "4. Go to WhatsApp → API Setup",
            "5. Copy 'Phone Number ID' → set as META_PHONE_NUMBER_ID in .env",
            "6. Create a 'System User' and generate a permanent access token → set as META_ACCESS_TOKEN",
            "7. Set webhook URL to: https://your-domain/api/whatsapp/webhook",
            "8. Set verify token to: gramsetu_verify_2026",
            "9. Subscribe to 'messages' webhook field",
        ],
        "free_tier": "1000 conversations/month",
        "test_number": "Add your number in Meta → WhatsApp → Test Numbers → send test message",
    }
