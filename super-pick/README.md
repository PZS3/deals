# Super Pick

Personal AI wardrobe concierge. Runs in Claude Code (Claude Max), $0/month.

## Layout

```
super-pick/
  setup.sh              one-time symlink installer
  README.md             this file
  profile.json          your body, palette, fit/budget rules
  wardrobe.json         what you own
  taste.json            auto-summarised preferences
  history.jsonl         append-only event log
  skill/                source of the Claude Code skill
    SKILL.md            the brain (auto-loads on shopping queries)
    references/         scoring, gap analysis, vision checks, etc.
```

The `skill/` folder is symlinked into `~/.claude/skills/super-pick/` by `setup.sh`,
so Claude Code finds it automatically.

## First-time setup

```bash
cd ~/Desktop/Project\ Code/deals
./super-pick/setup.sh
```

Then open Claude Code in this directory and ask a shopping question:

```bash
claude
> find me a navy linen shirt under 2000
```

The skill auto-loads, reads your profile + wardrobe + deals, and replies with
ranked picks.

## State files

These four files hold all of Super Pick's memory. Edit them carefully.

| File | Purpose | Edited by |
|---|---|---|
| `profile.json` | Body, sizes, climate, color palette, fit/pattern rules, budget | You (manually). Skill never overwrites. |
| `wardrobe.json` | Every item you own | Skill (on `bought`/`log offline`). You spot-check. |
| `taste.json` | Auto-summarised preferences from your event history | Skill (auto). Never edit manually. |
| `history.jsonl` | Append-only event log (queries, recommends, buys, rejects) | Skill (auto). Append-only. |

## Backup

Everything here is git-tracked. To restore:

```bash
cd ~/Desktop/Project\ Code/deals
git log -- super-pick/
git checkout <sha> -- super-pick/wardrobe.json
```

## Onboarding the wardrobe

1. Log into Myntra → My Account → Orders → All orders (load all pages).
2. Save page as HTML to `~/Desktop/myntra_orders.html`.
3. Open Claude Code in this directory: `cd ~/Desktop/Project\ Code/deals && claude`.
4. Type: `import my orders from ~/Desktop/myntra_orders.html`
5. Skill imports → vision-analyses each → writes to `wardrobe.json`.
6. Spot-check the file. Done.

For non-Myntra items, just say: `log this shirt — Allen Solly white linen XL ₹1800`.
