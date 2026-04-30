"""
meta_webhook.py — Meta WhatsApp Cloud API Webhook

Receives WhatsApp messages via Meta's webhook, processes through
GramSetu agent, and sends responses back via Meta's Messages API.

Setup:
1. Create Meta App at developers.facebook.com → WhatsApp → API Setup
2. Set webhook URL to https://your-domain/api/whatsapp/webhook
3. Verify token = META_VERIFY_TOKEN from .env
4. Webhook fields: messages

Meta sends:
  GET  /api/whatsapp/webhook?hub.mode=subscribe&hub.verify_token=XXX&hub.challenge=ABC
  POST /api/whatsapp/webhook  (message payload)
"""
import os
import json
import base64
import httpx
import asyncio
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import PlainTextResponse, JSONResponse

router = APIRouter(prefix="/api/whatsapp", tags=["whatsapp-meta"])

# ── Config ─────────────────────────────────────────────────
META_ACCESS_TOKEN = os.getenv("META_ACCESS_TOKEN", "")
META_VERIFY_TOKEN = os.getenv("META_VERIFY_TOKEN", "gramsetu_verify_2026")
META_PHONE_NUMBER_ID = os.getenv("META_PHONE_NUMBER_ID", "")
META_API_VERSION = os.getenv("META_API_VERSION", "v22.0")
META_API_URL = f"https://graph.facebook.com/{META_API_VERSION}/{META_PHONE_NUMBER_ID}"


# ════════════════════════════════════════════════════════════
# WEBHOOK VERIFICATION (GET)
# ════════════════════════════════════════════════════════════

@router.get("/webhook")
async def verify_webhook(request: Request):
    """
    Meta calls this to verify the webhook URL during setup.
    Returns the challenge string if the verify token matches.
    """
    params = request.query_params
    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")

    if mode == "subscribe" and token == META_VERIFY_TOKEN:
        print("[Meta] Webhook verified successfully")
        return PlainTextResponse(challenge)

    raise HTTPException(status_code=403, detail="Verification failed")


# ════════════════════════════════════════════════════════════
# INCOMING MESSAGES (POST)
# ════════════════════════════════════════════════════════════

@router.post("/webhook")
async def receive_message(request: Request):
    """
    Meta sends message payloads here.
    Processes through GramSetu agent and sends response.
    """
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"status": "bad_request"}, status_code=400)

    # Extract messages from Meta's payload format
    entries = body.get("entry", [])
    tasks = []

    for entry in entries:
        changes = entry.get("changes", [])
        for change in changes:
            value = change.get("value", {})
            messages = value.get("messages", [])

            for msg in messages:
                sender_phone = msg.get("from", "")
                msg_type = msg.get("type", "text")
                text = extract_text(msg)
                
                # Handle images: download from Meta, convert to base64
                if msg_type == "image" and msg.get("image", {}).get("id"):
                    image_id = msg["image"]["id"]
                    image_b64 = await download_meta_image(image_id)
                    caption = msg.get("image", {}).get("caption", "") or "[Selfie]"
                    if image_b64:
                        tasks.append(process_and_reply(sender_phone, caption, "image", image_b64))
                    else:
                        tasks.append(process_and_reply(sender_phone, caption or "📸 Photo received"))
                elif text and sender_phone:
                    tasks.append(process_and_reply(sender_phone, text))

    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)

    return JSONResponse({"status": "ok"})


# ════════════════════════════════════════════════════════════
# PROXY ENDPOINT: Send message manually (used by webapp admin)
# ════════════════════════════════════════════════════════════

@router.post("/send")
async def send_whatsapp_message(request: Request):
    """Send a WhatsApp message via Meta API."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    phone = body.get("phone", "")
    message = body.get("message", "")
    if not phone or not message:
        raise HTTPException(status_code=400, detail="phone and message required")

    result = await send_meta_message(phone, message)
    if result.get("sent"):
        return JSONResponse({"status": "sent", "message_id": result.get("message_id", "")})
    else:
        raise HTTPException(status_code=500, detail=result.get("error", "Failed to send"))


# ════════════════════════════════════════════════════════════
# CORE: Process message through GramSetu agent
# ════════════════════════════════════════════════════════════

_session_store: dict[str, dict] = {}  # phone → session_id


async def process_and_reply(phone: str, text: str, msg_type: str = "text", image_b64: str = ""):
    """Process a WhatsApp message through GramSetu and reply via Meta."""
    try:
        from backend.agents.graph import process_message as agent_process
        from lib.language_utils import detect_language

        lang = detect_language(text) or "hi" if text else "hi"

        # Get or create session
        session = _session_store.get(phone, {})
        session_id = session.get("session_id", "")

        # Run through agent
        result = await agent_process(
            user_id=phone,
            user_phone=phone,
            message=image_b64 if msg_type == "image" and image_b64 else text,
            message_type=msg_type,
            language=lang,
            session_id=session_id,
        )

        # Save session
        _session_store[phone] = {
            "session_id": result.get("session_id", ""),
            "language": lang,
        }

        # Send response
        response_text = result.get("response", "")
        if response_text:
            await send_meta_message(phone, response_text[:4000])

        # If screenshot available, send as image
        screenshot = result.get("screenshot_b64", "")
        if screenshot:
            await send_meta_image(phone, screenshot, "Form Screenshot")

    except Exception as e:
        print(f"[Meta] Agent processing failed for {phone}: {e}")
        await send_meta_message(phone, "❌ Processing error. Please try again.")


# ════════════════════════════════════════════════════════════
# META API: Send message
# ════════════════════════════════════════════════════════════

async def send_meta_message(to: str, text: str) -> dict:
    """Send a WhatsApp text message via Meta Graph API."""
    if not META_ACCESS_TOKEN or not META_PHONE_NUMBER_ID:
        print("[Meta] API not configured — skipping send")
        return {"sent": False, "error": "META_ACCESS_TOKEN not configured"}

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                f"{META_API_URL}/messages",
                headers={
                    "Authorization": f"Bearer {META_ACCESS_TOKEN}",
                    "Content-Type": "application/json",
                },
                json={
                    "messaging_product": "whatsapp",
                    "to": to,
                    "type": "text",
                    "text": {"body": text[:4096]},
                },
            )
        if response.status_code == 200:
            data = response.json()
            msg_id = data.get("messages", [{}])[0].get("id", "")
            return {"sent": True, "message_id": msg_id}
        else:
            print(f"[Meta] Send failed: {response.status_code} {response.text[:200]}")
            return {"sent": False, "error": f"HTTP {response.status_code}"}
    except Exception as e:
        print(f"[Meta] Send error: {e}")
        return {"sent": False, "error": str(e)}


async def send_meta_image(to: str, image_b64: str, caption: str = "") -> dict:
    """Send a WhatsApp image via Meta Graph API."""
    if not META_ACCESS_TOKEN or not META_PHONE_NUMBER_ID:
        return {"sent": False}

    import base64
    try:
        # Upload media first
        async with httpx.AsyncClient(timeout=15.0) as client:
            # Upload to Meta
            upload_resp = await client.post(
                f"{META_API_URL}/media",
                headers={"Authorization": f"Bearer {META_ACCESS_TOKEN}"},
                files={
                    "file": ("screenshot.jpg", base64.b64decode(image_b64), "image/jpeg"),
                    "messaging_product": (None, "whatsapp"),
                },
            )
        if upload_resp.status_code != 200:
            return {"sent": False, "error": "Upload failed"}

        media_id = upload_resp.json().get("id", "")

        # Send as image
        resp = await httpx.AsyncClient(timeout=15.0).post(
            f"{META_API_URL}/messages",
            headers={
                "Authorization": f"Bearer {META_ACCESS_TOKEN}",
                "Content-Type": "application/json",
            },
            json={
                "messaging_product": "whatsapp",
                "to": to,
                "type": "image",
                "image": {"id": media_id, "caption": caption[:1000] if caption else ""},
            },
        )
        if resp.status_code == 200:
            return {"sent": True, "message_id": resp.json().get("messages", [{}])[0].get("id", "")}
        return {"sent": False, "error": f"HTTP {resp.status_code}"}
    except Exception as e:
        return {"sent": False, "error": str(e)}


# ════════════════════════════════════════════════════════════
# HELPERS
# ════════════════════════════════════════════════════════════

def extract_text(msg: dict) -> str:
    """Extract text from Meta's message format."""
    msg_type = msg.get("type", "")

    if msg_type == "text":
        return msg.get("text", {}).get("body", "")

    if msg_type == "audio":
        return "[Voice note — send text for now]"

    if msg_type == "image":
        return msg.get("image", {}).get("caption", "") or "[Photo]"

    if msg_type == "interactive":
        interactive = msg.get("interactive", {})
        if "button_reply" in interactive:
            return interactive["button_reply"].get("id", "")
        if "list_reply" in interactive:
            return interactive["list_reply"].get("id", "")

    return ""


async def download_meta_image(image_id: str) -> str:
    """Download an image from Meta's media API and return as base64."""
    if not META_ACCESS_TOKEN:
        return ""
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            # Step 1: Get image URL from Meta
            url_resp = await client.get(
                f"https://graph.facebook.com/{META_API_VERSION}/{image_id}",
                headers={"Authorization": f"Bearer {META_ACCESS_TOKEN}"},
            )
            if url_resp.status_code != 200:
                return ""
            image_url = url_resp.json().get("url", "")
            if not image_url:
                return ""

            # Step 2: Download image bytes
            dl_resp = await client.get(
                image_url,
                headers={"Authorization": f"Bearer {META_ACCESS_TOKEN}"},
            )
            if dl_resp.status_code != 200:
                return ""

            # Step 3: Return base64
            return base64.b64encode(dl_resp.content).decode()
    except Exception as e:
        print(f"[Meta] Image download failed: {e}")
        return ""
