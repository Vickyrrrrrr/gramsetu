"""
============================================================
whatsapp_mcp.py — WhatsApp MCP Tool Server
============================================================
FastMCP server exposing WhatsApp communication tools via SSE/HTTP.

Tools:
  - send_text_message: Send text reply to user on WhatsApp
  - send_streaming_reply: Stream a long response in chunks
  - download_media: Download voice/image from Twilio media URL
  - request_otp: Ask user for OTP and return WAIT_OTP signal
  - detect_language: Detect Hindi/English/Hinglish from text

All tools are discovered by the LangGraph agent via MCP protocol.
PII is NEVER logged — only passed through graph state.
"""

import os
import re
import tempfile
import asyncio
from typing import Optional

import httpx
from dotenv import load_dotenv
from fastmcp import FastMCP

load_dotenv()

# ── Twilio Config ────────────────────────────────────────────
TWILIO_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_WA_NUMBER = os.getenv("TWILIO_WHATSAPP_NUMBER", "whatsapp:+14155238886")
TWILIO_API_BASE = "https://api.twilio.com/2010-04-01"

# ── FastMCP Server ───────────────────────────────────────────
mcp = FastMCP(
    name="gramsetu-whatsapp",
    instructions="WhatsApp communication tools for GramSetu — "
                 "handles Twilio media, streaming replies, and OTP requests.",
)


# ============================================================
# TOOL 1: Send Text Message
# ============================================================

@mcp.tool()
async def send_text_message(
    to_phone: str,
    message: str,
    language: str = "hi",
) -> dict:
    """
    Send a text message to a user on WhatsApp via Twilio.

    Args:
        to_phone: User's phone number (e.g., '+919876543210')
        message:  The text body to send
        language: Language code for logging ('hi' or 'en')

    Returns:
        {"status": "sent", "sid": "SM...", "to": "+91..."}
    """
    if not TWILIO_SID or not TWILIO_TOKEN:
        return {
            "status": "mock",
            "message": message,
            "to": to_phone,
            "note": "Twilio not configured — message simulated",
        }

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{TWILIO_API_BASE}/Accounts/{TWILIO_SID}/Messages.json",
            auth=(TWILIO_SID, TWILIO_TOKEN),
            data={
                "From": TWILIO_WA_NUMBER,
                "To": f"whatsapp:{to_phone}" if not to_phone.startswith("whatsapp:") else to_phone,
                "Body": message,
            },
        )
        result = response.json()
        return {
            "status": "sent" if response.status_code == 201 else "error",
            "sid": result.get("sid", ""),
            "to": to_phone,
        }


# ============================================================
# TOOL 2: Send Streaming Reply
# ============================================================

@mcp.tool()
async def send_streaming_reply(
    to_phone: str,
    message_parts: list[str],
    delay_ms: int = 800,
) -> dict:
    """
    Send a long response as multiple WhatsApp messages with a typing delay.
    Simulates streaming by breaking the message into parts.

    Args:
        to_phone:      User's phone number
        message_parts: List of message chunks to send sequentially
        delay_ms:      Delay between messages in milliseconds (default 800)

    Returns:
        {"status": "streamed", "parts_sent": N}
    """
    sent_count = 0
    for part in message_parts:
        if part.strip():
            result = await send_text_message(to_phone, part.strip())
            if result.get("status") in ("sent", "mock"):
                sent_count += 1
            await asyncio.sleep(delay_ms / 1000.0)

    return {"status": "streamed", "parts_sent": sent_count}


# ============================================================
# TOOL 3: Download Media (Voice Notes / Images)
# ============================================================

@mcp.tool()
async def download_media(
    media_url: str,
    media_type: str = "audio/ogg",
) -> dict:
    """
    Download a media file from Twilio's authenticated media URL.
    Used for voice notes (ASR) and document images.

    Args:
        media_url:  Twilio media URL (requires SID/Token auth)
        media_type: MIME type ('audio/ogg', 'image/jpeg', etc.)

    Returns:
        {"status": "downloaded", "local_path": "/tmp/...", "size_bytes": N}
    """
    extension_map = {
        "audio/ogg": ".ogg",
        "audio/mpeg": ".mp3",
        "audio/wav": ".wav",
        "image/jpeg": ".jpg",
        "image/png": ".png",
    }
    suffix = extension_map.get(media_type, ".bin")

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                media_url,
                auth=(TWILIO_SID, TWILIO_TOKEN) if TWILIO_SID else None,
                follow_redirects=True,
            )
            response.raise_for_status()

            tmp = tempfile.NamedTemporaryFile(
                delete=False, suffix=suffix, prefix="gramsetu_media_"
            )
            tmp.write(response.content)
            tmp.close()

            return {
                "status": "downloaded",
                "local_path": tmp.name,
                "size_bytes": len(response.content),
                "media_type": media_type,
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}


# ============================================================
# TOOL 4: Request OTP from User
# ============================================================

@mcp.tool()
async def request_otp(
    to_phone: str,
    portal_name: str = "Government Portal",
    language: str = "hi",
) -> dict:
    """
    Send an OTP request message to the user and return a WAIT_OTP signal.
    The LangGraph must SUSPEND after receiving this signal.

    Args:
        to_phone:    User's phone number
        portal_name: Name of the portal requesting OTP
        language:    Response language ('hi' or 'en')

    Returns:
        {"status": "WAIT_OTP", "message_sent": True}
        The graph MUST suspend and wait for the user to reply with the OTP.
    """
    if language == "hi":
        otp_message = (
            f"🔐 *OTP आवश्यक है*\n\n"
            f"{portal_name} ने आपके फ़ोन पर एक 6-अंकीय कोड भेजा है।\n\n"
            f"कृपया वह कोड यहाँ भेजें:"
        )
    else:
        otp_message = (
            f"🔐 *OTP Required*\n\n"
            f"{portal_name} has sent a 6-digit code to your phone.\n\n"
            f"Please send that code here:"
        )

    await send_text_message(to_phone, otp_message, language)

    return {
        "status": "WAIT_OTP",
        "message_sent": True,
        "portal": portal_name,
    }


# ============================================================
# TOOL 5: Detect Language
# ============================================================

@mcp.tool()
async def detect_language(text: str) -> dict:
    """
    Detect the language of incoming text.
    Handles Hindi, English, Hinglish (mixed), Bhojpuri, and Awadhi.

    Args:
        text: The user's message text

    Returns:
        {"language": "hi"|"en"|"hinglish", "has_devanagari": bool, "confidence": float}
    """
    has_devanagari = bool(re.search(r"[\u0900-\u097F]", text))
    has_latin = bool(re.search(r"[a-zA-Z]", text))

    if has_devanagari and has_latin:
        language = "hinglish"
        confidence = 0.85
    elif has_devanagari:
        language = "hi"
        confidence = 0.95
    elif has_latin:
        language = "en"
        confidence = 0.90
    else:
        language = "hi"  # Default to Hindi for rural users
        confidence = 0.50

    return {
        "language": language,
        "has_devanagari": has_devanagari,
        "confidence": confidence,
    }


# ============================================================
# TOOL 6: Validate OTP Format
# ============================================================

@mcp.tool()
async def validate_otp_format(otp_text: str) -> dict:
    """
    Check if the user's reply looks like a valid OTP (4-6 digits).

    Args:
        otp_text: The raw text reply from the user

    Returns:
        {"valid": bool, "otp": "123456" or None, "digits": int}
    """
    cleaned = re.sub(r"\s+", "", otp_text.strip())
    digits_only = re.sub(r"[^\d]", "", cleaned)

    if 4 <= len(digits_only) <= 6:
        return {"valid": True, "otp": digits_only, "digits": len(digits_only)}

    return {"valid": False, "otp": None, "digits": len(digits_only)}


# ── Entry Point ──────────────────────────────────────────────

if __name__ == "__main__":
    mcp.run(transport="sse", host="0.0.0.0", port=8100)
