---
name: skill-manager
description: Choose which skill sets from ~/skill-repo are installed into ~/.claude/skills — show the sets, recommend the ones that fit this machine, then install or uninstall what the user picks. Use when the user asks which skills or skill sets are installed or available, wants to add or remove a skill set, or is setting up skills on a new machine.
---

# Skill manager

Skills live in `~/skill-repo`, grouped into sets (top-level folders with a `set.json`). Installing a set symlinks each of its skills into `~/.claude/skills/<skill>`. All changes go through `~/skill-repo/scripts/install.sh`; do not create or delete links by hand.

1. Run `~/skill-repo/scripts/install.sh list`. Each set shows how many of its skills are installed, whether it is recommended on this machine (from `requires` in its `set.json`), and its description.
2. Show the user a short table: set, installed/partial/not installed, recommended or not, description. Ask which sets to install and which to uninstall (use AskUserQuestion with multi-select when available). Change nothing until they choose.
3. Run `install.sh install <set>...` and/or `install.sh uninstall <set>...`.
4. If a skill is reported `SKIPPED` because the name is already taken, show that line to the user and ask what to do. Do not remove the existing entry yourself.
5. Run `install.sh status` and report any `BROKEN` links. Tell the user that newly linked skills may need a new session to show up.

Uninstalling `core` removes this skill too; confirm with the user first if they pick it.

To add a new set: create `~/skill-repo/<set>/set.json` and a `README.md`, then move skills into it. `set.json` fields:

```json
{
  "description": "One line shown in the list",
  "requires": { "commands": ["repo"], "any_path": ["~/Vera", "~/OKS"] },
  "upstream": "where third-party skills came from (optional)"
}
```

`requires` is optional; a set with none is recommended everywhere.
