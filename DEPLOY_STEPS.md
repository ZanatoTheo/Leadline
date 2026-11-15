# Steps to go live (Railway service + Vercel frontend)

All commands run from `~/Projects/junction-26`.

## 1. Fix GitHub access (the 403 error)
1. On GitHub, go to **Settings → Developer settings → Personal access tokens**.
2. Create a token with write access to `ZanatoTheo/leadline`. For a fine-grained token, set **Contents: Read and write**.
3. Push the branch, and paste the token when asked for a password:
   ```
   git push -u origin leadline-service-demo
   ```

## 2. Make a shared secret
```
openssl rand -hex 32
```
Save the output. Both Railway and Vercel need it.

## 3. Deploy the service on Railway
1. Go to railway.com → **New Project → Deploy from GitHub repo** → pick `leadline`, branch **`leadline-service-demo`**.
2. **Settings → Volumes**: add a volume with mount path **`/data`**.
3. **Variables**: add these.
   - `LEADLINE_SERVICE_TOKEN` = the secret from step 2
   - `VERDA_API_KEY`, `VERDA_BASE_URL`, `VENUS_NEMOTRON_MODEL` (copy from `venus/.env`)
   - `ANTHROPIC_API_KEY`, and `VENUS_FALLBACK_PROVIDER` = `anthropic`
   - `VENUS_MAX_TOKENS` = `16384`
   - `CONTEXT_DEV_API_KEY`
   - Optional, and it spends Cala credits: `CALA_API_KEY`, and `LEADLINE_LIVE_CALA` = `1`
4. **Settings → Replicas**: keep it at **1**. The DB is a single file.
5. **Settings → Networking → Generate Domain**, and copy the address.
6. Check it from your terminal:
   ```
   curl https://<railway-domain>/healthz                                         # {"ok":true}
   curl https://<railway-domain>/status                                          # 401 is good
   curl -H "authorization: Bearer <secret>" https://<railway-domain>/status       # 200
   ```

## 4. Deploy the frontend on Vercel
1. Go to vercel.com → **Add New → Project** → import `leadline`.
2. **Root Directory** → **Edit** → `frontend`.
3. **Environment Variables**, for Production:
   - `LEADLINE_SERVICE_URL` = `https://<railway-domain>` (no slash at the end)
   - `LEADLINE_SERVICE_TOKEN` = the same secret
   - `LEADLINE_DEMO_LOGIN` = `true`
4. Point Vercel at the right branch: in **Settings → Git → Production Branch**, set **`leadline-service-demo`**. Leave `main` as it is; it has the team's version, which conflicts with this one.
5. Click **Deploy**.

## 5. Check the live site
1. Open the Vercel URL → **Log in** → click the **founder** demo button.
2. **Today** should show Bidra and Ada, and **Who to pitch** should show the agent's reasons.
3. Log out, click the **investor** demo button, and check that **Deal flow** shows 2 founders under Discover and Carbonlens under Matches.
4. If a page says **"Leadline is not reachable"**:
   - Check that `LEADLINE_SERVICE_URL` has no trailing slash.
   - Check that the token is the same on both sides.
   - After changing a Vercel variable, click **Redeploy**.

## Good to know
- **Your team's Vercel project:** if Vercel already deploys `main` for your team, use a **new Vercel project** for this one, so you don't replace their live site.
- **Saving a profile spends money:** Verda or Claude calls, and Cala calls if live Cala is on. Just viewing pages spends nothing.
- **Keys go only in Railway and Vercel.** They're never in the repo.
