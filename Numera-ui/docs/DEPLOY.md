# Deploying the frontend to the VM

**Read this before deploying.** A build made without the env vars below still
compiles, still deploys, and still loads — it just silently runs the whole app
in mock mode, showing demo content like `2x + 5 = 13` and never calling the
backend. That has already happened twice (2026-07-28).

## The command

Run from `Demo-1/Numera-ui`:

```bash
rm -rf .next out

EXPORT_BASE_PATH=/app \
NEXT_PUBLIC_API_BASE_URL=/api \
NEXT_PUBLIC_ALLOW_ANON_TUTOR=true \
NEXT_PUBLIC_VOICE_TRANSPORT=server \
NEXT_PUBLIC_WS_URL=wss://nablix.ai/api/voice/stream \
npm run build

tar czf - -C out . | ssh -i <key>.pem developer@74.162.34.219 \
  'tar xzf - -C /var/www/numera/app'
```

Live at **https://nablix.ai/app/** (not the bare IP — the port-80 block returns
404 by design).

## Why each var matters

| Var | If missing |
|---|---|
| `NEXT_PUBLIC_API_BASE_URL=/api` | **The app runs entirely on mock data.** No backend calls at all. This is the one that bites. |
| `EXPORT_BASE_PATH=/app` | Assets 404 — the app is served from a subpath. |
| `NEXT_PUBLIC_VOICE_TRANSPORT=server` | Falls back to browser STT; console warns `NEXT_PUBLIC_VOICE_TRANSPORT is unset`. |
| `NEXT_PUBLIC_WS_URL` | No streaming voice. |
| `NEXT_PUBLIC_ALLOW_ANON_TUTOR=true` | Students without a real login can't call the tutor at all. |

`NEXT_PUBLIC_*` are inlined at **build** time. Setting them on the VM does
nothing — only a rebuild changes them.

## Two checks before you trust a deploy

**1. Confirm the env actually got inlined.**
```bash
grep -rl '"/api"' out/_next/static/chunks/*.js | head -1   # must print a chunk
```

**2. Confirm your change is in the built output**, not just in the source — a
build can report success while serving stale chunks:
```bash
grep -rl "<some string from your change>" out/_next/static/chunks/
```

Then load the site and check `performance.getEntriesByType('resource')` contains
`/api/` calls. If the page shows `2x + 5 = 13`, the build was made without
`NEXT_PUBLIC_API_BASE_URL`.

## Note for whoever else deploys

`tar xzf` overwrites but never deletes, so a deploy replaces `index.html` and the
chunks it references. Whoever deploys last wins — including replacing a good
build with a mock-mode one. If you deploy the frontend, use the command above
verbatim.
