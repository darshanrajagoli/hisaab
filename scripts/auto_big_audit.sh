#!/usr/bin/env bash
# Retries the big demo audit through transient failures (quota limits,
# network blips, SerpApi/Gemini 5xx errors) until a run actually succeeds
# with enough scored tips, then exports the fixture bundle and
# commits+pushes automatically. Designed to run unattended for hours.
#
# Usage: nohup bash scripts/auto_big_audit.sh > /tmp/auto_big_audit.log 2>&1 &

set -u
cd "$(dirname "$0")/.."

LOCK_FILE="/tmp/auto_big_audit.lock"
if [ -f "$LOCK_FILE" ] && kill -0 "$(cat "$LOCK_FILE")" 2>/dev/null; then
    echo "Another instance is already running (PID $(cat "$LOCK_FILE")). Exiting."
    exit 1
fi
echo $$ > "$LOCK_FILE"
trap 'rm -f "$LOCK_FILE"' EXIT

CHANNEL="@RakeshBansal"
MAX_VIDEOS=20
QUOTA_RETRY_SECS=1800     # 30 min — daily/rate quota errors, unlikely to clear sooner
TRANSIENT_RETRY_SECS=120  # 2 min — network blips, 5xx overloads, other one-offs
MAX_ATTEMPTS=80
MIN_SCORED_TIPS=10

set -a
source .env
set +a

# Any line matching one of these means "not our bug, just try again later".
QUOTA_PATTERN='RESOURCE_EXHAUSTED|rate.?limit|429|quota'
TRANSIENT_PATTERN='ServerError|503|ConnectionError|ConnectionReset|Timeout|timed out|Temporary failure|EOF occurred|Connection aborted|Connection refused|Max retries exceeded|Broken pipe'

attempt=0
consecutive_transient=0

while [ "$attempt" -lt "$MAX_ATTEMPTS" ]; do
    attempt=$((attempt + 1))
    echo "=== Attempt $attempt/$MAX_ATTEMPTS at $(date) ==="
    log="/tmp/auto_big_audit_run_$$_${attempt}.log"

    HISAAB_RUN_CAP=200 python -m hisaab.cli audit "$CHANNEL" --max-videos "$MAX_VIDEOS" \
        > "$log" 2>&1
    status=$?

    if [ $status -eq 0 ]; then
        scored=$(grep -oE "Scoring: [0-9]+ scored" "$log" | grep -oE "[0-9]+" | head -1)
        scored=${scored:-0}
        echo "Run succeeded with ${scored} scored tips."

        # extract.py fails OPEN on a per-window LLM error (catches the
        # exception, logs a warning, returns []) so a run can exit 0 with
        # zero tips while actually being fully quota-exhausted throughout —
        # that looked like "success, just not enough data yet" and retried
        # every 2 min forever, never backing off, without ever recovering.
        if grep -qiE "$QUOTA_PATTERN" "$log"; then
            echo "Exit 0 but quota errors were swallowed during extraction — sleeping ${QUOTA_RETRY_SECS}s"
            sleep "$QUOTA_RETRY_SECS"
            continue
        fi

        consecutive_transient=0

        if [ "$scored" -lt "$MIN_SCORED_TIPS" ]; then
            echo "Fewer than ${MIN_SCORED_TIPS} scored tips — not enough evidence yet, retrying."
            sleep "$TRANSIENT_RETRY_SECS"
            continue
        fi

        python scripts/export_fixtures.py demo
        git add fixtures/demo
        if ! git diff --cached --quiet; then
            git commit -m "$(cat <<EOF
data: refresh demo fixture bundle from completed big audit run

Automated by scripts/auto_big_audit.sh. ${scored} scored tips in this run.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01VmiVb9nXkFmSpNY45qGLGn
EOF
)"
            # Network to GitHub can also blip — retry the push a few times
            # before giving up on this otherwise-successful run.
            for push_try in 1 2 3 4 5; do
                git push origin main && break
                echo "Push attempt ${push_try} failed, retrying in 30s"
                sleep 30
            done
        fi

        echo "Done."
        exit 0
    fi

    # Non-zero exit: classify why and decide how long to back off.
    if grep -qiE "$QUOTA_PATTERN" "$log"; then
        echo "Quota/rate-limit error, sleeping ${QUOTA_RETRY_SECS}s"
        consecutive_transient=0
        sleep "$QUOTA_RETRY_SECS"
    elif grep -qiE "$TRANSIENT_PATTERN" "$log"; then
        consecutive_transient=$((consecutive_transient + 1))
        echo "Transient error (#${consecutive_transient} in a row), sleeping ${TRANSIENT_RETRY_SECS}s"
        sleep "$TRANSIENT_RETRY_SECS"
    else
        # Unrecognized failure — still don't give up on an unattended run,
        # but back off further and log loudly so it's easy to spot later.
        consecutive_transient=$((consecutive_transient + 1))
        echo "UNRECOGNIZED FAILURE (exit $status) — see $log — retrying anyway after ${QUOTA_RETRY_SECS}s"
        sleep "$QUOTA_RETRY_SECS"
    fi
done

echo "Exhausted all $MAX_ATTEMPTS attempts without a qualifying run. See /tmp/auto_big_audit_run_*.log"
exit 1
