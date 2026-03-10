# DigiLocker Integration Guide

This document explains how GramSetu uses DigiLocker today (mock), and exactly what to change when you get the real DigiLocker API credentials.

---

## Current State (Mock)

Everything works end-to-end right now, but with **demo data** instead of real documents.

When a user starts a form fill, the flow is:
1. Agent asks the user for their name / phone / form type
2. `digilocker_fetch_node` in `backend/agents/graph.py` calls the DigiLocker MCP server
3. `backend/mcp_servers/digilocker_mcp.py` returns **hardcoded demo data** (Aadhaar name, DOB, address, etc.)
4. The form is pre-filled with that demo data and sent for user confirmation

The mock data lives in `_get_demo_data()` in `backend/mcp_servers/digilocker_mcp.py`.

---

## Getting Real DigiLocker API Access

1. Register your app at **https://partners.digitallocker.gov.in**
2. Submit the following for approval:
   - App name, description
   - Redirect URI: `https://your-domain.com/callback/digilocker`
   - Documents you need: Aadhaar, PAN, driving licence, etc.
3. After approval you get:
   - `DIGILOCKER_CLIENT_ID`
   - `DIGILOCKER_CLIENT_SECRET`
4. Add both to your `.env` file.

---

## What the Real OAuth Flow Looks Like

```
User says "apply for ration card"
  → GramSetu builds an OAuth URL:
    https://api.digitallocker.gov.in/public/oauth2/1/authorize
      ?response_type=code
      &client_id=YOUR_CLIENT_ID
      &redirect_uri=https://your-domain.com/callback/digilocker
      &state=<session_id>
      &scope=aadhaar+pan+driving_licence

  → User clicks the link, logs in to DigiLocker with Aadhaar OTP
  → DigiLocker redirects back to:
    https://your-domain.com/callback/digilocker?code=AUTH_CODE&state=SESSION_ID

  → Your server exchanges code for access_token (POST to DigiLocker token endpoint)
  → Fetches documents using the access_token
  → Pre-fills the form
```

---

## Code Changes Required

### 1. `backend/mcp_servers/digilocker_mcp.py`

This is the only file you need to change. It has two clearly marked sections:

**Step A — Generate the OAuth URL (already scaffolded):**

Find the `initiate_digilocker_auth` tool. Replace `_get_demo_data()` with real OAuth URL generation:

```python
# Current mock (line ~60):
return {"auth_url": f"https://example.com/mock-digilocker?state={state_id}", "state": state_id}

# Replace with:
import urllib.parse
params = {
    "response_type": "code",
    "client_id":     os.getenv("DIGILOCKER_CLIENT_ID"),
    "redirect_uri":  os.getenv("DIGILOCKER_REDIRECT_URI", "https://your-domain.com/callback/digilocker"),
    "state":         state_id,
    "scope":         "aadhaar driving_licence pan_card",
}
auth_url = "https://api.digitallocker.gov.in/public/oauth2/1/authorize?" + urllib.parse.urlencode(params)
return {"auth_url": auth_url, "state": state_id}
```

**Step B — Exchange auth code for token (in `whatsapp_bot/main.py`, the callback endpoint):**

```python
# In /callback/digilocker, find the TODO comment and add:
async with httpx.AsyncClient() as client:
    token_resp = await client.post(
        "https://api.digitallocker.gov.in/public/oauth2/1/token",
        data={
            "grant_type":    "authorization_code",
            "code":          code,
            "redirect_uri":  os.getenv("DIGILOCKER_REDIRECT_URI"),
            "client_id":     os.getenv("DIGILOCKER_CLIENT_ID"),
            "client_secret": os.getenv("DIGILOCKER_CLIENT_SECRET"),
        },
    )
    token_data = token_resp.json()
    access_token = token_data["access_token"]
    session["access_token"] = access_token
```

**Step C — Fetch real documents (in `digilocker_mcp.py`, the `fetch_documents` tool):**

```python
# Replace _get_demo_data() call with real API fetch:
async with httpx.AsyncClient(headers={"Authorization": f"Bearer {access_token}"}) as client:
    # Aadhaar eKYC
    aadhaar_resp = await client.get(
        "https://api.digitallocker.gov.in/public/oauth2/1/xml/eaadhaar"
    )
    # Parse XML and extract: name, dob, gender, address, aadhaar_number
    ...

    # PAN Card
    pan_resp = await client.get(
        "https://api.digitallocker.gov.in/public/oauth2/1/xml/INCOME_TAX_DEPARTMENT_PAN_CARD"
    )
    # Parse and extract: pan_number, name, dob
    ...
```

### 2. `.env` file

Add these three lines:

```
DIGILOCKER_CLIENT_ID=your_client_id_here
DIGILOCKER_CLIENT_SECRET=your_client_secret_here
DIGILOCKER_REDIRECT_URI=https://your-domain.com/callback/digilocker
```

### 3. Nothing else needs to change

The rest of the pipeline — `graph.py`, `main.py`, the web app — already handles real DigiLocker data. The integration is isolated to `digilocker_mcp.py`.

---

## Data DigiLocker Returns (and how it maps to forms)

| DigiLocker Field | Forms That Use It |
|------------------|------------------|
| `name`           | All forms |
| `dob`            | Aadhaar, PAN, pension, ration card |
| `gender`         | Aadhaar, voter ID, Ayushman Bharat |
| `address`        | Ration card, voter ID, pension |
| `aadhaar_number` | All forms (as primary ID) |
| `pan_number`     | PAN-linked schemes (PM-KISAN, income tax) |
| `photo_base64`   | Identity forms, voter ID |

The mapping logic is in `_map_to_form_fields()` in `digilocker_mcp.py`. It already handles all supported form types.

---

## Testing Without DigiLocker Credentials

The mock works for all demos. To test the OAuth redirect flow locally without approval:

1. Use DigiLocker's **sandbox environment**: `https://sandbox.digitallocker.gov.in`
2. Use test Aadhaar number: `999999990019`
3. Set `DIGILOCKER_BASE_URL=https://sandbox.digitallocker.gov.in` in `.env`

Sandbox credentials are available at: https://partners.digitallocker.gov.in/sandbox

---

## Security Notes

- Access tokens expire in 1 hour — store them only in the in-memory session (`_auth_sessions` dict), never in SQLite
- Never log the access token or auth code
- The `PII_ENCRYPTION_KEY` in `.env` already encrypts form data at rest — DigiLocker data flows through the same path
