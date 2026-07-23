#!/usr/bin/env bash
# Upload a CSV file to a Dynatrace lookup table using dtctl's OAuth session.
#
# Usage:
#   ./upload_lookup.sh <csv_file> <lookup_name>
#
# Example:
#   ./upload_lookup.sh /tmp/beneficiaries_lookup.csv banking_beneficiaries_scale
#
# The script reads the environment URL from dtctl config and prompts for a
# Bearer token. To get the token, open the Dynatrace UI:
#   Settings → Access tokens → Generate token
#   Required scope: storage:bucket-definitions:write  (lookup upload)
#   OR use the OAuth session token shown by: dtctl auth status
#
# Requires: curl, jq, dtctl (for env URL)

set -euo pipefail

FILE="${1:?Usage: $0 <csv_file> <lookup_name>}"
LOOKUP_NAME="${2:?Usage: $0 <csv_file> <lookup_name>}"

[[ -f "$FILE" ]] || { echo "File not found: $FILE" >&2; exit 1; }

# ── Get environment URL from dtctl ─────────────────────────────────────────
CONTEXT=$(dtctl config current-context --plain 2>/dev/null)
ENV_URL=$(dtctl config describe-context "$CONTEXT" --plain 2>/dev/null | awk '/^Environment:/ {print $2}')
[[ -n "$ENV_URL" ]] || { echo "Could not read environment URL from dtctl" >&2; exit 1; }

FILE_BYTES=$(wc -c < "$FILE")
FILE_MB=$(python3 -c "print(f'{$FILE_BYTES/1048576:.1f}')")

echo ""
echo "Context:     $CONTEXT"
echo "Environment: $ENV_URL"
echo "File:        $FILE ($FILE_MB MB)"
echo "Lookup:      /lookups/$LOOKUP_NAME"
echo ""
echo "Paste your Bearer token (from Dynatrace UI → Settings → Access tokens):"
echo -n "> "
read -r -s BEARER_TOKEN
echo ""
[[ -n "$BEARER_TOKEN" ]] || { echo "No token provided." >&2; exit 1; }

REQUEST=$(python3 -c "
import json
print(json.dumps({
  'lookupField': 'composite_key',
  'filePath': '/lookups/$LOOKUP_NAME',
  'overwrite': True,
  'displayName': '$LOOKUP_NAME',
  'skippedRecords': 0,
  'autoFlatten': True,
  'timezone': 'UTC',
  'locale': 'en_US',
  'description': 'Scale test: $LOOKUP_NAME',
  'parsePattern': 'CSV'
}))
")

echo "Uploading..."
HTTP_CODE=$(curl -s -o /tmp/_upload_resp.json -w "%{http_code}" \
  -X POST "${ENV_URL}/platform/storage/resource-store/v1/files/tabular/lookup:upload" \
  -H "Authorization: Bearer ${BEARER_TOKEN}" \
  -F "request=${REQUEST};type=application/json" \
  -F "content=@${FILE};type=text/csv")

echo "HTTP $HTTP_CODE"
cat /tmp/_upload_resp.json | python3 -m json.tool 2>/dev/null || cat /tmp/_upload_resp.json
echo ""

[[ "$HTTP_CODE" =~ ^2 ]] && echo "Upload succeeded." || { echo "Upload failed."; exit 1; }
