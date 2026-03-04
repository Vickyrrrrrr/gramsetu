"""
============================================================
stagehand_client.py — AI Browser Automation via Stagehand
============================================================
Wraps Stagehand SDK for GramSetu's form-filling pipeline.
Uses Groq API as the LLM backend for natural-language browser actions.

Key functions:
  - stagehand_fill_form()    — Fill a government portal using AI actions
  - stagehand_observe_page() — Get structured page state
  - stagehand_detect_otp()   — Check if OTP field is present

Falls back gracefully if Stagehand errors → caller uses legacy Playwright.
"""

import os
import base64
import asyncio
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

# ── Config ───────────────────────────────────────────────────
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
STAGEHAND_MODEL = os.getenv("STAGEHAND_MODEL", "groq/llama-3.3-70b-versatile")
USE_STAGEHAND = os.getenv("USE_STAGEHAND", "false").lower() in ("true", "1", "yes")


def is_stagehand_enabled() -> bool:
    """Check if Stagehand is enabled AND the Groq API key is available."""
    return USE_STAGEHAND and bool(GROQ_API_KEY) and GROQ_API_KEY != "gsk_your-key-here"


# ── Field label mapping for natural-language actions ─────────
# Maps GramSetu internal field names → human-readable labels
# that Stagehand's LLM can locate on any portal
_FIELD_LABELS = {
    "applicant_name":  "Full Name / Applicant Name",
    "full_name":       "Full Name / Applicant Name",
    "name":            "Full Name / Applicant Name",
    "date_of_birth":   "Date of Birth",
    "dob":             "Date of Birth",
    "gender":          "Gender",
    "aadhaar_number":  "Aadhaar Number",
    "aadhaar":         "Aadhaar Number",
    "mobile_number":   "Mobile Number",
    "mobile":          "Mobile Number",
    "email":           "Email Address",
    "house_number":    "House Number / Door Number",
    "village":         "Village / Town / Ward",
    "post_office":     "Post Office",
    "district":        "District",
    "state":           "State",
    "pin_code":        "PIN Code",
    "family_members":  "Number of Family Members",
    "annual_income":   "Annual Income",
    "category":        "Category (BPL/APL/AAY)",
    "account_number":  "Bank Account Number",
    "ifsc":            "IFSC Code",
    "ifsc_code":       "IFSC Code",
    "bank_name":       "Bank Name",
    "occupation":      "Occupation",
    "father_name":     "Father's Name",
    "relation":        "Relation",
}


async def stagehand_fill_form(
    portal_url: str,
    form_data: dict,
    form_type: str,
    screenshot_path: str = "",
    headless: bool = False,
) -> dict:
    """
    Fill a government portal form using Stagehand AI actions.

    Args:
        portal_url:      URL to navigate to (mock or real portal)
        form_data:       Dict of field_name -> value from DigiLocker
        form_type:       Type of form (ration_card, pension, etc.)
        screenshot_path: Path to save final screenshot
        headless:        Run browser in headless mode

    Returns:
        {
            "success": bool,
            "fields_filled": int,
            "screenshot_b64": str,
            "otp_detected": bool,
            "error": str or None,
        }
    """
    from stagehand import Stagehand, StagehandConfig

    result = {
        "success": False,
        "fields_filled": 0,
        "screenshot_b64": "",
        "otp_detected": False,
        "error": None,
    }

    try:
        config = StagehandConfig(
            env="LOCAL",
            model_name=STAGEHAND_MODEL,
            headless=headless,
            verbose=0,
        )

        # Set GROQ_API_KEY in environment for Stagehand's LLM calls
        os.environ["GROQ_API_KEY"] = GROQ_API_KEY

        async with Stagehand(config=config) as stagehand:
            page = stagehand.page

            # ── Navigate to portal ──────────────────────────────
            print(f"[Stagehand] 🚀 Navigating to {portal_url}")
            await page.goto(portal_url)
            await asyncio.sleep(1.5)  # Let portal JS settle

            # ── Fill each field using natural language ──────────
            fields_filled = 0
            total_fields = sum(1 for v in form_data.values() if v and not isinstance(v, dict))

            for field_name, field_value in form_data.items():
                if not field_value:
                    continue

                # Skip nested dicts (address sub-objects) — handle separately
                if isinstance(field_value, dict):
                    for sub_key, sub_val in field_value.items():
                        if sub_val:
                            label = _FIELD_LABELS.get(sub_key, sub_key.replace("_", " ").title())
                            try:
                                await page.act(
                                    f"Find the {label} field and enter '{sub_val}'"
                                )
                                fields_filled += 1
                                print(f"[Stagehand]   ✅ {label}: {sub_val}")
                            except Exception as e:
                                print(f"[Stagehand]   ⚠️ {label}: {e}")
                    continue

                label = _FIELD_LABELS.get(field_name, field_name.replace("_", " ").title())

                try:
                    await page.act(
                        f"Find the {label} field and enter '{field_value}'"
                    )
                    fields_filled += 1
                    print(f"[Stagehand]   ✅ {label}: {field_value}")
                except Exception as e:
                    print(f"[Stagehand]   ⚠️ {label}: {e}")

            # ── Check the declaration checkbox ──────────────────
            try:
                await page.act("Check the declaration checkbox to agree to the terms")
                print("[Stagehand]   ✅ Declaration checked")
            except Exception:
                print("[Stagehand]   ⚠️ Declaration checkbox not found or already checked")

            # ── Click the Send OTP / Submit button ──────────────
            try:
                await page.act("Click the 'Send OTP' or 'Submit' button to proceed")
                print("[Stagehand]   ✅ Send OTP clicked")
            except Exception:
                print("[Stagehand]   ⚠️ Submit/OTP button not found")

            await asyncio.sleep(1)

            # ── Detect OTP field ────────────────────────────────
            try:
                otp_observations = await page.observe(
                    "Is there an OTP input field visible on the page? "
                    "Look for fields labeled OTP, verification code, or similar."
                )
                otp_detected = bool(otp_observations)
                result["otp_detected"] = otp_detected
                if otp_detected:
                    print("[Stagehand]   🔐 OTP field detected — graph will suspend")
            except Exception:
                result["otp_detected"] = True  # Assume OTP needed on govt portals

            # ── Take final screenshot ───────────────────────────
            try:
                # Use the underlying Playwright page for screenshot
                pw_page = page._page if hasattr(page, '_page') else page
                ss_bytes = await pw_page.screenshot(type="png")
                result["screenshot_b64"] = base64.b64encode(ss_bytes).decode()

                if screenshot_path:
                    with open(screenshot_path, "wb") as f:
                        f.write(ss_bytes)
                    print(f"[Stagehand]   📸 Screenshot saved: {screenshot_path}")
            except Exception as e:
                print(f"[Stagehand]   ⚠️ Screenshot failed: {e}")

            result["success"] = True
            result["fields_filled"] = fields_filled
            print(f"[Stagehand] ✅ Done — {fields_filled}/{total_fields} fields filled for {form_type}")

    except ImportError as e:
        result["error"] = f"Stagehand not installed: {e}"
        print(f"[Stagehand] ❌ Import error: {e}")
    except Exception as e:
        result["error"] = str(e)
        print(f"[Stagehand] ❌ Error: {e}")

    return result


async def stagehand_observe_page(page) -> dict:
    """
    Get structured page state for the dashboard.

    Returns dict with current_step, visible_fields, errors, progress.
    """
    try:
        observations = await page.observe(
            "What form fields are visible on this page? "
            "List the labels and current values of each visible field."
        )
        return {
            "observations": observations,
            "status": "observed",
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


async def stagehand_detect_otp(page) -> dict:
    """
    Check if the current page has an OTP verification field.

    Returns dict with is_otp_page, confidence.
    """
    try:
        observations = await page.observe(
            "Is there an OTP or verification code input field? "
            "Look for: OTP, one-time password, verification code, कोड, सत्यापन."
        )
        is_otp = bool(observations)
        return {
            "is_otp_page": is_otp,
            "confidence": 0.9 if is_otp else 0.2,
        }
    except Exception as e:
        return {"is_otp_page": False, "confidence": 0.0, "error": str(e)}
