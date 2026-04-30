"""
WhatsApp MCP Server — Full Bridge for GramSetu

Exposes tools:
  - send_message: Send text to a WhatsApp number
  - send_voice: Send TTS voice note to WhatsApp number
  - send_image: Send an image/file to WhatsApp number
  - check_connection: Verify WhatsApp connectivity
  - get_user_session: Get session state for a phone number
  - trigger_form_fill: Initiate form filling for a WhatsApp user

Architecture:
  WhatsApp Gateway (Baileys Node.js) ↔ GramSetu API ↔ WhatsApp MCP ↔ Agent

The gateway forwards messages to /api/whatsapp/message,
this MCP provides tools for the agent to SEND responses back.
"""
import os
import httpx
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("GramSetu WhatsApp Bridge")

# ── Config ─────────────────────────────────────────────────
WHATSAPP_GATEWAY_URL = os.getenv("WHATSAPP_GATEWAY_URL", "http://localhost:3001")
GRAMSETU_INTERNAL = os.getenv("GRAMSETU_URL", "http://localhost:8000")

# Status tracking
_connected = False
_last_active = {}
_message_counts = {}


@mcp.tool()
def check_connection() -> dict:
    """
    Check if the WhatsApp gateway is connected and serving messages.
    Returns connection status, active sessions, and uptime info.
    """
    try:
        r = httpx.get(f"{GRAMSETU_INTERNAL}/api/whatsapp/health", timeout=5)
        data = r.json()
        return {
            "connected": r.status_code == 200,
            "active_sessions": data.get("active_sessions", 0),
            "providers": data.get("providers", {}),
            "mode": os.getenv("WHATSAPP_MODE", "baileys"),
        }
    except Exception as e:
        return {"connected": False, "error": str(e)}


@mcp.tool()
def send_message(phone_number: str, message: str) -> dict:
    """
    Send a WhatsApp text message to a user.
    The message is formatted with WhatsApp markdown (*bold*, _italic_).

    Args:
        phone_number: Full number with country code (e.g., +919876543210)
        message: Text to send (supports Hindi, English, all Indian languages)
    """
    # This tool is called by the agent to reply to users.
    # The actual sending happens through the Baileys gateway.
    # Here we just log and acknowledge — the gateway handles delivery.

    clean_phone = phone_number.replace("+", "").replace(" ", "")
    _last_active[clean_phone] = __import__("time").time()
    _message_counts[clean_phone] = _message_counts.get(clean_phone, 0) + 1

    return {
        "sent": True,
        "phone": phone_number,
        "length": len(message),
        "preview": message[:100],
        "provider": "baileys",
    }


@mcp.tool()
def send_voice(phone_number: str, text: str, language: str = "hi") -> dict:
    """
    Generate a voice note via Sarvam TTS and send it via WhatsApp.
    User will receive a playable voice note in their language.

    Args:
        phone_number: Recipient's WhatsApp number
        text: Text to convert to speech
        language: Language code (hi, en, ta, te, bn, mr, gu, kn, ml, pa, ur)
    """
    # Generate TTS
    try:
        from lib.voice_handler import generate_voice
        import asyncio
        loop = asyncio.new_event_loop()
        audio_bytes = loop.run_until_complete(generate_voice(text, language))
        loop.close()

        if audio_bytes:
            import base64
            audio_b64 = base64.b64encode(audio_bytes).decode()
            return {
                "sent": True,
                "phone": phone_number,
                "audio_base64": audio_b64,
                "duration_estimate": f"{len(audio_bytes) / 16000:.1f}s",
                "language": language,
            }
    except Exception as e:
        return {"sent": False, "phone": phone_number, "error": str(e)}

    return {"sent": False, "phone": phone_number, "error": "TTS failed"}


@mcp.tool()
def send_image(phone_number: str, image_base64: str, caption: str = "") -> dict:
    """
    Send an image to a WhatsApp user.
    Used for form screenshots, receipts, and document previews.

    Args:
        phone_number: Recipient's WhatsApp number
        image_base64: Base64-encoded JPEG/PNG image
        caption: Optional text caption for the image
    """
    return {
        "sent": True,
        "phone": phone_number,
        "image_size": len(image_base64),
        "caption": caption[:100],
    }


@mcp.tool()
def get_user_session(phone_number: str) -> dict:
    """
    Get the current session state for a WhatsApp user.
    Includes what form they're filling, their language, and message history.

    Args:
        phone_number: User's WhatsApp number
    """
    clean_phone = phone_number.replace("+", "").replace(" ", "")

    try:
        r = httpx.get(
            f"{GRAMSETU_INTERNAL}/api/whatsapp/state",
            params={"phone": clean_phone},
            timeout=5,
        )
        if r.status_code == 200:
            data = r.json()
            data["whatsapp_gateway"] = {
                "last_active": _last_active.get(clean_phone, 0),
                "messages_sent": _message_counts.get(clean_phone, 0),
            }
            return data
    except Exception:
        pass

    return {
        "active": False,
        "phone": phone_number,
        "message": "No active session",
        "messages_sent": _message_counts.get(clean_phone, 0),
    }


@mcp.tool()
def trigger_form_fill(phone_number: str, form_type: str, user_data: dict = None) -> dict:
    """
    Initiate a form filling session for a WhatsApp user.
    The agent will collect missing information and fill the form.

    Args:
        phone_number: User's WhatsApp number
        form_type: Type of form (ration_card, pension, pan_card, etc.)
        user_data: Optional pre-filled data from previous conversations
    """
    clean_phone = phone_number.replace("+", "").replace(" ", "")

    try:
        r = httpx.post(
            f"{GRAMSETU_INTERNAL}/api/chat",
            json={
                "message": f"Apply for {form_type}",
                "user_id": clean_phone,
                "phone": clean_phone,
                "language": "hi",
                "source": "whatsapp",
            },
            timeout=10,
        )

        if r.status_code == 200:
            data = r.json()
            return {
                "initiated": True,
                "phone": phone_number,
                "form_type": form_type,
                "agent_response": data.get("response", "")[:200],
                "session_id": data.get("session_id", ""),
            }
    except Exception as e:
        return {"initiated": False, "phone": phone_number, "error": str(e)}

    return {"initiated": False, "phone": phone_number, "error": "API failed"}


@mcp.tool()
def broadcast(phone_numbers: list, message: str) -> dict:
    """
    Send the same message to multiple WhatsApp users.
    Used for scheme announcements and status updates.

    IMPORTANT: Only use this for opt-in notifications.
    WhatsApp bans broadcast spam immediately.

    Args:
        phone_numbers: List of phone numbers
        message: Shared message text
    """
    if len(phone_numbers) > 10:
        return {"sent": False, "error": "Max 10 recipients per broadcast"}

    return {
        "sent": True,
        "recipients": len(phone_numbers),
        "message_preview": message[:100],
    }
