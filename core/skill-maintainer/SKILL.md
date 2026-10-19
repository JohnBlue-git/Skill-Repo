---
name: skill-maintainer
description: Check the skills in ~/skill-repo for staleness (old review, new model, outdated model IDs, prices, dates, frontmatter) and draft tested refreshes on a git branch for the user to review.
disable-model-invocation: true
argument-hint: "[skill names to refresh; empty = report only]"
---

# Skill maintainer

Keeps the skills in `~/skill-repo` current as models and Claude Code change. You draft and test changes; the user reviews and merges. Never merge, push, or edit the main checkout: every installed skill is a symlink into it, so edits there go live immediately.

## 1. Report

Run `python3 ~/skill-repo/scripts/check_skills.py --model <your current model ID>`. A skill is **due** when it was never reviewed, was last reviewed more than 180 days ago, or was reviewed on a different model. The script also lists stale-looking facts and skills with no evals.

Show the user the due skills and their findings, then stop and ask which skills to refresh, unless they were already named in the arguments.

## 2. Get current facts

Fetch the pages relevant to the findings instead of relying on memory:

- Skill frontmatter and features: https://code.claude.com/docs/en/skills
- Model IDs and retirements: https://platform.claude.com/docs/en/about-claude/models/overview
- Prices: https://platform.claude.com/docs/en/about-claude/pricing
- Prompting newer models: https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices

If a page cannot be fetched, say so and leave that fact unchanged.

## 3. Work in a worktree

```bash
B=refresh/$(date +%F)
git -C ~/skill-repo worktree add .worktrees/${B#refresh/} -b $B
```

Edit only inside `~/skill-repo/.worktrees/<date>/`.

## 4. Refresh each chosen skill

For a skill at `<set>/<skill>` with evals in `<skill>/evals/evals.json`:

1. **Test the current version.** For each eval, run two subagents in parallel with the eval's prompt:
   - *with skill*: told to read and follow `~/skill-repo/<set>/<skill>/SKILL.md`;
   - *baseline*: told not to use the Skill tool or read any SKILL.md.

   Both are dry runs. Tell each subagent to describe the commands and steps it would take and to stop before anything with side effects (builds, git push, Gerrit/Jenkins actions, sending messages, writing outside a scratch dir). Grade each response against the eval's `expectations`, as pass or fail per expectation.
2. **Edit** the copy in the worktree:
   - Fix facts confirmed stale in step 2.
   - Remove instructions the baseline already satisfies on this model.
   - Tone emphatic wording down to plain instructions.
   - Change the `description` only if evals show the skill triggering wrongly.
   - Keep the skill's structure and voice.
3. **Test the edited version** the same way, with subagents pointed at the worktree copy.
4. **Keep the edit only if** the edited version passes at least as many expectations as the current one on every eval. Otherwise revert that skill in the worktree and report why.
5. **Record the review** in the worktree's `reviews.json`: `"<skill>": {"date": "YYYY-MM-DD", "model": "<model ID>", "evals": "<passed>/<total>"}`. Record it even when no edit was kept.

Skills without evals get fact fixes only. Say so in the report, and offer to write evals using the format in skill-creator's `references/schemas.md`.

## 5. Commit and hand over

Commit in the worktree, one commit per skill. Then report a table with these columns:

| skill | before | after | baseline | change |
|---|---|---|---|---|

The first three are expectations passed (current version, edited version, baseline), and `change` is a one-line summary of the edit. Below the table, give the commands the user runs to review and merge:

```bash
git -C ~/skill-repo diff HEAD...refresh/<date>
git -C ~/skill-repo merge refresh/<date>
git -C ~/skill-repo worktree remove .worktrees/<date>
```
