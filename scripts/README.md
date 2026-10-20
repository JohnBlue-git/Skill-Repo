# Scripts

Both scripts work without Claude.

## install.sh

Links skill sets into `~/.claude/skills` (override with `CLAUDE_SKILLS_DIR`). It also links `personal/CLAUDE.md` as `~/.claude/CLAUDE.md`. It only creates or removes symlinks that point into this repo, and it never touches `~/.claude/skills/synced` or anything else it didn't create. The one exception: `claude-md` replaces a regular `~/.claude/CLAUDE.md` that is byte-identical to the repo copy.

```bash
scripts/install.sh list                  # sets, skills, installed?, recommended here?
scripts/install.sh install core bmc      # link every skill in these sets
scripts/install.sh uninstall bmc         # remove this repo's links for a set
scripts/install.sh status                # ok / BROKEN links, unmanaged entries, repo git status
scripts/install.sh claude-md             # link personal/CLAUDE.md as ~/.claude/CLAUDE.md
```

If `~/.claude/CLAUDE.md` differs from the repo copy, or is a symlink to somewhere else, `claude-md` changes nothing and prints the commands to merge, remove it, and rerun. `status` also reports whether the CLAUDE.md link is in place. Override the target with `CLAUDE_MD`.

A set is recommended when all `requires.commands` are on `PATH` and, if `requires.any_path` is given, at least one of those paths exists.

## check_skills.py

Reports which skills are due for review and the stale-looking facts in them: model IDs, dates that have passed, frontmatter fields not in the known list, emphatic wording, and missing evals. It makes no AI calls and changes no files.

```bash
scripts/check_skills.py --model claude-opus-5-5     # all skills
scripts/check_skills.py build-image tdd             # only these
scripts/check_skills.py --json
```

A skill is due when it has never been reviewed, was last reviewed more than 180 days ago, or was reviewed on a model other than `--model`. Reviews are recorded in `../reviews.json` by `/skill-maintainer`.
