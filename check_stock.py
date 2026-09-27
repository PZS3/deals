#!/Library/Frameworks/Python.framework/Versions/3.9/bin/python3
"""
Live per-size stock check for Myntra product pages.

Why: deals.json's `sizes_available` is NOT availability. On Myntra it is the
`sizes` field from the search listing, which is the size range the product is
manufactured in — it says nothing about what is in stock. On Ajio the scraper
hardcodes [] (scraper.py line ~187). Filtering on that field silently
recommends sold-out items, which is exactly what happened on 2026-09-04.

This fetches the product page and reads pdpData.sizes[].available, which is
real. Use it on a shortlist (5-30 items) before recommending — not on the whole
deals.json, which would be thousands of requests.

    from check_stock import check_many
    res = check_many([(deal_id, url), ...], want=("XL", "XXL"))
    # -> {deal_id: {"ok": True/False/None, "sizes": {"XL": 42, ...}, "note": str}}

ok is None when availability could not be determined (blocked, page shape
changed) — treat that as "unknown", never as "in stock".
"""

import json
import logging
import os
import re
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path

import requests

from classify import tee_style

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0 Safari/537.36")
HEADERS = {"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"}
MARKER = "window.__myx ="
_decoder = json.JSONDecoder()


def _to_int(v):
    try:
        return int(float(str(v).replace(",", ""))) if v not in (None, "") else None
    except ValueError:
        return None


_WAIST = re.compile(r"^W(\d+)(?:/L\d+)?$|^(\d+)W$")


def norm_size(label):
    """'W34/L32', 'W34', '34W' -> '34'; 'UK 10' -> 'UK10'; 'xl' -> 'XL'."""
    s = str(label).upper().replace(" ", "")
    m = _WAIST.match(s)
    return (m.group(1) or m.group(2)) if m else s


def _scheme(label):
    return "num" if re.fullmatch(r"(UK)?\d+(\.\d+)?", label) else "alpha"


def same_scheme(labels, want):
    """False when a product's sizes can't express the wanted ones at all
    (letter sizes on a waist-34 category, kids' 6Y on UK 10): that is
    'unknown', never 'sold out'."""
    return bool({_scheme(l) for l in labels} & {_scheme(norm_size(w)) for w in want})


def check_one(deal_id, url, want=("XL", "XXL"), timeout=25):
    """Return {'ok':bool|None,'sizes':{label:count|None},'note':str} for one URL."""
    out = {"ok": None, "sizes": {}, "note": ""}
    if not url or "myntra.com" not in url:
        out["note"] = "not a Myntra URL — cannot verify (Ajio has no stock data)"
        return deal_id, out
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout)
    except Exception as e:
        out["note"] = f"fetch failed: {type(e).__name__}"
        return deal_id, out
    if r.status_code != 200:
        out["note"] = f"HTTP {r.status_code}"
        return deal_id, out

    i = r.text.find(MARKER)
    if i < 0:
        out["note"] = "no embedded product JSON (blocked or page changed)"
        return deal_id, out
    try:
        data, _ = _decoder.raw_decode(r.text[r.text.find("{", i):])
    except Exception as e:
        out["note"] = f"JSON parse failed: {type(e).__name__}"
        return deal_id, out

    # Live price: search listings go stale, and deals.json carries rows
    # forward for days after they drop out of search (apply_live_prices).
    pr = (data.get("pdpData") or {}).get("price") or {}
    out["price"], out["mrp"] = _to_int(pr.get("discounted")), _to_int(pr.get("mrp"))

    # Store attributes the tee classifier uses (classify.tee_style).
    aa = (data.get("pdpData") or {}).get("articleAttributes") or {}
    out["attrs"] = {k: aa[k] for k in ("Fabrics", "Occasions", "Sport", "Technology") if aa.get(k)}

    sizes = (data.get("pdpData") or {}).get("sizes") or []
    if not sizes:
        out["note"] = "product page listed no sizes"
        return deal_id, out

    for s in sizes:
        label = norm_size(s.get("label", ""))
        if not s.get("available"):
            out["sizes"][label] = 0
            continue
        seller = s.get("sizeSellerData") or []
        out["sizes"][label] = (seller[0].get("availableCount") if seller
                               else s.get("availableCount")) or 1

    have = [k for k, v in out["sizes"].items() if v > 0]
    out["note"] = "in stock: " + (", ".join(have) if have else "nothing")
    if not same_scheme(out["sizes"], want):
        out["note"] = "sizes use another scheme — " + out["note"]
        return deal_id, out
    out["ok"] = any(out["sizes"].get(norm_size(w), 0) > 0 for w in want)
    return deal_id, out


def check_many(items, want=("XL", "XXL"), workers=5, pause=0.3):
    """items: iterable of (deal_id, url). Politely parallel, small pool."""
    results = {}

    def job(pair):
        time.sleep(pause)
        return check_one(pair[0], pair[1], want=want)

    with ThreadPoolExecutor(max_workers=workers) as ex:
        for deal_id, res in ex.map(job, list(items)):
            results[deal_id] = res
    return results


_AJIO_CODE = re.compile(r"/p/([0-9]+)(?:_[A-Za-z0-9]+)?")
_AJIO_STATE = re.compile(r'window\.\w+\s*=\s*(\{.+\})\s*;?\s*$', re.DOTALL)
_ajio_session = None


def check_ajio(deal_id, url, want):
    """Ajio per-size availability, same result shape as check_one.

    Ajio's product pages and /api/p/ return 403 to scripts, but a search for
    the bare numeric product code returns that one product, and the search's
    "Size & Fit" facet lists only sizes in stock (sold-out sizes are absent).
    Checked against the product page's variantOptions[].stock on 2026-09-27.
    Gives availability only, no unit counts: sizes map to None.
    """
    global _ajio_session
    out = {"ok": None, "sizes": {}, "note": ""}
    m = _AJIO_CODE.search(url or "")
    if not m:
        out["note"] = "no Ajio product code in url"
        return deal_id, out
    option = m.group(0)[3:]
    try:
        from curl_cffi import requests as cffi_requests
        if _ajio_session is None:
            _ajio_session = cffi_requests.Session(impersonate="chrome")
        r = _ajio_session.get(f"https://www.ajio.com/search/?text={m.group(1)}", timeout=25)
    except Exception as e:
        out["note"] = f"fetch failed: {type(e).__name__}"
        return deal_id, out
    if r.status_code != 200 or "Access Denied" in r.text[:500]:
        out["note"] = f"HTTP {r.status_code}"
        return deal_id, out
    state = None
    for script in r.text.split("<script")[1:]:
        body = script.split(">", 1)[-1].split("</script>", 1)[0]
        if len(body) > 50000 and "entities" in body:
            mm = _AJIO_STATE.search(body.strip())
            if mm:
                try:
                    state = json.loads(mm.group(1))
                except ValueError:
                    pass
            break
    if state is None:
        out["note"] = "no search state (blocked or page changed)"
        return deal_id, out
    ents = (state.get("grid") or {}).get("entities") or {}
    if not ents:
        out["ok"] = False
        out["note"] = "no longer listed on Ajio"
        return deal_id, out
    mine = [e for e in ents.values() if ((e.get("tags") or {}).get("optionCode") == option
                                         or (e.get("url") or "").endswith("/p/" + option))]
    if not mine:
        out["note"] = f"search returned {len(ents)} products, none is this one"
        return deal_id, out
    pv, wv = mine[0].get("price"), mine[0].get("wasPriceData")
    out["price"] = _to_int(pv.get("value") if isinstance(pv, dict) else pv)
    out["mrp"] = _to_int(wv.get("value") if isinstance(wv, dict) else wv) or out["price"]
    facets = ((state.get("facets") or {}).get("currentFacets") or {}).get("entities") or {}
    counts = {norm_size(k.split("-", 1)[1]): (v.get("count") or 0) for k, v in facets.items()
              if k.startswith("verticalsizegroupformat-") and (v.get("count") or 0) > 0}
    wanted = {norm_size(w) for w in want}
    # Colour variants can share the numeric code; the facet then counts, per
    # size, how many of those products have it. Only a size every one of them
    # has is certainly ours; a size none of them has is certainly sold out.
    n = len(ents)
    occ = [k.split("-", 1)[1] for k, v in facets.items() if k.startswith("occasion-") and (v.get("count") or 0) > 0]
    if n == 1 and len(occ) == 1:
        out["attrs"] = {"occasion": occ[0]}
    note = "in stock: " + (", ".join(sorted(counts)) if counts else "nothing")
    out["note"] = note if n == 1 else f"{note} (across {n} colour variants)"
    if counts and not same_scheme(counts, want):
        out["note"] = "sizes use another scheme — " + out["note"]
        return deal_id, out
    sure = {s for s, c in counts.items() if c >= n}
    out["sizes"] = {s: None for s in sure if s in wanted}
    if out["sizes"]:
        out["ok"] = True
    elif not wanted & set(counts):
        out["ok"] = False
    return deal_id, out


BASE_DIR = Path(__file__).parent
STOCK_PATH = BASE_DIR / "stock.json"
AJIO_PER_RUN = 500      # 4 runs a day = 2,000 checks, a margin over ~1,850 Ajio deals
AJIO_RECHECK = timedelta(hours=20)
RECHECK_AFTER = timedelta(hours=3)   # cron runs every 6h, so every run re-checks everything
KEEP_LAST_GOOD = timedelta(hours=24)  # an inconclusive check keeps a reading this recent
CHUNK = 100
log = logging.getLogger("stock")


def refresh_stock(deals_path=BASE_DIR / "deals.json", config_path=BASE_DIR / "config.json",
                  stock_path=STOCK_PATH, workers=4, force=()):
    """Live-check every Myntra deal in the owner's sizes; write stock.json.

    stock.json: {"checked_at": iso, "items": {deal_id: {"ok": bool|None,
    "sizes": {label: count}, "checked_at": iso, "note": str}}}. Only the
    sizes in config categories[cat].stock_sizes are kept, so "ok" means
    "buyable in a size he wears", not "buyable in some size".
    """
    deals = json.load(open(deals_path))["deals"]
    cats = json.load(open(config_path))["categories"]
    try:
        old = json.load(open(stock_path)).get("items", {})
    except (OSError, ValueError):
        old = {}
    now = datetime.now()
    live_ids = {d["id"] for d in deals}
    items = {k: v for k, v in old.items() if k in live_ids}

    def fresh(rec, age):
        try:
            return now - datetime.fromisoformat(rec["checked_at"]) < age
        except (KeyError, TypeError, ValueError):
            return False

    # A record is only trusted for the category it was checked against:
    # re-filing a deal (tee -> shirt) changes which sizes count as his.
    def usable(d, age, need_price=True):
        rec = items.get(d["id"])
        return bool(rec and rec.get("ok") is not None and (rec.get("price") or not need_price)
                    and rec.get("category") == d["category"] and fresh(rec, age))

    # Tee records also carry the store's attributes and the refined style.
    def record(d, rec, r):
        rec["category"] = d["category"]
        if r.get("price"):
            rec["price"], rec["mrp"] = r["price"], r.get("mrp") or r["price"]
        if d["category"] == "tshirt":
            rec["attrs"] = r.get("attrs") or {}
            rec["style"] = tee_style(d, rec["attrs"])
        return rec

    todo = [d for d in deals if d["store"] == "Myntra"
            and (d["category"] in force or not usable(d, RECHECK_AFTER))]
    log.info(f"[Stock] {len(todo)} Myntra deals to check ({len(items)} records kept)")

    checked = kept_old = 0
    for start in range(0, len(todo), CHUNK):
        chunk = todo[start:start + CHUNK]
        by_cat = {}
        for d in chunk:
            by_cat.setdefault(d["category"], []).append(d)
        res = {}
        for cat, rows in by_cat.items():
            want = tuple((cats.get(cat) or {}).get("stock_sizes") or ())
            if want:
                res.update(check_many([(d["id"], d["url"]) for d in rows], want=want, workers=workers))
        stamp = datetime.now().isoformat(timespec="seconds")
        unknown = 0
        for d in chunk:
            r = res.get(d["id"])
            if r is None:
                continue
            want = {norm_size(w) for w in (cats.get(d["category"]) or {}).get("stock_sizes") or ()}
            mine = {k: v for k, v in r["sizes"].items() if k in want}
            if r["ok"] is None:
                unknown += 1
                if usable(d, KEEP_LAST_GOOD, need_price=False):
                    kept_old += 1
                    continue
            items[d["id"]] = record(d, {"ok": r["ok"], "sizes": mine, "checked_at": stamp, "note": r["note"]}, r)
            checked += 1
        # Circuit breaker: a mostly-inconclusive chunk means Myntra is
        # blocking or changed its page. Stop instead of hammering it.
        if len(chunk) >= 20 and unknown > len(chunk) // 2:
            log.error(f"[Stock] {unknown}/{len(chunk)} inconclusive in one chunk — stopping; "
                      f"{len(todo) - start - len(chunk)} deals left unchecked this run")
            break

    # Ajio: one search per product, sequential and slow, so it is a rolling
    # window — never-checked first, then the stalest — capped per run.
    def age_key(d):
        rec = items.get(d["id"])
        try:
            return (1, datetime.fromisoformat(rec["checked_at"]))
        except (TypeError, KeyError, ValueError):
            return (0, datetime.min)
    ajio = sorted((d for d in deals if d["store"] == "Ajio"
                   and (d["category"] in force or not usable(d, AJIO_RECHECK))), key=age_key)
    log.info(f"[Stock] {len(ajio)} Ajio deals due; checking up to {AJIO_PER_RUN} this run")
    aj_checked = streak = 0
    for d in ajio[:AJIO_PER_RUN]:
        want = tuple((cats.get(d["category"]) or {}).get("stock_sizes") or ())
        if not want:
            continue
        _, r = check_ajio(d["id"], d["url"], want)
        time.sleep(1.0)
        if r["ok"] is None:
            streak += 1
            if streak >= 10:
                log.error(f"[Stock] 10 inconclusive Ajio checks in a row ({r['note']}) — stopping")
                break
            if usable(d, KEEP_LAST_GOOD, need_price=False):
                continue
        else:
            streak = 0
        items[d["id"]] = record(d, {"ok": r["ok"], "sizes": r["sizes"], "counts": False,
                                    "checked_at": datetime.now().isoformat(timespec="seconds"), "note": r["note"]}, r)
        aj_checked += 1
    log.info(f"[Stock] Ajio checked {aj_checked}")

    out = {"checked_at": datetime.now().isoformat(timespec="seconds"), "items": items}
    tmp = stock_path.with_suffix(".json.tmp")
    with open(tmp, "w") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, stock_path)

    states = Counter({True: "in", False: "sold_out", None: "unknown"}[v.get("ok")] for v in items.values())
    log.info(f"[Stock] checked {checked}, kept last good {kept_old}; records: {dict(states)}")
    apply_live_prices(deals_path, config_path, items)
    return out


def apply_live_prices(deals_path, config_path, items, max_age=timedelta(hours=30)):
    """Write each deal's live price into deals.json; drop deals no longer on sale.

    A row keeps the price it had when it was last in search results, and the
    scraper carries rows forward for days after that — typically because the
    item sold out or its sale ended (on 2026-09-27, 1,306 of 3,224 rows).
    The stock stage has just read the real price off the product page / the
    one-product Ajio search, so it overrides. The same min-discount and
    budget rules as the scraper then decide whether it is still a deal.
    """
    data = json.load(open(deals_path))
    cats = json.load(open(config_path))["categories"]
    now = datetime.now()
    changed = dropped = 0
    keep = []
    for d in data.get("deals", []):
        rec = items.get(d["id"])
        try:
            recent = rec and now - datetime.fromisoformat(rec["checked_at"]) < max_age
        except (KeyError, TypeError, ValueError):
            recent = False
        # Only a reading taken after the row was scraped is newer: for Ajio
        # both come from the same search data, and a still-fresh record from
        # an earlier run must not undo this run's scraped price.
        try:
            scraped = datetime.fromisoformat(d["scraped_at"])
        except (TypeError, KeyError, ValueError):
            scraped = datetime.min          # price of unknown age: a live reading wins
        try:
            newer = datetime.fromisoformat(rec["checked_at"]) >= scraped
        except (TypeError, KeyError, ValueError):
            newer = False
        if recent and newer and rec.get("price") and rec.get("category") == d["category"]:
            price, mrp = rec["price"], max(rec.get("mrp") or 0, rec["price"])
            if (price, mrp) != (d.get("price"), d.get("mrp")):
                changed += 1
                # Rounded like the stores' own discount figure (Ajio's
                # discountPercent), so a listed 30% doesn't become 29.
                d["discount_pct"] = round((mrp - price) * 100 / mrp) if mrp else 0
            d["price"], d["mrp"] = price, mrp
            d["price_checked_at"] = rec["checked_at"]
            conf = cats.get(d["category"]) or {}
            if d["discount_pct"] < conf.get("min_discount_pct", 30) or price > conf.get("max_price", 10 ** 9):
                dropped += 1
                continue
        keep.append(d)
    data["deals"] = keep
    data["total_deals"] = len(keep)
    data["prices_checked_at"] = now.isoformat(timespec="seconds")
    tmp = Path(deals_path).with_suffix(".json.tmp")
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, deals_path)
    log.info(f"[Prices] {changed} prices changed; {dropped} deals no longer on sale dropped; {len(keep)} left")


if __name__ == "__main__":
    if sys.argv[1:2] == ["--refresh"]:
        # check_stock.py --refresh [--force cat1,cat2]
        logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
        force = tuple(sys.argv[3].split(",")) if sys.argv[2:3] == ["--force"] and len(sys.argv) > 3 else ()
        refresh_stock(force=force)
        sys.exit(0)
    # usage: check_stock.py <deals.json> <id> [<id> ...]   (or - to read ids on stdin)
    deals = {d["id"]: d for d in json.load(open(sys.argv[1]))["deals"]}
    ids = sys.argv[2:] or [ln.strip() for ln in sys.stdin if ln.strip()]
    pairs = [(i, deals[i]["url"]) for i in ids if i in deals]
    for did, res in check_many(pairs).items():
        mark = {True: "IN STOCK", False: "SOLD OUT", None: "UNKNOWN "}[res["ok"]]
        print(f"{mark}  {did}  {res['note']}")
