# Demo-1

The first working demo draft with the Numera frontend and Nablix backend in one repo.

**Live:** frontend → https://demo-1-hqh6.vercel.app · backend → https://demo-1-phi-amber.vercel.app

| Folder | Stack | What it is |
|--------|-------|------------|
| [`nablix-backend/`](./nablix-backend) | FastAPI (Python 3.13) | REST API for sessions, tutoring, hints, canvas, and mocks. |
| [`Numera-ui/`](./Numera-ui) | Next.js 14 (TypeScript) | Web frontend for the tutor experience. |

The two apps are connected over HTTP. The UI reads the backend URL from env vars,
so the frontend and backend can still deploy independently.

## Run locally

Backend on port 8000:

```bash
cd nablix-backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
NABLIX_USE_MOCK_VISION=true python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Frontend on port 3000:

```bash
cd Numera-ui
npm install
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000 npm run dev -- --hostname 127.0.0.1 --port 3000
```

Open `http://127.0.0.1:3000`.

## Deploy

Both apps run on Vercel as two projects from this one repo.

**Backend** — new Vercel project, Root Directory `nablix-backend`. Served as a
Python serverless function via `nablix-backend/api/index.py` + `vercel.json`.
Env vars:

```text
NABLIX_USE_MOCK_VISION=true
NABLIX_CORS_ALLOWED_ORIGINS=["https://demo-1-hqh6.vercel.app"]
```

**Frontend** — new Vercel project, Root Directory `Numera-ui` (Next.js
auto-detected). Env var pointing at the backend:

```text
NEXT_PUBLIC_API_BASE_URL=https://demo-1-phi-amber.vercel.app
```

> Note: the backend keeps session state in memory, so sessions can drop on a
> serverless cold start — fine for the demo, not for sustained load.
