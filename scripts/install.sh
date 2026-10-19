#!/usr/bin/env bash
# Link skill sets from this repo into ~/.claude/skills, one symlink per skill.
# A set is any top-level folder with a set.json; a skill is any folder inside it with a SKILL.md.
# Only symlinks that point into this repo are ever created or removed.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="${CLAUDE_SKILLS_DIR:-$HOME/.claude/skills}"

usage() {
  cat <<EOF
Usage: $(basename "$0") <command> [set...]
  list                  sets, their skills, install state, and whether recommended here
  install <set>...      link every skill in each set into $DEST
  uninstall <set>...    remove this repo's links for each set
  status                check installed links (ok / broken) and list unmanaged entries
EOF
}

sets() { for f in "$REPO"/*/set.json; do basename "$(dirname "$f")"; done; }
skills_of() { for f in "$REPO/$1"/*/SKILL.md; do [ -e "$f" ] && basename "$(dirname "$f")"; done; }
check_set() { [ -f "$REPO/$1/set.json" ] || { echo "no such set: $1 (try: list)" >&2; exit 1; }; }

# Recommended when every listed command exists and, if any_path is given, at least one path exists.
is_recommended() {
  local j="$REPO/$1/set.json" c p
  for c in $(jq -r '.requires.commands // [] | .[]' "$j"); do
    command -v "$c" >/dev/null || return 1
  done
  [ "$(jq '.requires.any_path // [] | length' "$j")" -eq 0 ] && return 0
  for p in $(jq -r '.requires.any_path[]' "$j"); do
    [ -e "${p/#\~/$HOME}" ] && return 0
  done
  return 1
}

# installed | missing | conflict (the name is taken by something not from this set)
link_state() {
  local l="$DEST/$2"
  if [ -L "$l" ] && [ "$(readlink "$l")" = "$REPO/$1/$2" ]; then echo installed
  elif [ -e "$l" ] || [ -L "$l" ]; then echo conflict
  else echo missing; fi
}

cmd_list() {
  local s k st n_in n_all rec
  for s in $(sets); do
    n_in=0; n_all=0
    for k in $(skills_of "$s"); do
      n_all=$((n_all + 1))
      [ "$(link_state "$s" "$k")" = installed ] && n_in=$((n_in + 1))
    done
    if is_recommended "$s"; then rec="recommended"; else rec="not recommended here"; fi
    printf '%-14s %d/%d installed, %s — %s\n' "$s" "$n_in" "$n_all" "$rec" "$(jq -r .description "$REPO/$s/set.json")"
    for k in $(skills_of "$s"); do
      st=$(link_state "$s" "$k")
      [ "$st" = conflict ] && st="conflict ($DEST/$k exists)"
      printf '    %-32s %s\n' "$k" "$st"
    done
  done
}

cmd_install() {
  local s k rc=0
  mkdir -p "$DEST"
  for s in "$@"; do
    check_set "$s"
    for k in $(skills_of "$s"); do
      case "$(link_state "$s" "$k")" in
        installed) echo "ok       $k" ;;
        missing)   ln -s "$REPO/$s/$k" "$DEST/$k"; echo "linked   $k" ;;
        conflict)  echo "SKIPPED  $k: $DEST/$k already exists ($(readlink "$DEST/$k" 2>/dev/null || echo 'not a symlink'))" >&2; rc=1 ;;
      esac
    done
  done
  return $rc
}

cmd_uninstall() {
  local s k
  for s in "$@"; do
    check_set "$s"
    for k in $(skills_of "$s"); do
      if [ "$(link_state "$s" "$k")" = installed ]; then rm "$DEST/$k"; echo "removed  $k"; fi
    done
  done
}

cmd_status() {
  local l t rc=0
  for l in "$DEST"/*; do
    [ -e "$l" ] || [ -L "$l" ] || continue
    [ "$(basename "$l")" = synced ] && continue   # managed by claude.ai sync
    t=$(readlink "$l" || true)
    if [[ -L "$l" && "$t" == "$REPO"/* ]]; then
      if [ -f "$t/SKILL.md" ]; then echo "ok         $(basename "$l") -> ${t#"$REPO"/}"
      else echo "BROKEN     $(basename "$l") -> $t" >&2; rc=1; fi
    else
      echo "unmanaged  $(basename "$l")${t:+ -> $t}"
    fi
  done
  echo "--- repo: $(git -C "$REPO" branch --show-current 2>/dev/null)"
  git -C "$REPO" status --short 2>/dev/null | head -20
  return $rc
}

case "${1:-}" in
  list)      cmd_list ;;
  install)   shift; [ $# -gt 0 ] || { usage; exit 1; }; cmd_install "$@" ;;
  uninstall) shift; [ $# -gt 0 ] || { usage; exit 1; }; cmd_uninstall "$@" ;;
  status)    cmd_status ;;
  *)         usage; exit 1 ;;
esac
