# Demo-1

The first working demo draft with the Numera frontend and Nablix backend in one repo.

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

The frontend is deployed with GitHub Pages from `Numera-ui/`.

Deploy the backend on Koyeb from `nablix-backend/Dockerfile`, then set this
GitHub repository variable before rerunning the Pages workflow:

```text
NEXT_PUBLIC_API_BASE_URL=https://<your-koyeb-backend>.koyeb.app
```
