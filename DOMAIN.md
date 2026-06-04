# Token-Tracker production domain plan

Recommended professional URL:

- Marketing + dashboard: `https://token-tracker.dev`
- Optional API/proxy hostname: `https://api.token-tracker.dev/v1`
- Optional www redirect: `https://www.token-tracker.dev` → `https://token-tracker.dev`

If `token-tracker.dev` is unavailable, use one of these:

1. `trytoken-tracker.com`
2. `token-trackerai.com`
3. `gettoken-tracker.com`
4. `token-tracker.dev` with a different TLD like `.app` or `.io`

## DNS records

Point these to the production host:

```txt
A      @      <server-ip>
A      www    <server-ip>
A      api    <server-ip>
```

If using Cloudflare Tunnel instead of a public VM IP, use CNAME records to the tunnel target.

## Production env

Start from `deploy/production.env.example`:

```bash
cp deploy/production.env.example .env
```

Set:

- `OPENAI_API_KEY` — provider key used by the Token-Tracker proxy
- `TOKENWATCH_ADMIN_KEY` — long random secret for control-plane/dashboard access
- `TOKENWATCH_DEMO_MODE=true` — public read-only portfolio demo
- `TOKENWATCH_DEMO_MODE=false` — private production dashboard
- `CORS_ALLOWED_ORIGINS` — comma-separated production origins, e.g. `https://token-tracker.dev,https://api.token-tracker.dev`
- `DATABASE_URL` — use the Docker volume path from the example or a managed database for durable production data

Check the deploy posture before exposing the service:

```bash
tokenwatch preflight
```

## Run with Docker

```bash
docker compose up -d --build
docker compose logs -f tokenwatch
```

The included compose file mounts a persistent `tokenwatch-data` volume at `/app/data` and defaults SQLite to `/app/data/tokenwatch.db` via `TOKENWATCH_DOCKER_DATABASE_URL`. This keeps local `.env` dev settings from accidentally overriding container persistence.

## Nginx + HTTPS

Use `deploy/token-tracker.example.conf` as the reverse proxy template.

Basic certbot flow on Ubuntu/Debian:

```bash
sudo apt-get update
sudo apt-get install -y nginx certbot python3-certbot-nginx
sudo cp deploy/token-tracker.example.conf /etc/nginx/sites-available/token-tracker
sudo ln -s /etc/nginx/sites-available/token-tracker /etc/nginx/sites-enabled/token-tracker
sudo nginx -t
sudo certbot --nginx -d token-tracker.dev -d www.token-tracker.dev -d api.token-tracker.dev
```

After DNS + HTTPS:

- Landing page: `https://token-tracker.dev/`
- Dashboard: `https://token-tracker.dev/dashboard`
- Setup: `https://token-tracker.dev/setup`
- API docs: `https://token-tracker.dev/docs`
- Proxy base URL: `https://api.token-tracker.dev/v1` or `https://token-tracker.dev/v1`
