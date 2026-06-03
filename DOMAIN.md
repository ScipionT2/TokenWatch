# TokenWatch production domain plan

Recommended professional URL:

- Marketing + dashboard: `https://tokenwatch.dev`
- Optional API/proxy hostname: `https://api.tokenwatch.dev/v1`
- Optional www redirect: `https://www.tokenwatch.dev` → `https://tokenwatch.dev`

If `tokenwatch.dev` is unavailable, use one of these:

1. `trytokenwatch.com`
2. `tokenwatchai.com`
3. `gettokenwatch.com`
4. `tokenwatch.dev` with a different TLD like `.app` or `.io`

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

- `OPENAI_API_KEY` — provider key used by the TokenWatch proxy
- `TOKENWATCH_ADMIN_KEY` — long random secret for control-plane/dashboard access
- `TOKENWATCH_DEMO_MODE=true` — public read-only portfolio demo
- `TOKENWATCH_DEMO_MODE=false` — private production dashboard

## Run with Docker

```bash
docker compose up -d --build
docker compose logs -f tokenwatch
```

## Nginx + HTTPS

Use `deploy/tokenwatch.example.conf` as the reverse proxy template.

Basic certbot flow on Ubuntu/Debian:

```bash
sudo apt-get update
sudo apt-get install -y nginx certbot python3-certbot-nginx
sudo cp deploy/tokenwatch.example.conf /etc/nginx/sites-available/tokenwatch
sudo ln -s /etc/nginx/sites-available/tokenwatch /etc/nginx/sites-enabled/tokenwatch
sudo nginx -t
sudo certbot --nginx -d tokenwatch.dev -d www.tokenwatch.dev -d api.tokenwatch.dev
```

After DNS + HTTPS:

- Landing page: `https://tokenwatch.dev/`
- Dashboard: `https://tokenwatch.dev/dashboard`
- Setup: `https://tokenwatch.dev/setup`
- API docs: `https://tokenwatch.dev/docs`
- Proxy base URL: `https://api.tokenwatch.dev/v1` or `https://tokenwatch.dev/v1`
