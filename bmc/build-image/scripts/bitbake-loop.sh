#!/bin/bash
# Usage: bitbake-loop.sh <root_dir> <setup_arg> <log_file> [image] [max_attempts] [remote_host]
#
# Sources the platform's `setup` script, then repeatedly bitbakes <image>.
# On failure it identifies every recipe:task that failed (a single bitbake
# run can fail more than one already-in-flight task), runs `bitbake -b
# <recipe> -c cleanall` on each, and retries. Stops when:
#   - the build succeeds                              -> BUILD_SUCCEEDED
#   - the SAME set of recipes fails again              -> STOPPED (likely real bug)
#   - the failing recipe(s) can't be identified         -> STOPPED (needs manual triage)
#   - max_attempts is reached                          -> STOPPED
#
# If <remote_host> is given (e.g. user@host), `setup`/`bitbake` run over ssh
# on that host instead of locally — <root_dir> is a path on the remote host.
# Requires passwordless key-based ssh auth to be set up already. Each ssh
# call is its own shell, so cd+setup is re-chained onto every remote command
# (mirrors why this needs to be a script instead of separate Bash calls).
#
# Assumes `repo sync` for this root has already completed successfully.
# Does NOT use `set -u`, because the sourced `setup` script references
# unset variables (e.g. $ZSH_NAME) and would abort under nounset.
set -o pipefail

ROOT="$1"
PLATFORM="$2"
LOG="$3"
IMAGE="${4:-obmc-phosphor-image}"
MAX_ATTEMPTS="${5:-20}"
REMOTE_HOST="$6"

SSH_OPTS=(-o BatchMode=yes -o ConnectTimeout=15 -o IdentitiesOnly=yes -i ~/.ssh/id_rsa)

if [ -n "$REMOTE_HOST" ]; then
  ssh_check_out=$(ssh "${SSH_OPTS[@]}" "$REMOTE_HOST" "[ -d '$ROOT' ]" 2>&1)
  ssh_check_status=$?
  if [ "$ssh_check_status" -eq 255 ]; then
    echo "RESULT: BUILD_FAILED [$PLATFORM] (could not reach $REMOTE_HOST over ssh: $ssh_check_out)" | tee -a "$LOG"
    exit 1
  elif [ "$ssh_check_status" -ne 0 ]; then
    echo "RESULT: BUILD_FAILED [$PLATFORM] (no such directory on $REMOTE_HOST: $ROOT)" | tee -a "$LOG"
    exit 1
  fi

  echo "===== [$PLATFORM] setup (remote: $REMOTE_HOST) =====" | tee -a "$LOG"
  setup_out=$(ssh "${SSH_OPTS[@]}" "$REMOTE_HOST" "cd '$ROOT' && source setup '$PLATFORM' 2>&1 && command -v bitbake" 2>&1)
  echo "$setup_out" | tee -a "$LOG"

  if ! echo "$setup_out" | grep -q '/bitbake$'; then
    echo "RESULT: BUILD_FAILED [$PLATFORM] (setup did not put bitbake on PATH on $REMOTE_HOST - bad platform name, missing tooling, or ssh key auth not set up?)" | tee -a "$LOG"
    exit 1
  fi
else
  if [ ! -d "$ROOT" ]; then
    echo "RESULT: BUILD_FAILED [$PLATFORM] (no such directory: $ROOT)" | tee -a "$LOG"
    exit 1
  fi

  cd "$ROOT" || { echo "RESULT: BUILD_FAILED [$PLATFORM] (cd failed: $ROOT)" | tee -a "$LOG"; exit 1; }

  echo "===== [$PLATFORM] setup =====" | tee -a "$LOG"
  # Piping `source setup ...` through `| tee` would run the source in a
  # subshell (pipelines fork each stage), silently discarding the PATH/cd
  # changes it makes. Process substitution keeps `source` in this shell.
  # shellcheck disable=SC1091
  source setup "$PLATFORM" > >(tee -a "$LOG") 2>&1

  if ! command -v bitbake >/dev/null 2>&1; then
    echo "RESULT: BUILD_FAILED [$PLATFORM] (setup did not put bitbake on PATH - bad platform name?)" | tee -a "$LOG"
    exit 1
  fi
fi

prev_fail=""
attempt=1

while [ "$attempt" -le "$MAX_ATTEMPTS" ]; do
  echo "===== [$PLATFORM] bitbake $IMAGE (attempt $attempt) =====" | tee -a "$LOG"
  attempt_log=$(mktemp)

  if [ -n "$REMOTE_HOST" ]; then
    ssh "${SSH_OPTS[@]}" "$REMOTE_HOST" "cd '$ROOT' && source setup '$PLATFORM' >/dev/null 2>&1 && bitbake '$IMAGE'" 2>&1 | tee -a "$LOG" "$attempt_log"
  else
    bitbake "$IMAGE" 2>&1 | tee -a "$LOG" "$attempt_log"
  fi
  status=${PIPESTATUS[0]}

  if [ "$status" -eq 0 ]; then
    echo "RESULT: BUILD_SUCCEEDED [$PLATFORM] after $attempt attempt(s)" | tee -a "$LOG"
    rm -f "$attempt_log"
    exit 0
  fi

  # A single bitbake invocation can leave more than one task failed (already
  # in-flight parallel tasks finish even after the first failure aborts
  # scheduling). Track the whole SET of failing recipes, not just one -
  # otherwise two persistently-broken recipes can alternate which one shows
  # up "first" in the log each attempt, and the same-recipe-twice check
  # below never trips even though nothing is actually progressing.
  # Preferred: "ERROR: Task (/path/to/recipe_1.0.bb:do_compile) failed with exit code '1'"
  fail_recipes=$(grep -oP '(?<=^ERROR: Task \().*?(?=\) failed with exit code)' "$attempt_log" | sort -u)
  # Fallback: older/alternate bitbake "Summary: N task(s) failed:" list,
  # where each failing task is printed on its own indented line, e.g.
  # "  /path/to/recipe.bb:do_compile". Anchored to whole-line matches only
  # (not `grep -oE '[^[:space:]]+\.bb:do_...'` unanchored) so it can't match
  # unrelated "NOTE: Running task (path:do_x)" lines elsewhere in the log -
  # doing so previously swept up every task bitbake had run so far,
  # including the line's leading "(", into a bogus recipe path and drove a
  # do_cleanall storm across dozens of unrelated recipes on transient
  # failures (e.g. a bitbake-server timeout) that have no such Summary block.
  if [ -z "$fail_recipes" ]; then
    fail_recipes=$(grep -oE '^[[:space:]]+/[^[:space:]]+\.bb:do_[A-Za-z_]+[[:space:]]*$' "$attempt_log" | tr -d '[:space:]' | sort -u)
  fi
  rm -f "$attempt_log"

  if [ -z "$fail_recipes" ]; then
    echo "RESULT: STOPPED [$PLATFORM] (build failed but could not identify a single failing recipe - see log for manual triage)" | tee -a "$LOG"
    exit 1
  fi

  echo "===== [$PLATFORM] failing recipe(s): $(echo "$fail_recipes" | tr '\n' ' ') =====" | tee -a "$LOG"

  if [ "$fail_recipes" = "$prev_fail" ]; then
    echo "RESULT: STOPPED [$PLATFORM] ($(echo "$fail_recipes" | tr '\n' ' ') failed again after do_cleanall retry - likely a real bug, needs manual triage)" | tee -a "$LOG"
    exit 1
  fi
  prev_fail="$fail_recipes"

  while IFS= read -r fr; do
    recipe_path="${fr%%:do_*}"
    echo "===== [$PLATFORM] do_cleanall $recipe_path =====" | tee -a "$LOG"
    if [ -n "$REMOTE_HOST" ]; then
      ssh "${SSH_OPTS[@]}" "$REMOTE_HOST" "cd '$ROOT' && source setup '$PLATFORM' >/dev/null 2>&1 && bitbake -b '$recipe_path' -c cleanall" 2>&1 | tee -a "$LOG"
    else
      bitbake -b "$recipe_path" -c cleanall 2>&1 | tee -a "$LOG"
    fi
  done <<< "$fail_recipes"

  attempt=$((attempt + 1))
done

echo "RESULT: STOPPED [$PLATFORM] (max attempts $MAX_ATTEMPTS reached)" | tee -a "$LOG"
exit 1
