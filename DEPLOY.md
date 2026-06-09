# Deploying brackets.win

Production layout:

- **Frontend** — static files at `https://brackets.win` (e.g. Cloudflare Pages).
- **API + media** — Django on Fly (`brackets-win`), reached at `https://brackets.win/brackets/…` via a reverse proxy (not the bare `*.fly.dev` URL in the browser).

Session cookies require the SPA and API to share the same site origin. The frontend calls `/brackets/api` on `brackets.win`, not `brackets-win.fly.dev`.

## One-time Fly setup

```bash
cd backend

# App (if not created yet)
fly apps list

# Postgres (if not created yet)
# fly postgres create --name brackets-win-db
# fly postgres attach brackets-win-db -a brackets-win

# Persistent uploads (run once per region)
fly volumes create media_data --region iad --size 3 -a brackets-win

# Secrets
fly secrets set SECRET_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')" -a brackets-win
fly secrets set DB_PASSWORD="…" -a brackets-win   # if not already set via postgres attach
```

## Reverse proxy (Cloudflare recommended)

On `brackets.win`, proxy these paths to `https://brackets-win.fly.dev`:

| Path | Target |
|------|--------|
| `/brackets/*` | `https://brackets-win.fly.dev/brackets/*` |
| `/media/*` | `https://brackets-win.fly.dev/media/*` |

Cloudflare: **Rules** → **Origin Rules** or **Workers** / **Transform Rules** depending on your plan. Ensure cookies pass through (do not strip `Cookie` / `Set-Cookie`).

SPA fallback: all other paths serve the Vite `index.html` (Cloudflare Pages `_redirects` handles this).

## Deploy backend (GitHub Actions)

1. Repo secret: `FLY_ACCESS_TOKEN` (Fly deploy token).
2. Push to `master` with changes under `backend/` — workflow `.github/workflows/deploy-backend.yaml` runs tests, then `flyctl deploy`.

Manual:

```bash
cd backend
flyctl deploy
```

Migrations run via `release_command` in `fly.toml` before each deploy.

## Deploy frontend (GitHub Actions)

1. Cloudflare Pages project named `brackets-win`.
2. Repo secrets (**Settings → Secrets and variables → Actions**):
   - `CLOUDFLARE_API_TOKEN` — Cloudflare dashboard → **My Profile → API Tokens** → Create token with **Account → Cloudflare Pages → Edit** (scoped to your account).
   - `CLOUDFLARE_ACCOUNT_ID` — Cloudflare dashboard → any site → **Overview** → Account ID in the right sidebar.
3. Push to `master` with changes under `frontend/` — `.github/workflows/deploy-frontend.yaml` builds and deploys `frontend/dist`.

Manual:

```bash
npm ci --prefix frontend
npm run build --prefix frontend
# Upload frontend/dist to your static host
```

## Seed production catalog

From local dev (after you have the catalog you want):

```bash
cd backend
poetry run python manage.py export_dev_seed --copy-media
```

Copy `backend/seed/dev_catalog.json` and `backend/seed/media/` to a machine with Fly access, then:

```bash
fly ssh console -a brackets-win
# inside the VM, or run locally with production DATABASE_URL / VPN:
python manage.py import_dev_seed --copy-media --flush-catalog
```

Or bootstrap built-ins only:

```bash
fly ssh console -a brackets-win -C "python manage.py seed_catalog"
```

## Post-deploy smoke test

1. Open `https://brackets.win` — create account, sign in, sign out.
2. Create / join a bracket challenge; submit picks.
3. Create / join a streak challenge; make a pick.
4. Upload a streak competition image in admin; confirm it loads after a redeploy (volume mounted).
5. `fly logs -a brackets-win` — no 500s on `/brackets/api/auth/me`.

## Troubleshooting

| Symptom | Likely cause |
|---------|----------------|
| Login works locally, not prod | API still on `fly.dev` in browser; fix proxy + relative `/brackets/api`. |
| 500 on most API calls | Migrations not applied — `fly ssh console -C "python manage.py migrate"`. |
| Uploaded images 404 | Volume not mounted, or `/media` not proxied to Fly. |
| Cold start delay | Set `min_machines_running = 1` in `fly.toml` (costs more). |
