# Super Pick — AI Wardrobe Concierge (Design)

**Date:** 2026-04-28
**Author:** Prazwal + Claude
**Status:** Approved (sections 1–3 in chat); 4–6 written here
**Scope:** Personal use only · clothes & footwear only · terminal-based via Claude Code (Claude Max)

---

## 1. Problem

The existing Deal Finder scrapes Myntra + Ajio nightly and shows 1,300+ deals in a browser grid with text-based color filtering and a basic "Suits You" toggle. It fails at the actual job: when Prazwal hand-picked 11 shirts, **10 violated his own config rules** (slim fit at BMI 32.7, 6/11 checked, 1/11 solid against the "prefer solid" rule, brand concentration). The engine has no model of:
- True product attributes (color/pattern/fit from images, not titles)
- What Prazwal already owns (no wardrobe state)
- Personal taste (no learning from clicks/buys)
- Body-fit reality (slim fit recommendations at BMI 32.7)

## 2. Goals

- Recommendations match Prazwal's body, palette, and wardrobe gaps — automatically
- Vision-based product understanding (no more text-vs-image mismatches)
- Conversational interaction (find, compare, refine, explain, log buys)
- Wardrobe-aware (knows what's owned, recommends to fill gaps, blocks duplicates)
- Self-improving (taste profile updates from chat history)
- $0 incremental cost (uses Claude Max — no Anthropic API)

## 3. Non-Goals

- Multi-user / SaaS (personal only)
- Furniture / home / electronics (clothes & footwear only)
- Browser-based AI chat (terminal only, browser stays as static viewer)
- Real-time scraping (daily cron is enough)
- Photo upload of closet (Myntra order import is enough; can add later)

## 4. Architecture

```
┌──────────────────────────────────────────────────────────────┐
│  Browser (existing, unchanged)                               │
│  index.html → reads deals.json → static visual grid          │
│  Used for: casual browsing, refresh button                   │
└──────────────────────────────────────────────────────────────┘
                             │
                             │ reads deals.json
                             ▼
┌──────────────────────────────────────────────────────────────┐
│  ~/Desktop/Project Code/deals/                               │
│    scraper.py        existing — daily cron, Myntra+Ajio      │
│    deals.json        existing — 1,300+ deals refreshed daily │
│    index.html        existing — browser viewer               │
│    super-pick/       NEW                                     │
│      profile.json    body, climate, season palette           │
│      wardrobe.json   what is owned (seeded from Myntra)      │
│      taste.json      learned preferences (auto-updated)      │
│      history.jsonl   chat-event log for taste mining         │
└──────────────────────────────────────────────────────────────┘
                             │
                             │ loaded by skill
                             ▼
┌──────────────────────────────────────────────────────────────┐
│  ~/.claude/skills/super-pick/                  NEW           │
│    SKILL.md          entry point with frontmatter triggers   │
│    references/                                               │
│      scoring.md      scoring formula & weights               │
│      gap-analysis.md gap detection from wardrobe.json        │
│      vision-checks.md what to look for in product images     │
│      reply-templates.md response formats                     │
│      hard-rules.md   ban list (fit, color, pattern)          │
└──────────────────────────────────────────────────────────────┘
```

**Two surfaces:**
- **Browser** (`index.html`) — visual deal grid, no AI. Existing.
- **Terminal** (`claude` in `deals/`) — AI concierge via the Super Pick skill.

**Vision strategy:** lazy. Skill reads images for the top-5 candidates per query (~40 images/week — well within Max). No bulk pre-processing, no embedding store.

**State updates from chat:** when user says "I bought #2", skill writes to `wardrobe.json` + `taste.json`. No separate logging step.

## 5. Data Model

### 5.1 `super-pick/profile.json` — static, fill once

```json
{
  "physical": {
    "height_cm": 170,
    "weight_kg": 92,
    "bmi": 32.7,
    "build": "stocky",
    "skin_tone": "deep",
    "undertone": "warm-golden"
  },
  "sizes": {
    "shirt": ["XL", "XXL"],
    "tshirt": "XL",
    "trousers": "36",
    "jeans": "36",
    "shoes": "10"
  },
  "climate": {
    "city": "Vijayawada",
    "hot_months": ["Mar","Apr","May","Jun","Jul","Aug","Sep","Oct"],
    "fabric_avoid_when_hot": ["wool","heavy_canvas","fleece"]
  },
  "color_palette": {
    "season": "Deep Autumn",
    "great": ["navy","olive","mustard","burgundy","wine","maroon","forest_green",
              "teal","rust","burnt_orange","chocolate","brown","white","cream",
              "beige","ivory","emerald","terracotta","charcoal","deep_purple",
              "aubergine","royal_blue","camel","khaki","tan","gold","copper",
              "black","dark_grey"],
    "good":  ["grey","blue","green","orange","red","purple","yellow","indigo"],
    "avoid": ["icy_blue","baby_blue","pastel_pink","lavender","ash_grey","neon",
              "fluorescent","light_pink","pale_blue","silver","mauve","peach"]
  },
  "fit_rules": {
    "preferred": ["regular","tailored","relaxed"],
    "avoid":     ["slim","skinny","very_tight","muscle_fit"],
    "rationale": "BMI 32.7 — slim fit pulls and gaps"
  },
  "pattern_rules": {
    "prefer": ["solid","vertical_stripe","subtle_print","micro_check"],
    "avoid":  ["horizontal_stripe","large_bold_print","oversized_check","buffalo_check_oversize"]
  },
  "budget": {
    "shirt_max": 2500,
    "tshirt_max": 1500,
    "trouser_max": 3000,
    "jeans_max": 3000,
    "shoes_max": 5000,
    "jacket_max": 4000
  }
}
```

### 5.2 `super-pick/wardrobe.json` — what is owned

```json
{
  "version": 1,
  "updated_at": "2026-04-28T...",
  "items": [
    {
      "id": "wd_001",
      "category": "shirt",
      "subcategory": "casual",
      "brand": "Indian Terrain",
      "name": "Tartan Checked Linen Shirt",
      "color": "navy",
      "secondary_colors": ["red"],
      "pattern": "tartan_check",
      "fit": "regular",
      "fabric": "linen",
      "season": ["summer","spring"],
      "occasion": ["casual","outing"],
      "purchased": "2026-04-28",
      "source": "Myntra",
      "url": "https://...",
      "image": "https://...",
      "price_paid": 1250
    }
  ]
}
```

### 5.3 `super-pick/taste.json` — auto-updated summary

```json
{
  "version": 1,
  "updated_at": "2026-04-28T...",
  "summary": {
    "loved_colors": ["navy","olive","white"],
    "disliked_colors": ["pastel"],
    "favorite_brands": ["Indian Terrain"],
    "avoided_brands": [],
    "preferred_patterns": ["solid","subtle_check"],
    "preferred_fabrics": ["linen","cotton"],
    "fit_preference": "regular"
  }
}
```

### 5.4 `super-pick/history.jsonl` — append-only event log

```jsonl
{"ts":"2026-04-28T10:00","event":"query","text":"find white linen shirt"}
{"ts":"2026-04-28T10:00","event":"recommend","deal_ids":["myntra_xx","myntra_yy"]}
{"ts":"2026-04-28T10:05","event":"bought","deal_id":"myntra_xx","price":1649}
{"ts":"2026-04-28T11:00","event":"rejected","deal_id":"myntra_zz","reason":"too_pastel"}
```

`rebuild_taste.py` reads events, regenerates `summary` block in `taste.json`. Run nightly via cron, or on demand.

## 6. The Skill — `~/.claude/skills/super-pick/SKILL.md`

### 6.1 Frontmatter

```yaml
---
name: super-pick
description: Use for any shopping query about clothes/footwear — finding deals, comparing picks, buying, logging purchases. Triggers on words like "find", "shirt", "tshirt", "jeans", "shoes", "buy", "deal", "myntra", "ajio", "wardrobe", "outfit", "wear". Reads deals.json + profile.json + wardrobe.json + taste.json. Vision-analyzes top-5 product images. Replies with ranked picks and reasoning.
---
```

### 6.2 Workflow

1. **Load state** (silent): read `profile.json`, `wardrobe.json`, `taste.json`, `deals.json`.
2. **Parse intent**: category, color, occasion, budget, urgency from user message.
3. **Hard filter** (drop instantly per `references/hard-rules.md`):
   - Fit in `profile.fit_rules.avoid` → drop
   - Color in `profile.color_palette.avoid` → drop
   - Pattern in `profile.pattern_rules.avoid` → drop
   - Price > `profile.budget[category]` (unless user overrode)
   - Already-own near-duplicate (same brand + color + pattern + category) → drop, mention it
4. **Score remaining** (per `references/scoring.md`):
   - Wardrobe gap: 40%
   - Discount: 15%
   - Rating + review count: 15%
   - Color match: 10%
   - Taste affinity: 15%
   - Body friendliness: 5%
5. **Vision pass on top 5**: `Read` each product image → verify color/pattern/fit. Catch text-vs-image mismatches.
6. **Reply** in template (per `references/reply-templates.md`):
   ```
   Top picks for "<query>":

   1. <Brand> <Name> — ₹<price> (<discount>% off)
      Why: <1–2 sentences: gap filled, fit, fabric, occasion fit>
      ★ <rating> (<count>)  ·  <buy_url>

   2. ...

   ✗ Rejected: <name> — <reason>

   Want details on any? Buy one? Or refine?
   ```
7. **Log** the query + recommend events to `history.jsonl`.
8. **State updates from chat**:
   - "I bought #1" → append `bought` event, add to `wardrobe.json`
   - "Reject #2, color too pale" → log `rejected` event with reason
   - Periodically (every 10 events), run `rebuild_taste.py` logic inline to refresh summary

### 6.3 Reference files (loaded on demand)

- `scoring.md` — full formula, weight tuning rationale, edge cases
- `gap-analysis.md` — how to compute "what's missing" from wardrobe.json (count solids by color, count fits, count fabrics)
- `vision-checks.md` — for each top-5 image, what to verify (true color, pattern type, fit visible, fabric texture, model body type if visible)
- `reply-templates.md` — formats for browse / compare / buy-confirm / explain / refine
- `hard-rules.md` — ban list with rationale (so Claude can explain rejections)

## 7. Workflows (chat patterns)

### 7.1 Find + buy

```
$ cd ~/Desktop/Project\ Code/deals
$ claude
> find me a solid white linen shirt for my brother's wedding under 2K

[skill auto-loads, reads state, filters, scores, vision-checks top 5, replies with 5 ranked picks + 1 rejected duplicate]

> ok bought #1 from Myntra

[skill appends to wardrobe.json, logs bought event, confirms with new total: "wd_037 added. You now own 18 shirts (5 solid, 13 patterned)."]
```

### 7.2 Compare two

```
> compare #2 vs #4 — which one for office?

[skill reads both images again with focus on formal-ness, fabric weight, fit visibility on model. Replies with side-by-side reasoning + verdict]
```

### 7.3 Refine

```
> show only linen, regular fit, under 1500

[skill re-runs filter+score with stricter constraints, replies with new top 5]
```

### 7.4 Explain a rejection

```
> why did you reject the M&H one earlier?

[skill quotes hard-rules.md + wardrobe duplicate detection]
```

### 7.5 Wardrobe queries (no shopping)

```
> what white shirts do I own?
> what's my biggest wardrobe gap right now?
> show me everything from Indian Terrain

[skill answers from wardrobe.json without touching deals.json]
```

## 8. Wardrobe Import (one-time setup, in-chat)

No separate script — handled by skill workflow:

1. User logs into Myntra in browser → opens **My Account → Orders → All orders** page.
2. User saves page as HTML: `~/Desktop/myntra_orders.html`.
3. In Claude Code: `> import my orders from ~/Desktop/myntra_orders.html`
4. Skill reads the HTML (Read tool), extracts product URLs from order list.
5. For each URL, fetches the Myntra product page (WebFetch tool), pulls brand/name/color/image/price-paid.
6. For each product image, reads it (Read tool) and vision-extracts pattern + fit + fabric.
7. Writes all entries to `wardrobe.json`.
8. Reports: "Imported 47 items. Open `wardrobe.json` to spot-check or correct any."

For non-Myntra purchases (Ajio, in-store), user adds entries by chatting: "log this shirt I bought offline — Allen Solly white linen XL ₹1800". Skill writes the entry.

## 9. Failure Modes

| Failure | Behavior |
|---|---|
| `deals.json` >24h stale | Skill warns at top of reply: "Deals haven't refreshed since X. Run `python scraper.py` to update." |
| Product image URL 404 | Skill notes "Image unavailable for #N — recommendation based on text only" |
| `wardrobe.json` malformed | Skill refuses to write, prints diff, asks user to fix or restore from git |
| `scraper.py` errored last run | Skill detects via empty/no recent entries, suggests rerun |
| `profile.json` missing | Skill walks user through quick onboarding (asks 5 questions, generates default) |
| Vision read fails (rate limit, no internet) | Skill falls back to text-only ranking, flags reduced confidence |
| User contradicts past taste ("but I love pastel now") | Skill asks confirmation, then logs `taste_change` event with override |

## 10. Migration / Cleanup of Existing Code

Existing files to keep as-is:
- `scraper.py` — daily cron continues
- `deals.json` — read-only input to skill
- `index.html` — browser viewer unchanged
- `server.py` — refresh button unchanged
- `config.json` — kept for scraper

Existing `index.html` color logic (`COLOR_GREAT`, `COLOR_GOOD`, `COLOR_AVOID`, `getBestScore`) becomes redundant once skill takes over recommendations, but leave in place — browser is just a viewer.

`shirt_images/` directory: keep, useful for vision testing.

## 11. Out of Scope (explicit non-goals for v1)

- Outfit pairing recommendations ("this shirt with which trousers?") — possible v2 if wardrobe data is rich
- Price-drop alerts on watch-listed items — possible v2
- Wear logging / cost-per-wear analytics — possible v2
- Image upload of closet — possible v2
- Sharing recommendations with friends — never (personal only)
- Auto-buy on price drop — never (user always confirms)

## 12. Success Criteria

- After v1 ships, when Prazwal asks "find me a wedding shirt", **0 of top 5 picks violate** his profile.json hard rules
- Wardrobe seeded with all his Myntra purchases (50+ items expected)
- Taste profile reflects actual preferences within 2 weeks of use
- One end-to-end query: terminal-typed → reply → "bought #1" → wardrobe.json updated, in <30 seconds
