#!/bin/sh
# Creates the bucket on the local S3-compatible store. Safe to re-run.
set -eu

if aws --endpoint-url "$S3_ENDPOINT" s3api head-bucket --bucket "$S3_BUCKET" 2>/dev/null; then
  echo "bucket $S3_BUCKET already exists"
else
  aws --endpoint-url "$S3_ENDPOINT" s3api create-bucket --bucket "$S3_BUCKET"
  echo "bucket $S3_BUCKET created"
fi
