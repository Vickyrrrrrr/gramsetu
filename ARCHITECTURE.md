# GramSetu Architecture Guide

This document explains the project in plain language.

If you only want the short version:

- The web app on port 3000 is the frontend.
- The FastAPI app on port 8000 is the real backend brain.
- The LangGraph flow inside the backend decides what step comes next.
- The MCP servers are helper services that the backend starts automatically.
- The folder name `whatsapp_bot` is historical. Today it contains the main backend server, not a separate always-running WhatsApp-only app.
- In demo mode, some parts are real and some parts are mocked.

## 1. What This Project Is

GramSetu is an AI assistant for government form filling.

The idea is:

1. A user says something like `I want ration card`.
2. The system identifies the form.
3. It fetches user data.
4. It shows the extracted data for confirmation.
5. It fills the portal automatically.
6. It asks for OTP.
7. It submits the application and gives a receipt.

That is the business idea.

## 2. The Most Important Thing To Understand

There are two different views of this project:

1. What the project does today in your local demo.
2. What the project is designed to do in a real production scenario.

Those are not exactly the same.

## 3. Demo Mode vs Real Mode

### Demo Mode: what happens today

Today, when you run the project locally, the main path is:

```text
Browser -> Next.js web app -> FastAPI backend -> LangGraph -> mock DigiLocker data -> real Playwright on mock portal
```

What is real in demo mode:

- The web app is real.
- The FastAPI backend is real.
- The LangGraph orchestration is real.
- The step-by-step conversation state is real.
- The Playwright browser automation is real.
- The screenshot streaming is real.
- The OTP pause/resume behavior is real.
- The receipt generation is real.

What is mocked or simplified in demo mode:

- DigiLocker data is mock data unless real OAuth is wired.
- The government portal is a mock HTML portal served locally.
- The photo verification step is currently a UX step, not a real face-matching system.
- Real WhatsApp webhook delivery is not the primary active path in the current backend file.

### Real Mode: what the full product should do

In the real scenario, the target path is:

```text
WhatsApp user -> Twilio or Meta webhook -> FastAPI backend -> LangGraph -> real DigiLocker OAuth -> real government portal -> OTP -> submitted application
```

In real mode:

- User starts from WhatsApp instead of the web app.
- Identity/document data comes from real DigiLocker APIs.
- The system talks to real government portals, not the local mock portal.
- OTP goes to the user's real phone number.
- The final receipt corresponds to a real submission.

## 4. High-Level System Diagram

```text
                           +-----------------------+
                           |   Next.js Web App     |
                           |   port 3000           |
                           +-----------+-----------+
                                       |
                                       | /api/* and /ws/* proxy
                                       v
 +--------------------+     +-----------------------+     +----------------------+
 |  Optional WhatsApp | --> | FastAPI Backend       | --> | LangGraph Flow       |
 |  Channel           |     | whatsapp_bot/main.py  |     | backend/agents       |
 |  Twilio or Meta    |     | port 8000             |     |                      |
 +--------------------+     +-----------+-----------+     +----------+-----------+
                                         |                            |
                                         | auto-starts                |
                                         v                            v
                             +-----------------------+     +----------------------+
                             | MCP helper servers    |     | Playwright browser   |
                             | 8100 to 8103          |     | automation           |
                             +-----------------------+     +----------------------+
```

## 5. Main Folders and What They Mean

### `webapp/`

This is the Next.js frontend.

What it does:

- Shows the chat UI.
- Sends user messages to `/api/chat`.
- Shows screenshots and receipt buttons.
- Connects to WebSocket preview for live browser frames.

This is what you see in the browser at `http://localhost:3000`.

### `whatsapp_bot/`

This name is confusing, so here is the correct interpretation:

- It is not a separate permanently independent service in the current setup.
- It is the Python package that contains the main FastAPI backend server.
- The file `whatsapp_bot/main.py` is the actual backend app you run.

So when you start the backend, you are really starting:

```text
whatsapp_bot/main.py
```

Why is it called `whatsapp_bot` then?

- Because the project originally centered around WhatsApp interaction.
- The package name stayed, even though the backend now also powers the web app, TTS, screenshots, receipts, scheme discovery, and status APIs.

### `backend/agents/`

This is the orchestration brain.

Key files:

- `graph.py`: the LangGraph workflow.
- `schema.py`: state structure and graph status values.

### `backend/mcp_servers/`

These are helper servers started by the backend.

They are not the main app. They are support services.

### `dashboard/`

Optional Streamlit dashboard for admin/inspection use.

### `data/`

Local runtime storage.

Important contents:

- `data/checkpoints.db`: LangGraph checkpoint database.
- `data/screenshots/`: browser screenshots.
- `data/voice_cache/`: temporary voice files.

## 6. What LangGraph Is Doing Here

If you are new, think of LangGraph as a workflow engine for conversations.

Normal code often does this:

```text
message in -> function runs once -> result out
```

LangGraph instead does this:

```text
message in -> step 1 -> pause -> user reply -> step 2 -> pause -> user reply -> step 3
```

That is why it fits this project.

Form filling is not one answer. It is a multi-step process.

### The main graph states

The graph uses statuses like:

- `active`: keep running to the next node
- `wait_user`: stop and wait for a general reply
- `wait_confirm`: stop and wait for user confirmation
- `wait_otp`: stop and wait for OTP
- `completed`: flow finished
- `error`: something failed

### The current flow in this project

Today the graph behaves like this:

1. Detect form intent.
2. Stop and ask for photo verification step.
3. Continue to DigiLocker fetch.
4. Show extracted data summary.
5. Wait for `YES` or corrections.
6. Fill the portal with Playwright.
7. Show screenshot and ask for OTP.
8. Resume after OTP.
9. Generate receipt.

### Why checkpoints matter

When the graph pauses, it saves state in `data/checkpoints.db`.

That means the system can remember:

- which form the user selected
- what data was extracted
- whether the user is at confirmation stage
- whether the system is waiting for OTP

Without checkpoints, OTP flows would break easily.

## 7. The Actual Runtime Flow in Demo Mode

When you type in the web app, this is what happens:

```text
1. User types in browser.
2. Next.js page sends POST /api/chat.
3. FastAPI endpoint in whatsapp_bot/main.py receives it.
4. Backend calls process_message() in backend/agents/graph.py.
5. LangGraph loads or creates session state.
6. Graph runs until it reaches a wait state or completion.
7. Backend returns response JSON.
8. Web app shows the assistant message.
9. If there is a screenshot, the UI shows it.
10. If the flow is completed, the UI shows a receipt button.
```

## 8. The Current Step-by-Step Behavior

If the user types `ration card`, the current intended flow is:

### Step 1 of 4: identity verification

The graph detects the form and asks for a selfie or `continue`.

Important truth:

- Right now this is mostly a guided step in the conversation.
- It is not yet a real biometric face verification pipeline.

### Step 2 of 4: data verification

The system gets form data and shows a summary.

Today:

- The extraction is real as a flow.
- The data source is still demo/mock unless real DigiLocker integration is completed.

### Step 3 of 4: portal fill

The system launches Playwright and fills fields.

Today:

- This is real browser automation.
- But it fills the local mock portal for the demo path.

### Step 4 of 4: completion

After OTP, the system marks the submission completed and generates a receipt.

## 9. Demo vs Real, Subsystem by Subsystem

| Part | Demo today | Real target |
|---|---|---|
| User channel | Web app on port 3000 | WhatsApp plus web app |
| Backend | FastAPI on port 8000 | Same FastAPI backend |
| Conversation engine | LangGraph | Same LangGraph |
| Photo verification | Prompt only | Real verification service or vision pipeline |
| DigiLocker | Mock data | Real OAuth + document fetch |
| Portal | Local mock portal | Real government portals |
| Browser automation | Real Playwright | Real Playwright or stronger browser tooling |
| OTP | Real pause/resume logic, demo submission | Real pause/resume with real submission |
| Receipt | Real local receipt HTML | Real production receipt or acknowledgment |

## 10. What Each Server Does

### Server 1: Next.js web app, port 3000

Purpose:

- visual interface for the user
- chat window
- screenshot modal
- receipt button

It does not contain the main business logic.

It mostly forwards requests to the backend.

### Server 2: FastAPI backend, port 8000

This is the most important server.

It does all of this:

- receives web app requests
- manages sessions
- runs the LangGraph flow
- generates receipts
- serves screenshots
- exposes health and status endpoints
- auto-starts MCP helper servers

This is the real center of the system.

### Server 3 to 6: MCP helper servers, ports 8100 to 8103

These are started inside the backend process as daemon threads.

That means:

- you usually do not start them manually anymore
- when the backend starts, they try to start too

#### WhatsApp MCP, port 8100

Purpose:

- helper layer for WhatsApp-related tooling
- future integration point for real messaging operations

#### Browser MCP, port 8101

Purpose:

- helper layer for browser-related actions
- useful if you want tool-based browser automation outside the main graph

#### Audit MCP, port 8102

Purpose:

- audit trail and observability support
- useful for logging and admin views

#### DigiLocker MCP, port 8103

Purpose:

- helper layer for DigiLocker flows
- today can provide demo data
- in real mode should handle real document fetch and related tooling

### Optional dashboard server

If you run Streamlit, that becomes an extra UI for monitoring.

## 11. Important Clarification About the WhatsApp Path

You asked why there is a separate `whatsapp_bot` if there is also a web app.

The answer is:

- `whatsapp_bot` is the backend package name.
- The current active demo path is web app to backend.
- The original product vision was WhatsApp-first.
- So the naming stayed even though the backend now serves much more than WhatsApp.

In other words:

```text
webapp is the frontend
whatsapp_bot/main.py is the backend server
```

They are connected directly.

## 12. APIs You Actually Use Today

These are the important backend endpoints in the current codebase.

| Method | Endpoint | What it does |
|---|---|---|
| POST | `/api/chat` | main chat entry for the web app |
| POST | `/api/voice` | speech upload to text |
| POST | `/api/otp/{user_id}` | resumes flow after OTP |
| POST | `/api/schemes` | scheme discovery |
| POST | `/api/tts` | text to speech |
| POST | `/api/status` | simple application status response |
| GET | `/api/impact` | counters and usage info |
| GET | `/api/health` | health check |
| GET | `/api/mcp-status` | tells you if MCP servers are up |
| GET | `/api/receipt/{session_id}` | printable receipt HTML |
| GET | `/api/screenshot/{form_type}/{session_id}` | screenshot image |
| GET | `/api/audit-logs` | audit data |
| GET | `/callback/digilocker` | DigiLocker OAuth callback endpoint |
| WS | `/ws/browser/{session_id}` | live browser preview |

## 13. What Happens When You Start the Project

### If you run `start_demo.ps1`

This script opens two windows:

1. backend window
2. webapp window

The backend window runs `uvicorn whatsapp_bot.main:app`.

When backend startup happens, this is the order:

1. `.env` is loaded.
2. database is initialized.
3. FastAPI app starts on port 8000.
4. static files are mounted.
5. MCP helper servers are started in background threads.
6. API endpoints become available.

The web app window runs `npm run dev` and serves the UI on port 3000.

### If you run `start.ps1`

This is the more flexible script.

Examples:

- `./start.ps1`: backend only
- `./start.ps1 -Webapp`: backend plus web app
- `./start.ps1 -All`: backend plus everything optional
- `./start.ps1 -Prod`: backend without hot reload

Important current behavior:

- MCP servers are auto-started by backend startup.
- `-MCP` no longer needs to launch separate processes.

## 14. Why So Many Processes Can Feel Confusing

This project mixes several layers:

- frontend UI
- backend API
- graph orchestration
- browser automation
- optional MCP helpers
- optional dashboard

So if you just look at ports and windows, it can feel random.

The correct mental model is simpler:

```text
User UI -> FastAPI backend -> LangGraph -> helpers -> browser automation -> response back to UI
```

Everything else is support around that path.

## 15. The Single Best Way To Think About The Structure

If you remember only one thing, remember this:

- The web app is just the screen.
- FastAPI is the server.
- LangGraph is the step controller.
- Playwright is the hands that fill the form.
- DigiLocker is the data source.
- MCP servers are helper workers.

## 16. What Is Still Not Fully Real Yet

To avoid confusion, here is the honest list of what still needs real-world completion:

1. Real WhatsApp webhook path needs to be the active production entry path.
2. Photo verification needs real matching logic if that is a hard product requirement.
3. DigiLocker needs full real OAuth plus document fetch.
4. Real government portals need stable automation beyond the mock portal path.
5. Production deployment needs public hosting, secrets, monitoring, and failure handling.

## 17. Practical Mental Model For You

When you are debugging, ask these questions in this order:

1. Is the web app loading on port 3000?
2. Is the backend healthy on port 8000?
3. Is `/api/chat` returning responses?
4. Is LangGraph moving through the expected statuses?
5. Is Playwright opening and filling?
6. Is the screenshot or receipt reaching the UI?
7. Are MCP helper servers up if that part matters?

That order will save you a lot of confusion.

## 18. Recommended Reading Order

If you want to understand the code slowly, read in this order:

1. `webapp/app/app/page.tsx`
2. `whatsapp_bot/main.py`
3. `backend/agents/schema.py`
4. `backend/agents/graph.py`
5. `backend/mcp_servers/`
6. `DIGILOCKER_INTEGRATION.md`

That goes from easiest mental model to deepest implementation details.
