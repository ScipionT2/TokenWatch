# Deploy Token-Tracker to Google Cloud Run

Cloud Run is the fastest low-maintenance way to put Token-Tracker live for a portfolio/demo. It handles HTTPS, autoscaling, logs, and restarts without managing a VM.

## 1. Create production env

```bash
cp deploy/production.env.example .env.production
```

Edit the values:

```env
OPENAI_API_KEY=sk-...
TOKENWATCH_ADMIN_KEY=<long-random-secret>
TOKENWATCH_DEMO_MODE=true
TOKENWATCH_SEED_DEMO=true
CORS_ALLOWED_ORIGINS=https://token-tracker.dev,https://www.token-tracker.dev,https://api.token-tracker.dev
DATABASE_URL=sqlite+aiosqlite:////app/data/tokenwatch.db
```

For a public portfolio demo, keep `TOKENWATCH_DEMO_MODE=true`. For a private dashboard, set it to `false`.

Run a local readiness check:

```bash
tokenwatch preflight
```

## 2. Build and deploy

Replace the project/region if needed:

```bash
PROJECT_ID="project-bbb9e0cc-b0f2-478c-afa"
REGION="us-central1"
SERVICE="tokenwatch"

gcloud config set project "$PROJECT_ID"
gcloud builds submit --tag "gcr.io/$PROJECT_ID/$SERVICE"
gcloud run deploy "$SERVICE" \
  --image "gcr.io/$PROJECT_ID/$SERVICE" \
  --region "$REGION" \
  --platform managed \
  --allow-unauthenticated \
  --port 8000 \
  --memory 512Mi \
  --cpu 1 \
  --min-instances 0 \
  --max-instances 2 \
  --set-env-vars "HOST=0.0.0.0,PORT=8000,LOG_LEVEL=info,TOKENWATCH_DEMO_MODE=true,TOKENWATCH_SEED_DEMO=true,CORS_ALLOWED_ORIGINS=https://token-tracker.dev\\,https://www.token-tracker.dev\\,https://api.token-tracker.dev,BUDGET_MODE=observe" \
  --set-secrets "OPENAI_API_KEY=tokenwatch-openai-key:latest,TOKENWATCH_ADMIN_KEY=tokenwatch-admin-key:latest"
```

Notes:

- Prefer Secret Manager for `OPENAI_API_KEY` and `TOKENWATCH_ADMIN_KEY`.
- Cloud Run filesystem is ephemeral. For a serious production instance, use Cloud SQL/Postgres or another persistent database instead of SQLite. For a portfolio demo with seeded data, ephemeral SQLite is acceptable.

## 3. Map domains

```bash
gcloud run domain-mappings create --service tokenwatch --domain token-tracker.dev --region us-central1
gcloud run domain-mappings create --service tokenwatch --domain api.token-tracker.dev --region us-central1
```

Then create the DNS records shown by `gcloud run domain-mappings describe` in Cloudflare/registrar DNS.

## 4. Verify

```bash
curl -fsS https://token-tracker.dev/api/v1/health
curl -fsS -H "X-Token-Tracker-Admin-Key: $TOKENWATCH_ADMIN_KEY" https://token-tracker.dev/api/v1/preflight
```

Open:

- `https://token-tracker.dev/`
- `https://token-tracker.dev/dashboard`
- `https://token-tracker.dev/setup`
- `https://api.token-tracker.dev/v1`
