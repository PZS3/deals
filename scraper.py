#!/usr/bin/env python3
"""
Prazwal's Deal Finder — Myntra + Ajio only
Myntra: extract embedded JSON from HTML script tags
Ajio: direct JSON API endpoint
"""

import json
import re
import time
import random
import hashlib
import logging
from datetime import datetime
from pathlib import Path
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup

BASE_DIR = Path(__file__).parent
CONFIG_PATH = BASE_DIR / "config.json"
DEALS_PATH = BASE_DIR / "deals.json"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
log = logging.getLogger("deals")


def load_config():
    with open(CONFIG_PATH) as f:
        return json.load(f)


def get_session():
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-IN,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
    })
    return s


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


def matches_brand(name, brands):
    name_lower = name.lower()
    for brand in brands:
        if brand.lower() in name_lower:
            return brand
    return None


# ============================================================
# AJIO — curl-cffi search page + embedded entities extraction
# ============================================================
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
    }

    for cat_key, cat_conf in config["categories"].items():
        for query in search_queries.get(cat_key, []):
            try:
                log.info(f"[Ajio] {query}")
                url = f"https://www.ajio.com/search/?text={query.replace(' ', '%20')}"
                resp = session.get(url, timeout=25)

                if resp.status_code != 200 or "Access Denied" in resp.text[:500]:
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
                    fnl = p.get("fnlColorVariantData", {}) or {}
                    brand_name = fnl.get("brandName", "")
                    name = p.get("name", "")
                    full_name = f"{brand_name} {name}"

                    matched = matches_brand(full_name, brands)
                    if not matched:
                        continue

                    # Price
                    price_obj = p.get("price", {})
                    price = parse_price(price_obj.get("value")) if isinstance(price_obj, dict) else parse_price(price_obj)

                    mrp_obj = p.get("wasPriceData", {})
                    mrp = parse_price(mrp_obj.get("value")) if isinstance(mrp_obj, dict) else parse_price(mrp_obj)

                    if not price or price == 0:
                        continue
                    if not mrp:
                        mrp = price
                    if price > cat_conf["max_price"]:
                        continue

                    # Discount - can be "60% off" string or int
                    disc_raw = p.get("discountPercent", 0) or 0
                    disc_pct = 0
                    if isinstance(disc_raw, str):
                        d_match = re.search(r'(\d+)', disc_raw)
                        if d_match:
                            disc_pct = int(d_match.group(1))
                    elif isinstance(disc_raw, (int, float)):
                        disc_pct = int(disc_raw)
                    if not disc_pct and mrp and mrp > price:
                        disc_pct = int(((mrp - price) / mrp) * 100)
                    if disc_pct < cat_conf.get("min_discount_pct", 30):
                        continue

                    # Rating
                    rating = float(p.get("averageRating", 0) or 0)
                    rating_count_raw = p.get("ratingCount", "0") or "0"
                    rating_count = 0
                    if isinstance(rating_count_raw, str):
                        # Handle "2.2K", "1.5K", "204" etc
                        rc_str = rating_count_raw.strip()
                        if "K" in rc_str.upper():
                            num = float(rc_str.upper().replace("K", "").strip())
                            rating_count = int(num * 1000)
                        else:
                            rating_count = parse_price(rc_str) or 0
                    else:
                        rating_count = int(rating_count_raw)

                    # Strict rating: must be 4.0+ OR have no ratings at all (new product)
                    if rating > 0 and rating < config["min_rating"]:
                        continue

                    # Image
                    img = fnl.get("outfitPictureURL", "") or ""
                    if not img:
                        images = p.get("images", [])
                        if images:
                            img = images[0].get("url", "") if isinstance(images[0], dict) else str(images[0])
                    if img and not img.startswith("http"):
                        img = f"https://assets.ajio.com/medias/{img}"

                    # URL
                    url_path = p.get("url", "")
                    product_url = f"https://www.ajio.com{url_path}" if url_path else ""

                    # Color
                    color = (fnl.get("colorGroup", "") or p.get("colour", "") or "").strip().lower()

                    deals.append({
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
                    })

            except Exception as e:
                log.warning(f"[Ajio] Error for {query}: {e}")

            time.sleep(2)

    log.info(f"[Ajio] Total: {len(deals)} deals")
    return deals


# ============================================================
# MYNTRA — Extract JSON from embedded script tags
# ============================================================
def scrape_myntra(config):
    """Myntra embeds product JSON in script tags on search pages."""
    deals = []
    session = get_session()
    brands = config["brands"]

    # Myntra search URLs — sorted by discount, multiple brand groups, deep pagination
    search_urls = {
        "tshirt": [
            "https://www.myntra.com/men-tshirts?f=Brand%3AAllen+Solly%2CPUMA%2CAdidas%2CUnder+Armour%2CASICS%2CU.S.+Polo+Assn.&sort=discount",
            "https://www.myntra.com/men-tshirts?f=Brand%3AAllen+Solly%2CPUMA%2CAdidas%2CUnder+Armour%2CASICS%2CU.S.+Polo+Assn.&sort=discount&p=2",
            "https://www.myntra.com/men-tshirts?f=Brand%3AAllen+Solly%2CPUMA%2CAdidas%2CUnder+Armour%2CASICS%2CU.S.+Polo+Assn.&sort=discount&p=3",
            "https://www.myntra.com/men-tshirts?f=Brand%3ANike%2CReebok%2CLevi%2527s%2CTommy+Hilfiger%2CHRX+by+Hrithik+Roshan%2CJack+%26+Jones&sort=discount",
            "https://www.myntra.com/men-tshirts?f=Brand%3ANike%2CReebok%2CLevi%2527s%2CTommy+Hilfiger%2CHRX+by+Hrithik+Roshan%2CJack+%26+Jones&sort=discount&p=2",
            "https://www.myntra.com/men-tshirts?f=Brand%3ASuperdry%2CRoadster%2CH%26M%2CMast+%26+Harbour%2CCalvin+Klein&sort=discount",
            "https://www.myntra.com/men-tshirts?f=Brand%3ASuperdry%2CRoadster%2CH%26M%2CMast+%26+Harbour%2CCalvin+Klein&sort=discount&p=2",
        ],
        "shirt": [
            # Group 1: US Polo, Allen Solly, Levi's, Tommy
            "https://www.myntra.com/men-shirts?f=Brand%3AAllen+Solly%2CU.S.+Polo+Assn.%2CLevi%2527s%2CTommy+Hilfiger&sort=discount",
            "https://www.myntra.com/men-shirts?f=Brand%3AAllen+Solly%2CU.S.+Polo+Assn.%2CLevi%2527s%2CTommy+Hilfiger&sort=discount&p=2",
            "https://www.myntra.com/men-shirts?f=Brand%3AAllen+Solly%2CU.S.+Polo+Assn.%2CLevi%2527s%2CTommy+Hilfiger&sort=discount&p=3",
            "https://www.myntra.com/men-shirts?f=Brand%3AAllen+Solly%2CU.S.+Polo+Assn.%2CLevi%2527s%2CTommy+Hilfiger&sort=discount&p=4",
            # Group 2: Jack & Jones, Roadster, H&M, Superdry, Calvin Klein
            "https://www.myntra.com/men-shirts?f=Brand%3AJack+%26+Jones%2CRoadster%2CH%26M%2CSuperdry%2CCalvin+Klein%2CMast+%26+Harbour&sort=discount",
            "https://www.myntra.com/men-shirts?f=Brand%3AJack+%26+Jones%2CRoadster%2CH%26M%2CSuperdry%2CCalvin+Klein%2CMast+%26+Harbour&sort=discount&p=2",
            "https://www.myntra.com/men-shirts?f=Brand%3AJack+%26+Jones%2CRoadster%2CH%26M%2CSuperdry%2CCalvin+Klein%2CMast+%26+Harbour&sort=discount&p=3",
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
            "https://www.myntra.com/men-shirts?f=Brand%3APUMA%2CAdidas%2CUnder+Armour%2CFlying+Machine%2CSELECTED&sort=discount",
            "https://www.myntra.com/men-shirts?f=Brand%3APUMA%2CAdidas%2CUnder+Armour%2CFlying+Machine%2CSELECTED&sort=discount&p=2",
            # Group 6: Party/Occasion wear — premium brands
            "https://www.myntra.com/men-party-shirts?f=Brand%3AJack+%26+Jones%2CCalvin+Klein%2CTommy+Hilfiger%2CSuperdry%2CSELECTED&sort=discount",
            "https://www.myntra.com/men-party-shirts?f=Brand%3AJack+%26+Jones%2CCalvin+Klein%2CTommy+Hilfiger%2CSuperdry%2CSELECTED&sort=discount&p=2",
            "https://www.myntra.com/men-party-shirts?f=Brand%3AVan+Heusen%2CLouis+Philippe%2CArrow%2CAllen+Solly%2CIndian+Terrain&sort=discount",
            "https://www.myntra.com/men-party-shirts?f=Brand%3AVan+Heusen%2CLouis+Philippe%2CArrow%2CAllen+Solly%2CIndian+Terrain&sort=discount&p=2",
            # Group 7: Formal shirts
            "https://www.myntra.com/men-formal-shirts?f=Brand%3AVan+Heusen%2CLouis+Philippe%2CArrow%2CPeter+England%2CAllen+Solly&sort=discount",
            "https://www.myntra.com/men-formal-shirts?f=Brand%3AVan+Heusen%2CLouis+Philippe%2CArrow%2CPeter+England%2CAllen+Solly&sort=discount&p=2",
            "https://www.myntra.com/men-formal-shirts?f=Brand%3AVan+Heusen%2CLouis+Philippe%2CArrow%2CPeter+England%2CAllen+Solly&sort=discount&p=3",
            # Group 8: Printed/designer shirts
            "https://www.myntra.com/men-printed-shirts?f=Brand%3AJack+%26+Jones%2CSuperdry%2CMarks+%26+Spencer%2CPepe+Jeans%2CCalvin+Klein&sort=discount",
            "https://www.myntra.com/men-printed-shirts?f=Brand%3AJack+%26+Jones%2CSuperdry%2CMarks+%26+Spencer%2CPepe+Jeans%2CCalvin+Klein&sort=discount&p=2",
            # Group 9: Linen shirts (premium, wedding-worthy)
            "https://www.myntra.com/men-linen-shirts?f=Brand%3AMarks+%26+Spencer%2CAllen+Solly%2CVan+Heusen%2CLouis+Philippe%2CIndian+Terrain%2CJack+%26+Jones&sort=discount",
            "https://www.myntra.com/men-linen-shirts?f=Brand%3AMarks+%26+Spencer%2CAllen+Solly%2CVan+Heusen%2CLouis+Philippe%2CIndian+Terrain%2CJack+%26+Jones&sort=discount&p=2",
        ],
        "jeans": [
            "https://www.myntra.com/men-jeans?f=Brand%3ALevi%2527s%2CU.S.+Polo+Assn.%2CAllen+Solly%2CJack+%26+Jones%2CRoadster%2CH%26M&sort=discount",
            "https://www.myntra.com/men-jeans?f=Brand%3ALevi%2527s%2CU.S.+Polo+Assn.%2CAllen+Solly%2CJack+%26+Jones%2CRoadster%2CH%26M&sort=discount&p=2",
            "https://www.myntra.com/men-jeans?f=Brand%3ALevi%2527s%2CU.S.+Polo+Assn.%2CAllen+Solly%2CJack+%26+Jones%2CRoadster%2CH%26M&sort=discount&p=3",
        ],
        "trousers": [
            "https://www.myntra.com/men-trousers?f=Brand%3AAllen+Solly%2CU.S.+Polo+Assn.%2CTommy+Hilfiger%2CCalvin+Klein%2CJack+%26+Jones%2CLevi%2527s&sort=discount",
            "https://www.myntra.com/men-trousers?f=Brand%3AAllen+Solly%2CU.S.+Polo+Assn.%2CTommy+Hilfiger%2CCalvin+Klein%2CJack+%26+Jones%2CLevi%2527s&sort=discount&p=2",
            "https://www.myntra.com/men-trousers?f=Brand%3ARoadster%2CH%26M%2CMast+%26+Harbour%2CSuperdry%2CHRX+by+Hrithik+Roshan&sort=discount",
        ],
        "shorts": [
            "https://www.myntra.com/men-shorts?f=Brand%3APUMA%2CAdidas%2CNike%2CReebok%2CHRX+by+Hrithik+Roshan%2CU.S.+Polo+Assn.%2CRoadster&sort=discount",
            "https://www.myntra.com/men-shorts?f=Brand%3APUMA%2CAdidas%2CNike%2CReebok%2CHRX+by+Hrithik+Roshan%2CU.S.+Polo+Assn.%2CRoadster&sort=discount&p=2",
        ],
        "jacket": [
            "https://www.myntra.com/men-jackets?f=Brand%3APUMA%2CAdidas%2CNike%2CReebok%2CU.S.+Polo+Assn.%2CAllen+Solly%2CTommy+Hilfiger%2CSuperdry&sort=discount",
            "https://www.myntra.com/men-jackets?f=Brand%3APUMA%2CAdidas%2CNike%2CReebok%2CU.S.+Polo+Assn.%2CAllen+Solly%2CTommy+Hilfiger%2CSuperdry&sort=discount&p=2",
        ],
        "trackpant": [
            "https://www.myntra.com/men-track-pants?f=Brand%3APUMA%2CAdidas%2CNike%2CReebok%2CHRX+by+Hrithik+Roshan%2CUnder+Armour%2CASICS&sort=discount",
            "https://www.myntra.com/men-track-pants?f=Brand%3APUMA%2CAdidas%2CNike%2CReebok%2CHRX+by+Hrithik+Roshan%2CUnder+Armour%2CASICS&sort=discount&p=2",
        ],
        "shoes": [
            "https://www.myntra.com/men-sports-shoes?f=Brand%3APUMA%2CAdidas%2CUnder+Armour%2CASICS%2CNike%2CReebok%2CSkechers%2CNew+Balance&sort=discount",
            "https://www.myntra.com/men-sports-shoes?f=Brand%3APUMA%2CAdidas%2CUnder+Armour%2CASICS%2CNike%2CReebok%2CSkechers%2CNew+Balance&sort=discount&p=2",
            "https://www.myntra.com/men-sports-shoes?f=Brand%3APUMA%2CAdidas%2CUnder+Armour%2CASICS%2CNike%2CReebok%2CSkechers%2CNew+Balance&sort=discount&p=3",
            "https://www.myntra.com/men-casual-shoes?f=Brand%3APUMA%2CAdidas%2CNike%2CReebok%2CSkechers%2CNew+Balance&sort=discount",
            "https://www.myntra.com/men-casual-shoes?f=Brand%3APUMA%2CAdidas%2CNike%2CReebok%2CSkechers%2CNew+Balance&sort=discount&p=2",
        ],
    }

    for cat_key, cat_conf in config["categories"].items():
        for url in search_urls.get(cat_key, []):
            try:
                log.info(f"[Myntra] Fetching {cat_key} page...")
                resp = session.get(url, timeout=15)

                if resp.status_code != 200:
                    log.warning(f"[Myntra] HTTP {resp.status_code}")
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
                    name = p.get("productName", "") or p.get("name", "")
                    brand_name = p.get("brand", "") or p.get("brandName", "")
                    full_name = f"{brand_name} {name}"

                    matched = matches_brand(full_name, brands)
                    if not matched:
                        continue

                    mrp = p.get("mrp", 0) or 0
                    price = p.get("price", 0) or p.get("discountedPrice", 0) or mrp
                    if isinstance(mrp, str):
                        mrp = parse_price(mrp) or 0
                    if isinstance(price, str):
                        price = parse_price(price) or 0

                    if not price or price > cat_conf["max_price"]:
                        continue

                    disc_pct = 0
                    if mrp > price:
                        disc_pct = int(((mrp - price) / mrp) * 100)
                    if disc_pct < cat_conf.get("min_discount_pct", 40):
                        continue

                    rating = float(p.get("rating", 0) or 0)
                    rating_count = int(p.get("ratingCount", 0) or p.get("totalRatings", 0) or 0)
                    # Strict rating: must be 4.0+ OR have no ratings at all (new product)
                    if rating > 0 and rating < config["min_rating"]:
                        continue

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

                    # Size check: L = 40/42 for shirts, L for tshirts, 10/UK10 for shoes, 34 for pants
                    target_size = cat_conf["size"]
                    size_aliases = {
                        "L": ["L", "l", "40", "42", "Large"],
                        "34": ["34", "32-34", "34-36"],
                        "10": ["10", "UK10", "UK 10", "10UK"],
                    }
                    valid_sizes = size_aliases.get(target_size, [target_size])
                    if sizes and not any(s.strip() in valid_sizes for s in sizes):
                        continue

                    # Color
                    color = (p.get("primaryColour", "") or "").strip().lower()

                    deals.append({
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
                    })

            except Exception as e:
                log.warning(f"[Myntra] Error: {e}")

            time.sleep(2)

    log.info(f"[Myntra] Total: {len(deals)} deals")
    return deals


# ============================================================
# MAIN
# ============================================================
WOMEN_KEYWORDS = ['women', 'woman', "women's", 'ladies', 'girls', 'girl', 'bra ', 'legging',
    'kurti', 'saree', 'salwar', 'anarkali', 'lehenga', 'palazzo', 'skirt', 'crop top',
    'maternity', 'nightgown', 'bikini', 'lingerie', ' her ', 'feminine', 'floral dress']

def is_mens_product(deal):
    """Filter out women's products that slipped through."""
    name = deal.get("name", "").lower()
    brand = deal.get("brand", "").lower()
    # Skip furniture — no gender filter needed
    if deal.get("category") == "furniture":
        return True
    for kw in WOMEN_KEYWORDS:
        if kw in name:
            return False
    return True

def deduplicate(deals):
    seen = {}
    unique = []
    for d in deals:
        if not is_mens_product(d):
            continue
        key = f"{d['brand'].lower()}_{d['name'].lower()[:50]}_{d['store']}"
        if key not in seen:
            seen[key] = True
            unique.append(d)
    return unique


def run_scraper():
    config = load_config()
    all_deals = []

    # Ajio — curl-cffi search page scraping
    try:
        all_deals.extend(scrape_ajio(config))
    except Exception as e:
        log.error(f"[Ajio] Crashed: {e}")

    # Myntra — embedded JSON
    try:
        all_deals.extend(scrape_myntra(config))
    except Exception as e:
        log.error(f"[Myntra] Crashed: {e}")

    all_deals = deduplicate(all_deals)
    all_deals.sort(key=lambda x: x["discount_pct"], reverse=True)

    # Safety: merge with existing deals — never lose data
    if DEALS_PATH.exists():
        try:
            with open(DEALS_PATH) as f:
                existing = json.load(f)
            existing_deals = existing.get("deals", [])
            # Merge: keep existing deals not in new results + add all new
            new_ids = {d["id"] for d in all_deals}
            kept = [d for d in existing_deals if d["id"] not in new_ids]
            all_deals = all_deals + kept
            all_deals = deduplicate(all_deals)
            all_deals.sort(key=lambda x: x["discount_pct"], reverse=True)
            log.info(f"Merged: {len(all_deals)} total ({len(kept)} kept from previous)")
        except Exception as e:
            log.warning(f"Could not merge existing deals: {e}")

    result = {
        "last_updated": datetime.now().isoformat(),
        "total_deals": len(all_deals),
        "deals": all_deals
    }

    with open(DEALS_PATH, "w") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    log.info(f"DONE — {len(all_deals)} total deals saved to {DEALS_PATH}")
    return result


if __name__ == "__main__":
    run_scraper()
