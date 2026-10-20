#!/bin/bash
# Usage: repo-sync.sh <root_dir> <log_file> [remote_host]
# Runs `repo sync` in <root_dir>, tee'ing all output to <log_file>, and
# appends one final RESULT line the orchestrator (or a human) can grep for.
#
# If <remote_host> is given (e.g. user@host), `repo sync` runs over ssh on
# that host instead of locally — <root_dir> is a path on the remote host.
# Requires passwordless key-based ssh auth to be set up already.
set -o pipefail

ROOT="$1"
LOG="$2"
REMOTE_HOST="$3"

SSH_OPTS=(-o BatchMode=yes -o ConnectTimeout=15 -o IdentitiesOnly=yes -i ~/.ssh/id_rsa)

if [ -n "$REMOTE_HOST" ]; then
  ssh_check_out=$(ssh "${SSH_OPTS[@]}" "$REMOTE_HOST" "[ -d '$ROOT' ]" 2>&1)
  ssh_check_status=$?
  if [ "$ssh_check_status" -eq 255 ]; then
    echo "RESULT: SYNC_FAILED (could not reach $REMOTE_HOST over ssh: $ssh_check_out)" | tee -a "$LOG"
    exit 1
  elif [ "$ssh_check_status" -ne 0 ]; then
    echo "RESULT: SYNC_FAILED (no such directory on $REMOTE_HOST: $ROOT)" | tee -a "$LOG"
    exit 1
  fi

  echo "===== repo sync: $REMOTE_HOST:$ROOT =====" | tee -a "$LOG"
  ssh "${SSH_OPTS[@]}" "$REMOTE_HOST" "cd '$ROOT' && repo sync" 2>&1 | tee -a "$LOG"
  status=${PIPESTATUS[0]}
else
  if [ ! -d "$ROOT" ]; then
    echo "RESULT: SYNC_FAILED (no such directory: $ROOT)" | tee -a "$LOG"
    exit 1
  fi

  cd "$ROOT" || { echo "RESULT: SYNC_FAILED (cd failed: $ROOT)" | tee -a "$LOG"; exit 1; }

  echo "===== repo sync: $ROOT =====" | tee -a "$LOG"
  repo sync 2>&1 | tee -a "$LOG"
  status=${PIPESTATUS[0]}
fi

if [ "$status" -eq 0 ]; then
  echo "RESULT: SYNC_SUCCEEDED (${REMOTE_HOST:+$REMOTE_HOST:}$ROOT)" | tee -a "$LOG"
  exit 0
else
  echo "RESULT: SYNC_FAILED (${REMOTE_HOST:+$REMOTE_HOST:}$ROOT)" | tee -a "$LOG"
  exit 1
fi
