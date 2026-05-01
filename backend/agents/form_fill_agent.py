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
import json
import time
import asyncio
import base64
from typing import Optional, Literal
from dataclasses import dataclass, field

from backend.agents.portal_registry import (
    get_portal_info,
    get_field_labels,
)
from backend.agents.graph import _browser_ws_clients

from dotenv import load_dotenv
load_dotenv()

# ── Config ────────────────────────────────────────────────
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY", "")
NVIDIA_VLM_URL = os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
NVIDIA_VLM_MODEL = os.getenv("NIM_MODEL_VISION", "meta/llama-3.2-11b-vision-instruct")

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_VISION_MODEL = os.getenv("GROQ_MODEL_VISION", "meta-llama/llama-4-scout-17b-16e-instruct")

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
    login_detected: bool = False
    login_type: str = ""
    file_upload_detected: bool = False
    file_upload_fields: list = field(default_factory=list)
    confidence: float = 0.0
    reasoning: str = ""
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "action": self.action, "field": self.field, "value": self.value,
            "label": self.label, "page_phase": self.page_phase, "done": self.done,
            "otp_detected": self.otp_detected, "login_detected": self.login_detected,
            "login_type": self.login_type, "file_upload_detected": self.file_upload_detected,
            "confidence": self.confidence, "reasoning": self.reasoning,
        }


@dataclass
class FormFillResult:
    """Result of the full form fill run."""
    success: bool = False
    fields_filled: int = 0
    otp_detected: bool = False
    login_detected: bool = False
    login_type: str = ""
    file_upload_detected: bool = False
    manual_uploads: list = field(default_factory=list)
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
    """Analyze screenshot using NVIDIA NIM llama-3.2-11b-vision."""
    import httpx

    remaining = {k: v for k, v in form_data.items() if v}
    remaining_items = "\n".join(f"  - {k}: {v}" for k, v in list(remaining.items())[:15])

    prompt = f"""You are a web form-filling AI assistant. Look at the screenshot of a web portal.

**Form type:** {form_type}
**Language:** {language}
**Page context:** {page_context or "Unknown page"}

**Fields to fill:**
{remaining_items}

**Instructions:**
1. Look for blocking popups, overlays, cookie consent banners, or chat widgets. Close them first.
2. Check if this is a LOGIN/SIGN-IN page first. If you see login buttons, auth fields, or OAuth options, report it.
3. Check for FILE UPLOAD inputs — mark these, don't try to fill them.
4. Identify which field from the list is visible on screen.
5. Check if there's an OTP/verification field.

Respond with ONLY a valid JSON object. The response must start with '{{' and end with '}}'.

{{
  "action": "fill_field" | "click_button" | "select_option" | "scroll_down" | "wait_for_page" | "login_detected" | "done",
  "field": "field_name",
  "value": "value to enter",
  "label": "exact label text visible on screen",
  "page_phase": "login" | "personal" | "address" | "bank" | "file_upload" | "review" | "otp" | "unknown",
  "done": false,
  "otp_detected": false,
  "login_detected": false,
  "login_type": "",
  "file_upload_detected": false,
  "confidence": 0.95,
  "reasoning": "brief explanation"
}}

If a LOGIN/SIGN-IN page is visible, set login_detected=true and login_type to one of:
  - "otp" — if Aadhaar or mobile OTP fields visible
  - "password" — if email/username + password fields visible
  - "oauth" — if Google/Facebook/Apple sign-in buttons visible
  - "unknown" — if login buttons visible but type unclear

If file upload inputs are visible (choose file, browse, attach), set file_upload_detected=true.
If no more fields need filling, set action="done".
If OTP field is visible, set otp_detected=true.
If nothing visible, try scroll_down."""

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
                                "url": f"data:image/jpeg;base64,{screenshot_b64}"
                            }},
                        ],
                    }],
                    "max_tokens": 512,
                    "temperature": 0.1,
                },
            )
        if response.status_code != 200:
            print(f"[FormFill] NVIDIA Error {response.status_code}: {response.text}")
            return FormFillAction(action="wait_for_page", error=f"HTTP {response.status_code}")

        content = response.json()["choices"][0]["message"]["content"]
        print(f"[FormFill] NVIDIA Response: {content[:200]}...")
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
                    "model": "sarvam-v1",
                },
            )
        if response.status_code == 200:
            result = response.json()
            content = result.get("response", "")
            if content:
                return _parse_action_response(content)
    except Exception:
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
                                "url": f"data:image/jpeg;base64,{screenshot_b64}"
                            }},
                        ],
                    }],
                    "max_tokens": 256,
                    "temperature": 0.1,
                },
            )
        if response.status_code == 200:
            content = response.json()["choices"][0]["message"]["content"]
            print(f"[FormFill] Groq Response: {content[:200]}...")
            return _parse_action_response(content)
        else:
            print(f"[FormFill] Groq Error {response.status_code}: {response.text}")
    except Exception:
        pass
    return FormFillAction(action="wait_for_page", error="groq_failed")


def _parse_action_response(raw: str) -> FormFillAction:
    """Parse JSON from VLM response with high tolerance."""
    try:
        import re
        # Find anything that looks like JSON { ... } or [ { ... } ]
        m = re.search(r'(\[?\s*\{.*\}\s*\]?)', raw, re.DOTALL)
        if m:
            json_str = m.group(1).strip()
            parsed = json.loads(json_str)
            
            # If it's a list, take the first item
            if isinstance(parsed, list) and len(parsed) > 0:
                parsed = parsed[0]
            
            if isinstance(parsed, dict):
                # Map common action variations
                act = str(parsed.get("action", "wait_for_page")).lower()
                if act in ["fill", "type", "input"]:
                    act = "fill_field"
                if act in ["click", "press", "tap"]:
                    act = "click_button"
                if act in ["select", "choose", "dropdown"]:
                    act = "select_option"
                
                return FormFillAction(
                    action=act,
                    field=parsed.get("field"),
                    value=parsed.get("value"),
                    label=parsed.get("label"),
                    page_phase=parsed.get("page_phase", "unknown"),
                    done=parsed.get("done", False),
                    otp_detected=parsed.get("otp_detected", False) or parsed.get("otp", False),
                    otp_field_position=parsed.get("otp_field_position"),
                    login_detected=parsed.get("login_detected", False),
                    login_type=parsed.get("login_type", ""),
                    file_upload_detected=parsed.get("file_upload_detected", False),
                    file_upload_fields=parsed.get("file_upload_fields", []),
                    confidence=parsed.get("confidence", 0.8),
                    reasoning=parsed.get("reasoning", ""),
                )
    except Exception as e:
        print(f"[FormFill] Parse Error: {e} | Raw: {raw[:200]}")
    
    return FormFillAction(action="wait_for_page", error="parse_failed")


async def analyze_portal_screenshot(
    screenshot_b64: str,
    form_data: dict,
    form_type: str,
    language: str = "hi",
    page_context: str = "",
) -> FormFillAction:
    """
    Analyze a portal screenshot and decide the next action.
    Vision priority: NVIDIA NIM → Groq Vision → heuristic fallback.
    (Sarvam Vision temporarily skipped — insufficient quality)
    """
    # 1. NVIDIA NIM Vision (PRIMARY — llama-3.2-11b-vision-instruct, free tier)
    if NVIDIA_API_KEY and NVIDIA_API_KEY != "nvapi-your-key-here":
        result = await _analyze_with_nim_vision(
            screenshot_b64, form_data, form_type, language, page_context
        )
        if not result.error:
            return result

    # 2. Groq Vision (FALLBACK — llama-3.2-11b-vision-preview)
    if GROQ_API_KEY:
        result = await _analyze_with_groq_vision(
            screenshot_b64, form_data, form_type, language
        )
        if not result.error:
            return result

    # 3. Sarvam Vision (BACKUP — India-specific, lower quality)
    if _SARVAM_OK:
        result = await _analyze_with_sarvam_vision(
            screenshot_b64, form_data, form_type, language, page_context
        )
        if not result.error or result.error == "sarvam_failed":
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
                "portal_url": portal_url,
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

    # ── Core Fill Logic ────────────────────────────────────
    ss_path = os.path.join(screenshot_dir, f"{form_type}_{session_id}.png")

    try:
        # Initial status broadcast
        await _broadcast("loading", "Starting Browser...", 0.0)

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
            page.on("dialog", lambda d: asyncio.ensure_future(d.dismiss()))

            try:
                await _broadcast("loading", f"Navigating to {portal_url}...", 0.0)
                # Use domcontentloaded for faster loading of mock portals (avoids timeout on fonts)
                await page.goto(portal_url, wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(2000) 

                # Auto-dismiss common popups (like cookie policies)
                for label in ["Accept All Cookies", "Accept", "सहमति दें", "ठीक है", "Close", "बंद करें"]:
                    try:
                        btn = page.get_by_text(label, exact=False).first
                        if await btn.count() > 0 and await btn.is_visible():
                            await btn.click(timeout=2000)
                            await page.wait_for_timeout(500)
                    except Exception:
                        pass
            except Exception as e:
                print(f"[FormFill] Navigation warning (retrying): {e}")
                # Fallback: try localhost if 127.0.0.1 failed
                alt_url = portal_url.replace("127.0.0.1", "localhost")
                await page.goto(alt_url, wait_until="load", timeout=45000)

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

                    # Prioritize the label the AI actually saw on the screen
                    field_labels = []
                    if action.label:
                        field_labels.append(action.label)
                    
                    # Fallback to pre-defined labels from the registry
                    registry_labels = get_field_labels(form_type, field_name)
                    for rl in registry_labels:
                        if rl not in field_labels:
                            field_labels.append(rl)
                    
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

                elif action.login_detected:
                    # VLM detected a login page — stop filling, report back
                    result.login_detected = True
                    result.login_type = action.login_type or "unknown"
                    try:
                        ss_bytes = await page.screenshot(type="jpeg", quality=70)
                        result.screenshot_b64 = base64.b64encode(ss_bytes).decode()
                    except Exception:
                        pass
                    break

                elif action.file_upload_detected:
                    # VLM detected file upload fields — mark and continue with other fields
                    file_fields = action.file_upload_fields or [{"label": action.label or "Unknown file"}]
                    result.file_upload_detected = True
                    result.manual_uploads.extend(file_fields)
                    filled_count += 1  # mark as handled (not filled, but acknowledged)
                    # Remove from remaining so we don't try again
                    if action.field in remaining_data:
                        remaining_data.pop(action.field)
                    # Continue loop — other fields can still be filled

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
                result.steps_taken = steps_taken
                page_context = action.page_phase
                
                # Small pause to prevent rate limits and allow browser to settle
                await page.wait_for_timeout(2000)

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
    except Exception as e:
        result.error = str(e)
        print(f"[FormFill] Error: {e}")

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
        "login_detected": result.login_detected,
        "login_type": result.login_type,
        "file_upload_detected": result.file_upload_detected,
        "manual_uploads": [u.get("label", str(u)) for u in result.manual_uploads],
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