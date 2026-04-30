"""
voice_realtime.py - Realtime Speech-to-Text using Sarvam WebSocket API.
Provides streaming transcription for live voice input.
"""

import os
import json
import asyncio
import websockets
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter(tags=["voice-realtime"])

SARVAM_API_KEY = os.getenv("SARVAM_API_KEY", "")
SARVAM_WS_URL = "wss://api.sarvam.ai/speech-to-text-realtime"

@router.websocket("/api/voice/realtime")
async def websocket_realtime_stt(websocket: WebSocket):
    """
    WebSocket endpoint for realtime speech-to-text.
    Protocol:
    - Client sends: {"type": "start", "language": "hi"} (language is optional, defaults to hi)
    - Client sends: Binary audio chunks (PCM16, 16kHz, mono)
    - Server sends: {"type": "transcript", "text": "...", "is_final": false/true}
    - Client sends: {"type": "stop"} to end session
    """
    await websocket.accept()
    
    if not SARVAM_API_KEY or SARVAM_API_KEY == "your_sarvam_key_here":
        await websocket.send_json({
            "type": "error",
            "message": "Sarvam API key not configured"
        })
        await websocket.close()
        return
    
    sarvam_ws = None
    try:
        # Connect to Sarvam WebSocket
        headers = {
            "api-subscription-key": SARVAM_API_KEY,
            "X-Sarvam-Client": "GramSetu-Webapp"
        }
        
        sarvam_ws = await websockets.connect(SARVAM_WS_URL, additional_headers=headers)
        
        # Handle start message from client
        start_msg = await websocket.receive_json()
        language = start_msg.get("language", "hi")
        
        # Send config to Sarvam
        config = {
            "type": "config",
            "language_code": f"{language}-IN",
            "model": "saaras:v3",
            "audio_format": "pcm",
            "sample_rate": 16000
        }
        await sarvam_ws.send(json.dumps(config))
        
        # Start two concurrent tasks: receive from client, receive from Sarvam
        async def receive_from_client():
            try:
                while True:
                    # Try to receive binary audio data
                    try:
                        data = await asyncio.wait_for(websocket.receive(), timeout=0.1)
                        if data.get("type") == "websocket.receive":
                            if "bytes" in data:
                                audio_chunk = data["bytes"]
                                if audio_chunk and sarvam_ws:
                                    await sarvam_ws.send(audio_chunk)
                            elif "text" in data:
                                msg = json.loads(data["text"])
                                if msg.get("type") == "stop":
                                    break
                    except asyncio.TimeoutError:
                        continue
            except WebSocketDisconnect:
                pass
            finally:
                if sarvam_ws:
                    await sarvam_ws.close()
        
        async def receive_from_sarvam():
            try:
                async for message in sarvam_ws:
                    if isinstance(message, str):
                        data = json.loads(message)
                        # Forward transcript to client
                        await websocket.send_json({
                            "type": "transcript",
                            "text": data.get("transcript", ""),
                            "is_final": data.get("is_final", False)
                        })
                    elif isinstance(message, bytes):
                        # Some APIs send binary
                        await websocket.send_bytes(message)
            except Exception as e:
                print(f"[Realtime STT] Sarvam error: {e}")
            finally:
                await websocket.close()
        
        # Run both tasks concurrently
        await asyncio.gather(
            receive_from_client(),
            receive_from_sarvam(),
            return_exceptions=True
        )
        
    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"[Realtime STT] Error: {e}")
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass
    finally:
        if sarvam_ws and not sarvam_ws.closed:
            await sarvam_ws.close()
        try:
            await websocket.close()
        except Exception:
            pass
