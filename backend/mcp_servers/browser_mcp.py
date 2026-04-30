"""
Browser MCP Server — Playwright-powered form automation.

Exposes tools:
  - navigate: Open a URL
  - fill_field: Fill a single form field by label
  - click_button: Click a button by label
  - take_screenshot: Capture current page
  - fill_form: Fill entire form from data dict
  - get_page_state: Get current page state/details
  - detect_otp: Check if OTP field is on page
  - stop_session: Stop browser session

All tools operate on Playwright browser instances managed per session.
"""

import os
import asyncio
import base64
import json
from typing import Optional
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("GramSetu Browser Server")

# ── Aliases for backward compatibility with tests ──────────
# Tests import 'stagehand_fill' from browser_mcp
async def stagehand_fill(portal_url: str, form_data: dict, form_type: str,
                         screenshot_path: str = "", headless: bool = False) -> dict:
    """Fill form using Stagehand (delegates to fill_form MCP tool)."""
    try:
        from backend.stagehand_client import stagehand_fill_form
        return await stagehand_fill_form(portal_url, form_data, form_type, screenshot_path, headless)
    except ImportError:
        return {"success": False, "error": "Stagehand not available"}

# ── Browser session management ─────────────────────────────
_sessions: dict[str, dict] = {}
_pages: dict[str, object] = {}
_browsers: dict[str, object] = {}
_contexts: dict[str, object] = {}

_SCREENSHOT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data", "screenshots"
)
os.makedirs(_SCREENSHOT_DIR, exist_ok=True)


async def _get_or_create_page(session_id: str) -> object:
    """Get or create a Playwright page for the session."""
    if session_id in _pages:
        try:
            await _pages[session_id].title()
            return _pages[session_id]
        except Exception:
            pass

    from playwright.async_api import async_playwright

    pw = await async_playwright().start()
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

    _sessions[session_id] = {"pw": pw}
    _browsers[session_id] = browser
    _contexts[session_id] = context
    _pages[session_id] = page

    return page


@mcp.tool()
async def navigate(session_id: str, url: str) -> dict:
    """
    Navigate the browser to a URL.

    Args:
        session_id: Unique session identifier
        url: The URL to navigate to
    """
    try:
        page = await _get_or_create_page(session_id)
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(2000)

        # Auto-dismiss common popups
        for label in ["Accept All Cookies", "Accept", "Close", "ठीक है", "बंद करें"]:
            try:
                btn = page.get_by_text(label, exact=False).first
                if await btn.count() > 0 and await btn.is_visible():
                    await btn.click(timeout=2000)
                    await page.wait_for_timeout(500)
            except Exception:
                pass

        screenshot = await page.screenshot(type="jpeg", quality=60)
        return {
            "success": True,
            "url": url,
            "screenshot_b64": base64.b64encode(screenshot).decode(),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool()
async def fill_field(session_id: str, field_label: str, value: str, timeout: int = 3000) -> dict:
    """
    Fill a single form field on the current page.
    Tries multiple strategies: by label text, placeholder, name attribute.

    Args:
        session_id: Session identifier
        field_label: The visible label text (Hindi or English)
        value: The value to enter
        timeout: Max time to wait for the field in ms
    """
    try:
        page = await _get_or_create_page(session_id)

        strategies = [
            lambda: page.get_by_label(field_label).first,
            lambda: page.get_by_placeholder(field_label).first,
            lambda: page.locator(f"[name='{field_label}']").first,
            lambda: page.locator(f"[id='{field_label}']").first,
            lambda: page.locator(f"input[placeholder*='{field_label}']").first,
            lambda: page.get_by_text(field_label, exact=False).first,
        ]

        filled = False
        for strategy in strategies:
            try:
                locator = strategy()
                if await locator.count() > 0 and await locator.is_visible():
                    await locator.scroll_into_view_if_needed()
                    await locator.click(timeout=min(timeout, 1000))
                    await page.wait_for_timeout(200)
                    await locator.fill("")
                    await page.wait_for_timeout(100)
                    await locator.type(str(value), delay=40)
                    filled = True
                    break
            except Exception:
                continue

        await page.wait_for_timeout(300)
        screenshot = await page.screenshot(type="jpeg", quality=50)

        return {
            "success": filled,
            "field": field_label,
            "value": value,
            "screenshot_b64": base64.b64encode(screenshot).decode(),
        }
    except Exception as e:
        return {"success": False, "error": str(e), "field": field_label}


@mcp.tool()
async def click_button(session_id: str, button_label: str, role: str = "button") -> dict:
    """
    Click a button on the current page by its label.

    Args:
        session_id: Session identifier
        button_label: The button's visible text (e.g. "Submit", "Send OTP")
        role: ARIA role (button, link, etc.)
    """
    try:
        page = await _get_or_create_page(session_id)

        strategies = [
            lambda: page.get_by_role(role, name=button_label).first,
            lambda: page.get_by_text(button_label, exact=True).first,
            lambda: page.locator(f"button:has-text('{button_label}')").first,
            lambda: page.locator(f"input[value='{button_label}']").first,
            lambda: page.locator(f"a:has-text('{button_label}')").first,
        ]

        clicked = False
        for strategy in strategies:
            try:
                btn = strategy()
                if await btn.count() > 0 and await btn.is_visible():
                    await btn.scroll_into_view_if_needed()
                    await btn.click(timeout=3000)
                    clicked = True
                    break
            except Exception:
                continue

        await page.wait_for_timeout(1000)
        screenshot = await page.screenshot(type="jpeg", quality=50)

        return {
            "success": clicked,
            "button": button_label,
            "screenshot_b64": base64.b64encode(screenshot).decode(),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool()
async def take_screenshot(session_id: str, full_page: bool = False) -> dict:
    """
    Take a screenshot of the current page.

    Args:
        session_id: Session identifier
        full_page: Capture entire scrollable page
    """
    try:
        page = await _get_or_create_page(session_id)
        screenshot = await page.screenshot(type="jpeg", quality=70, full_page=full_page)
        return {
            "success": True,
            "screenshot_b64": base64.b64encode(screenshot).decode(),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool()
async def fill_form(session_id: str, form_data: dict, form_type: str = "generic") -> dict:
    """
    Fill an entire form on the current page from a data dict.
    Uses the VLM agent loop for intelligent field detection and filling.

    Args:
        session_id: Session identifier
        form_data: Dict of field_name -> value
        form_type: Type of form for field label matching
    """
    try:
        from backend.agents.form_fill_agent import _playwright_fill
    except ImportError:
        return {"success": False, "error": "form_fill_agent module not available"}

    page = await _get_or_create_page(session_id)
    portal_url = page.url

    result = await _playwright_fill(
        portal_url=portal_url,
        form_data=form_data,
        form_type=form_type,
        language="hi",
        session_id=session_id,
        max_steps=20,
    )

    return {
        "success": result.success,
        "fields_filled": result.fields_filled,
        "otp_detected": result.otp_detected,
        "screenshot_b64": result.screenshot_b64,
        "error": result.error,
        "steps_taken": result.steps_taken,
    }


@mcp.tool()
async def get_page_state(session_id: str) -> dict:
    """
    Get the current page state: URL, title, and page content summary.
    """
    try:
        page = await _get_or_create_page(session_id)
        url = page.url
        title = await page.title()

        # Get all visible input fields
        inputs = await page.locator("input:visible, select:visible, textarea:visible").all()
        fields = []
        for inp in inputs:
            try:
                name = await inp.get_attribute("name")
                field_type = await inp.get_attribute("type")
                placeholder = await inp.get_attribute("placeholder")
                label = name or placeholder or ""
                fields.append({"name": name, "type": field_type, "placeholder": placeholder})
            except Exception:
                pass

        return {
            "success": True,
            "url": url,
            "title": title,
            "visible_fields": fields,
            "field_count": len(fields),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool()
async def detect_otp(session_id: str) -> dict:
    """
    Check if the current page has an OTP/verification field.
    """
    try:
        page = await _get_or_create_page(session_id)
        content = await page.content()
        otp_keywords = ["otp", "verification", "सत्यापन", "कोड", "one-time", "verification code"]
        otp_detected = any(k in content.lower() for k in otp_keywords)

        return {
            "otp_detected": otp_detected,
            "confidence": 0.9 if otp_detected else 0.2,
        }
    except Exception as e:
        return {"otp_detected": False, "confidence": 0.0, "error": str(e)}


@mcp.tool()
async def select_option(session_id: str, field_label: str, option_value: str) -> dict:
    """
    Select an option from a dropdown/select field.

    Args:
        session_id: Session identifier
        field_label: The label of the select field
        option_value: The value to select
    """
    try:
        page = await _get_or_create_page(session_id)
        select = page.get_by_label(field_label).first
        if await select.count() > 0:
            await select.select_option(option_value, timeout=3000)
            return {"success": True, "field": field_label, "value": option_value}

        # Fallback: find by text
        select = page.locator(f"select:has(option:has-text('{option_value}'))").first
        if await select.count() > 0:
            await select.select_option(option_value, timeout=3000)
            return {"success": True, "field": field_label, "value": option_value}

        return {"success": False, "error": "Select field not found"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool()
async def stop_session(session_id: str) -> dict:
    """
    Close the browser session and clean up resources.
    """
    results = []
    try:
        if session_id in _pages:
            _pages.pop(session_id)
            results.append("page_closed")
    except Exception:
        pass
    try:
        if session_id in _contexts:
            ctx = _contexts.pop(session_id)
            await ctx.close()
            results.append("context_closed")
    except Exception:
        pass
    try:
        if session_id in _browsers:
            browser = _browsers.pop(session_id)
            await browser.close()
            results.append("browser_closed")
    except Exception:
        pass
    try:
        if session_id in _sessions:
            pw = _sessions.pop(session_id).get("pw")
            if pw:
                await pw.stop()
            results.append("playwright_stopped")
    except Exception:
        pass

    return {"stopped": True, "actions": results}
