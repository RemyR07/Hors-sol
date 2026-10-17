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
import re
import statistics
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta
from pathlib import Path

API = "https://prices.openfoodfacts.org/api/v1"
USER_AGENT = "HorsSol/0.1 (jeu de prix quotidien; https://es-tu-hors-sol.fr)"
MIN_RELEVES = 3          # sous ce seuil, le prix n'est pas fiable
FENETRE_JOURS = 365      # relevés pris en compte
MAX_AUTO = 300           # produits populaires ajoutés automatiquement
ECART_MAX = 0.6          # écarte les produits dont les prix sont trop dispersés
MIN_PRODUITS = 40        # sous ce seuil, on garde les données de la veille
MAX_PRIX = 20.0          # au-delà : pas un produit du quotidien (alcools, coffrets…)
MAX_PAR_KILO = 60.0      # au-delà : poids mal saisi (ex. Nutella « 15 g » à 4,75 €)
MIN_QTE_G = 30           # en dessous de 30 g / 3 cl : poids sans doute faux
MAX_PAR_MARQUE = 3       # variété : 3 produits automatiques maximum par marque

HERE = Path(__file__).parent


def get(path, **params):
    """Appel à l'API, avec 4 essais espacés si elle répond lentement ou en erreur (429, 5xx, coupure)."""
    url = f"{API}/{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    last = None
    for wait in (0, 3, 10, 30):
        if wait:
            time.sleep(wait)
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            last = e
            if e.code not in (429, 500, 502, 503, 504):
                raise
        except (urllib.error.URLError, TimeoutError, ConnectionError, json.JSONDecodeError) as e:
            last = e
    raise last


def popular_codes(limit):
    """Produits avec le plus de relevés de prix."""
    items = []
    for page in (1, 2, 3, 4):
        try:
            items += get("products", order_by="-price_count", size=100, page=page).get("items", [])
        except Exception as e:  # une page en échec : on garde ce qu'on a déjà
            print(f"  page {page} des produits populaires indisponible ({e})", file=sys.stderr)
        time.sleep(0.5)
    out = []
    for p in items:
        name = (p.get("product_name") or "").strip()
        if p.get("code") and name and p.get("product_quantity"):
            if len(name) > 70:
                continue
            out.append({
                "code": p["code"],
                "name": name,
                "brands": (p.get("brands") or "").split(",")[0].strip(),
                "qty": p.get("product_quantity"),
                "qty_unit": p.get("product_quantity_unit") or "g",
            })
    return out[:limit]


# ---------- Nettoyage des produits ajoutés automatiquement ----------
UNITES = r"(kg|g|gr|ml|cl|l|L)"
POIDS = [
    rf"\b\d+\s?[x×]\s?\d+(?:[.,]\d+)?\s?{UNITES}\b",       # 4x100g, 2 x 205 g, 6x1.5L
    rf"\b\d+(?:[.,]\d+)?\s?{UNITES}\s?[x×]\s?\d+\b",       # 125 g x 4
    rf"\b\d+(?:[.,]\d+)?\s?{UNITES}\b",                       # 250g, 1.75L, 500 ml
    r"\(\s*\d+(?:[.,]\d+)?\s?oz\s*\)", r"\b\d+\s?[x×]\b", r"\b[x×]\s?\d+\b", r"\b\d/\d\b", r"\bPET\b", r"\b\d+\s?-?\s?pack\b",
]
SOCIETE = re.compile(r"\b(SAS|S\.?A\.?U?\.?|SpA|GmbH|Srl|nv|Company|Belux|Nahrungsmittel|K\.?G\.?|Ltd|Inc|Iberica|Fratelli|G\. e R\.|Sprungli|Egidio|Glico|Mondelēz|McIlhenny)\b\.?", re.I)
ETRANGER = re.compile(r"(milch|mandel|nudeln|geröstet|ohne zucker|\bnatur mit\b|kokosnuss|drank|biologische|schuimbare|\brice drink\b|\bpeanut\b|\bsojasaus\b|\bvegetale\b)", re.I)
EMOJI = re.compile("[\U0001F000-\U0001FAFF\u2600-\u27BF]")
RAYONS = [
    ("Surgelés",   r"glace|häagen|haagen|ben & jerry|magnum|crème glacée|sorbet|pizza|surgel"),
    ("Boissons",   r"^eau |\beau |coca|pepsi|red bull|soda|limonade|\bjus\b|boisson|drink|\bavoine\b|barista|candy'?up|gazpacho"),
    ("Apéro",      r"chips|pringles|\btuc\b|cacahu[eè]tes grill|apéri|crackers|bretzel|houmous|olives"),
    ("Conserves",  r"cassegrain|bonduelle|conserve|\bthon\b|ratatouille|maïs|haricots|petits pois|flageolets|lentilles préparées|macédoine|courgettes"),
    ("Frais",      r"jambon|saucisse|chorizo|lardons|allumettes|bacon|sandwich|tortellini|girasoli|fleury michon|wraps|plat cuisiné"),
    ("Petit-déj",  r"tartiner|nutella|nocciolata|confiture|céréales|muesli|granola|pain de mie|tranches|brioche|pains au lait|biscottes|krisprolls|wasa|café|crème de marrons|kaonuts|beurre de cacahu"),
    ("Biscuits",   r"biscuit|\blu\b|oreo|pim'?s|figolu|galette|madeleine|gaufre|petit brun|\bbn\b|cookie|kinder|napolitain|chamonix|barquette|lulu|mikado|baiocchi|fourrés|marble cake|croûtons"),
    ("Crèmerie",   r"danette|yaourt|sojasun|mousse au|crème dessert|liégeois|petits? suisses?"),
    ("Confiserie", r"chocolat|milka|lindt|excellence|bonbon|\bbarre"),
    ("Crèmerie",   r"beurre|fromage|emmental|comté|mozzarella|crème fraîche|crème|yaourt|\blait\b|danette|chèvre|bûche|raclette|œuf|soja|sojasun|mystère|fondue|déliss"),
]

def joli_format(qty, unit):
    """« 500 g », « 1 kg », « 25 cl », « 1,5 L »."""
    if unit in ("g", "gr"):
        return f"{qty/1000:g} kg".replace(".", ",") if qty >= 1000 else f"{qty:g} g"
    if unit in ("ml", "cl", "l", "L"):
        ml = qty * {"ml": 1, "cl": 10, "l": 1000, "L": 1000}[unit]
        return f"{ml/1000:g} L".replace(".", ",") if ml >= 1000 else f"{ml/10:g} cl".replace(".", ",")
    return f"{qty:g} {unit}"

def nettoie_marque(brand):
    b = SOCIETE.sub("", brand or "").replace("  ", " ").strip(" -,.")
    if b.isupper() and len(b) > 3:
        b = b.title()
    return " ".join(b.split()[:2])

def nettoie_nom(name, brand):
    n = EMOJI.sub("", name)
    for pat in POIDS:
        n = re.sub(pat, " ", n, flags=re.I)
    n = re.sub(r"\s*[-–,]\s*$", "", re.sub(r"\s{2,}", " ", n)).strip(" -–,")
    n = re.sub(r"\s+-\s+-\s+", " - ", n)
    # mots tout en majuscules (« CRISTALINE », « KINDER ») : on les remet en minuscules
    n = " ".join(w.capitalize() if (w.isupper() and len(w) > 3 and not re.search(r"\d", w)) else w for w in n.split())
    b = nettoie_marque(brand)
    first = re.split(r"[^\wàâäéèêëîïôöùûüç']+", b.lower())[0] if b else ""
    if b and b.lower() not in n.lower() and not (first and len(first) > 2 and re.search(rf"\b{re.escape(first)}\b", n.lower())):
        n = f"{n} {b}"
    # « Nutella Nutella », « Menguy's … Menguy's » : on retire la marque répétée en fin de nom
    if b:
        low = n.lower()
        while low.count(b.lower()) > 1 and low.endswith(b.lower()):
            n = n[: -len(b)].strip(" -,"); low = n.lower()
    if n.isupper():
        n = n.capitalize()
    return n[:1].upper() + n[1:]

def vrai_poids(name, qty, unit):
    """« Sojasun 4x100 g » saisi 100 g : on prend 400 g (même unité que qty)."""
    fac = {"g": 1, "gr": 1, "kg": 1000, "ml": 1, "cl": 10, "l": 1000}
    m = re.search(rf"\b(\d+)\s?[x×]\s?(\d+(?:[.,]\d+)?)\s?{UNITES}\b", name, re.I)
    if m:
        nb, each, u = float(m.group(1)), float(m.group(2).replace(",", ".")), m.group(3).lower()
    else:
        m = re.search(rf"\b(\d+(?:[.,]\d+)?)\s?{UNITES}\s?[x×]\s?(\d+)\b", name, re.I)
        if not m:
            return qty
        each, u, nb = float(m.group(1).replace(",", ".")), m.group(2).lower(), float(m.group(3))
    total = nb * each * fac.get(u, 1)            # en g ou ml
    if unit in ("kg", "l", "L"):
        total /= 1000
    return total if total > qty * 1.5 else qty

def devine_rayon(name, unit):
    low = name.lower()
    for rayon, pat in RAYONS:
        if rayon == "Boissons" and unit != "L":
            continue
        if re.search(pat, low):
            return rayon
    return "Épicerie"


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


def auto_meta(p):
    """Fiche propre d'un produit ajouté automatiquement, ou None s'il faut l'écarter."""
    if ETRANGER.search(p["name"]):
        return None
    u = (p["qty_unit"] or "g").strip()
    u = {"G": "g", "KG": "kg", "ML": "ml", "CL": "cl", "Gr": "g", "gr": "g"}.get(u, u)
    if u not in ("g", "kg", "ml", "cl", "l", "L"):
        return None
    try:
        qty = vrai_poids(p["name"], float(p["qty"]), u)
    except (TypeError, ValueError):
        return None
    grams = qty * {"g": 1, "kg": 1000, "ml": 1, "cl": 10, "l": 1000, "L": 1000}[u]
    if grams < MIN_QTE_G:
        return None
    liquid = u in ("ml", "cl", "l", "L")
    name = nettoie_nom(p["name"], p["brands"])
    if len(name) < 3 or len(name) > 55:
        return None
    return {
        "name": name,
        "detail": joli_format(qty, u),
        "rayon": devine_rayon(name, "L" if liquid else "kg"),
        "qty": round(grams / 1000, 4),
        "unit": "L" if liquid else "kg",
        "auto": True,
        "brand": nettoie_marque(p["brands"]).lower(),
    }


def build(raw=None):
    catalog = json.loads((HERE / "catalog.json").read_text())
    catalog.pop("_info", None)
    since = date.today() - timedelta(days=FENETRE_JOURS)

    candidates = dict(catalog)
    if raw is None:
        for p in popular_codes(MAX_AUTO):
            meta = auto_meta(p)
            if meta and p["code"] not in candidates:
                candidates[p["code"]] = meta

    products = []
    failures = 0
    started = time.time()
    for code, meta in candidates.items():
        if raw is None and time.time() - started > 25 * 60:
            print("  temps maximum atteint (25 min) : on s'arrête là", file=sys.stderr)
            break
        try:
            prices = raw.get(code, []) if raw is not None else french_prices(code, since)
            failures = 0
        except Exception as e:  # un produit en erreur ne bloque plus toute la mise à jour
            failures += 1
            print(f"  erreur   {meta['name']} ({e})", file=sys.stderr)
            if failures >= 15:
                print("  l'API ne répond plus : on s'arrête là", file=sys.stderr)
                break
            continue
        s = summarize(prices)
        if not s:
            print(f"  ignoré  {meta['name']} ({len(prices)} relevés)", file=sys.stderr)
            continue
        per = round(s["median"] / meta["qty"], 2) if meta.get("qty") else None
        products.append({"code": code, **meta, **s, "per_unit": per})
        print(f"  ok      {meta['name']}: {s['median']} € (n={s['n']})", file=sys.stderr)
        if raw is None:
            time.sleep(0.5)

    # Garde-fous sur les produits automatiques : prix aberrants, doublons de nom, trop de produits d'une même marque.
    kept, per_brand, seen = [], {}, set()
    for pr in sorted(products, key=lambda x: (not x.get("auto"), -x["n"]), reverse=False):
        if pr.get("auto"):
            if pr["median"] > MAX_PRIX or (pr.get("per_unit") or 0) > MAX_PAR_KILO:
                print(f"  écarté  {pr['name']} (prix {pr['median']} €, {pr.get('per_unit')} €/{pr['unit']})", file=sys.stderr)
                continue
            key = (pr["name"].lower(), pr["detail"])
            b = pr.get("brand") or pr["name"].split()[0].lower()
            if key in seen or per_brand.get(b, 0) >= MAX_PAR_MARQUE:
                continue
            per_brand[b] = per_brand.get(b, 0) + 1
            seen.add(key)
        pr.pop("auto", None); pr.pop("brand", None)
        kept.append(pr)
    products = kept

    if len(products) < MIN_PRODUITS:
        # API en panne ou réponse vide : on garde les prix de la veille plutôt qu'un jeu vide
        print(f"Seulement {len(products)} produits : products.json n'est pas modifié.", file=sys.stderr)
        sys.exit(0)

    # Une seule série par jour pour tout le monde : la nouvelle liste n'entre en jeu
    # que le lendemain à minuit (champ "next"). La liste du jour ne bouge jamais en cours de journée.
    today = paris_today()
    new_list = sorted(products, key=lambda p: p["code"])
    path = HERE / "products.json"
    old = json.loads(path.read_text()) if path.exists() else None
    if old and old.get("products"):
        nxt = old.get("next") or {}
        if nxt.get("from") and nxt["from"] <= today.isoformat():
            current = {"updated": nxt.get("updated"), "products": nxt["products"]}
        else:
            current = {"updated": old.get("updated"), "products": old["products"]}
    else:
        current = {"updated": today.isoformat(), "products": new_list}

    out = {
        "updated": current["updated"],
        "source": "Open Prices (Open Food Facts) — ODbL",
        "window_days": FENETRE_JOURS,
        "products": current["products"],
        "next": {
            "from": (today + timedelta(days=1)).isoformat(),
            "updated": today.isoformat(),
            "products": new_list,
        },
    }
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print(f"{len(products)} produits prêts pour demain ({out['next']['from']}) ; "
          f"{len(current['products'])} produits en jeu aujourd'hui.", file=sys.stderr)
    return out


def paris_today():
    """Date du jour à Paris (le serveur GitHub est à l'heure UTC)."""
    try:
        from zoneinfo import ZoneInfo
        from datetime import datetime
        return datetime.now(ZoneInfo("Europe/Paris")).date()
    except Exception:
        return date.today()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--from-raw", help="fichier JSON {code: [prix…]} pour un calcul hors ligne")
    args = ap.parse_args()
    raw = json.loads(Path(args.from_raw).read_text()) if args.from_raw else None
    if raw:
        raw.pop("_source", None)
    build(raw)
