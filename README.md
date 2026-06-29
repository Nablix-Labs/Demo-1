# Nablix — AI Math Tutor (Demo-1)

A working demo of an AI math tutor: the **Numera** web frontend and the **Nablix** API backend, deployed together on Vercel from a single repo.

| | URL |
|---|---|
| **Frontend (the app)** | https://demo-1-hqh6.vercel.app |
| **Backend (the API)** | https://demo-1-phi-amber.vercel.app |
| **API docs (interactive)** | https://demo-1-phi-amber.vercel.app/docs |
| **Health check** | https://demo-1-phi-amber.vercel.app/health |

## What's in here

| Folder | Stack | Role |
|--------|-------|------|
| [`Numera-ui/`](./Numera-ui) | Next.js 14 · TypeScript | The web app a student uses — canvas, voice, hints, tutoring chat. |
| [`nablix-backend/`](./nablix-backend) | FastAPI · Python 3.13 | REST API that owns all tutoring logic. The UI never decides anything itself. |

The two talk over HTTP. The frontend reads the backend URL from `NEXT_PUBLIC_API_BASE_URL`, so each side deploys independently.

```
Student ──> Numera (frontend) ──HTTP──> Nablix (backend API) ──> tutoring logic
            demo-1-hqh6...              demo-1-phi-amber...        (mocked in demo)
```

## How to use it

1. Open the **frontend**: https://demo-1-hqh6.vercel.app
2. Start a session — the app calls `POST /session/start` and keeps the returned `session_id` for the whole run.
3. Interact: type or speak an answer, draw on the canvas, or ask for a hint. Each action is one API call (see the table below).
4. The backend responds with the tutor's next message, and the frontend renders it.

> [!NOTE]
> The backend keeps session state **in memory**. A page reload or a serverless cold start resets it, so grab a fresh session if things stop responding. Fine for a demo, not for sustained use.

## The API the frontend calls

Every frontend action maps to one backend endpoint. All requests/responses are JSON; field names are `snake_case`. No auth in the demo, and a fixed student (`ST001`) is used.

| Method | Endpoint | Triggered by | What it does |
|--------|----------|--------------|--------------|
| `GET`  | `/health` | — | Liveness check. Returns service status JSON. |
| `POST` | `/session/start` | Starting a lesson | Creates a session, returns the first question + UI flags. |
| `GET`  | `/session/{id}` | Resuming / refresh | Reads session metadata and past canvas submissions. |
| `POST` | `/session/end` | Ending a lesson | Closes the session. |
| `POST` | `/interaction` | Submitting an answer | **Core tutoring call** — evaluates input, returns the next message. |
| `POST` | `/hint/request` | Tapping "Hint" | Returns the next hint level for the current question. |
| `POST` | `/canvas/submit` | Submitting drawn work | OCRs the canvas snapshot, then tutors on it. *The only call that hits a live AI provider.* |
| `POST` | `/voice/session/start` | Enabling voice | Marks the session voice-active (mock token). |
| `POST` | `/voice/transcript` | Finishing a voice turn | Routes a spoken turn through `/interaction`. |

> The full request/response shapes live in the typed client at [`Numera-ui/lib/api.ts`](./Numera-ui/lib/api.ts) — it's the single source of truth for the contract.

## Viewing the backend

The backend is an API, not a page — opening its root URL returns a `Not Found` JSON by design. To actually see it, use these:

### Interactive docs — `/docs`
https://demo-1-phi-amber.vercel.app/docs

FastAPI's Swagger UI: every endpoint listed with its schema. Expand any route, hit **Try it out**, fill the JSON, and **Execute** to call the live backend straight from the browser.

### Health — `/health`
https://demo-1-phi-amber.vercel.app/health

A quick "is it up?" check. If this returns JSON, the backend is alive.

### Live logs — watch interactions as they happen
Every request is logged with a `request_id` by the backend's logging middleware. To watch them stream in real time:

1. Open the **backend project** in the Vercel dashboard → **Logs** (Runtime Logs).
2. Keep it open, then use the frontend in another tab.
3. Each click in the app appears as a log line here — method, path, and `request_id` — so you can follow a session end to end. The same `request_id` shows up in any error JSON the frontend receives, so you can match a UI error to its log line.

## Run locally

Backend on port 8000:

```bash
cd nablix-backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
NABLIX_USE_MOCK_VISION=true python -m uvicorn app.main:app --reload --port 8000
```

Frontend on port 3000 (point it at the local backend):

```bash
cd Numera-ui
npm install
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000 npm run dev
```

Open `http://127.0.0.1:3000`. Local docs live at `http://127.0.0.1:8000/docs`.

## Deploy

Both apps run on Vercel as **two projects from this one repo**:

- **Backend** — Root Directory `nablix-backend`, served as a Python function via [`nablix-backend/api/index.py`](./nablix-backend/api/index.py) + [`vercel.json`](./nablix-backend/vercel.json). Env: `NABLIX_USE_MOCK_VISION=true`, `NABLIX_CORS_ALLOWED_ORIGINS=["<frontend-url>"]`.
- **Frontend** — Root Directory `Numera-ui` (Next.js auto-detected). Env: `NEXT_PUBLIC_API_BASE_URL=<backend-url>`.

Set the backend's CORS origin to the frontend URL, then redeploy the backend so the browser isn't blocked.
