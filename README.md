# skill-repo

My Claude Code skills, grouped into sets. Each skill is installed as a symlink in `~/.claude/skills`, so after a `git pull` every machine is up to date, and an edit in the repo takes effect immediately.

## Layout

```
skill-repo/
├── README.md
├── reviews.json        when each skill was last reviewed, and on which model
├── core/               skill-manager, skill-maintainer
├── bmc/                build-image, gerrit-ci-retrigger
├── engineering/        third-party: mattpocock/skills
├── productivity/       third-party: mattpocock/skills
├── personal/           claude-usage-report, CLAUDE.md (global instructions)
└── scripts/            install.sh, check_skills.py
```

Each set folder has a `README.md` (for people) and a `set.json` (description, `requires`, optional `upstream`). Each skill is a `<set>/<skill>/SKILL.md` and can have test prompts in `<skill>/evals/evals.json` (the same format skill-creator uses).

## New machine

```bash
git clone <this repo> ~/skill-repo
~/skill-repo/scripts/install.sh install core
~/skill-repo/scripts/install.sh claude-md    # link personal/CLAUDE.md as ~/.claude/CLAUDE.md
```

Then ask Claude to "set up my skill sets" (skill-manager), or run `scripts/install.sh list` and install the sets you want.

## Updating CLAUDE.md

`~/.claude/CLAUDE.md` is a link to `personal/CLAUDE.md`, so editing either path changes the repo copy. Commit and push the change, then `git pull` on other machines.

## Keeping skills current

Run `/skill-maintainer` every ~6 months, or after switching to a new model. It:

1. reports which skills are due and why (`scripts/check_skills.py`);
2. fetches the current Anthropic docs for the facts it flagged;
3. in a worktree on a `refresh/<date>` branch, tests each chosen skill against its evals (with the skill and without it), edits it, and re-tests;
4. keeps an edit only if it scores at least as well as the current version, then commits.

It never merges. You review with `git diff HEAD...refresh/<date>` and merge yourself.

## Rules

- Skill names must be unique across all sets, because they share one flat `~/.claude/skills` folder.
- Don't check out other branches in this folder: the installed skills would change immediately. `skill-maintainer` uses `.worktrees/` for that reason.
- Pull upstream changes for third-party sets by hand, and keep the `evals/` folders added here.
