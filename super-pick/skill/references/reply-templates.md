# Reply templates

Use these formats. Don't drift — Prazwal expects predictable structure.

## 1. Browse / find

When user says: "find me X", "show me Y", "any good Z deals?"

```
Top picks for "<exact user query>":

1. <Brand> <Short Name> — ₹<price> (<discount>% off, was ₹<mrp>)
   Why: <one sentence on wardrobe gap or color match>. <Optional second sentence on fabric/occasion/fit detail.>
   Fit: <regular/relaxed/tailored>  ·  Fabric: <linen/cotton/etc>  ·  Color: <true color from vision>
   ★ <rating> (<rating_count> reviews)
   Buy: <full URL>

2. <Brand> <Short Name> — ₹<price> (<discount>% off)
   Why: ...
   ...

3. ...
4. ...
5. ...

✗ Skipped: <Brand> <Name> — <reason>
   [include 1–3 interesting skips, e.g., "duplicate of wd_004" or "fabric was polyester per image" or "image showed teal, not navy"]

Want details on any? Buy one? Or refine?
```

If <5 candidates passed:

```
Slim pickings for "<query>" — only <N> matched all your rules.

1. ...
2. ...

To see more, try: loosen budget / accept "good" colors / wait for tomorrow's scrape.
```

## 2. Compare two

When user says: "compare #2 vs #4", "which one is better?", "#1 or #3 for office?"

```
<Brand A> #N vs <Brand B> #M for <occasion>:

| Aspect | #N <Brand A> | #M <Brand B> |
|---|---|---|
| Price | ₹X | ₹Y |
| Fit | regular | tailored |
| Fabric | linen | cotton-linen |
| Color | white | off-white |
| Wedding-grade? | yes — premium | yes — slightly casual |

Verdict: <#N or #M>. <One-line reason that matters most for the use case.>
```

## 3. Buy confirmation

When user says: "I bought #N", "buying #N", "ordered #N", "got #N"

```
Logged. wd_<NEW_ID> added to wardrobe.

You now own:
- <category>: <count> total (<count_solid> solid, <count_patterned> patterned)
- Wardrobe gap update: <one line on what's now closer to ideal, or what's still missing>

Anything else?
```

## 4. Reject feedback

When user says: "reject #N because <reason>"

```
Noted. Logged rejection of #<N> (reason: <reason>).
This will reduce the score of similar items going forward.
```

## 5. Explain a pick

When user says: "why #2?", "explain #1", "tell me more about #3"

```
#<N>: <Brand> <Name>

Score breakdown (out of 100):
- Wardrobe gap: <X>/100  (<one-line: e.g., "fills your missing white linen slot">)
- Discount: <X>/100      (<discount>% off, ₹<savings> savings)
- Rating: <X>/100        (★ <rating> from <count> reviewers)
- Color match: <X>/100   (<great/good/unknown> for Deep Autumn palette)
- Taste fit: <X>/100     (<matches/neutral on/against your past picks>)
- Body friendly: <X>/100 (<fit and color slimming notes>)

Composite: <total>/100 — ranked #<N> of 5.

Fabric per image: <linen/cotton/etc>. Construction: <notes>. Suitable for: <occasion list>.
```

## 6. Wardrobe query

When user says: "what do I own in <X>?", "show my <category>", "what's in my closet?"

```
Your <category>:

| ID | Brand | Color | Pattern | Fit | Fabric | Bought |
|---|---|---|---|---|---|---|
| wd_001 | Indian Terrain | navy | tartan check | regular | linen | 2026-04-28 |
| ... |

Total: <N> items.
```

## 7. Gap analysis

When user says: "what's my biggest gap?", "what should I buy next?", "what am I missing?"

(Use format from `gap-analysis.md` — repeating here for visibility.)

```
Your biggest wardrobe gaps right now:

1. <Item> (own <N>, target <M>) — <utility reason>
2. ...
3. ...
4. ...
5. ...

Rebalance candidates (you over-own these):
- <Item> (own <N>, target <M>) — pause buying
```

## 8. Onboarding (only if profile is incomplete)

```
Welcome to Super Pick. I need 5 quick things to start recommending well:

1. Height (cm) and weight (kg)?
2. Shirt size, trouser waist (in), shoe UK size?
3. City + climate (so I get fabric right)?
4. Skin tone (fair / wheatish / deep) and undertone (warm / cool / neutral)? Or send a selfie.
5. Roughly how much do you spend on clothes per month?

I'll fill in the rest with smart defaults — you can edit profile.json later.
```

## 9. Stale data warning (prepend if applicable)

```
⚠️ Deals last refreshed <X> hours ago. Consider running `python scraper.py` for fresh data.

[then proceed with normal reply]
```

## 10. No-results edge case

When zero candidates pass all filters:

```
Nothing in today's deals matches that exactly.

Candidates that came close but failed:
- <Brand> <Name> — failed: <reason>
- <Brand> <Name> — failed: <reason>

Suggestions:
- Refresh deals: `python scraper.py` (might pull new stock)
- Loosen one rule: <which one>?
- Try a different category: <suggestion>?
```

## Style rules for all replies

- **Lead with the answer.** Don't preamble.
- **Use the user's language.** If they said "shacket", call it a shacket. If they said "wedding shirt", call it a wedding shirt.
- **No headers in plain conversation.** Use them only in long replies (compare, explain, gap analysis).
- **Show prices in INR with ₹ symbol.** Use Indian comma format if needed (₹1,49,500 not ₹149,500).
- **Numbered picks.** Always 1, 2, 3 — Prazwal will reference them ("buy #2").
- **Always end with a follow-up cue.** "Want details? Buy? Refine?" — keeps the conversation moving.
- **Never thank, never apologize.** Just answer.
- **Never use emojis** in replies. Plain text only.
- **Markdown tables OK in compare/explain/wardrobe.** Plain text in browse/buy/reject.
