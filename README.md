# Nablix

AI math tutor — monorepo containing the backend API and the web UI.

| Folder | Stack | What it is |
|--------|-------|------------|
| [`nablix-backend/`](./nablix-backend) | FastAPI (Python 3.13) | REST + WebSocket API. See its README. |
| [`Numera-ui/`](./Numera-ui) | Next.js 14 (TypeScript) | Web frontend. See its README. |

The two are wired only over HTTP — the UI reads the backend URL from env vars,
so they deploy independently.

## Run locally

**Backend** (port 8000):
```bash
cd nablix-backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # fill in API keys
uvicorn app.main:app --reload --port 8000
```

**Frontend** (port 3000):
```bash
cd Numera-ui
npm install
cp .env.local.example .env.local   # point NEXT_PUBLIC_API_BASE_URL at the backend
npm run dev
```

The UI's `NEXT_PUBLIC_API_BASE_URL` / `NEXT_PUBLIC_WS_URL` must point at the
running backend (local: `http://127.0.0.1:8000`).
