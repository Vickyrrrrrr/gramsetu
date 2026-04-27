"""
============================================================
form_fill_agent.py — LLM Vision-Based Form Filler
============================================================
An autonomous agent that sees government portals and fills them.

No CSS selectors. No hard-coded element paths.
The LLM sees the portal screenshot and decides what to do.

Agent Loop:
  1. Take screenshot
  2. VLM analyzes page → returns JSON action
  3. Execute action via Playwright
  4. Repeat until submission or OTP page

Key Features:
  - Vision-native: understands Hindi/English labels on screen
  - Self-healing: adapts when portal UI changes
  - Step-limited: max 20 actions per form (no infinite loops)
  - Checkpoint-backed: suspend/resume across server restarts
  - WebSocket streaming: live screenshots to webapp

Provider Stack:
  Vision:     NVIDIA NIM llama-3.2-90b-vision (primary)
              Groq Vision (fallback)
              Sarvam Vision (backup)
  Actions:    Playwright (deterministic execution)
  State:      LangGraph SqliteSaver checkpoints
"""

import os
import io
import json
import time
import asyncio
import base64
import tempfile
import threading
from typing import Optional, Literal
from dataclasses import dataclass, field
from datetime import datetime

from dotenv import load_dotenv
load_dotenv()

from backend.agents.portal_registry import (
    get_portal_info,
    get_field_labels,
    match_field_by_label,
    PORTAL_URLS,
)
from backend.agents.schema import GramSetuState, GraphStatus
from backend.agents.graph import _browser_ws_clients

# ── Config ────────────────────────────────────────────────
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY", "")
NVIDIA_VLM_URL = os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
NVIDIA_VLM_MODEL = os.getenv("NVIDIA_VLM_MODEL", "meta/llama-3.2-90b-vision-instruct")

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_VISION_MODEL = os.getenv("GROQ_MODEL_VISION", "llama-3.2-11b-vision-preview")

SARVAM_API_KEY = os.getenv("SARVAM_API_KEY", "")
_SARVAM_OK = bool(SARVAM_API_KEY and SARVAM_API_KEY not in ("", "your_sarvam_key_here"))

# ── WebSocket Clients (shared with graph.py) ─────────────────

# ── Cancellation Signals ─────────────────────────────────────
# session_id -> bool (if true, agent should abort)
_cancel_signals: dict = {}

# ── Screenshot Cache ─────────────────────────────────────
_screenshot_cache: dict = {}


@dataclass
class FormFillAction:
    """One action returned by the VLM."""
    action: Literal["fill_field", "click_button", "select_option", "scroll_down",
                  "wait_for_page", "take_screenshot", "done"]
    field: Optional[str] = None
    value: Optional[str] = None
    label: Optional[str] = None
    page_phase: str = "unknown"
    done: bool = False
    otp_detected: bool = False
    otp_field_position: Optional[dict] = None
    confidence: float = 0.0
    reasoning: str = ""
    error: Optional[str] = None


@dataclass
class FormFillResult:
    """Result of the full form fill run."""
    success: bool = False
    fields_filled: int = 0
    otp_detected: bool = False
    otp_field_position: Optional[dict] = None
    screenshot_b64: str = ""
    screenshot_path: str = ""
    reference_number: str = ""
    error: Optional[str] = None
    steps_taken: int = 0
    actions: list = field(default_factory=list)


# ============================================================
# VLM: Analyze Portal Screenshot
# ============================================================

async def _analyze_with_nim_vision(
    screenshot_b64: str,
    form_data: dict,
    form_type: str,
    language: str,
    page_context: str = "",
) -> FormFillAction:
    """Analyze screenshot using NVIDIA NIM llama-3.2-90b-vision."""
    import httpx

    remaining = {k: v for k, v in form_data.items() if v}
    remaining_items = "\n".join(f"  - {k}: {v}" for k, v in list(remaining.items())[:15])

    prompt = f"""You are a government form-filling AI assistant. Look at the screenshot of an Indian government portal.

**Form type:** {form_type}
**Language:** {language}
**Page context:** {page_context or "Unknown page"}

**Fields to fill:**
{remaining_items}

**Instructions:**
1. Look carefully at the screenshot for ANY blocking popups, overlays, or cookie consent banners (e.g., "Accept All Cookies", "Close", "OK", "आईये", "सहमति दें").
2. **PRIORITY 1**: If a popup is blocking the form, set action="click_button" and label to the button text that closes it.
3. **PRIORITY 2**: If no popup, identify which field from the list is visible on screen.
4. Check if there is an OTP/verification field.
5. Check if the submit button is visible.

Respond with ONLY valid JSON (no markdown):
{{
  "action": "fill_field" | "click_button" | "select_option" | "scroll_down" | "wait_for_page" | "done",
  "field": "field_name",
  "value": "value to enter",
  "label": "exact label text visible on screen",
  "page_phase": "personal" | "address" | "bank" | "review" | "otp" | "unknown",
  "done": false,
  "otp_detected": false,
  "otp_field_position": {{"x": 0, "y": 0}},
  "confidence": 0.95,
  "reasoning": "brief explanation"
}}

If a blocking popup is seen, prioritize clicking its close/accept button.
If no more fields need filling and form appears complete, set action="done".
If OTP field is visible, set otp_detected=true and otp_field_position to clickable center.
If nothing visible to fill, try scroll_down."""

    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            response = await client.post(
                f"{NVIDIA_VLM_URL}/chat/completions",
                headers={
                    "Authorization": f"Bearer {NVIDIA_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": NVIDIA_VLM_MODEL,
                    "messages": [{
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {
                                "url": f"data:image/png;base64,{screenshot_b64}"
                            }},
                        ],
                    }],
                    "max_tokens": 512,
                    "temperature": 0.1,
                },
            )
        if response.status_code != 200:
            return FormFillAction(action="wait_for_page", error=f"HTTP {response.status_code}")

        content = response.json()["choices"][0]["message"]["content"]
        return _parse_action_response(content)
    except Exception as e:
        return FormFillAction(action="wait_for_page", error=str(e))


async def _analyze_with_sarvam_vision(
    screenshot_b64: str,
    form_data: dict,
    form_type: str,
    language: str,
    page_context: str = "",
) -> FormFillAction:
    """Analyze screenshot using Sarvam Vision 3B."""
    import httpx

    remaining = {k: v for k, v in form_data.items() if v}
    remaining_items = "\n".join(f"  - {k}: {v}" for k, v in list(remaining.items())[:15])

    prompt = f"""Analyze this government portal screenshot for form filling.

Form: {form_type} | Fields remaining: {remaining_items}

Return JSON:
{{
  "action": "fill_field",
  "field": "field_name",
  "value": "value",
  "label": "visible label",
  "page_phase": "personal",
  "done": false,
  "otp_detected": false,
  "otp_field_position": {{"x": 0, "y": 0}},
  "confidence": 0.9,
  "reasoning": ""
}}"""

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://api.sarvam.ai/vision/v1/analyze",
                headers={"Authorization": f"Bearer {SARVAM_API_KEY}"},
                json={
                    "image": screenshot_b64,
                    "prompt": prompt,
                    "model": "sarvam-vision-1",
                },
            )
        if response.status_code == 200:
            result = response.json()
            content = result.get("response", "")
            if content:
                return _parse_action_response(content)
    except Exception as e:
        pass
    return FormFillAction(action="wait_for_page", error="sarvam_failed")


async def _analyze_with_groq_vision(
    screenshot_b64: str,
    form_data: dict,
    form_type: str,
    language: str,
) -> FormFillAction:
    """Fallback: Groq Vision (free tier)."""
    import httpx

    remaining = {k: v for k, v in form_data.items() if v}
    remaining_items = "\n".join(f"  - {k}: {v}" for k, v in list(remaining.items())[:15])

    prompt = f"""Analyze this government portal. Fill these fields: {remaining_items}
Return JSON with action, field, value, label, page_phase, done, otp_detected, confidence."""

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
                json={
                    "model": GROQ_VISION_MODEL,
                    "messages": [{
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {
                                "url": f"data:image/png;base64,{screenshot_b64}"
                            }},
                        ],
                    }],
                    "max_tokens": 256,
                    "temperature": 0.1,
                },
            )
        if response.status_code == 200:
            content = response.json()["choices"][0]["message"]["content"]
            return _parse_action_response(content)
    except Exception:
        pass
    return FormFillAction(action="wait_for_page", error="groq_failed")


def _parse_action_response(raw: str) -> FormFillAction:
    """Parse JSON from VLM response."""
    try:
        import re
        # Extract JSON from possible markdown code blocks
        if "```" in raw:
            parts = raw.split("```")
            for part in parts:
                stripped = part.strip()
                if stripped.startswith("json"):
                    stripped = stripped[4:].strip()
                if stripped.startswith("{") and stripped.endswith("}"):
                    parsed = json.loads(stripped)
                    return FormFillAction(
                        action=parsed.get("action", "wait_for_page"),
                        field=parsed.get("field"),
                        value=parsed.get("value"),
                        label=parsed.get("label"),
                        page_phase=parsed.get("page_phase", "unknown"),
                        done=parsed.get("done", False),
                        otp_detected=parsed.get("otp_detected", False),
                        otp_field_position=parsed.get("otp_field_position"),
                        confidence=parsed.get("confidence", 0.5),
                        reasoning=parsed.get("reasoning", ""),
                    )
            # Try finding JSON anywhere in the response
            m = re.search(r'\{.*\}', raw, re.DOTALL)
            if m:
                parsed = json.loads(m.group(0))
                return FormFillAction(
                    action=parsed.get("action", "wait_for_page"),
                    field=parsed.get("field"),
                    value=parsed.get("value"),
                    label=parsed.get("label"),
                    page_phase=parsed.get("page_phase", "unknown"),
                    done=parsed.get("done", False),
                    otp_detected=parsed.get("otp_detected", False),
                    otp_field_position=parsed.get("otp_field_position"),
                    confidence=parsed.get("confidence", 0.5),
                    reasoning=parsed.get("reasoning", ""),
                )
        else:
            parsed = json.loads(raw.strip())
            return FormFillAction(
                action=parsed.get("action", "wait_for_page"),
                field=parsed.get("field"),
                value=parsed.get("value"),
                label=parsed.get("label"),
                page_phase=parsed.get("page_phase", "unknown"),
                done=parsed.get("done", False),
                otp_detected=parsed.get("otp_detected", False),
                otp_field_position=parsed.get("otp_field_position"),
                confidence=parsed.get("confidence", 0.5),
                reasoning=parsed.get("reasoning", ""),
            )
    except Exception as e:
        return FormFillAction(action="wait_for_page", error=f"parse_error: {e}")


async def analyze_portal_screenshot(
    screenshot_b64: str,
    form_data: dict,
    form_type: str,
    language: str = "hi",
    page_context: str = "",
) -> FormFillAction:
    """
    Analyze a portal screenshot and decide the next action.
    Priority: Sarvam Vision → NVIDIA NIM → Groq Vision → fallback.
    """
    # 1. Sarvam Vision (India-trained, excellent for Indic portals)
    if _SARVAM_OK:
        result = await _analyze_with_sarvam_vision(
            screenshot_b64, form_data, form_type, language, page_context
        )
        if not result.error or result.error == "sarvam_failed":
            return result

    # 2. NVIDIA NIM Vision (Fallback, high quality)
    if NVIDIA_API_KEY and NVIDIA_API_KEY != "nvapi-your-key-here":
        result = await _analyze_with_nim_vision(
            screenshot_b64, form_data, form_type, language, page_context
        )
        if not result.error:
            return result

    # 3. Groq Vision (Secondary fallback)
    if GROQ_API_KEY:
        result = await _analyze_with_groq_vision(
            screenshot_b64, form_data, form_type, language
        )
        if not result.error:
            return result

    # 4. Heuristic fallback (no VLM)
    return _heuristic_action(screenshot_b64, form_data, form_type)


def _heuristic_action(
    screenshot_b64: str,
    form_data: dict,
    form_type: str,
) -> FormFillAction:
    """
    Fallback when no VLM is available.
    Uses portal_registry field labels to guess next action.
    """
    remaining = [k for k, v in form_data.items() if v]
    if not remaining:
        return FormFillAction(action="done", done=True, confidence=1.0)

    next_field = remaining[0]
    labels = get_field_labels(form_type, next_field)
    primary_label = labels[0] if labels else next_field.replace("_", " ").title()

    return FormFillAction(
        action="fill_field",
        field=next_field,
        value=str(form_data.get(next_field, "")),
        label=primary_label,
        page_phase="unknown",
        confidence=0.3,
        reasoning="Heuristic fallback (no VLM available)",
    )


# ============================================================
# Playwright Actions (Deterministic Execution)
# ============================================================

async def _playwright_fill(
    portal_url: str,
    form_data: dict,
    form_type: str,
    language: str = "hi",
    session_id: str = "",
    user_id_for_ws: str = "",
    max_steps: int = 20,
    screenshot_dir: Optional[str] = None,
) -> FormFillResult:
    """
    Core agent loop: see portal → decide action → execute → repeat.
    Uses Playwright for deterministic browser control.

    Args:
        portal_url:     Target portal URL
        form_data:     Field name → value mapping
        form_type:     Form type (ration_card, pension, etc.)
        language:      User language
        session_id:   For WebSocket + screenshot naming
        user_id_for_ws: Frontend WebSocket channel key
        max_steps:    Max actions (default 20, prevents infinite loops)
        screenshot_dir: Where to save screenshots

    Returns:
        FormFillResult with screenshot, otp status, fields filled
    """
    import asyncio as _aio
    from playwright.async_api import async_playwright

    screenshot_dir = screenshot_dir or os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "data", "screenshots"
    )
    os.makedirs(screenshot_dir, exist_ok=True)

    result = FormFillResult()
    remaining_data = {k: v for k, v in form_data.items() if v}

    # ── WebSocket Broadcast ────────────────────────────────
    async def _broadcast(frame_b64: str, step: str = "", progress: float = 0):
        try:
            import json as _json
            payload = _json.dumps({
                "type": "browser_frame",
                "screenshot": frame_b64,
                "step": step,
                "progress": progress,
            })
            for key in {session_id, user_id_for_ws}:
                if not key:
                    continue
                clients = _browser_ws_clients.get(key, [])
                dead = []
                for ws in clients:
                    try:
                        await ws.send_text(payload)
                    except Exception:
                        dead.append(ws)
                for ws in dead:
                    try:
                        clients.remove(ws)
                    except ValueError:
                        pass
        except Exception:
            pass

    # ── Thread-safe async event loop ─────────────────
    _pw_result: dict = {"error": None, "final_screenshot": "", "final_path": ""}

    def _run_sync():
        loop = _aio.new_event_loop()
        _aio.set_event_loop(loop)
        try:
            loop.run_until_complete(_do_fill())
        finally:
            loop.close()

    async def _do_fill():
        nonlocal remaining_data, result

        ss_path = os.path.join(screenshot_dir, f"{form_type}_{session_id}.png")

        try:
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-dev-shm-usage"],
                )
                context = await browser.new_context(
                    viewport={"width": 1280, "height": 900},
                    locale="hi-IN",
                    timezone_id="Asia/Kolkata",
                )
                page = await context.new_page()
                page.on("dialog", lambda d: _aio.ensure_future(d.dismiss()))

                try:
                    await page.goto(portal_url, wait_until="commit", timeout=60000)
                    await page.wait_for_timeout(3000) # Give JS a moment to render
                except Exception as e:
                    print(f"[FormFill] Navigation failed to {portal_url}: {e}")
                    # Fallback retry with longer timeout
                    await page.goto(portal_url, wait_until="load", timeout=90000)

                # Take initial screenshot
                try:
                    ss_bytes = await page.screenshot(type="jpeg", quality=60)
                    b64 = base64.b64encode(ss_bytes).decode()
                    await _broadcast(b64, "Portal loaded", 0.0)
                except Exception:
                    b64 = ""

                # Agent loop
                steps_taken = 0
                page_context = ""
                filled_count = 0
                scroll_count = 0
                stuck_count = 0
                last_action = None

                while steps_taken < max_steps:
                    steps_taken += 1

                    # ── Check for Cancellation Signal ─────────
                    if _cancel_signals.get(session_id):
                        print(f"[FormFill] Session {session_id[:8]}... ABORTED by user.")
                        _cancel_signals.pop(session_id, None)
                        break

                    # ── Analyze with VLM ──────────────────
                    try:
                        ss_bytes = await page.screenshot(type="jpeg", quality=50)
                        b64 = base64.b64encode(ss_bytes).decode()
                        _screenshot_cache[session_id] = b64
                    except Exception as e:
                        b64 = ""
                        print(f"[FormFill] Screenshot failed: {e}")

                    action = await analyze_portal_screenshot(
                        b64, remaining_data, form_type, language, page_context
                    )

                    if action.error:
                        action.action = "wait_for_page"

                    # ── Execute Action ─────────────────────
                    if action.action == "done" or action.done:
                        result.success = True
                        result.fields_filled = filled_count
                        result.steps_taken = steps_taken
                        try:
                            await page.click("#declaration", timeout=2000)
                            await page.click("#send-otp-btn", timeout=2000)
                        except Exception:
                            pass
                        break

                    elif action.action == "fill_field" and action.field:
                        field_name = action.field
                        field_value = action.value or remaining_data.get(field_name, "")

                        if not field_value:
                            remaining_data.pop(field_name, None)
                            continue

                        field_labels = get_field_labels(form_type, field_name)
                        filled = False

                        for label in field_labels:
                            try:
                                locator = page.get_by_label(label).first
                                if await locator.count() > 0:
                                    await locator.scroll_into_view_if_needed()
                                    await locator.click(timeout=1000)
                                    await page.wait_for_timeout(200)
                                    await locator.fill("")
                                    await locator.type(field_value, delay=40)
                                    await page.wait_for_timeout(300)
                                    filled = True
                                    filled_count += 1
                                    remaining_data.pop(field_name, None)
                                    stuck_count = 0
                                    break
                            except Exception:
                                pass

                        if filled:
                            progress = filled_count / max(len(form_data), 1)
                            try:
                                ss_bytes = await page.screenshot(type="jpeg", quality=50)
                                await _broadcast(
                                    base64.b64encode(ss_bytes).decode(),
                                    f"Filled: {field_name}",
                                    progress,
                                )
                            except Exception:
                                pass

                    elif action.action == "click_button":
                        # Priority labels including popups
                        button_labels = [
                            "Accept All Cookies", "Accept", "OK", "Close", "Dismiss", "X", "Close Window",
                            "सहमति दें", "ठीक है", "बंद करें", "हटाएं",
                            "Submit", "जमा करें", "Apply", "आवेदन करें",
                            "Register", "Proceed", "Next", "Continue"
                        ]
                        if action.label:
                            button_labels.insert(0, action.label)
                        for bl in button_labels:
                            try:
                                btn = page.get_by_role("button", name=bl).first
                                if await btn.count() > 0:
                                    await btn.click(timeout=1000)
                                    await page.wait_for_timeout(1500)
                                    break
                            except Exception:
                                pass

                    elif action.action == "scroll_down":
                        scroll_count += 1
                        if scroll_count > 5:
                            break
                        await page.evaluate("window.scrollBy(0, 400)")
                        await page.wait_for_timeout(500)

                    elif action.action == "select_option" and action.field and action.value:
                        field_labels = get_field_labels(form_type, action.field)
                        for label in field_labels:
                            try:
                                sel = page.get_by_label(label).first
                                if await sel.count() > 0:
                                    await sel.select_option(action.value, timeout=1000)
                                    filled_count += 1
                                    break
                            except Exception:
                                pass

                    elif action.action == "wait_for_page":
                        await page.wait_for_timeout(1000)

                    # Stuck detection
                    if action.action == last_action:
                        stuck_count += 1
                        if stuck_count > 3:
                            await page.evaluate("window.scrollBy(0, 400)")
                            stuck_count = 0
                    else:
                        stuck_count = 0
                    last_action = action.action

                    result.actions.append(action)
                    page_context = action.page_phase

                # ── Final State ────────────────────────────
                try:
                    final_ss = await page.screenshot(type="jpeg", quality=70)
                    result.screenshot_b64 = base64.b64encode(final_ss).decode()
                    await page.screenshot(path=ss_path, full_page=False)
                    result.screenshot_path = ss_path
                    await _broadcast(result.screenshot_b64, "complete", 1.0)
                except Exception as e:
                    print(f"[FormFill] Final screenshot: {e}")

                # Check for OTP page
                otp_keywords = ["otp", "verification", "सत्यापन", "कोड", "one-time"]
                try:
                    content = await page.content()
                    if any(k in content.lower() for k in otp_keywords):
                        result.otp_detected = True
                except Exception:
                    pass

                await browser.close()
                result.fields_filled = filled_count
                result.steps_taken = steps_taken

        except Exception as e:
            result.error = str(e)
            print(f"[FormFill] Error: {e}")

    thread = threading.Thread(target=_run_sync, daemon=True)
    thread.start()
    thread.join(timeout=120)

    if _pw_result.get("error"):
        result.error = _pw_result.get("error")
    if _pw_result.get("final_screenshot"):
        result.screenshot_b64 = _pw_result["final_screenshot"]
    if _pw_result.get("final_path"):
        result.screenshot_path = _pw_result["final_path"]

    return result


# ============================================================
# Public API: run_form_fill_agent
# ============================================================

async def run_form_fill_agent(
    form_type: str,
    form_data: dict,
    language: str = "hi",
    session_id: str = "",
    user_id: str = "",
    max_steps: int = 20,
) -> dict:
    """
    Main entry point. Call this from graph.py's fill_form_node.

    Args:
        form_type:   Type of form (ration_card, pension, etc.)
        form_data:   All extracted field values
        language:    User language code
        session_id:  For checkpointing and WebSocket
        user_id:     Web frontend user ID
        max_steps:   Max VLM steps (default 20)

    Returns:
        dict with fields_filled, screenshot_b64, otp_detected, etc.
    """
    start_time = time.time()
    form_type = form_type or "ration_card"
    session_id = session_id or f"ff_{int(time.time())}"
    user_id_for_ws = user_id or session_id

    portal_info = get_portal_info(form_type)
    portal_url = portal_info["url"]

    screenshot_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "data", "screenshots"
    )
    os.makedirs(screenshot_dir, exist_ok=True)

    print(f"[FormFill] Starting: {form_type} | {len(form_data)} fields | "
          f"session={session_id} | steps={max_steps}")

    result = await _playwright_fill(
        portal_url=portal_url,
        form_data=form_data,
        form_type=form_type,
        language=language,
        session_id=session_id,
        user_id_for_ws=user_id_for_ws,
        max_steps=max_steps,
        screenshot_dir=screenshot_dir,
    )

    elapsed = time.time() - start_time
    print(f"[FormFill] Done: {result.fields_filled}/{len(form_data)} fields filled | "
          f"OTP={result.otp_detected} | {result.steps_taken} steps | "
          f"{elapsed:.1f}s | error={result.error}")

    return {
        "success": result.success,
        "fields_filled": result.fields_filled,
        "otp_detected": result.otp_detected,
        "otp_field_position": result.otp_field_position,
        "screenshot_b64": result.screenshot_b64,
        "screenshot_path": result.screenshot_path,
        "reference_number": result.reference_number,
        "error": result.error,
        "steps_taken": result.steps_taken,
        "elapsed_seconds": round(elapsed, 1),
        "actions": [
            {"action": a.action, "field": a.field, "confidence": a.confidence}
            for a in result.actions
        ],
    }


async def analyze_portal_for_fields(
    screenshot_b64: str,
    form_type: str,
    language: str = "hi",
) -> dict:
    """
    Analyze a portal screenshot and return detected fields.
    Used for debugging and testing.
    """
    action = await analyze_portal_screenshot(
        screenshot_b64=screenshot_b64,
        form_data={},
        form_type=form_type,
        language=language,
        page_context="initial",
    )

    return {
        "action": action.action,
        "field": action.field,
        "value": action.value,
        "label": action.label,
        "page_phase": action.page_phase,
        "otp_detected": action.otp_detected,
        "confidence": action.confidence,
        "reasoning": action.reasoning,
    }