# Onboarding defaults

When `profile.json` is missing or incomplete, use these defaults to fill the rest of the file after asking the 5 onboarding questions in `SKILL.md` Step 0.

## Defaults table

| Field | Default | When to override |
|---|---|---|
| `physical.build` | derived from BMI: <22 = "slim", 22-25 = "average", 25-30 = "stocky", 30+ = "stocky-heavy" | always derive |
| `climate.city` | from question 3 | always ask |
| `climate.hot_months` | for India south (Vijayawada/Chennai/Bangalore): Mar-Oct. For India north (Delhi/Punjab): Apr-Sep. For Mumbai: Mar-Nov. | derive from city |
| `climate.fabric_avoid_when_hot` | `["wool", "heavy_canvas", "fleece", "thick_corduroy", "leather"]` | rarely override |
| `color_palette.season` | derived from undertone + skin: warm + deep = "Deep Autumn"; warm + medium = "Soft Autumn"; cool + deep = "Deep Winter"; cool + medium = "Cool Winter" | derive |
| `color_palette.great` | season-specific list (see below) | rarely override |
| `color_palette.avoid` | inverse of season palette | rarely override |
| `fit_rules.preferred` | BMI 25+: `["regular", "tailored", "relaxed", "comfort"]`. BMI <25: `["regular", "tailored", "slim"]` | derive from BMI |
| `fit_rules.avoid` | BMI 28+: `["slim", "skinny", "muscle_fit", "very_tight"]`. BMI <25: `["oversized", "very_baggy"]` | derive from BMI |
| `pattern_rules.prefer` | universal: `["solid", "vertical_stripe", "subtle_print", "micro_check"]` | rarely override |
| `pattern_rules.avoid` | BMI 28+: `["horizontal_stripe", "broad_horizontal_stripe", "large_bold_print"]`. BMI <25: less restrictive | derive |
| `budget_inr.shirt_max` | 2500 | from question 5 |
| `budget_inr.tshirt_max` | 1500 | proportional |
| `budget_inr.shoes_max` | 5000 | proportional |
| `sizes` | from question 2 | always ask |

## Color palettes by season

### Deep Autumn (warm undertone, deep skin)
- Great: navy, olive, mustard, burgundy, wine, maroon, forest green, teal, rust, burnt orange, chocolate, brown, white, cream, beige, ivory, emerald, terracotta, charcoal, deep purple, aubergine, royal blue, camel, khaki, tan, gold, copper, black, dark grey
- Good: grey, blue, green, orange, red, purple, yellow, indigo
- Avoid: icy blue, baby blue, pastel pink, lavender, ash grey, neon, fluorescent, light pink, pale blue, silver, mauve, peach, mint

### Deep Winter (cool undertone, deep skin)
- Great: black, navy, charcoal, true white, ice white, ruby red, magenta, royal blue, emerald, deep purple, fuchsia, hot pink, true red, cobalt
- Good: grey, blue, green, red, purple
- Avoid: warm beige, mustard, rust, terracotta, peach, coral, gold (clashes with cool undertone)

### Soft Autumn (warm undertone, medium skin)
- Great: olive, camel, khaki, soft white, peach, salmon, warm beige, soft red, terracotta, soft teal, sage green, dusty rose, soft brown
- Good: muted versions of warm colors
- Avoid: icy/jewel tones (too sharp), neon, pure black

### Cool Winter (cool undertone, medium skin)
- Great: pure white, navy, royal blue, emerald, fuchsia, ruby, charcoal
- Good: grey, blue, purple
- Avoid: warm beiges, mustard, orange-reds

## Asking the 5 questions

Format the questions clearly and wait for ALL answers before computing defaults.

```
Welcome to Super Pick. I need 5 quick things:

1. Height (cm) and weight (kg)?
2. Shirt size (S/M/L/XL/XXL), trouser waist (inches), shoe size (UK)?
3. City + country?
4. Skin tone (fair / wheatish / medium / deep) and undertone (warm-golden / cool-pink / neutral)? If unsure, send a selfie.
5. Roughly how much per month do you spend on clothes? (helps set budget caps)

Answer all 5 in one message and I'll set up your profile.
```

After parsing answers:
- Compute BMI: `weight / (height/100)^2`
- Derive build, season, fit_rules, pattern_rules from tables above
- Apply budget proportionally: shirt_max ≈ monthly_budget * 0.4, tshirt_max ≈ monthly_budget * 0.25, shoes_max ≈ monthly_budget * 0.6 (if shoes are needed in that month)
- Write `profile.json` with derived defaults
- Confirm: "Profile saved. Ready to find deals."

## When user wants to change a default

If user says "I don't actually mind slim fit" or "I love pastels":
- DO NOT silently change profile.json
- Ask: "Update profile permanently to allow <X>? (y/n)"
- Only on explicit `y`, write the change
