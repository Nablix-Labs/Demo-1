# Demo 2 staging: frontend and nginx (Manav's work packages)

Rollout roadmap of 26 Sep 2026, Gate 2. This covers the frontend build and the
nginx routes only. Backend, voice, database and Student Model isolation are
owned by Chirudeva, Aditya and Saravanan.

## Routing decision

Paths on the existing `nablix.ai` HTTPS server, as the roadmap proposes. No new
DNS record or certificate is needed.

| Path | Goes to | Status (28 Sep) |
|---|---|---|
| `/demo2/` | static export in `/var/www/numera/demo2` | uploaded, not routed |
| `/demo2-api/` | Demo 2 backend `127.0.0.1:8011` | backend healthy, not routed |
| `/demo2-voice` | Demo 2 voice `127.0.0.1:8014/voice/stream` | **no process on 8014 yet** (Aditya) |
| `/demo2-auth/` | Demo 2 auth / Student Model | **no isolated endpoint yet** (Saravanan) |

The frontend is built against these four paths and nothing else, so it never
calls a Demo 1 path directly. Where `/demo2-auth/` points is an nginx
decision, which means switching to the isolated auth later needs no rebuild.

## Build

From `Numera-ui/`:

```bash
rm -rf .next out
EXPORT_BASE_PATH=/demo2 \
NEXT_PUBLIC_API_BASE_URL=/demo2-api \
NEXT_PUBLIC_AUTH_BASE_URL=/demo2-auth \
NEXT_PUBLIC_ALLOW_ANON_TUTOR=true \
NEXT_PUBLIC_VOICE_TRANSPORT=server \
NEXT_PUBLIC_VOICE_WS_URL=wss://nablix.ai/demo2-voice \
npm run build

COPYFILE_DISABLE=1 tar czf - --no-xattrs -C out . | ssh -i ~/Downloads/Nablix-Dev-Ubu_key.pem \
  developer@74.162.34.219 'mkdir -p /var/www/numera/demo2 && tar xzf - -C /var/www/numera/demo2'
```

Checks run on the built output (28 Sep, commit ba15f47, build `D8DotBkt74AoQWlDHsgV7`):

- every script tag is under `/demo2/_next`;
- the bundle contains `/demo2-api`, `/demo2-auth` and `wss://nablix.ai/demo2-voice`;
- no `/api/` call and no `wss://nablix.ai/api/voice` URL. The only `"/api"`
  string is Next.js's router internals.

The frontend source needed no change for a second base path: every backend
URL comes from these env vars, and raw assets already go through `basePath`.

## nginx

Add inside the `listen 443 ssl` server block in
`/etc/nginx/sites-available/fastapi`, next to the existing `/app/` block.
Take a backup of the file before editing.

```nginx
    # ── Demo 2 staging (rollout roadmap, Gate 2) ──────────────────────────
    location = /demo2 { return 301 /demo2/; }
    location /demo2/ {
        root /var/www/numera;
        index index.html;
        try_files $uri $uri/ /demo2/index.html;
    }

    location /demo2-api/ {
        proxy_pass http://127.0.0.1:8011/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 3600;
        proxy_connect_timeout 300;
        proxy_send_timeout 3600;
    }

    # Exact match: the client connects to wss://nablix.ai/demo2-voice?session=...
    location = /demo2-voice {
        proxy_pass http://127.0.0.1:8014/voice/stream;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_read_timeout 86400;
    }

    # Auth: DECISION PENDING. Until Saravanan provides an isolated endpoint,
    # this refuses rather than silently logging Demo 2 users into production.
    location /demo2-auth/ {
        return 503 '{"error":"DEMO2_AUTH_NOT_ISOLATED"}';
        default_type application/json;
    }
```

Then:

```bash
sudo nginx -t && sudo systemctl reload nginx
# Demo 1 must be unchanged:
curl -sS -o /dev/null -w '%{http_code}\n' https://nablix.ai/app/        # 200
curl -sS -o /dev/null -w '%{http_code}\n' https://nablix.ai/api/docs    # 200
# Demo 2:
curl -sS -o /dev/null -w '%{http_code}\n' https://nablix.ai/demo2/      # 200
curl -sS https://nablix.ai/demo2-api/health                             # 200 from 8011
```

Rollback: restore the backup of `sites-available/fastapi`, then
`sudo nginx -t && sudo systemctl reload nginx`. The static directory can stay;
nothing reaches it without the route.

## Still open before staging traffic

1. **Auth.** Point `/demo2-auth/` at the isolated Demo 2 auth when it exists.
   Pointing it at production `https://nablix.ai:8080/` would work today but
   would authenticate Demo 2 users against production learner identities.
   The roadmap says not to do that.
2. **Voice.** `/demo2-voice` returns 502 until a Demo 2 voice process listens on
   `127.0.0.1:8014` with `NABLIX_MAIN_BACKEND_URL` pointing at 8011.
3. **Browser checks**, once 1 and 2 exist: direct entry and refresh of nested
   routes (e.g. `/demo2/workbook/`), login, session start, canvas, voice
   connection, and a clean console.
