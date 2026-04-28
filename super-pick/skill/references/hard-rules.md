# Hard rules — never break these

These are non-negotiable filters. Apply BEFORE scoring. A candidate that violates any of these is dropped, not demoted.

## 1. Fit bans (never recommend)

These fits don't work at BMI 32.7:

- `slim`
- `slim fit`
- `super slim`
- `extra slim`
- `skinny`
- `muscle fit`
- `body fit`
- `very tight`

**Detection:** lowercase the deal `name`, check for any of the above as a substring. Also check `subcategory` field if present.

**Exception:** if user explicitly asks for slim ("find me a slim white shirt"), allow it but warn: "Note — slim fit at your build typically pulls. Confirm sizing carefully."

**Why:** Prazwal is 92kg, BMI 32.7. Slim/skinny fits cause button-gapping at the chest, fabric pulling at the belly, sleeve tightness at biceps. He'll regret the purchase. Regular and tailored fits sit cleanly.

## 2. Color bans (never recommend)

From `profile.color_palette.avoid` — for a Deep Autumn complexion (deep skin, warm-golden undertone), pastels and icy/silvery tones wash out the skin.

Banned colors (substring match in `deal.color` or `deal.name`):

- `icy blue`, `baby blue`, `sky blue`, `light blue`, `powder blue`, `pale blue`
- `pastel pink`, `light pink`, `blush`, `rose`, `baby pink`
- `lavender`, `lilac`, `mauve`
- `ash grey`, `light grey`, `pale grey`, `silver`
- `neon`, `fluorescent`, `lime green`, `hot pink`
- `peach`, `coral pink`, `salmon`
- `mint`, `aqua`

**Detection priority:** check the more specific phrase first (e.g., `icy blue` before `blue`). A shirt described as just `blue` is fine; `light blue` is banned.

**Vision check:** if title says "blue" but the image is clearly icy/baby blue, drop in vision pass.

**Why:** Pastels on warm-toned dark skin look flat and washed out. Icy/silvery cool tones fight the warm undertone. The list comes from a Deep Autumn palette analysis.

## 3. Pattern bans (never recommend)

- `horizontal stripe` (any size)
- `broad horizontal stripe`
- `large bold print` (loud florals, oversized graphics)
- `oversized check` / `buffalo check oversize`
- Logo-heavy prints (entire shirt covered in brand text)

**Detection:** keyword match in `deal.name`. Vision pass confirms.

**Why:** Horizontal stripes widen visually. Large patterns and loud prints are unflattering on stocky builds and at age 28+ in formal/smart-casual contexts.

## 4. Budget enforcement

`deal.price > profile.budget_inr[<category>_max]` → drop.

Override: if user explicitly says "find me a shirt under 5000" or "splurge on a wedding shirt", their stated budget overrides profile budget.

## 5. Wardrobe duplicate

A "near-duplicate" of an existing wardrobe item:
- Same category AND same brand AND same color family AND same pattern type

Example: if wardrobe has `Indian Terrain navy tartan-check linen shirt`, drop any new `Indian Terrain navy check shirt` candidate. But a `US Polo navy check shirt` would NOT be a duplicate (different brand).

When dropped for duplicate, mention it in the reply: `✗ Skipped: <name> — duplicate of wd_<id>`.

## 6. Hot-month fabric ban

If `current_month` is in `profile.climate.hot_months` (Mar-Oct in Vijayawada):

Drop any deal whose `name` contains:
- `wool`
- `heavy canvas`
- `fleece`
- `thick corduroy`
- `puffer` (jacket)
- `leather` (jacket)

Exception: if user explicitly asks ("find me a wool blazer for a winter trip to Manali"), allow it. Note: "this is heavy fabric — confirm it's for cooler climate use".

## 7. Wrong category

`deal.category != intent.category` → drop.

Trivial check, but catches cases where the scraper miscategorized.

## 8. Women's items (sometimes get scraped)

If `deal.name` or page contains: `women`, `women's`, `ladies`, `girls`, `her` (as a possessive in the name) → drop.

Vision pass: if model in image is female → drop.

## 9. Out of stock or no-size cases

If `deal.sizes_available` is provided and Prazwal's size (XL or XXL for shirts) is NOT in the list → drop.

If `deal.sizes_available` is empty/missing → don't drop, but note in reply: "size availability not confirmed — verify on Myntra".

## 10. Stale or broken deal

- `deal.image` is empty or 404 → don't drop entirely, but vision check fails → drop.
- `deal.url` is empty → drop (can't buy it).
- `deal.price` is null or 0 → drop.
- `deal.discount_pct` < 30 → drop (default `min_discount_pct` from config).

## Edge: user explicitly overrides

If user says "I don't care about my color rules, find me a sky blue shirt":

- Show the candidates
- Add a single-line caveat at top: "You overrode the Deep Autumn palette — consider this a one-off."
- Do NOT change `profile.json` permanently unless user says "update my profile to allow X" with confirmation.

## Edge: gift mode

If user says "find a shirt for my brother / dad / friend":

- Skip Prazwal's hard rules (different person)
- Ask: "What's their build / size / color preference?"
- Apply only the budget rule and quality rules (rating, discount)
- Don't log the recommendation to taste.json (it's not Prazwal's preference)
