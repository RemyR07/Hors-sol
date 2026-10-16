#!/usr/bin/env python3
"""
Hors-Sol — mise à jour automatique des prix.

Génère products.json, le seul fichier de données que lit le jeu.
À lancer une fois par jour (GitHub Actions, cron, Cloudflare Worker…).

Logique :
  1. Produits du quotidien = les produits les plus relevés par les Français
     sur Open Prices (un produit que plein de gens scannent est un produit
     que plein de gens achètent), + ceux listés dans catalog.json.
  2. Pour chacun : relevés en France, en euros, sur les 12 derniers mois.
  3. On garde le produit seulement s'il a au moins MIN_RELEVES relevés.
  4. Prix de référence = médiane (insensible aux promos et erreurs de saisie).

Données : Open Prices (Open Food Facts), licence ODbL — créditer la source.

Usage :
  python3 update_prices.py                  # interroge l'API Open Prices
  python3 update_prices.py --from-raw raw_prices.json   # hors ligne
"""
import argparse
import json
import statistics
import sys
import time
import urllib.parse
import urllib.request
from datetime import date, timedelta
from pathlib import Path

API = "https://prices.openfoodfacts.org/api/v1"
USER_AGENT = "HorsSol/0.1 (jeu de prix quotidien; https://es-tu-hors-sol.fr)"
MIN_RELEVES = 3          # sous ce seuil, le prix n'est pas fiable
FENETRE_JOURS = 365      # relevés pris en compte
MAX_AUTO = 60            # produits populaires ajoutés automatiquement
ECART_MAX = 0.6
MIN_PRODUITS = 8         # sous ce seuil, on garde les données de la veille          # écarte les produits dont les prix sont trop dispersés

HERE = Path(__file__).parent


def get(path, **params):
    url = f"{API}/{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def popular_codes(limit):
    """Produits avec le plus de relevés de prix."""
    data = get("products", order_by="-price_count", size=100)
    out = []
    for p in data.get("items", []):
        name = (p.get("product_name") or "").strip()
        if p.get("code") and name and p.get("product_quantity"):
            out.append({
                "code": p["code"],
                "name": name,
                "brands": (p.get("brands") or "").split(",")[0].strip(),
                "qty": p.get("product_quantity"),
                "qty_unit": p.get("product_quantity_unit") or "g",
            })
    return out[:limit]


def french_prices(code, since):
    """Relevés en France, en euros, depuis `since`."""
    prices, page = [], 1
    while page <= 5:
        data = get("prices", product_code=code, order_by="-date", size=100, page=page)
        items = data.get("items", [])
        for it in items:
            loc = it.get("location") or {}
            country = (loc.get("osm_address_country_code") or "").upper()
            d = it.get("date") or ""
            if it.get("currency") == "EUR" and country == "FR" and d >= since.isoformat():
                if not it.get("price_per") or it.get("price_per") == "UNIT":
                    prices.append(float(it["price"]))
        if not items or (items and (items[-1].get("date") or "") < since.isoformat()):
            break
        page += 1
        time.sleep(0.5)  # on reste poli avec l'API
    return prices


def summarize(prices):
    if len(prices) < MIN_RELEVES:
        return None
    med = statistics.median(prices)
    q = statistics.quantiles(prices, n=4) if len(prices) >= 4 else [min(prices), med, max(prices)]
    if med <= 0 or (q[2] - q[0]) / med > ECART_MAX:
        return None
    return {"median": round(med, 2), "p25": round(q[0], 2), "p75": round(q[2], 2), "n": len(prices)}


def build(raw=None):
    catalog = json.loads((HERE / "catalog.json").read_text())
    catalog.pop("_info", None)
    since = date.today() - timedelta(days=FENETRE_JOURS)

    candidates = dict(catalog)
    if raw is None:
        for p in popular_codes(MAX_AUTO):
            if p["code"] not in candidates:
                unit = "L" if p["qty_unit"] in ("ml", "cl", "l", "L") else "kg"
                factor = 1000 if p["qty_unit"] in ("g", "ml") else 1
                candidates[p["code"]] = {
                    "name": f'{p["name"]} {p["brands"]}'.strip(),
                    "detail": f'{p["qty"]} {p["qty_unit"]}',
                    "rayon": "Courses",
                    "qty": p["qty"] / factor,
                    "unit": unit,
                }

    products = []
    for code, meta in candidates.items():
        prices = raw.get(code, []) if raw is not None else french_prices(code, since)
        s = summarize(prices)
        if not s:
            print(f"  ignoré  {meta['name']} ({len(prices)} relevés)", file=sys.stderr)
            continue
        per = round(s["median"] / meta["qty"], 2) if meta.get("qty") else None
        products.append({"code": code, **meta, **s, "per_unit": per})
        print(f"  ok      {meta['name']}: {s['median']} € (n={s['n']})", file=sys.stderr)
        if raw is None:
            time.sleep(0.5)

    if len(products) < MIN_PRODUITS:
        # API en panne ou réponse vide : on garde les prix de la veille plutôt qu'un jeu vide
        print(f"Seulement {len(products)} produits : products.json n'est pas modifié.", file=sys.stderr)
        sys.exit(0)

    out = {
        "updated": date.today().isoformat(),
        "source": "Open Prices (Open Food Facts) — ODbL",
        "window_days": FENETRE_JOURS,
        "products": sorted(products, key=lambda p: p["code"]),
    }
    (HERE / "products.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print(f"{len(products)} produits écrits dans products.json", file=sys.stderr)
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--from-raw", help="fichier JSON {code: [prix…]} pour un calcul hors ligne")
    args = ap.parse_args()
    raw = json.loads(Path(args.from_raw).read_text()) if args.from_raw else None
    if raw:
        raw.pop("_source", None)
    build(raw)
