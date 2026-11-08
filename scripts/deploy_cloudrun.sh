#!/usr/bin/env bash
# Deploy to Google Cloud Run with SQLite + Litestream (backed up to one Cloud Storage bucket).
# No Cloud SQL, so small apps can run inside Google Cloud's free tier. See docs/deployment.md.
#
# PRINTS the commands by default (dry run). Pass --apply to run them.
#
#   GCP_PROJECT=my-project SERVICE=my-saas ./scripts/deploy_cloudrun.sh            # review
#   SECRET_KEY=... GCP_PROJECT=my-project SERVICE=my-saas ./scripts/deploy_cloudrun.sh --apply
#
# Settings (environment variables):
#   GCP_PROJECT (required)  SERVICE (default: django-saas)  REGION (default: us-central1)
#   BUCKET (default: <project>-<service>-db)  HOST (custom domain; default: the run.app URL)
#   JOBS_SCHEDULE (cron, default "0 3 * * *": daily 03:00)  JOBS_TIMEZONE (default Etc/UTC)
#   JOBS_SCHEDULE=off skips the Cloud Scheduler job.
#   SECRET_KEY (required with --apply; stored in Secret Manager, never printed)
#   Every optional variable below that is set in your shell IS deployed: unset what you don't want.
#   Optional secrets, deployed only when set: GOOGLE_CLIENT_SECRET, GITHUB_CLIENT_SECRET,
#   STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET, EMAIL_HOST_PASSWORD, ANTHROPIC_API_KEY, JOBS_TRIGGER_TOKEN
#   Optional plain settings, passed through when set: GOOGLE_CLIENT_ID, GITHUB_CLIENT_ID,
#   BILLING_ENABLED, SITE_NAME, DEFAULT_FROM_EMAIL, EMAIL_BACKEND, EMAIL_HOST, EMAIL_PORT,
#   EMAIL_HOST_USER, EMAIL_USE_TLS, ACCOUNT_EMAIL_VERIFICATION, AI_MODEL, AI_EFFORT, AI_MAX_INPUT_CHARS,
#   MFA_ENROLLMENT_ENABLED, UPLOADS_ENABLED, UPLOAD_MAX_FILE_BYTES, GS_BUCKET_NAME, PLAUSIBLE_DOMAIN
#   (uploads need their own private bucket + bucket-level access for the service account: docs/uploads.md)
set -euo pipefail
cd "$(dirname "$0")/.."

APPLY=0
[[ "${1:-}" == "--apply" ]] && APPLY=1

PROJECT="${GCP_PROJECT:?set GCP_PROJECT}"
SERVICE="${SERVICE:-django-saas}"
REGION="${REGION:-us-central1}"
BUCKET="${BUCKET:-${PROJECT}-${SERVICE}-db}"
SA="${SERVICE}@${PROJECT}.iam.gserviceaccount.com"
SCHED_SA="${SERVICE}-jobs@${PROJECT}.iam.gserviceaccount.com"
JOBS_SCHEDULE="${JOBS_SCHEDULE:-0 3 * * *}"
JOBS_TIMEZONE="${JOBS_TIMEZONE:-Etc/UTC}"
TAG="$(git rev-parse --short HEAD 2>/dev/null || echo manual)"
IMAGE="${REGION}-docker.pkg.dev/${PROJECT}/${SERVICE}/app:${TAG}"

if PROJECT_NUMBER=$(gcloud projects describe "$PROJECT" --format='value(projectNumber)' 2>/dev/null); then
  RUNAPP_HOST="${SERVICE}-${PROJECT_NUMBER}.${REGION}.run.app"
else
  (( APPLY )) && { echo "Cannot read project $PROJECT: run 'gcloud auth login' first." >&2; exit 1; }
  RUNAPP_HOST="${SERVICE}-PROJECT_NUMBER.${REGION}.run.app"
fi
HOST="${HOST:-$RUNAPP_HOST}"
HOSTS="$HOST"; ORIGINS="https://$HOST"
JOBS_URL="https://$HOST/internal/jobs/run/"
[[ "$HOST" != "$RUNAPP_HOST" ]] && { HOSTS+=",$RUNAPP_HOST"; ORIGINS+=",https://$RUNAPP_HOST"; }

run() {  # print; run only with --apply
  printf '+ %s\n' "$*"
  if (( APPLY )); then "$@"; fi
}
create() {  # like run, but "already exists" on a re-run is not an error
  printf '+ %s\n' "$*"
  if (( APPLY )); then "$@" || echo "  (exists already? continuing)"; fi
}

if (( APPLY )); then
  [[ -n "${SECRET_KEY:-}" ]] || { echo "SECRET_KEY must be set for --apply." >&2; exit 1; }
  [[ -z "$(git status --porcelain 2>/dev/null)" ]] || {
    echo "Uncommitted changes: commit first so the deployed image matches a commit." >&2; exit 1; }
fi

echo "== 1. APIs, image registry, service account (no project-wide roles)"
run gcloud services enable run.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com \
  secretmanager.googleapis.com storage.googleapis.com cloudscheduler.googleapis.com --project="$PROJECT"
create gcloud artifacts repositories create "$SERVICE" --repository-format=docker --location="$REGION" \
  --project="$PROJECT"
create gcloud iam service-accounts create "$SERVICE" --display-name="$SERVICE" --project="$PROJECT"

echo "== 2. Database bucket gs://$BUCKET: private, versioned, old versions deleted after 7 days"
create gcloud storage buckets create "gs://$BUCKET" --project="$PROJECT" --location="$REGION" \
  --uniform-bucket-level-access --public-access-prevention
LIFECYCLE=$(mktemp)
POLICY=$(mktemp)
trap 'rm -f "$LIFECYCLE" "$POLICY"' EXIT
printf '%s' '{"rule":[{"action":{"type":"Delete"},"condition":{"isLive":false,"daysSinceNoncurrentTime":7}}]}' >"$LIFECYCLE"
run gcloud storage buckets update "gs://$BUCKET" --versioning --lifecycle-file="$LIFECYCLE" --project="$PROJECT"
echo "   The service account gets access to THIS bucket only."
run gcloud storage buckets add-iam-policy-binding "gs://$BUCKET" --member="serviceAccount:$SA" \
  --role=roles/storage.objectAdmin --project="$PROJECT"

echo "== 3. Secrets -> Secret Manager (values are never printed)"
SECRET_FLAGS=()
for var in SECRET_KEY GOOGLE_CLIENT_SECRET GITHUB_CLIENT_SECRET STRIPE_SECRET_KEY STRIPE_WEBHOOK_SECRET \
  EMAIL_HOST_PASSWORD ANTHROPIC_API_KEY JOBS_TRIGGER_TOKEN; do
  [[ -n "${!var:-}" || "$var" == SECRET_KEY ]] || continue
  name="${SERVICE}-$(echo "$var" | tr '[:upper:]_' '[:lower:]-')"
  SECRET_FLAGS+=("$var=$name:latest")
  printf '+ <value of %s> | gcloud secrets create/versions add %s\n' "$var" "$name"
  if (( APPLY )); then
    if gcloud secrets describe "$name" --project="$PROJECT" >/dev/null 2>&1; then
      printf '%s' "${!var}" | gcloud secrets versions add "$name" --data-file=- --project="$PROJECT" >/dev/null
    else
      printf '%s' "${!var}" | gcloud secrets create "$name" --data-file=- --replication-policy=automatic \
        --project="$PROJECT" >/dev/null
    fi
    gcloud secrets add-iam-policy-binding "$name" --member="serviceAccount:$SA" \
      --role=roles/secretmanager.secretAccessor --project="$PROJECT" >/dev/null
  fi
done

echo "== 4. Build the image with Cloud Build"
run gcloud builds submit --tag="$IMAGE" --project="$PROJECT" .

ENV=(
  DEBUG=false
  TRUST_PROXY_SSL_HEADER=true
  "LITESTREAM_REPLICA_URL=gs://$BUCKET/db"
  "ALLOWED_HOSTS=$HOSTS"
  "CSRF_TRUSTED_ORIGINS=$ORIGINS"
  "BILLING_SUCCESS_URL=https://$HOST/account/?billing=success"
  "BILLING_CANCEL_URL=https://$HOST/account/?billing=cancelled"
  "BILLING_PORTAL_RETURN_URL=https://$HOST/account/"
)
# Scheduled jobs: only a Google-signed token for the scheduler's own service account is accepted.
[[ "$JOBS_SCHEDULE" != off ]] && ENV+=("JOBS_OIDC_AUDIENCE=$JOBS_URL" "JOBS_INVOKER_EMAIL=$SCHED_SA")
for var in GOOGLE_CLIENT_ID GITHUB_CLIENT_ID BILLING_ENABLED SITE_NAME DEFAULT_FROM_EMAIL EMAIL_BACKEND \
  EMAIL_HOST EMAIL_PORT EMAIL_HOST_USER EMAIL_USE_TLS ACCOUNT_EMAIL_VERIFICATION AI_MODEL AI_EFFORT \
  AI_MAX_INPUT_CHARS MFA_ENROLLMENT_ENABLED UPLOADS_ENABLED UPLOAD_MAX_FILE_BYTES GS_BUCKET_NAME PLAUSIBLE_DOMAIN; do
  [[ -n "${!var:-}" ]] && ENV+=("$var=${!var}")
done
# The ^|^ prefix makes | the separator, so comma lists (ALLOWED_HOSTS) stay one value.
ENV_ARG="^|^$(IFS='|'; echo "${ENV[*]}")"
SECRET_ARG=$(IFS=,; echo "${SECRET_FLAGS[*]}")

echo "== 5. Deploy. The container restores the DB from the bucket, migrates, then serves under Litestream."
echo "   SQLite has one writer: keep max-instances at 1. Request-based CPU billing keeps idle cost near 0."
run gcloud run deploy "$SERVICE" --image="$IMAGE" --region="$REGION" --service-account="$SA" \
  --project="$PROJECT" --set-env-vars="$ENV_ARG" --set-secrets="$SECRET_ARG" \
  --execution-environment=gen2 --min-instances=0 --max-instances=1 --concurrency=20 \
  --cpu=1 --memory=512Mi --cpu-throttling --timeout=300 --allow-unauthenticated

if [[ "$JOBS_SCHEDULE" != off ]]; then
  echo "== 6. Scheduled jobs: Cloud Scheduler POSTs $JOBS_URL ($JOBS_SCHEDULE, $JOBS_TIMEZONE)"
  echo "   Signed with an OIDC token for $SCHED_SA, an account with no roles; the app checks it."
  create gcloud iam service-accounts create "${SERVICE}-jobs" --display-name="${SERVICE} scheduled jobs" \
    --project="$PROJECT"
  SCHED_ARGS=(--location="$REGION" --project="$PROJECT" --schedule="$JOBS_SCHEDULE" --time-zone="$JOBS_TIMEZONE"
    --uri="$JOBS_URL" --http-method=POST --oidc-service-account-email="$SCHED_SA"
    --oidc-token-audience="$JOBS_URL" --attempt-deadline=300s)
  if (( APPLY )) && gcloud scheduler jobs describe "${SERVICE}-jobs" --location="$REGION" --project="$PROJECT" \
    >/dev/null 2>&1; then
    run gcloud scheduler jobs update http "${SERVICE}-jobs" "${SCHED_ARGS[@]}"
  else
    run gcloud scheduler jobs create http "${SERVICE}-jobs" "${SCHED_ARGS[@]}"
  fi
fi

echo "== 7. Keep the image registry small: newest 2 images, nothing older than 14 days"
printf '%s' '[{"name":"keep-newest-2","action":{"type":"Keep"},"mostRecentVersions":{"keepCount":2}},{"name":"delete-old","action":{"type":"Delete"},"condition":{"olderThan":"14d"}}]' >"$POLICY"
run gcloud artifacts repositories set-cleanup-policies "$SERVICE" --location="$REGION" --project="$PROJECT" \
  --policy="$POLICY"

if (( APPLY )); then
  echo "Done: https://$HOST  (check https://$HOST/healthz)"
else
  echo "Dry run: nothing was created. Review the commands, then re-run with --apply."
fi
