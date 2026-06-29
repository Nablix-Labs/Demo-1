# Numera — AI Math Tutor

Frontend for the Numera AI Math Tutor by Nablix. Built by **Manav Arya Singh**.

## Tech Stack

| Layer | Technology |
|---|---|
| Framework | Next.js 14 + TypeScript (App Router) |
| UI / Styling | shadcn/ui + Tailwind CSS |
| State | Zustand |
| Math Rendering | KaTeX |
| Canvas | react-konva |
| Voice / Realtime | Native WebSocket API |
| HTTP / REST | Axios |
| Testing | Playwright + Axe DevTools |

## Getting Started

```bash
npm install
cp .env.local.example .env.local  # add your API URLs
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

## Project Structure

```
numera/
├── app/                  # Next.js App Router
│   ├── layout.tsx        # Root layout + global CSS
│   └── page.tsx          # Main session page
├── components/
│   ├── ToolRail.tsx      # Far-left dark nav rail
│   ├── MediaPanel/       # Tutor tile, voice bar, transcript
│   ├── SlideDots.tsx     # Vertical slide navigation
│   └── Canvas/           # Drawing stage + toolbar + bar model
├── store/
│   └── useNumeraStore.ts # Zustand global state
├── hooks/
│   └── useWebSocket.ts   # Voice WebSocket hook
└── lib/
    ├── api.ts            # Axios REST client
    └── cn.ts             # Tailwind class merge utility
```

## Architecture Notes

- **Frontend = display + interaction only.** All tutoring logic, session state, and content decisions are backend-controlled.
- Canvas data lives in-memory only — never `localStorage`.
- "Check My Work" exports a PNG snapshot via `konva.Stage.toDataURL()` and POSTs it to `/interaction`.
- Voice streaming uses a plain `WebSocket` to `wss://{env}/voice`.
- All REST calls go through the Axios client in `lib/api.ts` with token injection.

## Environment Variables

See `.env.local.example`.

---

*Nablix · Confidential · Numera v0.1*
