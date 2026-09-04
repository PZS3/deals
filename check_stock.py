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
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import requests

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0 Safari/537.36")
HEADERS = {"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"}
MARKER = "window.__myx ="
_decoder = json.JSONDecoder()


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

    sizes = (data.get("pdpData") or {}).get("sizes") or []
    if not sizes:
        out["note"] = "product page listed no sizes"
        return deal_id, out

    for s in sizes:
        label = str(s.get("label", "")).upper().strip()
        if not s.get("available"):
            out["sizes"][label] = 0
            continue
        seller = s.get("sizeSellerData") or []
        out["sizes"][label] = (seller[0].get("availableCount") if seller
                               else s.get("availableCount")) or 1

    out["ok"] = any(out["sizes"].get(w.upper(), 0) > 0 for w in want)
    have = [k for k, v in out["sizes"].items() if v > 0]
    out["note"] = "in stock: " + (", ".join(have) if have else "nothing")
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


if __name__ == "__main__":
    # usage: check_stock.py <deals.json> <id> [<id> ...]   (or - to read ids on stdin)
    deals = {d["id"]: d for d in json.load(open(sys.argv[1]))["deals"]}
    ids = sys.argv[2:] or [ln.strip() for ln in sys.stdin if ln.strip()]
    pairs = [(i, deals[i]["url"]) for i in ids if i in deals]
    for did, res in check_many(pairs).items():
        mark = {True: "IN STOCK", False: "SOLD OUT", None: "UNKNOWN "}[res["ok"]]
        print(f"{mark}  {did}  {res['note']}")
