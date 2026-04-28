# Scoring formula

Each surviving candidate gets a 0–100 score. Sort descending, take top 5.

## Formula

```
score =  0.40 * gap_score
       + 0.15 * discount_score
       + 0.15 * rating_score
       + 0.10 * color_match_score
       + 0.15 * taste_score
       + 0.05 * body_friendliness_score
```

## Sub-scores (each 0–100)

### gap_score

The biggest signal. "Does this fill a gap in the wardrobe?"

Compute from `wardrobe.json`:
- For the requested category, group owned items by (color_family, pattern, fabric).
- A "gap" is any combination Prazwal does NOT own, weighted by how universally useful it is.

Reference table (gap value if missing):

| Category | Missing item | Gap value |
|---|---|---|
| shirt | white solid (any fabric) | 95 |
| shirt | navy solid (any fabric) | 90 |
| shirt | beige/cream solid linen | 85 |
| shirt | olive solid | 75 |
| shirt | burgundy solid | 65 |
| shirt | white linen | 90 |
| shirt | black solid casual | 60 |
| tshirt | white plain | 85 |
| tshirt | navy plain | 80 |
| tshirt | black plain | 70 |
| jeans | dark indigo straight | 90 |
| jeans | black straight | 75 |
| trousers | navy chinos | 85 |
| trousers | beige chinos | 80 |
| trousers | grey wool-blend formal | 70 |
| shoes | white sneakers | 90 |
| shoes | black formal | 85 |
| shoes | brown leather casual | 75 |

Already owned → gap value drops by 50 per duplicate (e.g., 1 white shirt owned → next white shirt gets 45 instead of 95).

If wardrobe.json is empty (first-time use), every gap value is 100 → all picks score high on this axis until items are logged.

### discount_score

```
discount_score = max(0, min(100, (discount_pct - 30) * 100 / 60))
```

So 30% off = 0, 90% off = 100, capped at 100. Anything below 30% is filtered out by hard rules anyway.

### rating_score

```
if rating >= 4.5:  100
elif rating >= 4.0: 80
elif rating >= 3.5: 50
elif rating == 0:   40   (new product, neutral)
else:               20

# review count bonus
if rating_count >= 100: rating_score += 10
elif rating_count >= 20: rating_score += 5

rating_score = min(100, rating_score)
```

### color_match_score

Read color from `deal.color` and `deal.name`. Match against `profile.color_palette`:

```
if any avoid color matches: dropped (won't reach this stage)
elif any great color matches: 100
elif any good color matches: 60
else: 30  (unknown — neutral)
```

### taste_score

Boost candidates that match learned preferences from `taste.json`:

```
taste_score = 50  # baseline neutral

if deal.brand in taste.summary.favorite_brands: taste_score += 25
if deal.brand in taste.summary.avoided_brands:  taste_score -= 30
if any color in taste.summary.loved_colors matches deal: taste_score += 20
if any color in taste.summary.disliked_colors matches: taste_score -= 25
if pattern matches taste.summary.preferred_patterns: taste_score += 15
if fabric matches taste.summary.preferred_fabrics: taste_score += 10

taste_score = max(0, min(100, taste_score))
```

If taste.json is fresh/empty (no events logged yet), taste_score = 50 for everyone (neutral).

### body_friendliness_score

```
body_friendliness = 50  # baseline

# fit
if 'regular' in deal.name.lower() or 'tailored' in deal.name.lower(): body += 25
elif 'relaxed' in deal.name.lower() or 'comfort' in deal.name.lower(): body += 20
elif 'classic' in deal.name.lower(): body += 15
# slim/skinny dropped at hard-filter, won't reach here

# colour
dark_solids = ['black', 'navy', 'charcoal', 'maroon', 'burgundy', 'forest', 'espresso', 'chocolate', 'dark']
if any(c in (deal.color or '').lower() for c in dark_solids): body += 15
if 'solid' in deal.name.lower(): body += 10

# vertical stripe is slimming
if 'vertical stripe' in deal.name.lower() or 'pin stripe' in deal.name.lower(): body += 10

# horizontal stripe widens (was filtered, but double-check broad stripes that slipped through)
if 'horizontal' in deal.name.lower() or 'broad stripe' in deal.name.lower(): body -= 30

body = max(0, min(100, body))
```

## Edge cases

### When too few candidates pass

If <5 candidates remain after hard filter, don't pad with low-quality picks. Reply with what you have and suggest:
- "Loosen budget by ₹500?"
- "Consider <next-best-color>?"
- "Wait for tomorrow's scrape — new deals daily."

### When everything scores low

If top score is <40, say "Slim pickings today — best available are below 40/100. Worth waiting." Show the top 3 anyway with the warning.

### When a tie

Ties broken by: higher discount → higher rating → lower price.

### When the user provides their own constraints

User-provided constraints OVERRIDE profile defaults for that query only. Example: "find me a slim white shirt" — Prazwal explicitly asked for slim, so don't auto-reject. But add a one-line caution: "Note: slim fit at your build typically pulls — confirm sizing carefully."
