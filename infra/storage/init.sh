#!/bin/sh
# Creates the bucket on the local S3-compatible store. Safe to re-run.
set -eu

if aws --endpoint-url "$S3_ENDPOINT" s3api head-bucket --bucket "$S3_BUCKET" 2>/dev/null; then
  echo "bucket $S3_BUCKET already exists"
else
  aws --endpoint-url "$S3_ENDPOINT" s3api create-bucket --bucket "$S3_BUCKET"
  echo "bucket $S3_BUCKET created"
fi

# T4.6: the browser PUTs a PDF straight to the bucket from the web origin (ADR-0012), so the
# bucket answers that origin's CORS preflight. Applied on every run: it replaces the old rules.
cors="{\"CORSRules\":[{\"AllowedOrigins\":[\"$WEB_ORIGIN\"],\"AllowedMethods\":[\"PUT\"],\"AllowedHeaders\":[\"*\"],\"ExposeHeaders\":[\"ETag\"],\"MaxAgeSeconds\":600}]}"
aws --endpoint-url "$S3_ENDPOINT" s3api put-bucket-cors --bucket "$S3_BUCKET" --cors-configuration "$cors"
echo "bucket $S3_BUCKET allows PUT from $WEB_ORIGIN"
