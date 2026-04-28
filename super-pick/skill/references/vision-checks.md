# Vision checks — what to verify in product images

Run on every top-5 candidate before showing to user. The point: catch text-vs-image mismatches that the text-based scraper missed.

## How to read the image

The deal record has `deal.image` — a URL like `http://assets.myntassets.com/...jpg`. Use the `Read` tool with that URL. If Read on remote URL fails, download to `/tmp/super-pick-img-<deal.id>.jpg` first via WebFetch, then Read.

## Checklist (run all, fail if any fail)

### 1. True color

Look at the dominant color of the garment in the image. Compare to:
- `deal.color` field
- color words in `deal.name`

**Pass:** image color matches the text. (e.g., title says "navy", image is dark blue)

**Fail:** image is sky blue but title says "blue" (Prazwal's `avoid` list includes pale blues — this is the most common mistake). Demote.

**Common failures to flag:**
- "Blue" → image is icy blue, baby blue, sky blue → DROP (color avoid)
- "Pink" → image is pastel pink → DROP
- "Green" → image is mint or lime → DROP
- "Grey" → image is ash/silver/pale grey → DROP
- "Purple" → image is lavender → DROP

### 2. Pattern

Look at the actual pattern on the fabric:

| Visual pattern | Allowed? |
|---|---|
| Solid (no pattern) | Yes — bonus |
| Vertical stripes | Yes — bonus |
| Pin stripes (subtle vertical) | Yes |
| Micro check / small graph check | Yes |
| Medium check (gingham-ish) | Tolerate |
| Tartan / large plaid | Caution — only if it's a single tartan shirt for variety |
| Buffalo check (large) | DROP if oversized |
| Horizontal stripes | DROP |
| Broad horizontal stripes | DROP — widens visually |
| Loud floral (large prints) | DROP |
| Subtle floral (small) | Tolerate |
| Geometric subtle | Tolerate |
| Logo-heavy print (brand text everywhere) | DROP |

If image shows a pattern that text didn't reveal (e.g., title says "casual shirt" but image is a loud floral), use the image.

### 3. Fit (visible on model)

If the image shows a model wearing the shirt:

| Visual cue | Likely fit |
|---|---|
| Fabric drapes loosely, no pulling | Regular / relaxed — Pass |
| Fabric falls cleanly, lightly tailored | Tailored — Pass |
| Fabric pulls across chest, button gaps | Slim / skinny — DROP |
| Sleeves hug bicep tightly | Slim / muscle fit — DROP |
| Generous through chest and waist | Relaxed / comfort — Pass (bonus for Prazwal) |
| Boxy / oversized | Pass (relaxed) |

If model isn't visible (flat lay), rely on text: title containing "slim/skinny/muscle" → DROP.

### 4. Fabric (visible texture)

Skin in image + texture:

| Visible texture | Likely fabric |
|---|---|
| Slubby weave, slight wrinkles | Linen — bonus in hot_months |
| Smooth, slight sheen | Cotton or cotton blend — Pass |
| Very smooth, plastic-like sheen | Polyester / synthetic — Caution (heat in Vijayawada) |
| Heavy weave, thick | Canvas / heavy cotton — DROP if hot_months |
| Knitted texture | Knit shirt or jersey — Pass for casual |

### 5. Construction details (bonus, optional)

- Buttons: real buttons / contrast buttons → quality cue
- Collar: spread / button-down / band → match to occasion
- Pockets: chest pocket presence → casual indicator
- Hem: curved (untucked) vs straight (tucked) → casual vs office

### 6. Female-targeted product (drop)

If model is female, OR title contains "women" / "girls" / "ladies" / "her" → DROP. Scraper occasionally pulls women's items in unisex categories.

## Reply integration

If a candidate fails vision check, **demote it** and pick the next-highest scoring item. In the reply, optionally mention the demotion if interesting:

```
✗ Skipped: Indian Terrain "navy linen shirt" (#myntra_xx)
  Image showed teal, not navy. Teal is good but not what you asked for.
```

## When vision read fails (rate limit, no internet, broken image)

Note in the reply:
```
Note: Couldn't load images for #2 and #4. Recommendations based on text only — confirm fit/colour by visiting the product page.
```

Don't crash. Continue with text-only ranking.
