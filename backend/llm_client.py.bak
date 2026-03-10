"""
============================================================
llm_client.py — NVIDIA NIM Multi-Model LLM Client
============================================================
Uses NVIDIA NIM APIs exclusively with purpose-specific models:

  INTENT     → meta/llama-3.1-8b-instruct       (fast JSON classification)
  CONVERSATIONAL → nvidia/llama-3.1-nemotron-70b-instruct (warm, multilingual)
  EXTRACTION → meta/llama-3.1-70b-instruct       (precise structured output)
  GENERAL    → meta/llama-3.3-70b-instruct       (best reasoning, default)

Groq is a last-resort fallback ONLY if NIM API key is missing.
"""

import os
import json
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

# ── API Keys ─────────────────────────────────────────────────
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY", "")
GROQ_API_KEY   = os.getenv("GROQ_API_KEY", "")

# ── NIM Base URL ─────────────────────────────────────────────
NVIDIA_URL = os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
GROQ_URL   = "https://api.groq.com/openai/v1"

# ── Purpose-Specific NIM Models ──────────────────────────────
# Fast & accurate JSON output — intent classification
NIM_MODEL_INTENT        = os.getenv("NIM_MODEL_INTENT",        "meta/llama-3.1-8b-instruct")
# Warm, nuanced, multilingual — conversational chat with users
NIM_MODEL_CONVERSATIONAL= os.getenv("NIM_MODEL_CONVERSATIONAL","nvidia/llama-3.1-nemotron-70b-instruct")
# Precise structured extraction — pulling fields from user text / documents
NIM_MODEL_EXTRACTION    = os.getenv("NIM_MODEL_EXTRACTION",    "meta/llama-3.1-70b-instruct")
# Best general reasoning — scheme research, eligibility, summaries
NIM_MODEL_GENERAL       = os.getenv("NIM_MODEL_GENERAL",       "meta/llama-3.3-70b-instruct")

# Legacy alias (graph.py uses NVIDIA_MODEL)
NVIDIA_MODEL = NIM_MODEL_GENERAL

# Groq fallback model
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.1-70b-versatile")


def _nim_ok() -> bool:
    return bool(NVIDIA_API_KEY and NVIDIA_API_KEY not in ("", "nvapi-your-key-here"))

def _groq_ok() -> bool:
    return bool(GROQ_API_KEY and GROQ_API_KEY not in ("", "your_groq_key_here"))

def get_active_provider() -> str:
    if _nim_ok():  return "nvidia"
    if _groq_ok(): return "groq"
    return "fallback"


# ── Main task-specific interfaces ─────────────────────────────

async def chat_intent(messages: list[dict], temperature: float = 0.1, max_tokens: int = 256) -> str:
    """Fast intent classification — uses llama-3.1-8b for speed + JSON accuracy."""
    return await _nim_call(NIM_MODEL_INTENT, messages, temperature, max_tokens)


async def chat_conversational(messages: list[dict], temperature: float = 0.6, max_tokens: int = 512) -> str:
    """Warm conversational reply — uses Nemotron-70b for nuance + multilingual depth."""
    return await _nim_call(NIM_MODEL_CONVERSATIONAL, messages, temperature, max_tokens)


async def chat_extraction(messages: list[dict], temperature: float = 0.1, max_tokens: int = 512) -> str:
    """Structured data extraction — uses llama-3.1-70b for precise field parsing."""
    return await _nim_call(NIM_MODEL_EXTRACTION, messages, temperature, max_tokens)


async def chat(
    messages: list[dict],
    temperature: float = 0.3,
    max_tokens: int = 1024,
    use_web_search: bool = False,  # kept for API compat — NIM doesn't need this flag
) -> str:
    """
    General-purpose NIM call using llama-3.3-70b (best reasoning).
    Falls back to Groq if NIM key is missing, then returns "" so
    callers can apply their own domain-appropriate fallback.
    """
    result = await _nim_call(NIM_MODEL_GENERAL, messages, temperature, max_tokens)
    return result  # "" if everything failed — caller decides fallback


# ── Internal NIM caller ───────────────────────────────────────

async def _nim_call(model: str, messages: list[dict], temperature: float, max_tokens: int) -> str:
    """
    Call NVIDIA NIM with a specific model.
    Falls back to Groq if the NIM CALL fails (not just when key is missing).
    Returns empty string on total failure so callers can apply their own fallback.
    """
    # 1) Try NIM
    if _nim_ok():
        result = await _openai_compat(NVIDIA_URL, NVIDIA_API_KEY, model, messages, temperature, max_tokens)
        if result:
            return result
        # NIM call failed → try same request with the GENERAL model as 2nd chance
        if model != NIM_MODEL_GENERAL:
            result = await _openai_compat(NVIDIA_URL, NVIDIA_API_KEY, NIM_MODEL_GENERAL, messages, temperature, max_tokens)
            if result:
                return result

    # 2) Groq fallback — tried whenever NIM fails OR key missing
    if _groq_ok():
        try:
            result = await _openai_compat(GROQ_URL, GROQ_API_KEY, GROQ_MODEL, messages, temperature, max_tokens)
            if result:
                return result
        except Exception as e:
            print(f"[LLM] Groq fallback failed: {e}")

    return ""  # empty → caller uses its own appropriate fallback


async def _openai_compat(
    base_url: str,
    api_key: str,
    model: str,
    messages: list[dict],
    temperature: float,
    max_tokens: int,
) -> str:
    """Call any OpenAI-compatible API (NVIDIA NIM or Groq)."""
    import httpx
    try:
        # 10s timeout: fast fail so WhatsApp replies don't get delayed minutes
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{base_url}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"model": model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens},
            )
            if response.status_code != 200:
                body = response.text[:300]
                print(f"[LLM] {base_url} ({model}) HTTP {response.status_code}: {body}")
                return ""
            result = response.json()
            content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
            if not content:
                print(f"[LLM] {base_url} ({model}) returned empty content")
            return content
    except Exception as e:
        print(f"[LLM] {base_url} ({model}) failed: {type(e).__name__}: {e}")
    return ""


def _fallback(messages: list) -> str:
    """Keyword-based fallback when no LLM is available."""
    last = messages[-1].get("content", "") if messages else ""
    lower = last.lower()

    if any(w in lower for w in ["ration", "राशन", "bpl"]):
        return '{"intent": "ration_card", "confidence": 0.9}'
    elif any(w in lower for w in ["pension", "पेंशन"]):
        return '{"intent": "pension", "confidence": 0.9}'
    elif any(w in lower for w in ["pan", "voter", "पैन"]):
        return '{"intent": "identity", "confidence": 0.9}'
    elif any(w in lower for w in ["kisan", "किसान", "farmer"]):
        return '{"intent": "pm_kisan", "confidence": 0.9}'
    elif "scheme" in lower or "eligible" in lower or "योजना" in lower:
        return (
            "Based on your profile, you may be eligible for: "
            "Ration Card (BPL), PM-KISAN, Old Age Pension. "
            "Please provide your age, occupation, and income for accurate results."
        )

    return "I understand your request. Please provide more details so I can help you."


async def extract_json(response: str) -> Optional[dict]:
    """Extract JSON from LLM response (handles markdown code blocks)."""
    import re
    # Try direct parse
    try:
        return json.loads(response)
    except json.JSONDecodeError:
        pass

    # Try extracting from markdown code block
    match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', response, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # Try finding JSON object
    match = re.search(r'\{.*\}', response, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    return None
