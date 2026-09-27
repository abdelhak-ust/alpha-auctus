# Deploying Nexus to Cloud Run

Two Cloud Run services:

| Service | Source | What it is |
|---|---|---|
| `nexus-backend` | `backend/Dockerfile` | FastAPI + LangGraph + Docling. Postgres on **Cloud SQL**, uploaded files on a **Cloud Storage** bucket mounted as a volume, Gemini via **Vertex AI** (service-account auth, no key). |
| `nexus-client` | `client/Dockerfile` | Vite SPA + `client/server.ts`. The browser calls the backend directly, so the backend URL is baked in at build time. |

Order matters: backend first (the client needs its URL), then client, then point the
backend's CORS at the client URL.

Run every command from the repo root. Nothing here writes a real project id into the repo.

---

## 0. Variables (set once per terminal)

```bash
export PROJECT_ID=your-gcp-project-id
export REGION=us-central1
export SQL_INSTANCE=nexus-db
export BUCKET=${PROJECT_ID}-nexus-blobs
export SA=nexus-backend@${PROJECT_ID}.iam.gserviceaccount.com
export REPO=${REGION}-docker.pkg.dev/${PROJECT_ID}/nexus

gcloud auth login
gcloud config set project $PROJECT_ID
gcloud config set run/region $REGION
```

## 1. Enable the APIs

```bash
gcloud services enable run.googleapis.com cloudbuild.googleapis.com \
  artifactregistry.googleapis.com sqladmin.googleapis.com aiplatform.googleapis.com \
  secretmanager.googleapis.com storage.googleapis.com
```

## 2. Artifact Registry (holds the client image)

```bash
gcloud artifacts repositories create nexus --repository-format=docker --location=$REGION
```

## 3. Cloud SQL — Postgres 16 (~5–10 min)

```bash
gcloud sql instances create $SQL_INSTANCE --database-version=POSTGRES_16 \
  --edition=ENTERPRISE --tier=db-f1-micro --region=$REGION

gcloud sql databases create nexus --instance=$SQL_INSTANCE

export DB_PASS=$(openssl rand -hex 24)   # hex → safe inside a URL
gcloud sql users create nexus --instance=$SQL_INSTANCE --password=$DB_PASS
```

Migrations need no extensions (no pgvector in the MVP tables); the container runs
`alembic upgrade head` on every boot.

## 4. Bucket for uploaded documents

```bash
gcloud storage buckets create gs://$BUCKET --location=$REGION --uniform-bucket-level-access
```

## 5. Service account for the backend

```bash
gcloud iam service-accounts create nexus-backend --display-name="Nexus backend"

for role in roles/aiplatform.user roles/cloudsql.client roles/secretmanager.secretAccessor; do
  gcloud projects add-iam-policy-binding $PROJECT_ID --member=serviceAccount:$SA --role=$role
done

gcloud storage buckets add-iam-policy-binding gs://$BUCKET \
  --member=serviceAccount:$SA --role=roles/storage.objectUser
```

## 6. Database URL as a secret

Cloud Run reaches Cloud SQL through a Unix socket at `/cloudsql/<connection-name>`.
Both asyncpg (SQLAlchemy) and psycopg (the LangGraph checkpointer) accept the `host=` form.

```bash
export CONN=$(gcloud sql instances describe $SQL_INSTANCE --format='value(connectionName)')

printf 'postgresql+asyncpg://nexus:%s@/nexus?host=/cloudsql/%s' "$DB_PASS" "$CONN" \
  | gcloud secrets create nexus-database-url --data-file=-
```

## 7. Deploy the backend (first build ~10–15 min: torch + Docling)

```bash
gcloud run deploy nexus-backend \
  --source backend \
  --service-account=$SA \
  --add-cloudsql-instances=$CONN \
  --set-secrets=DATABASE_URL=nexus-database-url:latest \
  --set-env-vars=ENVIRONMENT=production,GCP_PROJECT_ID=$PROJECT_ID,VERTEX_LOCATION=$REGION,BLOB_DIR=/mnt/blobs \
  --execution-environment=gen2 \
  --add-volume=name=blobs,type=cloud-storage,bucket=$BUCKET \
  --add-volume-mount=volume=blobs,mount-path=/mnt/blobs \
  --memory=4Gi --cpu=2 --timeout=3600 \
  --no-cpu-throttling --min-instances=1 --max-instances=1 \
  --allow-unauthenticated

export BACKEND_URL=$(gcloud run services describe nexus-backend --format='value(status.url)')
curl $BACKEND_URL/api/health
```

Why these flags:
- **`--no-cpu-throttling` + `--min-instances=1`**: documents are processed in a background
  task *after* the upload request returns. With default throttling, Cloud Run freezes the
  CPU between requests and the graph stalls.
- **`--max-instances=1`**: startup recovery (`recover_stuck_documents`) and on-boot
  migrations assume one process.
- **`--memory=4Gi`**: Docling layout models plus a PDF in memory. Models download from
  Hugging Face on the first PDF/DOCX per instance, so that first upload is slower.

## 8. Build and deploy the client

```bash
gcloud builds submit client --config=client/cloudbuild.yaml \
  --substitutions=_IMAGE=$REPO/nexus-client:latest,_BACKEND_URL=$BACKEND_URL

gcloud run deploy nexus-client \
  --image=$REPO/nexus-client:latest \
  --memory=512Mi --min-instances=1 --max-instances=1 \
  --allow-unauthenticated

export CLIENT_URL=$(gcloud run services describe nexus-client --format='value(status.url)')
```

## 9. Allow the client origin on the backend (CORS)

```bash
gcloud run services update nexus-backend \
  --update-env-vars="^##^CORS_ORIGINS=[\"$CLIENT_URL\"]"
```

## 10. Open it

```bash
echo $CLIENT_URL
```

Open that URL, create a project, and upload a document. If processing fails, read the logs:

```bash
gcloud run services logs read nexus-backend --limit=100
```

---

## Redeploying

- Backend: rerun step 7. It keeps the env vars, secrets, and volume; `--source backend` is enough.
- Client: rerun step 8. The backend URL is stable, so no CORS change is needed.

## Deploying from GitHub (automatic redeploys)

`.github/workflows/deploy.yml` redeploys both services on every push to `main` (or on
demand from the Actions tab). It only **redeploys**: steps 0–9 above must have been run once
by hand, because they create the database, bucket, secret, and service flags that later
deploys reuse.

GitHub signs in to GCP with **Workload Identity Federation**, so no service-account key is
stored in GitHub. One-time setup (with the step-0 variables still exported):

```bash
export GH_REPO=abdelhak-ust/alpha-auctus
export PROJECT_NUMBER=$(gcloud projects describe $PROJECT_ID --format='value(projectNumber)')
export DEPLOYER=github-deployer@${PROJECT_ID}.iam.gserviceaccount.com

# 1. A pool + provider that trusts GitHub's tokens, only for this repo.
gcloud iam workload-identity-pools create github --location=global
gcloud iam workload-identity-pools providers create-oidc github \
  --location=global --workload-identity-pool=github \
  --issuer-uri=https://token.actions.githubusercontent.com \
  --attribute-mapping=google.subject=assertion.sub,attribute.repository=assertion.repository \
  --attribute-condition="assertion.repository=='$GH_REPO'"

# 2. The service account the workflow acts as.
gcloud iam service-accounts create github-deployer --display-name="GitHub deployer"
for role in roles/run.admin roles/cloudbuild.builds.editor roles/artifactregistry.writer \
            roles/storage.admin roles/serviceusage.serviceUsageConsumer; do
  gcloud projects add-iam-policy-binding $PROJECT_ID --member=serviceAccount:$DEPLOYER --role=$role
done
# It deploys services that run as other service accounts, so it may "act as" them.
for runtime_sa in $SA ${PROJECT_NUMBER}-compute@developer.gserviceaccount.com; do
  gcloud iam service-accounts add-iam-policy-binding $runtime_sa \
    --member=serviceAccount:$DEPLOYER --role=roles/iam.serviceAccountUser
done

# 3. Let workflows from this repo (and only this repo) impersonate it.
gcloud iam service-accounts add-iam-policy-binding $DEPLOYER \
  --role=roles/iam.workloadIdentityUser \
  --member="principalSet://iam.googleapis.com/projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/github/attribute.repository/$GH_REPO"

# 4. Repo variables the workflow reads (not secrets: none of these grants access alone).
gh variable set GCP_PROJECT_ID --repo $GH_REPO --body "$PROJECT_ID"
gh variable set GCP_REGION --repo $GH_REPO --body "$REGION"
gh variable set GCP_DEPLOYER_SA --repo $GH_REPO --body "$DEPLOYER"
gh variable set GCP_WIF_PROVIDER --repo $GH_REPO \
  --body "projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/github/providers/github"
```

Then merge to `main` (or run the workflow from the Actions tab) and watch it in the
repository's **Actions** tab. The URLs don't change between deploys, so `$CLIENT_URL` from
step 8 stays your app's URL.

## Known limits of this setup

- **The client's board data is not durable.** `client/server.ts` keeps it in SQLite inside the
  container, so it resets to the `database.json` seed on every redeploy or restart.
  (SQLite on a Cloud Storage mount is unsafe: it has no file locking.) The backend's data
  (documents, features, tasks) lives in Cloud SQL and survives.
- **No authentication.** Both URLs are public, and anyone with the backend URL can upload
  documents and spend Vertex AI quota. For anything beyond a private demo, put both services
  behind IAP.
- **Always-on billing.** `min-instances=1` with no CPU throttling bills around the clock.
  Delete the services and the SQL instance when you're done:
  `gcloud run services delete nexus-backend nexus-client && gcloud sql instances delete $SQL_INSTANCE`.
