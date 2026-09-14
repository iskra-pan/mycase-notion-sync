# MyCase ↔ Notion Sync

Two-way sync between a Notion case-tracking database and MyCase matters:
- New Notion page → creates a MyCase matter, writes the Matter ID back.
- Edits on either side → pushed to the other, per a per-field source-of-truth
  rule (see `app/field_mapping.py`).
- New Notion database columns → auto-creates a matching MyCase custom field.

Sync runs on a schedule (Cloud Scheduler polling, every few minutes) rather
than live webhooks - simpler and more robust than standing up two
different providers' webhook-verification handshakes, and a few minutes of
latency is a non-issue for case management. See **Status** below for what's
tested vs. what still needs a verification pass against real MyCase docs.

## Why deploy before finishing the app?

MyCase's OAuth redirect URI **"can only be set and updated by MyCase
support."** That means if you give them a temporary/local URL now and
switch to a real one later, you're filing another support ticket to change
it. So instead: deploy this skeleton to Cloud Run first (5 minutes), get
its permanent URL, and give MyCase that URL once. Everything else (the
real sync logic) gets added later and redeployed to the *same* service, so
the URL never changes again.

## What "redirect URI" to give MyCase

Once deployed (steps below) your Cloud Run service gets a permanent URL
like:

```
https://mycase-notion-sync-abc123-uc.a.run.app
```

The exact value to put in MyCase's onboarding form (their question #1) is
that URL plus this app's callback path:

```
https://mycase-notion-sync-abc123-uc.a.run.app/auth/mycase/callback
```

For their question #2 (write access to all resources): you already said
yes, which is required anyway since you need to *create* matters in
MyCase, not just read them.

---

## 1. Run it locally first (optional but recommended)

```bash
cd mycaseNotionSync
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
copy .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(32))"   # paste into INTERNAL_TASK_SECRET
uvicorn main:app --reload --port 8080
```

Visit `http://localhost:8080/health` — should return `{"status": "ok"}`.
You can't fully test the MyCase login flow yet (no client_id/secret until
they approve the form), but this confirms the app runs.

## 2. Deploy to Cloud Run

Prerequisites: a Google Cloud project with billing enabled, and the
[gcloud CLI](https://cloud.google.com/sdk/docs/install) installed and
authenticated (`gcloud init`).

```bash
# One-time setup
gcloud config set project YOUR_PROJECT_ID
gcloud services enable run.googleapis.com cloudbuild.googleapis.com firestore.googleapis.com

# Create the Firestore database (Native mode) that will hold the OAuth tokens
gcloud firestore databases create --location=us-central1

# Deploy straight from source - Cloud Build containerizes it for you using the Dockerfile
gcloud run deploy mycase-notion-sync \
  --source . \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars GCP_PROJECT_ID=YOUR_PROJECT_ID
```

`--allow-unauthenticated` is required here: MyCase's servers (not you)
call the `/auth/mycase/callback` URL, so it must be publicly reachable.

At the end of the deploy, gcloud prints a **Service URL** — that's your
permanent base URL. Copy it.

### Set the real secrets

You don't yet have `MYCASE_CLIENT_ID`/`MYCASE_CLIENT_SECRET` (MyCase gives
you those after approving the form). Once you have them:

```bash
gcloud run services update mycase-notion-sync \
  --region us-central1 \
  --set-env-vars MYCASE_CLIENT_ID=xxx,MYCASE_REDIRECT_URI=https://<your-service-url>/auth/mycase/callback \
  --set-secrets MYCASE_CLIENT_SECRET=mycase-client-secret:latest,INTERNAL_TASK_SECRET=internal-task-secret:latest
```

(That assumes you stored the secret values in Secret Manager first —
`gcloud secrets create mycase-client-secret --data-file=-` etc. Plain
`--set-env-vars` also works if you'd rather keep it simple for now; move
the client secret to Secret Manager before this goes to production.)

**Important:** `MYCASE_REDIRECT_URI` must be *character-for-character*
identical to whatever URL you give MyCase support. Trailing slash
mismatches are a common cause of "redirect_uri_mismatch" errors.

## 3. What to send back to MyCase

Reply to their onboarding email with:

1. Redirect URI: `https://<your-service-url>/auth/mycase/callback`
2. Yes, write access to all resources.

## 4. Once MyCase approves and gives you client_id/secret

1. Set them on the Cloud Run service (command above).
2. Visit `https://<your-service-url>/auth/mycase/login` **while logged in
   to MyCase as the firm's account** — this is a one-time manual step an
   admin does in a browser, not something the app does itself.
3. You'll be redirected to MyCase to approve access, then back to
   `/auth/mycase/callback`, which should show "MyCase connected
   successfully."
4. Check `https://<your-service-url>/auth/mycase/status` to confirm
   (`{"connected": true, ...}`).

## 5. Keep the connection alive (important)

MyCase access tokens last 24 hours; refresh tokens last **2 weeks**. If
nothing refreshes the token for 2 weeks straight, the connection dies and
step 4 has to be repeated manually. Set up a Cloud Scheduler job to hit
the refresh endpoint twice a day:

```bash
gcloud scheduler jobs create http mycase-token-refresh \
  --location us-central1 \
  --schedule "0 */12 * * *" \
  --uri "https://<your-service-url>/auth/mycase/internal/refresh" \
  --http-method POST \
  --headers "X-Task-Secret=<same value as INTERNAL_TASK_SECRET>"
```

## 6. Set up the Notion side

For a single firm's own workspace, use a Notion **internal integration** -
no OAuth needed:

1. In Notion: Settings → Connections → "Develop or manage integrations" →
   New integration. Copy its secret token.
2. Open your case-tracking database → "..." menu → Connections → add the
   integration (this is the "Share with integration" step).
3. Add one new column to the database: **`MyCase Matter ID`**, type Text.
   This is where the app writes the matter ID/link back after creating it.
4. Copy the database ID out of its URL:
   `notion.so/<workspace>/<DATABASE_ID>?v=...`
5. Set `NOTION_TOKEN` and `NOTION_DATABASE_ID` on the Cloud Run service
   (same `--set-env-vars` / `--set-secrets` pattern as step 2 above).

## 7. Edit the field mapping to match your database

Open [app/field_mapping.py](app/field_mapping.py) - `STANDARD_FIELDS` for
built-in matter attributes (client name, matter type, attorney, etc.),
`CUSTOM_FIELDS` for everything else (email, dates, contact info). Each row
names the exact Notion column, the matching MyCase field, its type, and
which system wins on conflict. Rename the placeholder rows to match your
actual Notion database columns, then redeploy
(`gcloud run deploy mycase-notion-sync --source .`).

## 8. Turn on the sync schedule

Three Cloud Scheduler jobs, same shared-secret pattern as the token
refresh job in step 5:

```bash
gcloud scheduler jobs create http mycase-notion-poll \
  --location us-central1 --schedule "*/5 * * * *" \
  --uri "https://<your-service-url>/sync/poll-notion" --http-method POST \
  --headers "X-Task-Secret=<INTERNAL_TASK_SECRET>"

gcloud scheduler jobs create http mycase-matters-poll \
  --location us-central1 --schedule "*/10 * * * *" \
  --uri "https://<your-service-url>/sync/poll-mycase" --http-method POST \
  --headers "X-Task-Secret=<INTERNAL_TASK_SECRET>"

gcloud scheduler jobs create http notion-schema-poll \
  --location us-central1 --schedule "0 * * * *" \
  --uri "https://<your-service-url>/sync/poll-notion-schema" --http-method POST \
  --headers "X-Task-Secret=<INTERNAL_TASK_SECRET>"
```

## Status: what's tested vs. what needs verification

**Built and tested** (a mocked test suite drove all four scenarios below
end-to-end: new-page-creates-matter, edited-page-pushes-update,
mycase-change-pushes-to-notion, new-property-creates-custom-field):
- OAuth flow, token storage/refresh (`app/mycase_auth.py`)
- Notion client - query/update pages, read/update database schema
  (`app/notion_client.py`) - Notion's API is fully documented, no guesswork
- Field mapping config, conflict resolution, sync orchestration
  (`app/field_mapping.py`, `app/sync_engine.py`)
- Firestore-backed case mapping + poll-cursor storage (`app/storage.py`)

**Needs a verification pass before touching real firm data**
(`app/mycase_client.py`): MyCase's docs site renders via JavaScript, which
this project's research tooling can't execute - so the *mechanics* here
are real (confirmed OAuth endpoints, Bearer auth) but the *data-API*
specifics are best-effort placeholders:
- `MYCASE_API_BASE` - the actual host for data calls (not `auth.mycase.com`,
  that's OAuth-only per their docs)
- Exact JSON field names for creating/updating a matter
- Exact path/payload for reading and setting custom field values
- Exact path/payload for creating a new custom field

Once MyCase approves API access, they typically provide a Postman
collection or fuller onboarding docs - forward me the "Cases" and "Custom
Fields" sections (or just paste the page text/JSON examples from the
Stoplight docs in your browser) and I'll fix the payload builders in
`app/mycase_client.py` directly - nothing else in the project needs to
change.

## Not yet built

- **Google Drive folder automation** - separate, smaller piece; Google
  Drive API, triggered from the Notion→MyCase matter-creation step.
- **Reports on pending/filed cases** - once the mapping table is populated,
  this is a straightforward read-only endpoint over Firestore + MyCase.
- **Real-time webhooks** - optional latency upgrade once polling is proven
  reliable in production; not required to meet the brief.

## Project layout

```
mycaseNotionSync/
  main.py                FastAPI app entrypoint
  app/
    config.py             env-var driven settings
    security.py            signed OAuth "state" (CSRF) helper
    storage.py              Firestore-backed storage (local-file fallback for dev):
                             OAuth tokens, case mappings, poll cursors
    mycase_auth.py           /auth/mycase/login, /callback, /status, /internal/refresh
    mycase_client.py          MyCase matters + custom fields (needs verification - see Status)
    notion_client.py          Notion pages/database read+write (confirmed against live docs)
    notion_values.py          Notion property JSON <-> plain Python values
    field_mapping.py           the editable Notion <-> MyCase field mapping table
    sync_engine.py             two-way sync orchestration + conflict resolution
    sync_routes.py              /sync/poll-notion, /poll-mycase, /poll-notion-schema
  Dockerfile
  requirements.txt
  .env.example
```
