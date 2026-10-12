#!/usr/bin/env python3
"""
Extractor for Bambu Lab filament store product URLs.
Matches product variants against the local filament database.
"""
import json
import os
import re
from urllib.parse import urlparse, parse_qs
import requests
from bs4 import BeautifulSoup

HERE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(HERE, "filament_db.json")

def load_db():
    if os.path.exists(DB_PATH):
        with open(DB_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def find_in_db(code=None, name=None, material=None, db=None):
    if db is None:
        db = load_db()
    
    # 1. Match by exact code
    if code:
        clean_code = re.sub(r"\D", "", str(code))
        for item in db:
            if item.get("code") == clean_code:
                return item
                
    # 2. Match by exact English or Chinese name
    if name:
        name_clean = name.strip().lower()
        for item in db:
            if (item.get("name_en", "").strip().lower() == name_clean or
                item.get("name_zh", "").strip() == name.strip()):
                if material:
                    # check if material matches roughly
                    mat_clean = material.strip().lower()
                    db_mat = item.get("material", "").strip().lower()
                    if mat_clean in db_mat or db_mat in mat_clean:
                        return item
                else:
                    return item

    # 3. Fuzzy match name
    if name:
        name_clean = name.strip().lower()
        for item in db:
            if name_clean in item.get("name_en", "").strip().lower():
                return item
                
    return None

def extract_from_url(url: str):
    """
    Extract product info and variants from a Bambu Lab store URL.
    Returns dict with product info and list of variants.
    """
    db = load_db()
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    target_sku = qs.get("id", [None])[0]

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    try:
        resp = requests.get(url, headers=headers, timeout=12)
        resp.raise_for_status()
        html = resp.text
    except Exception as e:
        return {
            "success": False,
            "error": f"Failed to fetch page: {str(e)}"
        }

    soup = BeautifulSoup(html, "html.parser")
    
    product_name = None
    variants = []
    
    # Try ld+json ProductGroup
    for s in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(s.string or "")
            if data.get("@type") == "ProductGroup":
                product_name = data.get("name")
                for v in data.get("hasVariant", []):
                    raw_title = v.get("name", "")
                    sku = str(v.get("sku", ""))
                    
                    # Pattern e.g.: "PLA Wood - White Oak (13106) / Filament with spool / 1 kg"
                    m = re.search(r"-\s*(.*?)\s*\((\d+)\)", raw_title)
                    if m:
                        c_name = m.group(1).strip()
                        c_code = m.group(2).strip()
                    else:
                        c_name = raw_title.split("/")[0].replace(product_name or "", "").replace("-", "").strip()
                        c_code = ""

                    # Match against local Bambu filament database
                    db_match = find_in_db(code=c_code, name=c_name, material=product_name, db=db)
                    
                    if db_match:
                        hex_val = db_match.get("hex", "#D6CCA3")
                        name_zh = db_match.get("name_zh", "")
                        name_en = db_match.get("name_en", c_name)
                        mat_str = db_match.get("material", product_name).upper()
                    else:
                        hex_val = "#C0C0C0"
                        name_zh = ""
                        name_en = c_name
                        mat_str = (product_name or "PLA").upper()

                    variants.append({
                        "sku": sku,
                        "name": name_en,
                        "name_en": name_en,
                        "name_zh": name_zh,
                        "code": f"({c_code})" if c_code else "",
                        "raw_code": c_code,
                        "material": mat_str,
                        "hex": hex_val,
                        "is_target": (sku == target_sku) if target_sku else False
                    })
        except Exception:
            pass

    # Fallback if no ld+json found: try regex matching on the page
    if not variants:
        # Look for regex matches like "White Oak (13106)"
        code_matches = re.findall(r"([A-Za-z\s]+)\s*\((\d{5})\)", html)
        seen = set()
        for name_found, code_found in code_matches:
            name_found = name_found.strip()
            if (name_found, code_found) in seen:
                continue
            seen.add((name_found, code_found))
            db_match = find_in_db(code=code_found, name=name_found, db=db)
            if db_match:
                variants.append({
                    "sku": "",
                    "name": db_match.get("name_en", name_found),
                    "name_en": db_match.get("name_en", name_found),
                    "name_zh": db_match.get("name_zh", ""),
                    "code": f"({code_found})",
                    "raw_code": code_found,
                    "material": db_match.get("material", "PLA").upper(),
                    "hex": db_match.get("hex", "#A2D312"),
                    "is_target": False
                })

    # Pick selected index
    selected_idx = 0
    for i, v in enumerate(variants):
        if v.get("is_target"):
            selected_idx = i
            break

    # If title wasn't found from schema, extract from page title
    if not product_name and soup.title:
        title_text = soup.title.string or ""
        product_name = title_text.split("|")[0].split("-")[0].strip()

    return {
        "success": True,
        "product_name": product_name or "Filament",
        "target_sku": target_sku,
        "selected_index": selected_idx,
        "variants": variants
    }

if __name__ == "__main__":
    test_url = "https://us.store.bambulab.com/products/pla-wood?srsltid=AU7gw4UIkioibBC3-5Dzx3K5c_u2zoSpj5ZKrkCI1uS6uzkb_C4kt44P&id=43075832086664"
    res = extract_from_url(test_url)
    print(json.dumps(res, indent=2, ensure_ascii=False))
