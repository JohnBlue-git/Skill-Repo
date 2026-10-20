# Personal

- **[claude-usage-report](./claude-usage-report/SKILL.md)**: daily/weekly/monthly Claude Code usage and cost dashboard built from local transcripts.
- **[CLAUDE.md](./CLAUDE.md)**: my global Claude Code instructions, loaded in every project. Not a skill, so `install.sh install personal` does not install it. Run `scripts/install.sh claude-md` instead, which links it as `~/.claude/CLAUDE.md`.

  To update it, edit either path (they are the same file), then commit and push. Other machines pick it up with `git pull`; they don't need to rerun anything.
