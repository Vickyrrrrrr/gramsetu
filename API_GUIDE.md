# GramSetu API Guide (v3)

This guide documents the endpoints currently implemented in `whatsapp_bot/main.py`.

Base URL:

`http://localhost:8000`

## Health and Root

### `GET /api/health`

Returns service health and runtime mode.

### `GET /`

Returns landing page (`index.html`) if present.

## Message Processing

### `POST /api/chat`

Test chat endpoint (non-Twilio).

Request:

```json
{
  "message": "I want ration card",
  "user_id": "test-user",
  "phone": "9999999999",
  "form_type": ""
}
```

Response:

```json
{
  "success": true,
  "response": "...",
  "status": "wait_confirm",
  "session_id": "...",
  "current_node": "confirm",
  "language": "hi",
  "form_type": "ration_card",
  "form_data": {},
  "confidence_scores": {},
  "missing_fields": []
}
```

### `POST /webhook`

Twilio WhatsApp webhook endpoint.

- Validates Twilio signature if `TWILIO_AUTH_TOKEN` is configured
- Handles text and voice media
- Detects OTP when graph is in `WAIT_OTP`

## Graph Resume / OTP

### `POST /api/otp/{user_id}`

Resume a suspended graph with OTP (v3 mode only).

Request:

```json
{
  "otp": "483921"
}
```

## Schemes, Voice, and Status

### `POST /api/schemes`

Eligibility discovery endpoint.

Request:

```json
{
  "age": 65,
  "gender": "male",
  "income": 80000,
  "occupation": "farmer",
  "language": "hi"
}
```

### `POST /api/tts`

Generate TTS audio for a text response.

Request:

```json
{
  "text": "Your form is ready",
  "language": "hi"
}
```

### `POST /api/status`

Demo application-status response endpoint.

Request:

```json
{
  "user_id": "test-user",
  "form_type": "ration_card",
  "language": "hi"
}
```

## Dashboard / Admin Data

### `GET /api/logs?limit=100`

Recent audit logs.

### `GET /api/conversations?limit=50`

Recent conversations.

### `GET /api/submissions`

All submissions.

### `GET /api/submissions/pending`

Pending review submissions.

### `POST /api/confirm/{submission_id}`

Confirm a submission.

Request body is optional:

```json
{
  "notes": "Verified by admin"
}
```

### `POST /api/reject/{submission_id}`

Reject a submission.

### `GET /api/stats`

Aggregated dashboard stats.

### `GET /api/impact`

Runtime impact counters.

### `GET /api/graph/state/{user_id}`

Debug state snapshot for active session.

## DigiLocker Callback

### `GET /callback/digilocker`

OAuth callback page used by DigiLocker flow.

## Environment Variables

Core:

- `USE_V3_GRAPH` (`true`/`false`)
- `PORT`

NVIDIA:

- `NVIDIA_API_KEY`
- `NVIDIA_BASE_URL`
- `NVIDIA_MODEL`

Twilio:

- `TWILIO_ACCOUNT_SID`
- `TWILIO_AUTH_TOKEN`

Security:

- `PII_ENCRYPTION_KEY` (optional; generated at runtime if missing)

## Notes

- v3 graph is the default mode.
- Legacy v2 pipeline remains in the codebase for compatibility fallback.
- MCP servers live in `backend/mcp_servers/` and can be run separately as needed.

