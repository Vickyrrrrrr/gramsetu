# GramSetu — WhatsApp Live Testing Guide

## Your ngrok URL (active now)
```
https://exultingly-subchorionic-chante.ngrok-free.dev
```

## Step 1 — Set the Twilio Webhook (2 minutes)

1. Open: **https://console.twilio.com**
2. Left sidebar → **Messaging** → **Try it out** → **Send a WhatsApp Message**
3. Click the **Sandbox Settings** tab
4. In the field **"WHEN A MESSAGE COMES IN"**, paste:
   ```
   https://exultingly-subchorionic-chante.ngrok-free.dev/webhook
   ```
5. Set method to **HTTP POST**
6. Click **Save**

## Step 2 — Connect YOUR WhatsApp to the Sandbox

1. Open WhatsApp on your phone
2. Send a message to: **+1 415 523 8886** (Twilio sandbox number)
3. Message body: **join [your-sandbox-word]**
   - Find your sandbox word in: Twilio Console → Messaging → WhatsApp → Sandbox Settings
   - It looks like "join [word]-[word]" e.g. `join red-apple`
4. You'll get a confirmation: "You are now connected to the sandbox"

## Step 3 — Test the Bot

Send any of these to **+1 415 523 8886**:

| Message | What happens |
|---|---|
| `मुझे राशन कार्ड चाहिए` | Intent detected → form summary auto-filled from DigiLocker |
| `I want to apply for pension` | Pension form auto-filled |
| `ration card` or `1` | Same as Hindi ration card |
| `YES` | Confirms form → triggers portal fill → asks for OTP |
| Any 6-digit number | Submits OTP → form completed ✅ |
| `0` or `reset` | Start over |

## Step 4 — What the Demo Shows

```
User: मुझे राशन कार्ड चाहिए
Bot:  📋 Your Form Summary (from DigiLocker)
        🟢 Name: Ram Kumar Sharma (DigiLocker)
        🟢 Aadhaar: XXXX-XXXX-9087 (DigiLocker)
        🟢 DOB: 1985-03-15 (DigiLocker)
        🟡 Family members: 4 (estimated — can correct)
        🟡 Income: ₹1,20,000 (estimated)
      Confidence: 74%
      Reply YES to submit | Send corrections like "income 80000"

User: YES
Bot:  🌐 Filling form on portal...
        📍 https://nfsa.gov.in/
        📝 10 fields entered (from DigiLocker)
      🔐 OTP required — send the 6-digit code

User: 123456
Bot:  ✅ OTP Submitted!
        Your form has been submitted successfully.
        You'll receive a confirmation SMS.
```

## DigiLocker API — Hackathon vs Production

### Right now (Hackathon Demo)
- ✅ 100% working — uses **realistic demo data** automatically
- ✅ No DigiLocker account needed
- ✅ Shows real name (Ram Kumar Sharma), real Aadhaar format, real address
- ✅ PII masked (XXXX-XXXX-9087 format)
- ✅ Confidence scores shown per field (🟢🟡🔴)
- **Judges see the full agent flow working end-to-end**

### For Production (Post-Hackathon)
1. Apply at: **https://developers.digilocker.gov.in**
2. Fill "Application for API Access" form
3. Approval takes **4–8 weeks** (government process)
4. Once approved → add to `.env`:
   ```
   DIGILOCKER_CLIENT_ID=your_client_id
   DIGILOCKER_CLIENT_SECRET=your_secret
   DIGILOCKER_REDIRECT_URI=https://your-domain.com/callback/digilocker
   ```
5. Everything else stays the same — the code already handles real DigiLocker OAuth

## Test Chat (No WhatsApp Needed)

```bash
# Test via REST API directly:
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "I want a ration card", "user_id": "test", "phone": "9999999999"}'
```

Or open: **http://localhost:8000/docs** → `/api/chat` → Try it out

## Dashboard
```bash
# Start Streamlit dashboard (separate terminal):
.venv\Scripts\streamlit run dashboard\app.py
# Open: http://localhost:8501
```

## Common Issues

| Issue | Fix |
|---|---|
| "Invalid Twilio signature" | TWILIO_AUTH_TOKEN not set in .env (auto-skipped in dev) |
| Bot not responding on WhatsApp | Check ngrok tunnel, verify webhook URL in Twilio Console |
| ngrok URL expired | Restart: `ngrok http 8000 --pooling-enabled` |
| "No module found" error | Run: `pip install -r requirements.txt` |
