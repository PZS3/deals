#!/usr/bin/env python3
"""
Prazwal's Deal Finder — Myntra + Ajio only
Myntra: extract embedded JSON from HTML script tags
Ajio: direct JSON API endpoint
"""

import json
import os
import re
import time
import random
import hashlib
import logging
from datetime import datetime, timedelta
from pathlib import Path

import requests
from bs4 import BeautifulSoup

BASE_DIR = Path(__file__).parent
CONFIG_PATH = BASE_DIR / "config.json"
DEALS_PATH = BASE_DIR / "deals.json"

# How long a deal survives after it stops showing up in search results.
MAX_KEEP_DAYS = 7

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
log = logging.getLogger("deals")


def load_config():
    with open(CONFIG_PATH) as f:
        return json.load(f)


DEFAULT_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"


def get_session(config=None):
    s = requests.Session()
    agents = (config or {}).get("user_agents") or [DEFAULT_UA]
    s.headers.update({
        "User-Agent": random.choice(agents),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-IN,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
    })
    return s


def fetch_with_retry(session, url, timeout, tries=3):
    """GET with backoff. Returns the response, or None after the last failure."""
    for attempt in range(1, tries + 1):
        try:
            resp = session.get(url, timeout=timeout)
            if resp.status_code == 200:
                return resp
            log.warning(f"HTTP {resp.status_code} for {url[:90]} (attempt {attempt}/{tries})")
        except Exception as e:
            log.warning(f"Fetch failed for {url[:90]} (attempt {attempt}/{tries}): {e}")
        if attempt < tries:
            time.sleep(2 * attempt + random.uniform(0, 1))
    return None


def make_id(store, text):
    h = hashlib.md5(text.encode()).hexdigest()[:8]
    return f"{store}_{h}"


def parse_price(text):
    if not text:
        return None
    cleaned = re.sub(r'[^\d.]', '', str(text).replace(',', ''))
    if cleaned:
        try:
            return int(float(cleaned))
        except ValueError:
            return None
    return None


def parse_rating_count(raw):
    """Rating counts arrive as int, '204', '2.2K', or None."""
    if raw is None:
        return 0
    if isinstance(raw, (int, float)):
        return int(raw)
    rc = str(raw).strip().upper()
    try:
        if rc.endswith("K"):
            return int(float(rc[:-1]) * 1000)
        return int(float(rc))
    except ValueError:
        return parse_price(rc) or 0


def matches_brand(name, brands):
    name_lower = name.lower()
    for brand in brands:
        if brand.lower() in name_lower:
            return brand
    return None


# ============================================================
# AJIO — curl-cffi search page + embedded entities extraction
# ============================================================
def parse_ajio_product(pid, p, brands, cat_key, cat_conf, config):
    """One Ajio entity -> deal dict, or None if it doesn't qualify."""
    fnl = p.get("fnlColorVariantData", {}) or {}
    brand_name = fnl.get("brandName", "")
    name = p.get("name", "")
    full_name = f"{brand_name} {name}"

    matched = matches_brand(full_name, brands)
    if not matched:
        return None

    price_obj = p.get("price", {})
    price = parse_price(price_obj.get("value")) if isinstance(price_obj, dict) else parse_price(price_obj)

    mrp_obj = p.get("wasPriceData", {})
    mrp = parse_price(mrp_obj.get("value")) if isinstance(mrp_obj, dict) else parse_price(mrp_obj)

    if not price:
        return None
    if not mrp:
        mrp = price
    if price > cat_conf["max_price"]:
        return None

    # Discount - can be "60% off" string or int
    disc_raw = p.get("discountPercent", 0) or 0
    disc_pct = 0
    if isinstance(disc_raw, str):
        d_match = re.search(r'(\d+)', disc_raw)
        if d_match:
            disc_pct = int(d_match.group(1))
    elif isinstance(disc_raw, (int, float)):
        disc_pct = int(disc_raw)
    if not disc_pct and mrp > price:
        disc_pct = int(((mrp - price) / mrp) * 100)
    if disc_pct < cat_conf.get("min_discount_pct", 30):
        return None

    rating = float(p.get("averageRating", 0) or 0)
    rating_count = parse_rating_count(p.get("ratingCount"))

    # Strict rating: must be 4.0+ OR have no ratings at all (new product)
    if rating > 0 and rating < config["min_rating"]:
        return None

    img = fnl.get("outfitPictureURL", "") or ""
    if not img:
        images = p.get("images", [])
        if images:
            img = images[0].get("url", "") if isinstance(images[0], dict) else str(images[0])
    if img and not img.startswith("http"):
        img = f"https://assets.ajio.com/medias/{img}"

    url_path = p.get("url", "")
    product_url = f"https://www.ajio.com{url_path}" if url_path else ""

    color = (fnl.get("colorGroup", "") or p.get("colour", "") or "").strip().lower()

    return {
        "id": make_id("ajio", product_url or f"{pid}_{name}"),
        "store": "Ajio",
        "brand": matched,
        "name": name,
        "category": cat_key,
        "color": color,
        "image": img,
        "url": product_url,
        "mrp": mrp or 0,
        "price": price,
        "discount_pct": disc_pct,
        "rating": round(rating, 1),
        "rating_count": rating_count,
        "sizes_available": [],
        "scraped_at": datetime.now().isoformat()
    }


def scrape_ajio(config):
    """Ajio: use curl-cffi to load search pages, extract product entities from embedded JSON."""
    deals = []
    brands = config["brands"]

    try:
        from curl_cffi import requests as cffi_requests
    except ImportError:
        log.warning("[Ajio] curl-cffi not installed, skipping")
        return deals

    session = cffi_requests.Session(impersonate="chrome")

    # Search queries per category
    search_queries = {
        "tshirt": ["puma tshirt men", "adidas tshirt men", "us polo tshirt men", "reebok tshirt men",
                    "nike tshirt men", "under armour tshirt men", "hrx tshirt men", "allen solly tshirt men"],
        "shirt": ["us polo shirt men", "allen solly shirt men", "jack jones shirt men", "levi shirt men",
                   "tommy hilfiger shirt men", "roadster shirt men", "puma shirt men", "adidas shirt men",
                   "calvin klein shirt men", "superdry shirt men", "under armour shirt men",
                   "van heusen shirt men", "arrow shirt men", "peter england shirt men",
                   "louis philippe shirt men", "indian terrain shirt men", "wrangler shirt men",
                   "pepe jeans shirt men", "gap shirt men", "benetton shirt men",
                   "marks spencer shirt men", "celio shirt men", "flying machine shirt men",
                   "men party wear shirt", "men formal shirt premium", "men linen shirt",
                   "men printed shirt designer", "men occasion wear shirt",
                   "selected homme shirt men", "jack jones premium shirt",
                   "tommy hilfiger formal shirt", "van heusen party shirt",
                   "louis philippe formal shirt", "arrow formal shirt men"],
        "jeans": ["levi jeans men", "us polo jeans men", "jack jones jeans men", "roadster jeans men"],
        "trousers": ["allen solly trousers men", "us polo trousers men", "jack jones trousers men"],
        "shorts": ["puma shorts men", "adidas shorts men", "nike shorts men", "reebok shorts men"],
        "jacket": ["puma jacket men", "adidas jacket men", "nike jacket men", "under armour jacket men"],
        "trackpant": ["puma track pants men", "adidas joggers men", "nike track pants men", "reebok joggers men"],
        "shoes": ["puma shoes men", "adidas shoes men", "asics shoes men", "nike shoes men",
                   "reebok shoes men", "skechers shoes men", "new balance shoes men", "under armour shoes men"],
        "slides": ["skechers slides men", "adidas slides men", "crocs men", "puma slides men",
                    "nike slides men", "reebok slides men", "under armour slides men"],
    }

    for cat_key, cat_conf in config["categories"].items():
        for query in search_queries.get(cat_key, []):
            try:
                log.info(f"[Ajio] {query}")
                url = f"https://www.ajio.com/search/?text={query.replace(' ', '%20')}"
                resp = fetch_with_retry(session, url, timeout=25)

                if resp is None or "Access Denied" in resp.text[:500]:
                    log.warning(f"[Ajio] Blocked for {query}")
                    continue

                soup = BeautifulSoup(resp.text, "html.parser")

                # Find the big script with entities
                entities = {}
                for sc in soup.find_all("script"):
                    text = sc.string or ""
                    if len(text) > 50000 and "entities" in text:
                        m = re.search(r'window\.\w+\s*=\s*(\{.+\})\s*;?\s*$', text, re.DOTALL)
                        if m:
                            try:
                                data = json.loads(m.group(1))
                                entities = data.get("grid", {}).get("entities", {})
                            except json.JSONDecodeError:
                                pass
                        break

                log.info(f"  -> {len(entities)} products")

                for pid, p in entities.items():
                    try:
                        deal = parse_ajio_product(pid, p, brands, cat_key, cat_conf, config)
                    except Exception as e:
                        log.warning(f"[Ajio] Bad product {pid}: {e}")
                        continue
                    if deal:
                        deals.append(deal)

            except Exception as e:
                log.warning(f"[Ajio] Error for {query}: {e}")

            time.sleep(config.get("scrape_delay_seconds", 2) + random.uniform(0, 1))

    log.info(f"[Ajio] Total: {len(deals)} deals")
    return deals


# ============================================================
# MYNTRA — Extract JSON from embedded script tags
# ============================================================

# Size check. Numeric shirt sizing maps to letters roughly as
# 38/39=S, 40=M, 42=L, 44=XL, 46=XXL — so XL accepts 44/46 and
# XXL accepts 46/48. Keep the letter AND numeric forms: Myntra
# uses letters for tshirts and numbers for formal shirts.
SIZE_ALIASES = {
    "L": ["L", "l", "40", "42", "Large", "LARGE", "Lg"],
    # 42 deliberately NOT in XL: in Indian shirt sizing 42=L,
    # 44=XL, 46=XXL. Letter-sized rows match "XL" directly, so
    # only numeric-only listings depend on this — and for those,
    # 44 is the real XL. Including 42 let 31 L-max shirts through.
    "XL": ["XL", "xl", "X-Large", "XLARGE", "X Large", "44", "46"],
    "XXL": ["XXL", "xxl", "2XL", "2xl", "XX-Large", "XXLARGE", "44", "46"],
    "34": ["34", "32-34", "34-36", "32", "33", "34W"],
    "10": ["10", "UK10", "UK 10", "10UK", "44", "IND-10"],
}


def parse_myntra_product(p, brands, cat_key, cat_conf, config):
    """One Myntra search result -> deal dict, or None if it doesn't qualify."""
    name = p.get("productName", "") or p.get("name", "")
    brand_name = p.get("brand", "") or p.get("brandName", "")
    full_name = f"{brand_name} {name}"

    matched = matches_brand(full_name, brands)
    if not matched:
        return None

    mrp = p.get("mrp", 0) or 0
    price = p.get("price", 0) or p.get("discountedPrice", 0) or mrp
    if isinstance(mrp, str):
        mrp = parse_price(mrp) or 0
    if isinstance(price, str):
        price = parse_price(price) or 0

    if not price or price > cat_conf["max_price"]:
        return None

    disc_pct = 0
    if mrp > price:
        disc_pct = int(((mrp - price) / mrp) * 100)
    if disc_pct < cat_conf.get("min_discount_pct", 30):
        return None

    rating = float(p.get("rating", 0) or 0)
    rating_count = parse_rating_count(p.get("ratingCount") or p.get("totalRatings"))
    # Strict rating: must be 4.0+ OR have no ratings at all (new product)
    if rating > 0 and rating < config["min_rating"]:
        return None

    img = p.get("searchImage", "") or p.get("image", "") or p.get("defaultImage", "")
    pid = p.get("productId", "") or p.get("id", "")
    link = p.get("landingPageUrl", "") or p.get("url", "")
    if pid and not link:
        link = f"/{pid}"
    if link and not link.startswith("http"):
        if not link.startswith("/"):
            link = f"/{link}"
        link = f"https://www.myntra.com{link}"

    raw_sizes = p.get("sizes", "")
    if isinstance(raw_sizes, str):
        sizes = [s.strip() for s in raw_sizes.split(",") if s.strip()]
    elif isinstance(raw_sizes, list):
        sizes = [s.get("label", s) if isinstance(s, dict) else str(s) for s in raw_sizes]
    else:
        sizes = []

    valid_sizes = SIZE_ALIASES.get(cat_conf["size"], [cat_conf["size"]])
    # If no sizes listed at all, let it through (don't filter)
    if sizes and not any(s.strip() in valid_sizes for s in sizes):
        return None

    color = (p.get("primaryColour", "") or "").strip().lower()

    return {
        "id": make_id("myntra", link or full_name),
        "store": "Myntra",
        "brand": matched,
        "name": name,
        "category": cat_key,
        "color": color,
        "image": img,
        "url": link,
        "mrp": mrp,
        "price": price,
        "discount_pct": disc_pct,
        "rating": round(rating, 1),
        "rating_count": rating_count,
        "sizes_available": sizes,
        "scraped_at": datetime.now().isoformat()
    }


def scrape_myntra(config):
    """Myntra embeds product JSON in script tags on search pages."""
    deals = []
    brands = config["brands"]

    # Myntra works best with standard requests (curl-cffi gets empty products)
    session = get_session(config)

    SLIDE_BRANDS = "Skechers%2CADIDAS%2CPuma%2CNike%2CReebok%2CCrocs%2CUNDER+ARMOUR"

    # Myntra search URLs — sorted by discount, multiple brand groups, deep pagination
    search_urls = {
        "tshirt": [
            "https://www.myntra.com/men-tshirts?f=Brand%3AAllen+Solly%2CPuma%2CADIDAS%2CUNDER+ARMOUR%2CASICS%2CU.S.+Polo+Assn.&sort=discount",
            "https://www.myntra.com/men-tshirts?f=Brand%3AAllen+Solly%2CPuma%2CADIDAS%2CUNDER+ARMOUR%2CASICS%2CU.S.+Polo+Assn.&sort=discount&p=2",
            "https://www.myntra.com/men-tshirts?f=Brand%3AAllen+Solly%2CPuma%2CADIDAS%2CUNDER+ARMOUR%2CASICS%2CU.S.+Polo+Assn.&sort=discount&p=3",
            "https://www.myntra.com/men-tshirts?f=Brand%3ANike%2CReebok%2CLevis%2CTommy+Hilfiger%2CHRX+by+Hrithik+Roshan%2CJack+%26+Jones&sort=discount",
            "https://www.myntra.com/men-tshirts?f=Brand%3ANike%2CReebok%2CLevis%2CTommy+Hilfiger%2CHRX+by+Hrithik+Roshan%2CJack+%26+Jones&sort=discount&p=2",
            "https://www.myntra.com/men-tshirts?f=Brand%3ASuperdry%2CRoadster%2CH%26M%2CMast+%26+Harbour%2CCalvin+Klein%2CCalvin+Klein+Jeans&sort=discount",
            "https://www.myntra.com/men-tshirts?f=Brand%3ASuperdry%2CRoadster%2CH%26M%2CMast+%26+Harbour%2CCalvin+Klein%2CCalvin+Klein+Jeans&sort=discount&p=2",
        ],
        "shirt": [
            # Group 1: US Polo, Allen Solly, Levi's, Tommy
            "https://www.myntra.com/men-shirts?f=Brand%3AAllen+Solly%2CU.S.+Polo+Assn.%2CLevis%2CTommy+Hilfiger&sort=discount",
            "https://www.myntra.com/men-shirts?f=Brand%3AAllen+Solly%2CU.S.+Polo+Assn.%2CLevis%2CTommy+Hilfiger&sort=discount&p=2",
            "https://www.myntra.com/men-shirts?f=Brand%3AAllen+Solly%2CU.S.+Polo+Assn.%2CLevis%2CTommy+Hilfiger&sort=discount&p=3",
            "https://www.myntra.com/men-shirts?f=Brand%3AAllen+Solly%2CU.S.+Polo+Assn.%2CLevis%2CTommy+Hilfiger&sort=discount&p=4",
            # Group 2: Jack & Jones, Roadster, H&M, Superdry, Calvin Klein
            "https://www.myntra.com/men-shirts?f=Brand%3AJack+%26+Jones%2CRoadster%2CH%26M%2CSuperdry%2CCalvin+Klein%2CCalvin+Klein+Jeans%2CMast+%26+Harbour&sort=discount",
            "https://www.myntra.com/men-shirts?f=Brand%3AJack+%26+Jones%2CRoadster%2CH%26M%2CSuperdry%2CCalvin+Klein%2CCalvin+Klein+Jeans%2CMast+%26+Harbour&sort=discount&p=2",
            "https://www.myntra.com/men-shirts?f=Brand%3AJack+%26+Jones%2CRoadster%2CH%26M%2CSuperdry%2CCalvin+Klein%2CCalvin+Klein+Jeans%2CMast+%26+Harbour&sort=discount&p=3",
            # Group 3: Van Heusen, Arrow, Peter England, Louis Philippe, Indian Terrain
            "https://www.myntra.com/men-shirts?f=Brand%3AVan+Heusen%2CArrow%2CPeter+England%2CLouis+Philippe%2CIndian+Terrain&sort=discount",
            "https://www.myntra.com/men-shirts?f=Brand%3AVan+Heusen%2CArrow%2CPeter+England%2CLouis+Philippe%2CIndian+Terrain&sort=discount&p=2",
            "https://www.myntra.com/men-shirts?f=Brand%3AVan+Heusen%2CArrow%2CPeter+England%2CLouis+Philippe%2CIndian+Terrain&sort=discount&p=3",
            "https://www.myntra.com/men-shirts?f=Brand%3AVan+Heusen%2CArrow%2CPeter+England%2CLouis+Philippe%2CIndian+Terrain&sort=discount&p=4",
            # Group 4: Wrangler, Pepe Jeans, Gap, Benetton, Marks & Spencer, Celio
            "https://www.myntra.com/men-shirts?f=Brand%3AWrangler%2CPepe+Jeans%2CGAP%2CUnited+Colors+of+Benetton%2CMarks+%26+Spencer%2CCelio&sort=discount",
            "https://www.myntra.com/men-shirts?f=Brand%3AWrangler%2CPepe+Jeans%2CGAP%2CUnited+Colors+of+Benetton%2CMarks+%26+Spencer%2CCelio&sort=discount&p=2",
            "https://www.myntra.com/men-shirts?f=Brand%3AWrangler%2CPepe+Jeans%2CGAP%2CUnited+Colors+of+Benetton%2CMarks+%26+Spencer%2CCelio&sort=discount&p=3",
            # Group 5: Puma, Adidas, Under Armour, Flying Machine, Selected Homme
            "https://www.myntra.com/men-shirts?f=Brand%3APuma%2CADIDAS%2CUNDER+ARMOUR%2CFlying+Machine%2CSELECTED&sort=discount",
            "https://www.myntra.com/men-shirts?f=Brand%3APuma%2CADIDAS%2CUNDER+ARMOUR%2CFlying+Machine%2CSELECTED&sort=discount&p=2",
            # Group 6: Party/Occasion wear — premium brands
            "https://www.myntra.com/men-party-shirts?f=Brand%3AJack+%26+Jones%2CCalvin+Klein%2CCalvin+Klein+Jeans%2CTommy+Hilfiger%2CSuperdry%2CSELECTED&sort=discount",
            "https://www.myntra.com/men-party-shirts?f=Brand%3AJack+%26+Jones%2CCalvin+Klein%2CCalvin+Klein+Jeans%2CTommy+Hilfiger%2CSuperdry%2CSELECTED&sort=discount&p=2",
            "https://www.myntra.com/men-party-shirts?f=Brand%3AVan+Heusen%2CLouis+Philippe%2CArrow%2CAllen+Solly%2CIndian+Terrain&sort=discount",
            "https://www.myntra.com/men-party-shirts?f=Brand%3AVan+Heusen%2CLouis+Philippe%2CArrow%2CAllen+Solly%2CIndian+Terrain&sort=discount&p=2",
            # Group 7: Formal shirts
            "https://www.myntra.com/men-formal-shirts?f=Brand%3AVan+Heusen%2CLouis+Philippe%2CArrow%2CPeter+England%2CAllen+Solly&sort=discount",
            "https://www.myntra.com/men-formal-shirts?f=Brand%3AVan+Heusen%2CLouis+Philippe%2CArrow%2CPeter+England%2CAllen+Solly&sort=discount&p=2",
            "https://www.myntra.com/men-formal-shirts?f=Brand%3AVan+Heusen%2CLouis+Philippe%2CArrow%2CPeter+England%2CAllen+Solly&sort=discount&p=3",
            # Group 8: Printed/designer shirts
            "https://www.myntra.com/men-printed-shirts?f=Brand%3AJack+%26+Jones%2CSuperdry%2CMarks+%26+Spencer%2CPepe+Jeans%2CCalvin+Klein%2CCalvin+Klein+Jeans&sort=discount",
            "https://www.myntra.com/men-printed-shirts?f=Brand%3AJack+%26+Jones%2CSuperdry%2CMarks+%26+Spencer%2CPepe+Jeans%2CCalvin+Klein%2CCalvin+Klein+Jeans&sort=discount&p=2",
            # Group 9: Linen shirts (premium, wedding-worthy)
            "https://www.myntra.com/men-linen-shirts?f=Brand%3AMarks+%26+Spencer%2CAllen+Solly%2CVan+Heusen%2CLouis+Philippe%2CIndian+Terrain%2CJack+%26+Jones&sort=discount",
            "https://www.myntra.com/men-linen-shirts?f=Brand%3AMarks+%26+Spencer%2CAllen+Solly%2CVan+Heusen%2CLouis+Philippe%2CIndian+Terrain%2CJack+%26+Jones&sort=discount&p=2",
        ],
        "jeans": [
            "https://www.myntra.com/men-jeans?f=Brand%3ALevis%2CU.S.+Polo+Assn.%2CAllen+Solly%2CJack+%26+Jones%2CRoadster%2CH%26M&sort=discount",
            "https://www.myntra.com/men-jeans?f=Brand%3ALevis%2CU.S.+Polo+Assn.%2CAllen+Solly%2CJack+%26+Jones%2CRoadster%2CH%26M&sort=discount&p=2",
            "https://www.myntra.com/men-jeans?f=Brand%3ALevis%2CU.S.+Polo+Assn.%2CAllen+Solly%2CJack+%26+Jones%2CRoadster%2CH%26M&sort=discount&p=3",
        ],
        "trousers": [
            "https://www.myntra.com/men-trousers?f=Brand%3AAllen+Solly%2CU.S.+Polo+Assn.%2CTommy+Hilfiger%2CCalvin+Klein%2CCalvin+Klein+Jeans%2CJack+%26+Jones%2CLevis&sort=discount",
            "https://www.myntra.com/men-trousers?f=Brand%3AAllen+Solly%2CU.S.+Polo+Assn.%2CTommy+Hilfiger%2CCalvin+Klein%2CCalvin+Klein+Jeans%2CJack+%26+Jones%2CLevis&sort=discount&p=2",
            "https://www.myntra.com/men-trousers?f=Brand%3ARoadster%2CH%26M%2CMast+%26+Harbour%2CSuperdry%2CHRX+by+Hrithik+Roshan&sort=discount",
        ],
        "shorts": [
            "https://www.myntra.com/men-shorts?f=Brand%3APuma%2CADIDAS%2CNike%2CReebok%2CHRX+by+Hrithik+Roshan%2CU.S.+Polo+Assn.%2CRoadster&sort=discount",
            "https://www.myntra.com/men-shorts?f=Brand%3APuma%2CADIDAS%2CNike%2CReebok%2CHRX+by+Hrithik+Roshan%2CU.S.+Polo+Assn.%2CRoadster&sort=discount&p=2",
        ],
        "jacket": [
            "https://www.myntra.com/men-jackets?f=Brand%3APuma%2CADIDAS%2CNike%2CReebok%2CU.S.+Polo+Assn.%2CAllen+Solly%2CTommy+Hilfiger%2CSuperdry&sort=discount",
            "https://www.myntra.com/men-jackets?f=Brand%3APuma%2CADIDAS%2CNike%2CReebok%2CU.S.+Polo+Assn.%2CAllen+Solly%2CTommy+Hilfiger%2CSuperdry&sort=discount&p=2",
        ],
        # HRX has ~2,900 deep-discount listings; sharing a discount sort with
        # it, the other sports brands never reached the first 4 pages.
        "trackpant": [
            "https://www.myntra.com/men-track-pants?f=Brand%3APuma%2CADIDAS%2CNike%2CReebok%2CUNDER+ARMOUR%2CASICS&sort=discount",
            "https://www.myntra.com/men-track-pants?f=Brand%3APuma%2CADIDAS%2CNike%2CReebok%2CUNDER+ARMOUR%2CASICS&sort=discount&p=2",
            "https://www.myntra.com/men-track-pants?f=Brand%3APuma%2CADIDAS%2CNike%2CReebok%2CUNDER+ARMOUR%2CASICS&sort=discount&p=3",
            "https://www.myntra.com/men-track-pants?f=Brand%3APuma%2CADIDAS%2CNike%2CReebok%2CUNDER+ARMOUR%2CASICS&sort=discount&p=4",
            "https://www.myntra.com/men-track-pants?f=Brand%3AHRX+by+Hrithik+Roshan&sort=discount",
            "https://www.myntra.com/men-track-pants?f=Brand%3AHRX+by+Hrithik+Roshan&sort=discount&p=2",
        ],
        "shoes": [
            "https://www.myntra.com/men-sports-shoes?f=Brand%3APuma%2CADIDAS%2CUNDER+ARMOUR%2CASICS%2CNike%2CReebok%2CSkechers%2CNew+Balance&sort=discount",
            "https://www.myntra.com/men-sports-shoes?f=Brand%3APuma%2CADIDAS%2CUNDER+ARMOUR%2CASICS%2CNike%2CReebok%2CSkechers%2CNew+Balance&sort=discount&p=2",
            "https://www.myntra.com/men-sports-shoes?f=Brand%3APuma%2CADIDAS%2CUNDER+ARMOUR%2CASICS%2CNike%2CReebok%2CSkechers%2CNew+Balance&sort=discount&p=3",
            "https://www.myntra.com/men-casual-shoes?f=Brand%3APuma%2CADIDAS%2CNike%2CReebok%2CSkechers%2CNew+Balance&sort=discount",
            "https://www.myntra.com/men-casual-shoes?f=Brand%3APuma%2CADIDAS%2CNike%2CReebok%2CSkechers%2CNew+Balance&sort=discount&p=2",
        ],
        # Every page, not just the top-discount ones: the comfort models
        # (Adilette Comfort, Skechers Arch Fit, Crocs) rarely lead a discount
        # sort. men-flip-flops had 311 listings on 2026-09-27 = 7 pages.
        "slides": [
            f"https://www.myntra.com/men-flip-flops?f=Brand%3A{SLIDE_BRANDS}&sort=discount&p={p}"
            for p in range(1, 8)
        ] + [
            f"https://www.myntra.com/men-sandals?f=Brand%3A{SLIDE_BRANDS}&sort=discount&p={p}"
            for p in range(1, 4)
        ],
    }

    # Discount-sorted pages are mostly old clearance stock (median product id
    # 33M vs 46M for Myntra's newest tees on 2026-09-27), yet 46 of the 50
    # newest tees were 30%+ off too. So every filter group is also read
    # newest-first (2 pages) and by popularity (1 page).
    for cat, urls in search_urls.items():
        extra = []
        for u in urls:
            if "sort=discount" in u and not re.search(r"&p=([2-9]|\d\d)", u):
                base = re.sub(r"&p=1$", "", u)
                extra += [base.replace("sort=discount", "sort=new"),
                          base.replace("sort=discount", "sort=popularity")]
        # The server-rendered page holds only the first 50 results whatever
        # &p= says (p=2 returned p=1's exact list, checked 2026-09-27), so
        # later pages were duplicate requests.
        search_urls[cat] = [u for u in urls if not re.search(r"&p=([2-9]|\d\d)", u)] + extra

    for cat_key, cat_conf in config["categories"].items():
        for url in search_urls.get(cat_key, []):
            try:
                log.info(f"[Myntra] Fetching {cat_key} page...")
                resp = fetch_with_retry(session, url, timeout=15)
                if resp is None:
                    continue

                soup = BeautifulSoup(resp.text, "html.parser")
                scripts = soup.find_all("script")

                # Find the script containing window.__myx with searchData
                products = []
                for script in scripts:
                    text = script.string or ""
                    if "searchData" not in text or len(text) < 1000:
                        continue

                    # Parse window.__myx = {...};
                    m = re.search(r'window\.__myx\s*=\s*(\{.+\})\s*;?\s*$', text, re.DOTALL)
                    if m:
                        try:
                            data = json.loads(m.group(1))
                            products = data.get("searchData", {}).get("results", {}).get("products", [])
                            if products:
                                break
                        except json.JSONDecodeError:
                            pass

                    # Fallback: extract products array by bracket matching
                    idx = text.find('"products":[')
                    if idx > 0:
                        bracket_start = idx + len('"products":[')
                        depth = 1
                        pos = bracket_start
                        while pos < len(text) and depth > 0:
                            if text[pos] == '[': depth += 1
                            elif text[pos] == ']': depth -= 1
                            pos += 1
                        try:
                            products = json.loads('[' + text[bracket_start:pos-1] + ']')
                            break
                        except json.JSONDecodeError:
                            pass

                if not products:
                    log.warning(f"[Myntra] No product JSON found in page")
                    continue

                log.info(f"  -> {len(products)} products found")

                for p in products:
                    try:
                        deal = parse_myntra_product(p, brands, cat_key, cat_conf, config)
                    except Exception as e:
                        log.warning(f"[Myntra] Bad product {p.get('productId', '?')}: {e}")
                        continue
                    if deal:
                        deals.append(deal)

            except Exception as e:
                log.warning(f"[Myntra] Error: {e}")

            time.sleep(random.uniform(1.5, 3.5))  # Random delay to avoid rate limiting

    log.info(f"[Myntra] Total: {len(deals)} deals")
    return deals


# ============================================================
# MAIN
# ============================================================
WOMEN_KEYWORDS = ['women', 'woman', "women's", 'ladies', 'girls', 'girl', 'legging',
    'kurti', 'saree', 'salwar', 'anarkali', 'lehenga', 'palazzo', 'skirt', 'crop top',
    'maternity', 'nightgown', 'bikini', 'lingerie', ' her ', 'feminine', 'floral dress']

# Whole words only: a substring " bra" matched " brand" and threw out every
# "Brand Logo" product (about half of Myntra's newest tees, 2026-09-27).
KIDS_RE = re.compile(r"\b(boys?|kids?|bras?)\b", re.I)

def is_mens_product(deal):
    """Filter out women's products that slipped through."""
    name = deal.get("name", "").lower()
    # Skip furniture — no gender filter needed
    if deal.get("category") == "furniture":
        return True
    for kw in WOMEN_KEYWORDS:
        if kw in name:
            return False
    return not KIDS_RE.search(name)

# Owner hard rule (profile.json fit_rules.avoid): never slim/skinny/muscle
# fits — BMI 32.7. Applies to clothing; shoe names use 'slim' differently.
FIT_BAN_RE = re.compile(r"\b(slim|skinny|muscle\s*fit|extra\s*slim|super\s*slim)\b", re.I)
TSHIRT_RE = re.compile(r"\bt[\s-]?shirts?\b|\btees?\b|\bpolo\b", re.I)
SHIRT_RE = re.compile(r"\bshirts?\b", re.I)
# Myntra names repeat the brand, and "U.S. Polo Assn." tripped TSHIRT_RE's
# polo: 49 USPA casual shirts were filed as tees (2026-09-27).
USPA_RE = re.compile(r"u\.?\s*s\.?\s*polo\s*assn\.?", re.I)

# Activewear vs casual tees: shared with the stock stage, which refines it
# from the product page's fabric/occasion.
from classify import tee_style

# Ajio labels a product with the category of the SEARCH that found it, so
# "adidas jacket men" filed Adilette Comfort slides under jacket and a U.S.
# Polo sandal landed in shirt. The name is the better signal for footwear.
# No "boot": it would pull "Boot Cut" jeans into shoes.
SLIDES_RE = re.compile(r"\b(slides?|sliders?|flip[\s-]?flops?|sandals?|slippers?|clogs?|floaters?)\b", re.I)
SHOES_RE = re.compile(r"\b(shoes?|sneakers?)\b", re.I)
# Garment words win: "Sneaker Print Regular Fit T-Shirt" is a tee.
APPAREL_RE = re.compile(r"\b(t[\s-]?shirts?|tees?|shirts?|polos?|jackets?|shorts|trousers|jeans|"
                        r"joggers|track\s*pants?|hoodies?|sweatshirts?)\b", re.I)
FOOTWEAR = {"shoes", "slides"}

def deduplicate(deals):
    seen = set()
    seen_alt = set()
    unique = []
    for d in deals:
        if not is_mens_product(d):
            continue
        # Ajio files polos/tees under 'shirt' (72 rows on 2026-07-30) and
        # shirts under 'tshirt' — the name decides, so the right budget cap
        # and tab apply. Also repairs rows kept from earlier runs.
        name = d.get("name", "")
        if d.get("category") in ("shirt", "tshirt"):
            bare = USPA_RE.sub("", name)
            if TSHIRT_RE.search(bare):
                d["category"] = "tshirt"
            elif SHIRT_RE.search(bare):
                d["category"] = "shirt"
        if not APPAREL_RE.search(name):
            # A shoe word wins: "Court Slide 4 Tennis Shoes", "Go Walk Flex
            # Slip-On Shoes" are shoes even when a slides search found them.
            if SHOES_RE.search(name):
                d["category"] = "shoes"
            elif SLIDES_RE.search(name):
                d["category"] = "slides"
        if d.get("category") not in FOOTWEAR and FIT_BAN_RE.search(d.get("name", "")):
            continue
        if d.get("category") == "tshirt":
            d["style"] = tee_style(d)
        else:
            d.pop("style", None)
        # Myntra serves http:// image urls — mixed content on https pages.
        img = d.get("image") or ""
        if img.startswith("http://"):
            d["image"] = "https://" + img[7:]
        # Same product scraped twice with different ids (url variants):
        # collapse on (store, brand, name, color) too.
        alt = (d["store"], d["brand"].lower(), d["name"].lower(), (d.get("color") or "").lower())
        if alt in seen_alt:
            continue
        seen_alt.add(alt)
        # Key on the store's own product id — it's unique and stable.
        # The old key (brand + name[:50] + store) silently dropped ~70% of
        # Myntra: Myntra repeats the brand inside the name (531/546 rows) so
        # the 50-char window ran out before the distinguishing part, and colour
        # wasn't in the key at all — so the same shirt in 4 colours collapsed
        # into 1. Ajio names don't repeat the brand (6/1197), which is why it
        # looked like Myntra simply had less stock.
        key = f"{d['store']}_{d['id']}" if d.get("id") else \
              f"{d['brand'].lower()}_{d['name'].lower()}_{d.get('color','')}_{d['store']}"
        if key not in seen:
            seen.add(key)
            unique.append(d)
    return unique


FIRST_SEEN_PATH = BASE_DIR / "first_seen.json"


def load_first_seen():
    """id -> first time any run saw it. Outlives deals.json rows, which get
    dropped (sale ended, sold out, 7 days out of search) and would otherwise
    come back badged NEW."""
    try:
        return json.load(open(FIRST_SEEN_PATH))
    except (OSError, ValueError):
        return {}


def save_first_seen(new):
    seen = load_first_seen()
    added = {k: v for k, v in new.items() if k not in seen}
    if added:
        seen.update(added)
        tmp = FIRST_SEEN_PATH.with_suffix(".json.tmp")
        with open(tmp, "w") as f:
            json.dump(seen, f, separators=(",", ":"))
        os.replace(tmp, FIRST_SEEN_PATH)


def run_scraper():
    config = load_config()
    # One stamp for the whole run, so "Newest first" can tie-break a run's
    # new rows by product id instead of by crawl order.
    run_at = datetime.now().isoformat(timespec="seconds")
    all_deals = []

    # Myntra FIRST — preferred store (faster delivery in Vijayawada)
    try:
        all_deals.extend(scrape_myntra(config))
    except Exception as e:
        log.error(f"[Myntra] Crashed: {e}")

    # Ajio second — slower delivery, used as backup/variety
    try:
        all_deals.extend(scrape_ajio(config))
    except Exception as e:
        log.error(f"[Ajio] Crashed: {e}")

    all_deals = deduplicate(all_deals)
    all_deals.sort(key=lambda x: x["discount_pct"], reverse=True)

    # Safety: merge with existing deals — never lose data
    if DEALS_PATH.exists():
        try:
            with open(DEALS_PATH) as f:
                existing = json.load(f)
            existing_deals = existing.get("deals", [])
            # Merge: keep existing deals not in new results + add all new.
            # Age cap: a deal that stops appearing in search results is gone
            # (sold out / price changed), so retire it after MAX_KEEP_DAYS
            # instead of carrying a stale price forever. The old dedup key
            # used to prune these by accident — keying on id doesn't, so the
            # cap has to be explicit.
            cutoff = datetime.now() - timedelta(days=MAX_KEEP_DAYS)
            new_ids = {d["id"] for d in all_deals}
            # first_seen survives re-scrapes. Rows from before the field
            # existed stay None: their real first sighting is unknown, and
            # back-filling from scraped_at would badge them all NEW.
            first = {d["id"]: d.get("first_seen") for d in existing_deals}
            first.update(load_first_seen())
            for d in all_deals:
                d["first_seen"] = first[d["id"]] if d["id"] in first else run_at
            save_first_seen({d["id"]: d["first_seen"] for d in all_deals if d.get("first_seen")})
            kept, expired = [], 0
            for d in existing_deals:
                if d["id"] in new_ids:
                    continue
                try:
                    fresh = datetime.fromisoformat(d["scraped_at"]) >= cutoff
                except (KeyError, ValueError):
                    fresh = False  # no usable timestamp — treat as stale
                if fresh:
                    kept.append(d)
                else:
                    expired += 1
            all_deals = all_deals + kept
            all_deals = deduplicate(all_deals)
            all_deals.sort(key=lambda x: x["discount_pct"], reverse=True)
            log.info(f"Merged: {len(all_deals)} total ({len(kept)} kept, {expired} expired >{MAX_KEEP_DAYS}d)")
        except Exception as e:
            log.warning(f"Could not merge existing deals: {e}")

    # Budget cap applied LAST so it also covers rows kept from previous runs
    # and rows deduplicate() reclassified shirt->tshirt (lower cap).
    cats = config["categories"]
    before = len(all_deals)
    all_deals = [d for d in all_deals
                 if d["price"] <= cats.get(d["category"], {}).get("max_price", 10**9)]
    if before - len(all_deals):
        log.info(f"Budget cap dropped {before - len(all_deals)} rows")

    result = {
        "last_updated": datetime.now().isoformat(),
        "total_deals": len(all_deals),
        "deals": all_deals
    }

    # Atomic write: the dashboard and Super Pick read this file while the
    # scraper runs — a kill mid-dump must not leave a truncated deals.json.
    tmp_path = DEALS_PATH.with_suffix(".json.tmp")
    with open(tmp_path, "w") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    os.replace(tmp_path, DEALS_PATH)

    log.info(f"DONE — {len(all_deals)} total deals saved to {DEALS_PATH}")
    return result


if __name__ == "__main__":
    run_scraper()
    # Stock is a separate stage: if it fails, deals.json still publishes.
    try:
        from check_stock import refresh_stock
        refresh_stock()
    except Exception as e:
        log.error(f"[Stock] refresh failed: {e}")
