# Gap analysis — what's missing in the wardrobe

Use this when:
- Computing `gap_score` for a candidate (Step 4 of main workflow)
- User asks "what's my wardrobe gap?"
- User asks "what should I buy next?"

## Algorithm

1. Read `wardrobe.json` items.
2. Group by `category` → `color_family` → `pattern` → `fabric`.
3. Compare against the **ideal capsule wardrobe** below.
4. Output the missing items, ranked by ideal-vs-actual gap × utility weight.

## Ideal capsule wardrobe (men, India, age ~28, BMI 32.7)

This is the target inventory. Adjust gap scores from `scoring.md` based on shortfall.

### Shirts (target: 12)

| Color | Pattern | Fabric | Quantity | Why |
|---|---|---|---|---|
| White | Solid | Linen | 1 | Wedding / formal occasions |
| White | Solid | Cotton | 2 | Office / smart casual workhorse |
| Navy | Solid | Cotton | 2 | Universal, slimming |
| Beige/Cream | Solid | Linen | 1 | Vijayawada heat, premium look |
| Olive | Solid | Cotton | 1 | Earthy, suits Deep Autumn palette |
| Light blue | Solid | Cotton | 1 | Office classic |
| Burgundy | Solid | Cotton | 1 | Statement, jewel tone |
| Navy | Vertical stripe | Cotton | 1 | Slimming variety |
| Tan | Subtle check | Linen | 1 | Smart casual variety |
| (free pick) | Subtle print | Cotton | 1 | Weekend / outing |

### T-shirts (target: 8)

| Color | Pattern | Fabric | Quantity |
|---|---|---|---|
| White | Plain crew | Cotton | 2 |
| Navy | Plain crew | Cotton | 2 |
| Black | Plain crew | Cotton | 2 |
| Olive / Burgundy / Charcoal | Plain | Cotton | 2 (rotate) |

### Jeans (target: 3)

| Color | Wash | Fit |
|---|---|---|
| Dark indigo | No fade | Straight or regular |
| Black | Solid | Straight or regular |
| Mid blue | Subtle wash | Regular |

### Trousers (target: 4)

| Color | Style | Fabric |
|---|---|---|
| Navy | Chinos | Cotton |
| Beige / khaki | Chinos | Cotton |
| Charcoal grey | Formal | Wool-blend (winter only) |
| Olive / brown | Chinos | Cotton |

### Shoes (target: 4 pairs)

| Type | Color |
|---|---|
| Sneakers | White |
| Formal lace-up | Black or dark brown |
| Casual loafer | Tan or brown |
| Sports / running | Any (function over form) |

### Outerwear (target: 2)

| Type | Color | When |
|---|---|---|
| Blazer | Navy or charcoal | Office, dressy occasions |
| Bomber / windcheater | Olive or black | Travel, mild weather |

## Gap calculation

For a candidate deal, compute:

```
ideal_qty = lookup(category, color_family, pattern, fabric) from tables above
owned_qty = count(wardrobe items matching same combination)
shortfall = max(0, ideal_qty - owned_qty)

if shortfall > 0:
    gap_score = base_value (from scoring.md table) * (shortfall / ideal_qty)
else:
    gap_score = max(0, 30 - 50 * (owned_qty - ideal_qty))   # over-owning penalty
```

## "What's my biggest gap?" reply format

```
Your biggest wardrobe gaps right now:

1. White solid linen shirt (own 0, target 1) — needed for weddings
2. Navy solid cotton shirt (own 0, target 2) — universal workhorse
3. White cotton t-shirt (own 1, target 2) — daily basics
4. Dark indigo jeans (own 0, target 1) — wardrobe staple
5. White sneakers (own 0, target 1) — pairs with everything

Rebalance candidates (you over-own these):
- Mast & Harbour checked shirts (own 5, target 1) — pause buying
```

## Notes

- The ideal capsule is a **starting heuristic**, not gospel. Override based on Prazwal's lifestyle (works from home, no daily office wear → skip formal trousers).
- For `subcategory` like "wedding-grade" vs "casual", weight wedding shirts higher in March–May (wedding season).
- Climate filter: in `hot_months`, prefer linen/cotton; in `cool_months`, allow wool-blend.
