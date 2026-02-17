#!/usr/bin/env bash
# scripts/backup_db_to_r2.sh

set -euo pipefail

if [[ -z "${BACKUP_DATABASE_URL:-}" ]]; then
  echo "Missing BACKUP_DATABASE_URL"
  exit 1
fi
if [[ -z "${R2_ACCESS_KEY_ID:-}" || -z "${R2_SECRET_ACCESS_KEY:-}" || -z "${R2_BUCKET:-}" || -z "${R2_ENDPOINT:-}" ]]; then
  echo "Missing one or more R2 secrets: R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET, R2_ENDPOINT"
  exit 1
fi

PREFIX="${R2_PREFIX:-erp-backups}"
TS="$(date -u +%Y-%m-%dT%H-%M-%SZ)"
FILE="backup-${TS}.dump"
KEY="${PREFIX}/${FILE}"

echo "Creating pg_dump -> ${FILE}"
pg_dump "${BACKUP_DATABASE_URL}" \
  --format=custom \
  --no-owner \
  --no-acl \
  --verbose \
  --file="${FILE}"

echo "Uploading to R2 -> s3://${R2_BUCKET}/${KEY}"
export AWS_ACCESS_KEY_ID="${R2_ACCESS_KEY_ID}"
export AWS_SECRET_ACCESS_KEY="${R2_SECRET_ACCESS_KEY}"
export AWS_DEFAULT_REGION="auto"

aws s3 cp "${FILE}" "s3://${R2_BUCKET}/${KEY}" \
  --endpoint-url "${R2_ENDPOINT}"

echo "Done ✅"
