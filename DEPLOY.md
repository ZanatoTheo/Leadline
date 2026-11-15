# Deploy Leadline

Two parts: the Python service on **Railway** (API + SQLite database + agent worker) and the Next.js frontend on
**Vercel**. Vercel deploys production from `main`, so land the work there first.

## Step 0: push and merge

```bash
git push origin leadline-service-demo
git checkout main && git merge leadline-service-demo && git push origin main
```

Generate a shared secret and keep it handy:

```bash
openssl rand -hex 32
```

## Step 1: Python service on Railway (do this first)

1. On railway.com, go to **New Project → Deploy from GitHub repo** and pick this repo. Railpack detects Python
   from the root `requirements.txt` (which also installs `./venus`) and starts it with `scripts/start_service.sh` (set in `railway.json`). The
   exported agent is committed at `leadline/agent/`, so no build step is needed.
2. Under **Settings → Volumes**, add a volume with mount path `/data`.
3. Under **Variables**, add:
   - `LEADLINE_SERVICE_TOKEN` = the secret from step 0
   - `VERDA_API_KEY`, `VERDA_BASE_URL`, `VENUS_NEMOTRON_MODEL`
   - `ANTHROPIC_API_KEY`, `VENUS_FALLBACK_PROVIDER=anthropic`
   - `VENUS_MAX_TOKENS=16384` (without it Verda replies get cut off at 8192 tokens)
   - Optional: `CALA_API_KEY` + `LEADLINE_LIVE_CALA=1` for live Cala in profile builds (spends credits)
   - `CONTEXT_DEV_API_KEY`
4. Under **Settings → Networking**, click **Generate Domain**.
5. Check it:

   ```bash
   curl https://<service-domain>/healthz   # → {"ok":true}
   curl https://<service-domain>/status    # → 401 (good: the token is required)
   curl -H "authorization: Bearer <secret>" https://<service-domain>/status   # → 200
   ```

## Step 2: Frontend on Vercel

1. On vercel.com, go to **Add New → Project** and import the repo.
2. Next to **Root Directory**, click **Edit** and choose `frontend`. Next.js is detected automatically.
3. Under **Environment Variables**, add these (tick Production, plus Preview if you want preview deploys to
   work):
   - `LEADLINE_SERVICE_URL` = `https://<service-domain>` (no trailing slash)
   - `LEADLINE_SERVICE_TOKEN` = the same secret
   - `LEADLINE_DEMO_LOGIN` = `true` (optional; turns on the one-click demo logins)
4. Click **Deploy**.

## Step 3: Check the live site

Open the Vercel URL, log in (or use a demo login) and confirm `/today` loads. If a page says "Leadline is not
reachable", check the URL and the token on both sides. Changes to Vercel variables only apply after you redeploy.

## Keep in mind

- **Replicas:** run one Railway replica only, because the database is a single SQLite file on the volume.
- **First start:** the database is copied from the seed file in the repo (`leadline/data/leadline.db`), which
  includes 14 old failed agent jobs.
- **Re-exporting the agent:** `scripts/inject_agent.sh` re-applies the Leadline fallback patch itself
  (`scripts/patch_agent_fallback.py`: `model_bad_reply` and `output_invalid` in `FALLBACK_CODES`). Commit the
  result — the exported agent is tracked in git so Railway builds need no export step.
- **Local dev is unchanged:** no token set → no auth, service on 127.0.0.1:8765.
