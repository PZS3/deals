"""Activewear vs casual t-shirts.

Neither store tags this on the search listing the scraper reads, so the
scraper decides from the name (tee_style(deal)). The stock stage already
downloads each product page, and refines the answer with the store's own
attributes when it has them (tee_style(deal, attrs)):
  Myntra: pdpData.articleAttributes {Fabrics, Occasions, Sport, Technology}
  Ajio:   the single-product search's occasion facet {occasion}
Audited 2026-09-27 on 60 random tees: 57 right by name alone; all 3 misses
were polyester training tees with no cue in the name, which the Myntra
fabric check catches.
"""
import re

# Performance fabric/tech, or the activity the tee is built for.
ACTIVE_RE = re.compile(r"""(
      dri[\s-]?fit | \bdf\b | dry[\s-]?fit | drycell | dry\s?cell
    | (rapid|quick|fast|ultra|play|cool)[\s-]?dry | \bgo\s?dri\b
    | wicking | speedwick | moisture
    | aeroready | heat\.?rdy | climacool | climalite | climachill | activchill
    | cloudspun | cloudspin | ultraspun | adizero | \bmiler\b
    | hyverse | \bvanish\b | seamless | heatgear | iso[\s-]?chill | tech\s?vent
    | performance
    | compression | \btights?\b | base\s?layer
    | \btrain(ing)?\b | \brun(ning|ner)?\b | \bgym\b | workout | fitness
    | \byoga\b | pilates | raceday | singlet | marathon
    | replica | \bstadium\b
)""", re.I | re.X)
# Everyday cues; only consulted after ACTIVE_RE.
CASUAL_RE = re.compile(r"""(
      \bcotton\b | oversized | \bboxy\b | lifestyle | \blife\s+co\b
    | drop[\s-]?shoulder | bio\s+finish | house\s+of\s+graphics
    | sportswear | sportwears? | sportstyle | \bnsw\b
    | heavyweight | \bmax90\b | \bwashed\b | vintage | \bringer\b
    | \bcasual\b | americana | \bclassics\b | \bt7\b
)""", re.I | re.X)
CLUB_RE = re.compile(r"\bclub\b", re.I)                  # Nike Club = lifestyle...
KIT_RE = re.compile(r"jersey|replica|\bteams?\b|\bfc\b", re.I)   # ...unless it's a kit
WEAK_CASUAL_RE = re.compile(r"\brelaxed\b|(basketball|hoops).*\bgraphic\b|\bgraphic\b.*(basketball|hoops)", re.I)
# HRX "Colourblocked" tees are its polyester training line.
HRX_ACTIVE_RE = re.compile(r"colou?r[\s-]?block", re.I)
# Sporty but ambiguous alone (fan tees, "Sport Graphic"...): last resort.
SPORTY_RE = re.compile(r"""(
      \bsports?\b | \bactive\b | \bathletic\b | evostripe
    | basketball | football | soccer | cricket | tennis | \bgolf\b | \bcourt\b
    | badminton | hockey | rugby | cycling | trekking | hiking
    | \bjersey\b(?!\s+(men'?s\s+)?polo) | \bf?jsy\b
    | sleeveless | \btank\b
    | \btech\b | velocity | project\s+rock
)""", re.I | re.X)

SPORT_BRANDS = ("hrx", "puma", "nike", "adidas", "reebok", "under armour", "asics",
                "skechers", "decathlon", "performax", "technosport")
SYNTHETIC = {"polyester", "elastane", "nylon", "technical fabrics"}
PERF_TECH = {"dri-fit", "drycell", "dry fit", "rapid-dry", "ultra dry", "playdry",
             "moisture wicking", "coolcell", "ultralite", "3d chassis", "realflex", "climacool"}


def _store_label(attrs, brand):
    if not attrs:
        return None
    if any(k in attrs for k in ("Fabrics", "Occasions", "Sport", "Technology")):   # Myntra
        tech = {t.strip().lower() for t in str(attrs.get("Technology", "")).split(",")}
        if tech & PERF_TECH:
            return "active"
        fab = {f.strip().lower() for f in str(attrs.get("Fabrics", "")).split(",") if f.strip()}
        if fab and fab <= SYNTHETIC and any(s in brand.lower() for s in SPORT_BRANDS):
            return "active"
        occ = str(attrs.get("Occasions", "")).strip().lower()
        if occ == "sports":
            return "active"
        if occ:
            return "casual"
        sport = str(attrs.get("Sport", "")).strip().lower()
        if sport and sport != "na":
            return "active"
        return None
    occ = str(attrs.get("occasion", "")).strip().lower()                         # Ajio
    if occ:
        return "active" if occ in ("active", "sports") else "casual"
    return None


def tee_style(deal, attrs=None):
    """'active' or 'casual' for a deals.json tshirt row."""
    name = deal.get("name", "") or ""
    brand = deal.get("brand", "") or ""
    if ACTIVE_RE.search(name):
        return "active"
    # Nike Club is lifestyle; adidas Club is its tennis line.
    if CASUAL_RE.search(name) or (CLUB_RE.search(name) and "nike" in brand.lower()
                                  and not KIT_RE.search(name)):
        return "casual"
    if "hrx" in (brand + " " + name).lower() and HRX_ACTIVE_RE.search(name):
        return "active"
    store = _store_label(attrs, brand)
    if store:
        return store
    if WEAK_CASUAL_RE.search(name):
        return "casual"
    if SPORTY_RE.search(name):
        return "active"
    return "casual"
