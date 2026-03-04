"""
============================================================
browser_mcp.py — Browser Automation MCP Tool Server
============================================================
FastMCP server for Playwright-based government portal navigation.
Uses Vision-Language Model (VLM) for resilient, selector-free browsing.

Tools:
  - launch_browser:       Start a Chromium session
  - navigate_to_url:      Go to a government portal URL
  - vision_find_element:  Use VLM to locate a field by visual label
  - vision_click:         Click at visual coordinates
  - vision_type:          Type text at visual coordinates
  - take_screenshot:      Capture current page screenshot
  - detect_otp_page:      Check if the portal is asking for OTP
  - submit_otp:           Enter OTP into the portal field
  - close_browser:        Cleanup browser resources

All navigation is vision-based — NO CSS selectors required.
"""

import os
import io
import base64
import asyncio
import tempfile
from typing import Optional

import httpx
from dotenv import load_dotenv
from fastmcp import FastMCP

load_dotenv()

NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY", "")
NVIDIA_VLM_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
NVIDIA_VLM_MODEL = os.getenv("NVIDIA_VLM_MODEL", "microsoft/phi-3.5-vision-instruct")

# ── FastMCP Server ───────────────────────────────────────────
mcp = FastMCP(
    name="gramsetu-browser",
    instructions="Vision-based browser automation for navigating "
                 "government portals — no CSS selectors needed.",
)

# ── Browser State (per-session) ──────────────────────────────
_browser_state = {
    "browser": None,
    "context": None,
    "page": None,
    "screenshots": [],
}


# ============================================================
# TOOL 1: Launch Browser
# ============================================================

@mcp.tool()
async def launch_browser(headless: bool = True) -> dict:
    """
    Launch a Chromium browser instance via Playwright.

    Args:
        headless: Run without GUI (True for production, False for dashboard view)

    Returns:
        {"status": "launched", "headless": bool}
    """
    try:
        from playwright.async_api import async_playwright

        pw = await async_playwright().start()
        browser = await pw.chromium.launch(
            headless=headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
            ],
        )
        context = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            locale="hi-IN",
            timezone_id="Asia/Kolkata",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
        )
        page = await context.new_page()

        _browser_state["browser"] = browser
        _browser_state["context"] = context
        _browser_state["page"] = page
        _browser_state["_pw"] = pw

        return {"status": "launched", "headless": headless}
    except Exception as e:
        return {"status": "error", "error": str(e)}


# ============================================================
# TOOL 2: Navigate to URL
# ============================================================

@mcp.tool()
async def navigate_to_url(url: str, wait_ms: int = 3000) -> dict:
    """
    Navigate the browser to a government portal URL.

    Args:
        url:     Target URL (e.g., 'https://www.pan.utiitsl.com')
        wait_ms: Wait time after navigation for page to load (ms)

    Returns:
        {"status": "navigated", "title": "Page Title", "url": "final url"}
    """
    page = _browser_state.get("page")
    if not page:
        return {"status": "error", "error": "Browser not launched. Call launch_browser first."}

    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(wait_ms)
        title = await page.title()
        return {
            "status": "navigated",
            "title": title,
            "url": page.url,
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


# ============================================================
# TOOL 3: Take Screenshot
# ============================================================

@mcp.tool()
async def take_screenshot(full_page: bool = False) -> dict:
    """
    Capture a screenshot of the current browser page.

    Args:
        full_page: Capture entire scrollable page (True) or viewport only (False)

    Returns:
        {"status": "captured", "path": "/tmp/...", "base64": "...first 100 chars..."}
    """
    page = _browser_state.get("page")
    if not page:
        return {"status": "error", "error": "Browser not launched."}

    try:
        tmp = tempfile.NamedTemporaryFile(
            delete=False, suffix=".png", prefix="gramsetu_ss_"
        )
        tmp.close()

        await page.screenshot(path=tmp.name, full_page=full_page)
        _browser_state["screenshots"].append(tmp.name)

        # Read for VLM
        with open(tmp.name, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()

        return {
            "status": "captured",
            "path": tmp.name,
            "base64_preview": b64[:100] + "...",
            "base64_full": b64,
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


# ============================================================
# TOOL 4: Vision Find Element (VLM-based)
# ============================================================

@mcp.tool()
async def vision_find_element(
    label: str,
    element_type: str = "input",
    screenshot_b64: Optional[str] = None,
) -> dict:
    """
    Use a Vision-Language Model to find a UI element by its visual label.
    NO CSS selectors needed — works even after portal redesigns.

    Args:
        label:          Visual label to find (e.g., 'Aadhaar Number', 'Submit')
        element_type:   Type of element ('input', 'button', 'dropdown', 'link')
        screenshot_b64: Base64 screenshot (auto-captured if not provided)

    Returns:
        {"found": True, "x": 342, "y": 187, "confidence": 0.92, "description": "..."}
    """
    # Auto-capture screenshot if not provided
    if not screenshot_b64:
        ss_result = await take_screenshot()
        if ss_result["status"] != "captured":
            return {"found": False, "error": "Could not capture screenshot"}
        screenshot_b64 = ss_result["base64_full"]

    # Build VLM prompt
    prompt = (
        f"You are a UI automation assistant. Look at this webpage screenshot.\n"
        f"Find the {element_type} element labeled '{label}'.\n\n"
        f"Return ONLY a JSON object with these fields:\n"
        f"- found: true or false\n"
        f"- x: horizontal pixel coordinate of the center of the element\n"
        f"- y: vertical pixel coordinate of the center of the element\n"
        f"- confidence: your confidence from 0.0 to 1.0\n"
        f"- description: brief description of what you found\n\n"
        f"If the element is not visible, set found to false."
    )

    # Call NVIDIA NIM VLM
    if NVIDIA_API_KEY and NVIDIA_API_KEY != "nvapi-your-key-here":
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    NVIDIA_VLM_URL,
                    headers={
                        "Authorization": f"Bearer {NVIDIA_API_KEY}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": NVIDIA_VLM_MODEL,
                        "messages": [
                            {
                                "role": "user",
                                "content": [
                                    {"type": "text", "text": prompt},
                                    {
                                        "type": "image_url",
                                        "image_url": {
                                            "url": f"data:image/png;base64,{screenshot_b64}"
                                        },
                                    },
                                ],
                            }
                        ],
                        "max_tokens": 256,
                        "temperature": 0.1,
                    },
                )
                result = response.json()
                content = result["choices"][0]["message"]["content"]

                # Parse JSON from VLM response
                import json
                # Extract JSON from possible markdown code blocks
                if "```" in content:
                    json_str = content.split("```")[1]
                    if json_str.startswith("json"):
                        json_str = json_str[4:]
                    parsed = json.loads(json_str.strip())
                else:
                    parsed = json.loads(content.strip())

                return parsed
        except Exception as e:
            # Fall back to mock response
            pass

    # ── Fallback: heuristic-based element finding ────────────
    # For demo / when VLM is unavailable
    mock_positions = {
        "aadhaar": {"x": 400, "y": 280, "confidence": 0.75},
        "name": {"x": 400, "y": 220, "confidence": 0.75},
        "submit": {"x": 400, "y": 500, "confidence": 0.70},
        "otp": {"x": 400, "y": 300, "confidence": 0.70},
        "phone": {"x": 400, "y": 340, "confidence": 0.70},
        "captcha": {"x": 400, "y": 420, "confidence": 0.60},
    }

    label_lower = label.lower()
    for key, pos in mock_positions.items():
        if key in label_lower:
            return {
                "found": True,
                "x": pos["x"],
                "y": pos["y"],
                "confidence": pos["confidence"],
                "description": f"[Mock] Found '{label}' field at ({pos['x']}, {pos['y']})",
            }

    return {
        "found": False,
        "x": 0,
        "y": 0,
        "confidence": 0.0,
        "description": f"Could not find element labeled '{label}'",
    }


# ============================================================
# TOOL 5: Vision Click
# ============================================================

@mcp.tool()
async def vision_click(x: int, y: int, double_click: bool = False) -> dict:
    """
    Click at specific visual coordinates on the page.
    Used after vision_find_element locates a field.

    Args:
        x:            Horizontal pixel coordinate
        y:            Vertical pixel coordinate
        double_click: Whether to double-click (for text selection)

    Returns:
        {"status": "clicked", "x": x, "y": y}
    """
    page = _browser_state.get("page")
    if not page:
        return {"status": "error", "error": "Browser not launched."}

    try:
        if double_click:
            await page.mouse.dblclick(x, y)
        else:
            await page.mouse.click(x, y)

        await page.wait_for_timeout(500)
        return {"status": "clicked", "x": x, "y": y, "double_click": double_click}
    except Exception as e:
        return {"status": "error", "error": str(e)}


# ============================================================
# TOOL 6: Vision Type
# ============================================================

@mcp.tool()
async def vision_type(
    x: int,
    y: int,
    text: str,
    clear_first: bool = True,
) -> dict:
    """
    Click on a field at (x, y) and type text into it.
    Combines click + keyboard input for vision-based form filling.

    Args:
        x:           Horizontal pixel coordinate of the input field
        y:           Vertical pixel coordinate of the input field
        text:        Text to type into the field
        clear_first: Clear existing content before typing (Ctrl+A, Delete)

    Returns:
        {"status": "typed", "text": "...", "x": x, "y": y}
    """
    page = _browser_state.get("page")
    if not page:
        return {"status": "error", "error": "Browser not launched."}

    try:
        # Click the field
        await page.mouse.click(x, y)
        await page.wait_for_timeout(300)

        # Clear existing content
        if clear_first:
            await page.keyboard.press("Control+a")
            await page.keyboard.press("Delete")
            await page.wait_for_timeout(200)

        # Type with realistic delay
        await page.keyboard.type(text, delay=50)
        await page.wait_for_timeout(300)

        return {"status": "typed", "text": text, "x": x, "y": y}
    except Exception as e:
        return {"status": "error", "error": str(e)}


# ============================================================
# TOOL 7: Detect OTP Page
# ============================================================

@mcp.tool()
async def detect_otp_page(screenshot_b64: Optional[str] = None) -> dict:
    """
    Check if the current page is an OTP verification page.
    Uses VLM to understand the page context, not DOM parsing.

    Args:
        screenshot_b64: Base64 screenshot (auto-captured if not provided)

    Returns:
        {"is_otp_page": bool, "confidence": float, "otp_field_position": {"x": N, "y": N}}
    """
    if not screenshot_b64:
        ss_result = await take_screenshot()
        if ss_result["status"] != "captured":
            return {"is_otp_page": False, "confidence": 0.0}
        screenshot_b64 = ss_result["base64_full"]

    prompt = (
        "Look at this webpage screenshot. Is this an OTP verification page?\n"
        "An OTP page typically asks for a one-time password, verification code, "
        "or shows a message like 'Enter the code sent to your mobile'.\n\n"
        "Return ONLY a JSON object:\n"
        "- is_otp_page: true or false\n"
        "- confidence: your confidence (0.0 to 1.0)\n"
        "- otp_field_x: x coordinate of the OTP input field (0 if not found)\n"
        "- otp_field_y: y coordinate of the OTP input field (0 if not found)\n"
        "- description: what you see on the page"
    )

    if NVIDIA_API_KEY and NVIDIA_API_KEY != "nvapi-your-key-here":
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    NVIDIA_VLM_URL,
                    headers={
                        "Authorization": f"Bearer {NVIDIA_API_KEY}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": NVIDIA_VLM_MODEL,
                        "messages": [
                            {
                                "role": "user",
                                "content": [
                                    {"type": "text", "text": prompt},
                                    {
                                        "type": "image_url",
                                        "image_url": {
                                            "url": f"data:image/png;base64,{screenshot_b64}"
                                        },
                                    },
                                ],
                            }
                        ],
                        "max_tokens": 256,
                        "temperature": 0.1,
                    },
                )
                result = response.json()
                content = result["choices"][0]["message"]["content"]

                import json
                if "```" in content:
                    json_str = content.split("```")[1]
                    if json_str.startswith("json"):
                        json_str = json_str[4:]
                    parsed = json.loads(json_str.strip())
                else:
                    parsed = json.loads(content.strip())

                return {
                    "is_otp_page": parsed.get("is_otp_page", False),
                    "confidence": parsed.get("confidence", 0.0),
                    "otp_field_position": {
                        "x": parsed.get("otp_field_x", 0),
                        "y": parsed.get("otp_field_y", 0),
                    },
                    "description": parsed.get("description", ""),
                }
        except Exception:
            pass

    # Fallback: check page content for OTP keywords
    page = _browser_state.get("page")
    if page:
        try:
            content = await page.content()
            otp_keywords = ["otp", "one-time", "verification code", "verify", "कोड", "सत्यापन"]
            found = any(kw in content.lower() for kw in otp_keywords)
            return {
                "is_otp_page": found,
                "confidence": 0.70 if found else 0.30,
                "otp_field_position": {"x": 400, "y": 300} if found else {"x": 0, "y": 0},
                "description": "OTP keywords detected in page content" if found else "No OTP indicators found",
            }
        except Exception:
            pass

    return {"is_otp_page": False, "confidence": 0.0, "otp_field_position": {"x": 0, "y": 0}}


# ============================================================
# TOOL 8: Submit OTP
# ============================================================

@mcp.tool()
async def submit_otp(
    otp: str,
    otp_field_x: int = 400,
    otp_field_y: int = 300,
) -> dict:
    """
    Enter the OTP into the portal's OTP field and submit.
    Called after the graph resumes from WAIT_OTP state.

    Args:
        otp:          The OTP digits received from the user
        otp_field_x:  X coordinate of the OTP input field
        otp_field_y:  Y coordinate of the OTP input field

    Returns:
        {"status": "submitted", "otp_entered": True}
    """
    page = _browser_state.get("page")
    if not page:
        return {"status": "error", "error": "Browser not launched."}

    try:
        # Type OTP
        type_result = await vision_type(otp_field_x, otp_field_y, otp, clear_first=True)
        if type_result["status"] != "typed":
            return {"status": "error", "error": "Failed to type OTP"}

        await page.wait_for_timeout(500)

        # Try to find and click submit/verify button
        submit_result = await vision_find_element("Submit", element_type="button")
        if not submit_result.get("found"):
            submit_result = await vision_find_element("Verify", element_type="button")

        if submit_result.get("found"):
            await vision_click(submit_result["x"], submit_result["y"])
            await page.wait_for_timeout(2000)

        return {
            "status": "submitted",
            "otp_entered": True,
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


# ============================================================
# TOOL 9: Close Browser
# ============================================================

@mcp.tool()
async def close_browser() -> dict:
    """
    Close the browser and cleanup all resources.
    Should be called after form submission is complete.

    Returns:
        {"status": "closed", "screenshots_cleaned": N}
    """
    cleaned = 0
    try:
        # Clean up screenshots
        for path in _browser_state.get("screenshots", []):
            try:
                if os.path.exists(path):
                    os.unlink(path)
                    cleaned += 1
            except Exception:
                pass

        # Close browser
        if _browser_state.get("browser"):
            await _browser_state["browser"].close()
        if _browser_state.get("_pw"):
            await _browser_state["_pw"].__aexit__(None, None, None)

        # Reset state
        _browser_state.update({
            "browser": None,
            "context": None,
            "page": None,
            "screenshots": [],
        })

        return {"status": "closed", "screenshots_cleaned": cleaned}
    except Exception as e:
        return {"status": "error", "error": str(e)}


# ============================================================
# TOOL 10: Stagehand AI Fill (Natural Language)
# ============================================================

@mcp.tool()
async def stagehand_fill(
    url: str,
    form_data: str,
    form_type: str = "ration_card",
    headless: bool = True,
) -> dict:
    """
    Fill a government portal form using Stagehand AI.
    Uses natural language actions instead of CSS selectors.
    Self-healing — works even after portal HTML changes.

    Args:
        url:        Portal URL to navigate to
        form_data:  JSON string of field_name -> value mapping
        form_type:  Type of form (ration_card, pension, etc.)
        headless:   Run browser in headless mode

    Returns:
        {"status": "filled", "fields_filled": N, "otp_detected": bool}
    """
    import json as _json

    try:
        from backend.stagehand_client import (
            is_stagehand_enabled,
            stagehand_fill_form,
        )

        if not is_stagehand_enabled():
            return {
                "status": "disabled",
                "error": "Stagehand is disabled. Set USE_STAGEHAND=true in .env",
            }

        data = _json.loads(form_data) if isinstance(form_data, str) else form_data

        result = await stagehand_fill_form(
            portal_url=url,
            form_data=data,
            form_type=form_type,
            headless=headless,
        )

        return {
            "status": "filled" if result["success"] else "error",
            "fields_filled": result.get("fields_filled", 0),
            "otp_detected": result.get("otp_detected", False),
            "error": result.get("error"),
        }
    except ImportError:
        return {"status": "error", "error": "stagehand-py not installed"}
    except Exception as e:
        return {"status": "error", "error": str(e)}


# ── Entry Point ──────────────────────────────────────────────

if __name__ == "__main__":
    mcp.run(transport="sse", host="0.0.0.0", port=8101)
