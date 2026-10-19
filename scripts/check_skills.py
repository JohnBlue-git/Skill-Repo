#!/usr/bin/env python3
"""Report which skills in this repo are due for a refresh, and the stale facts in them.

No AI involved: this only flags things for skill-maintainer (or you) to look at.

Usage: check_skills.py [--model CURRENT_MODEL_ID] [skill ...]
"""
import argparse
import datetime
import json
import os
import re
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
REVIEW_DAYS = 180
# Frontmatter fields documented for Claude Code skills (code.claude.com/docs/en/skills).
# Anything else is flagged for checking against the current docs, not treated as an error.
KNOWN_FIELDS = {
    "name", "description", "disable-model-invocation", "user-invocable", "allowed-tools",
    "argument-hint", "arguments", "context", "agent", "background", "paths", "model",
    "license", "hooks",
}
MODEL_ID = re.compile(r"\bclaude-(?:opus|sonnet|haiku|fable|mythos)-[0-9][0-9a-z-]*\b")
DEADLINE = re.compile(r"\b(?:until|through|after|before|expires?|ends?|by)\s+(\d{4}-\d{2}-\d{2})\b", re.I)
EMPHATIC = re.compile(r"\b(?:CRITICAL|IMPORTANT|MUST|NEVER|ALWAYS)\b")
TEXT_SUFFIXES = {".md", ".json", ".py", ".sh", ".txt", ".yaml", ".yml", ".html"}


def frontmatter(skill_md):
    lines = skill_md.read_text().splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    fields = {}
    for line in lines[1:]:
        if line.strip() == "---":
            return fields
        m = re.match(r"^([A-Za-z][\w-]*):\s*(.*)$", line)
        if m:
            fields[m.group(1)] = m.group(2).strip().strip('"')
    return None


def skills():
    for set_json in sorted(REPO.glob("*/set.json")):
        for skill_md in sorted(set_json.parent.glob("*/SKILL.md")):
            yield set_json.parent.name, skill_md.parent


def recent_models(days=14):
    """Models seen in Claude Code transcripts modified in the last `days` days."""
    seen = {}
    cutoff = time.time() - days * 86400
    for f in Path.home().glob(".claude/projects/*/*.jsonl"):
        if f.stat().st_mtime < cutoff:
            continue
        with open(f, errors="replace") as fh:
            for line in fh:
                if '"model"' not in line:
                    continue
                try:
                    model = json.loads(line).get("message", {}).get("model")
                except (json.JSONDecodeError, AttributeError):
                    continue
                if model and model.startswith("claude-"):
                    seen[model] = seen.get(model, 0) + 1
    return sorted(seen.items(), key=lambda kv: -kv[1])


def check(set_name, skill_dir, review, current_model, today):
    findings = []
    fm = frontmatter(skill_dir / "SKILL.md")
    if fm is None:
        findings.append("SKILL.md has no frontmatter block")
        fm = {}
    if fm.get("name") and fm["name"] != skill_dir.name:
        findings.append(f"frontmatter name '{fm['name']}' != folder '{skill_dir.name}'")
    if not fm.get("description"):
        findings.append("missing description")
    elif len(fm["description"]) > 1024:
        findings.append(f"description is {len(fm['description'])} chars (limit 1024)")
    for key in sorted(set(fm) - KNOWN_FIELDS):
        findings.append(f"frontmatter field '{key}' not in known list; check current docs")

    for f in sorted(skill_dir.rglob("*")):
        if not f.is_file() or f.suffix not in TEXT_SUFFIXES or "evals" in f.relative_to(skill_dir).parts:
            continue
        text = f.read_text(errors="replace")
        rel = f.relative_to(skill_dir)
        ids = sorted(set(MODEL_ID.findall(text)))
        if ids:
            findings.append(f"{rel}: model IDs {', '.join(ids)}")
        for d in sorted(set(DEADLINE.findall(text))):
            if d < today:
                findings.append(f"{rel}: date {d} has passed")
    n = len(EMPHATIC.findall((skill_dir / "SKILL.md").read_text()))
    if n:
        findings.append(f"SKILL.md: {n} emphatic words (CRITICAL/MUST/NEVER/...)")

    evals_file = skill_dir / "evals" / "evals.json"
    n_evals = len(json.loads(evals_file.read_text()).get("evals", [])) if evals_file.exists() else 0
    if n_evals == 0:
        findings.append("no evals/evals.json; only fact checks are possible")

    if not review:
        due = "never reviewed"
    elif (datetime.date.fromisoformat(today) - datetime.date.fromisoformat(review["date"])).days > REVIEW_DAYS:
        due = f"last reviewed {review['date']} (> {REVIEW_DAYS} days)"
    elif current_model and review.get("model") != current_model:
        due = f"reviewed on {review.get('model')}, now on {current_model}"
    else:
        due = ""
    return {"set": set_name, "skill": skill_dir.name, "due": due, "evals": n_evals,
            "review": review, "findings": findings}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", help="model ID you are on now; a skill reviewed on another model is due")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("only", nargs="*", help="limit to these skill names")
    args = ap.parse_args()

    reviews_file = REPO / "reviews.json"
    reviews = json.loads(reviews_file.read_text()) if reviews_file.exists() else {}
    today = datetime.date.today().isoformat()
    results = [check(s, d, reviews.get(d.name), args.model, today)
               for s, d in skills() if not args.only or d.name in args.only]
    models = recent_models()

    if args.json:
        json.dump({"today": today, "recent_models": models, "skills": results}, sys.stdout, indent=2)
        return
    print(f"Models used in the last 14 days: {', '.join(f'{m} ({n})' for m, n in models) or 'none found'}")
    print(f"Due = never reviewed, reviewed > {REVIEW_DAYS} days ago, or reviewed on a different model.\n")
    for r in results:
        print(f"{r['set']}/{r['skill']}  evals={r['evals']}  {'DUE: ' + r['due'] if r['due'] else 'ok'}")
        for f in r["findings"]:
            print(f"    - {f}")


if __name__ == "__main__":
    main()
