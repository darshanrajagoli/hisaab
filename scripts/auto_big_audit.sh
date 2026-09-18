#!/usr/bin/env bash
# Retries the big demo audit until Gemini's daily quota resets, then
# exports the fixture bundle and commits+pushes automatically.
#
# Usage: nohup bash scripts/auto_big_audit.sh > /tmp/auto_big_audit.log 2>&1 &

set -u
cd "$(dirname "$0")/.."

CHANNEL="@RakeshBansal"
MAX_VIDEOS=20
RETRY_SECS=1800   # 30 min between attempts
MAX_ATTEMPTS=48   # ~24h ceiling

set -a
source .env
set +a

for attempt in $(seq 1 "$MAX_ATTEMPTS"); do
    echo "=== Attempt $attempt/$MAX_ATTEMPTS at $(date) ==="
    HISAAB_RUN_CAP=200 python -m hisaab.cli audit "$CHANNEL" --max-videos "$MAX_VIDEOS" \
        > "/tmp/auto_big_audit_run_${attempt}.log" 2>&1
    status=$?

    if grep -q "RESOURCE_EXHAUSTED" "/tmp/auto_big_audit_run_${attempt}.log"; then
        echo "Quota still exhausted, sleeping ${RETRY_SECS}s"
        sleep "$RETRY_SECS"
        continue
    fi

    if [ $status -ne 0 ]; then
        echo "Run failed for a non-quota reason (exit $status) — inspect log and stopping."
        exit 1
    fi

    scored=$(grep -oE "Scoring: [0-9]+ scored" "/tmp/auto_big_audit_run_${attempt}.log" | grep -oE "[0-9]+" | head -1)
    echo "Run succeeded with ${scored:-0} scored tips."

    if [ "${scored:-0}" -lt 10 ]; then
        echo "Fewer than 10 scored tips — not enough evidence yet, stopping (rerun manually with a different/second channel if needed)."
    fi

    python scripts/export_fixtures.py demo

    git add fixtures/demo
    if ! git diff --cached --quiet; then
        git commit -m "$(cat <<EOF
data: refresh demo fixture bundle from completed big audit run

Automated by scripts/auto_big_audit.sh after Gemini's daily quota reset.
${scored:-0} scored tips in this run.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01VmiVb9nXkFmSpNY45qGLGn
EOF
)"
        git push origin main
    fi

    echo "Done."
    exit 0
done

echo "Exhausted all $MAX_ATTEMPTS attempts without a successful run."
exit 1
