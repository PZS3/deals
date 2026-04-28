# Super Pick — State Files

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
