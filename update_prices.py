#!/usr/bin/env python3
"""
Hors-Sol — mise à jour automatique des prix.

Génère products.json, le seul fichier de données que lit le jeu.
À lancer une fois par jour (GitHub Actions, cron, Cloudflare Worker…).

Logique :
  1. On télécharge le fichier complet d'Open Prices (publié chaque nuit) et on garde
     tous les produits relevés en France, en euros, sur les 12 derniers mois.
     (Secours si le fichier est indisponible : les 800 produits les plus relevés, via l'API.)
  2. Règles de fiabilité : au moins MIN_RELEVES relevés, dans MIN_MAGASINS magasins,
     un relevé de moins de RECENT_MOIS mois, prix peu dispersés.
  3. Fiche Open Food Facts : nom en français obligatoire, poids lisible, pas d'alcool,
     de complément alimentaire, de produit bébé ou animal. Fiches gardées dans products.json (clé "_fiches").
  4. Prix de référence = médiane (insensible aux promos et erreurs de saisie).
  5. + produits de catalog.json (noms choisis à la main) et produits frais de l'Insee.

Données : Open Prices (Open Food Facts), licence ODbL — créditer la source.

Usage :
  python3 update_prices.py                  # interroge l'API Open Prices
  python3 update_prices.py --from-raw raw_prices.json   # hors ligne
"""
import argparse
import gzip
import tempfile
import xml.etree.ElementTree as ET
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
INSEE = "https://bdm.insee.fr/series/sdmx/data/SERIES_BDM/{ids}?lastNObservations=4&detail=dataonly"
INSEE_FRAIS_MOIS = 4     # une série Insee n'est gardée que si son dernier prix a moins de 4 mois (fruits de saison…)
USER_AGENT = "HorsSol/0.1 (jeu de prix quotidien; https://es-tu-hors-sol.fr)"
MIN_RELEVES = 3          # sous ce seuil, le prix n'est pas fiable
FENETRE_JOURS = 365      # relevés pris en compte
MAX_AUTO = 800           # produits populaires examinés chaque nuit
MIN_MAGASINS = 2         # produit automatique : relevé dans au moins 2 magasins différents
RECENT_MOIS = 6          # … et au moins un relevé de moins de 6 mois
ECART_MAX = 0.6          # écarte les produits dont les prix sont trop dispersés
MIN_PRODUITS = 40        # sous ce seuil, on garde les données de la veille
MAX_PRIX = 20.0          # au-delà : pas un produit du quotidien (alcools, coffrets…)
MAX_PAR_KILO = 60.0      # au-delà : poids mal saisi (ex. Nutella « 15 g » à 4,75 €)
MIN_QTE_G = 30           # en dessous de 30 g / 3 cl : poids sans doute faux
MAX_PAR_MARQUE = 3       # variété : 3 produits automatiques maximum par marque
MIN_PAR_KILO = 0.30      # en dessous (0,10 €/L pour les boissons, ex. pack d'eau) : poids mal saisi (ex. 5 kg noté au lieu de 500 g)
MAX_AUTO_TOTAL = 1000    # plafond de produits automatiques (taille de la page du jeu)

# Fichier complet Open Prices (régénéré chaque nuit) et fiches produits Open Food Facts
DUMP = "https://prices.openfoodfacts.org/data"
OFF_PRODUIT = ("https://world.openfoodfacts.org/api/v2/product/{code}"
               "?fields=product_name_fr,product_name,lang,brands,product_quantity,product_quantity_unit,quantity,categories_tags")
FICHES_MAX_PAR_NUIT = 1500        # nouvelles fiches lues au maximum par lancement
FICHES_MINUTES = 30               # … et pas plus de 30 minutes
FICHES_VALIDITE_JOURS = 90        # une fiche est relue au bout de 3 mois
EXCLUS_CATS = {"en:alcoholic-beverages", "en:dietary-supplements", "en:pet-food", "en:baby-foods", "en:baby-milks"}
CAT_RAYONS = [  # rayon affiché, d'après les catégories Open Food Facts (le premier qui correspond gagne)
    ("Surgelés",    ["en:ice-creams-and-sorbets", "en:frozen-desserts", "en:ice-creams"]),
    ("Boulangerie", ["en:breads", "en:viennoiseries"]),
    ("Apéro",       ["en:salty-snacks", "en:appetizers", "en:crisps", "en:chips-and-fries", "en:dips", "en:salted-spreads", "en:rillettes"]),
    ("Épicerie",    ["en:sauces", "en:condiments", "en:vinegars", "en:mayonnaises"]),
    ("Biscuits",    ["en:biscuits-and-cakes", "en:biscuits", "en:cakes"]),
    ("Confiserie",  ["en:chocolates", "en:confectioneries", "en:candies"]),
    ("Petit-déj",   ["en:breakfast-cereals", "en:sweet-spreads", "en:hazelnut-spreads", "en:jams", "en:coffees", "en:teas",
                     "en:honeys", "en:cocoa-and-chocolate-powders"]),
    ("Crèmerie",    ["en:dairies", "en:cheeses", "en:yogurts", "en:eggs", "en:butters", "en:dairy-desserts", "en:milks"]),
    ("Boissons",    ["en:beverages", "en:waters", "en:plant-based-milk-alternatives"]),
    ("Conserves",   ["en:canned-foods"]),
    ("Frais",       ["en:prepared-meats", "en:meals", "en:sandwiches", "en:fresh-pasta", "en:meat-analogues"]),
    ("Boucherie",   ["en:meats", "en:poultries"]),
    ("Surgelés",    ["en:frozen-foods"]),       # en dernier : certaines fiches sont mal classées « surgelé »
]
CATS_UTILES = EXCLUS_CATS | {t for _, tags in CAT_RAYONS for t in tags}

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


# ---------- Produits frais : prix moyens mensuels de l'Insee (source officielle) ----------
def insee_fetch(ids):
    """Télécharge les dernières valeurs des séries Insee (SDMX, accès libre). Renvoie le texte XML."""
    url = INSEE.format(ids="+".join(ids))
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/xml"})
    last = None
    for wait in (0, 5, 20):
        if wait:
            time.sleep(wait)
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read().decode("utf-8")
        except Exception as e:  # réseau, 5xx…
            last = e
    raise last


def insee_parse(xml_text):
    """{idbank: (période 'AAAA-MM', valeur)} : dernière observation de chaque série."""
    root = ET.fromstring(xml_text)
    out = {}
    for el in root.iter():
        if not el.tag.endswith("Series"):
            continue
        idb = el.attrib.get("IDBANK")
        obs = []
        for o in el:
            if o.tag.endswith("Obs"):
                v = o.attrib.get("OBS_VALUE")
                try:
                    obs.append((o.attrib.get("TIME_PERIOD", ""), float(v)))
                except (TypeError, ValueError):
                    pass
        if idb and obs:
            out[idb] = max(obs)
    return out


def insee_products(today, xml_text=None):
    cat = json.loads((HERE / "insee.json").read_text())
    cat.pop("_info", None)
    data = insee_parse(xml_text if xml_text is not None else insee_fetch(list(cat)))
    oldest = (today.replace(day=1) - timedelta(days=31 * (INSEE_FRAIS_MOIS - 1))).strftime("%Y-%m")
    products = []
    for idb, meta in cat.items():
        if idb not in data:
            print(f"  insee ? {meta['name']} (pas de donnée)", file=sys.stderr)
            continue
        period, value = data[idb]
        if period < oldest:
            print(f"  insee - {meta['name']} (dernier prix {period}, hors saison ou série arrêtée)", file=sys.stderr)
            continue
        kilo = meta["unit"] == "kg" and meta.get("qty")
        price = round(value * meta["qty"], 2) if kilo else round(value, 2)
        if not (0.15 <= price <= MAX_PRIX):
            print(f"  insee - {meta['name']} ({price} € hors bornes)", file=sys.stderr)
            continue
        products.append({"code": "insee-" + idb, "name": meta["name"], "detail": meta["detail"], "rayon": meta["rayon"],
                         "qty": meta.get("qty"), "unit": meta["unit"], "median": price, "p25": None, "p75": None, "n": None,
                         "per_unit": round(value, 2) if kilo else None, "src": "insee", "period": period})
        print(f"  insee ok {meta['name']}: {price} € ({period})", file=sys.stderr)
    return products


def popular_codes(limit):
    """Produits avec le plus de relevés de prix."""
    items = []
    for page in range(1, MAX_AUTO // 100 + 1):
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
SOCIETE = re.compile(r"\b(SAS|SARL|France|Foods Europe|B\.V|BV|S\.?A\.?U?\.?|SpA|GmbH|Srl|nv|Company|Belux|Nahrungsmittel|K\.?G\.?|Ltd|Inc|Iberica|Fratelli|G\. e R\.|Sprungli|Egidio|Glico|Mondelēz|McIlhenny)\b\.?", re.I)
ETRANGER = re.compile(r"(milch|mandel|nudeln|geröstet|ohne zucker|\bnatur mit\b|kokosnuss|drank|biologische|schuimbare|\brice drink\b|\bpeanut\b|\bsojasaus\b|\bvegetale\b)", re.I)
EMOJI = re.compile("[\U0001F000-\U0001FAFF\u2600-\u27BF]")
RAYONS = [
    ("Surgelés",   r"glace|häagen|haagen|ben ?& ?jerry|magnum|crème glacée|sorbet|pizza|surgel"),
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
    # « Délisse, Leclerc » : on ne garde que la première marque ; on retire « SAS », « sarl »…
    b = SOCIETE.sub("", re.sub(r"[?!]+", "", (brand or "").split(",")[0])).replace("  ", " ").strip(" -,.")
    if b.isupper() and len(b) > 3:
        b = b.title()
    mots = b.split()
    # la marque entière (« Ben & Jerry's », « Old El Paso », « Marque Repère ») ; trop longue : pas de marque
    return " ".join(mots) if len(mots) <= 5 else ""

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
    """Relevés en France, en euros, depuis `since` : (prix, nombre de magasins différents, date du relevé le plus récent)."""
    prices, page, shops, newest = [], 1, set(), ""
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
                    shops.add(it.get("location_id") or loc.get("id") or loc.get("osm_id"))
                    newest = max(newest, d)
        if not items or (items and (items[-1].get("date") or "") < since.isoformat()):
            break
        page += 1
        time.sleep(0.5)  # on reste poli avec l'API
    ids = shops - {None}
    # si l'API ne donne pas l'identifiant du magasin, on ne peut pas compter : la règle des 2 magasins ne s'applique pas
    return prices, (len(ids) if ids else 99), newest


# ---------- Fichier complet Open Prices (publié chaque nuit) + fiches Open Food Facts ----------
def telecharge(url, dest):
    """Télécharge un fichier (avec 3 essais) vers `dest`."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    last = None
    for wait in (0, 10, 60):
        if wait:
            time.sleep(wait)
        try:
            with urllib.request.urlopen(req, timeout=120) as r, open(dest, "wb") as f:
                while True:
                    chunk = r.read(1 << 20)
                    if not chunk:
                        break
                    f.write(chunk)
            return dest
        except Exception as e:
            last = e
    raise last


def lignes_jsonl_gz(path):
    with gzip.open(path, "rt", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue


def releves_du_fichier(since, dump_dir=None):
    """{code: (prix, nb de magasins, date du relevé le plus récent)} pour TOUS les produits relevés en France.
    Mêmes règles que l'ancienne méthode : euros, magasin en France, prix à l'unité, pas de doublon signalé."""
    d = Path(dump_dir) if dump_dir else Path(tempfile.mkdtemp())
    loc_path, prix_path = d / "locations.jsonl.gz", d / "prices.jsonl.gz"
    if not dump_dir:
        telecharge(f"{DUMP}/locations.jsonl.gz", loc_path)
        telecharge(f"{DUMP}/prices.jsonl.gz", prix_path)
    fr = {l.get("id") for l in lignes_jsonl_gz(loc_path)
          if (l.get("osm_address_country_code") or "").upper() == "FR"}
    since_s, stats, total = since.isoformat(), {}, 0
    for it in lignes_jsonl_gz(prix_path):
        total += 1
        code = it.get("product_code")
        loc = it.get("location_id", it.get("location"))
        if not code or it.get("type") not in (None, "PRODUCT") or it.get("currency") != "EUR" or loc not in fr:
            continue
        if it.get("duplicate_of") or (it.get("price_per") not in (None, "", "UNIT")):
            continue
        dt = it.get("date") or ""
        if dt < since_s:
            continue
        try:
            price = float(it["price"])
        except (KeyError, TypeError, ValueError):
            continue
        if price <= 0:
            continue
        s = stats.setdefault(code, [[], set(), ""])
        s[0].append(price); s[1].add(loc); s[2] = max(s[2], dt)
    print(f"Fichier Open Prices : {total} prix au total, {len(fr)} magasins en France, "
          f"{len(stats)} produits relevés en France sur 12 mois", file=sys.stderr)
    return {c: (s[0], len(s[1]), s[2]) for c, s in stats.items()}


def http_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    last = None
    for wait in (0, 5, 20):
        if wait:
            time.sleep(wait)
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return {"status": 0}
            last = e
        except (urllib.error.URLError, TimeoutError, ConnectionError, json.JSONDecodeError) as e:
            last = e
    raise last


def fiche_off(code):
    """Fiche Open Food Facts réduite à ce qui nous sert (nom français, marque, poids, catégories utiles)."""
    data = http_json(OFF_PRODUIT.format(code=code))
    t = date.today().isoformat()
    if data.get("status") != 1 or not data.get("product"):
        return {"absent": True, "t": t}       # pas un produit alimentaire connu d'Open Food Facts
    p = data["product"]
    cats = [c for c in (p.get("categories_tags") or []) if c in CATS_UTILES]
    return {"fr": (p.get("product_name_fr") or "").strip(), "nom": (p.get("product_name") or "").strip(),
            "lang": p.get("lang") or "", "marque": p.get("brands") or "", "qte": p.get("product_quantity"),
            "unite": p.get("product_quantity_unit") or "", "quantite": p.get("quantity") or "", "cats": cats, "t": t}


def nom_francais(f):
    """Le nom affiché doit être en français : nom français d'Open Food Facts, sinon nom principal d'une fiche française."""
    if f.get("fr"):
        return f["fr"]
    if f.get("lang") == "fr" and f.get("nom"):
        return f["nom"]
    return ""


def unite_de(f):
    """Poids/volume : champs d'Open Food Facts, sinon on lit « 1,5 L », « 400 g »… dans la quantité affichée."""
    qte, u = f.get("qte"), (f.get("unite") or "").strip()
    if qte and u:
        return qte, u
    m = re.search(r"(\d+(?:[.,]\d+)?)\s?(kg|g|gr|ml|cl|l)\b", f.get("quantite") or "", re.I)
    if m:
        return float(m.group(1).replace(",", ".")), m.group(2)
    return qte, (u or None)


def rayon_par_categorie(cats):
    for rayon, tags in CAT_RAYONS:
        if any(t in cats for t in tags):
            return rayon
    return None


_FICHES = {}


def charge_fiches():
    """Mémoire des fiches : rangée dans products.json (clé "_fiches"), retirée du jeu par build.py."""
    try:
        return dict(json.loads((HERE / "products.json").read_text()).get("_fiches") or {})
    except Exception:
        return {}


def summarize(prices):
    if len(prices) < MIN_RELEVES:
        return None
    med = statistics.median(prices)
    q = statistics.quantiles(prices, n=4) if len(prices) >= 4 else [min(prices), med, max(prices)]
    if med <= 0 or (q[2] - q[0]) / med > ECART_MAX:
        return None
    return {"median": round(med, 2), "p25": round(q[0], 2), "p75": round(q[2], 2), "n": len(prices)}


def ILLISIBLE_OK(name):
    """Nom lisible : surtout des lettres, pas de code, d'adresse web ni de caractères bizarres."""
    if re.search(r"[_@#{}\[\]<>|\\/?=*]|https?:|www\.|\.com\b", name):
        return False
    lettres = sum(ch.isalpha() for ch in name)
    if lettres < 3 or lettres < 0.6 * len(name.replace(" ", "")):
        return False
    if re.search(r"\d{5,}", name):          # un code-barres ou une référence dans le nom
        return False
    if re.search(r"(\s[&+\-–]|\b(de|du|des|di|del|la|le|les|the|old|san|st|et|à|au|aux))\s*$|,\s*$", name, re.I):
        return False                          # nom coupé (« Ben & », « Old », « Les »)
    return True


def candidats_du_fichier(releves, deja, exclus):
    """Produits du fichier complet qui passent nos règles de fiabilité, avec une fiche propre en français."""
    recent = (date.today() - timedelta(days=30 * RECENT_MOIS)).isoformat()
    eligibles = [c for c, (pr, ns, nw) in releves.items()
                 if c not in deja and c not in exclus and ns >= MIN_MAGASINS and nw >= recent and summarize(pr)]
    eligibles.sort(key=lambda c: -len(releves[c][0]))       # les plus relevés d'abord
    print(f"{len(eligibles)} produits passent les règles de fiabilité "
          f"(≥{MIN_RELEVES} relevés, ≥{MIN_MAGASINS} magasins, relevé de moins de {RECENT_MOIS} mois, prix peu dispersés)",
          file=sys.stderr)
    fiches = charge_fiches()
    perime = (date.today() - timedelta(days=FICHES_VALIDITE_JOURS)).isoformat()
    lus, start, out = 0, time.time(), {}
    n = {"pas lue (on la lira la nuit prochaine)": 0, "inconnu d'Open Food Facts (souvent non alimentaire)": 0,
         "alcool, complément, bébé ou animaux": 0, "pas de nom en français": 0, "nom, poids ou unité inutilisable": 0}
    for c in eligibles:
        f = fiches.get(c)
        if (not f or f.get("t", "") < perime) and lus < FICHES_MAX_PAR_NUIT and time.time() - start < FICHES_MINUTES * 60:
            try:
                f = fiche_off(c)
                fiches[c] = f
                lus += 1
                time.sleep(0.7)   # Open Food Facts : 100 fiches par minute au maximum
            except Exception as e:
                print(f"  fiche illisible {c} ({e})", file=sys.stderr)
        if not f:
            n["pas lue (on la lira la nuit prochaine)"] += 1; continue
        if f.get("absent"):
            n["inconnu d'Open Food Facts (souvent non alimentaire)"] += 1; continue
        if set(f.get("cats") or []) & EXCLUS_CATS:
            n["alcool, complément, bébé ou animaux"] += 1; continue
        nom = nom_francais(f)
        if not nom or len(nom) > 70 or ETRANGER.search(nom):
            n["pas de nom en français"] += 1; continue
        qte, u = unite_de(f)
        meta = auto_meta({"code": c, "name": nom, "brands": f.get("marque", ""), "qty": qte, "qty_unit": u,
                          "cats": f.get("cats") or []})
        if not meta:
            n["nom, poids ou unité inutilisable"] += 1; continue
        out[c] = meta
    _FICHES.clear(); _FICHES.update(sorted(fiches.items()))   # enregistrées dans products.json (clé "_fiches")
    print(f"{lus} fiches lues cette nuit ; {len(out)} produits avec une fiche propre en français", file=sys.stderr)
    for k, v in n.items():
        if v:
            print(f"  écartés : {v} — {k}", file=sys.stderr)
    return out


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
    if len(name) < 3 or len(name) > 55 or not ILLISIBLE_OK(name):
        return None
    return {
        "name": name,
        "detail": joli_format(qty, u),
        "rayon": rayon_par_categorie(p.get("cats") or []) or devine_rayon(name, "L" if liquid else "kg"),
        "qty": round(grams / 1000, 4),
        "unit": "L" if liquid else "kg",
        "auto": True,
        "brand": nettoie_marque(p["brands"]).lower(),
    }


def build(raw=None, insee_xml=None, dump_dir=None):
    catalog = json.loads((HERE / "catalog.json").read_text())
    catalog.pop("_info", None)
    since = date.today() - timedelta(days=FENETRE_JOURS)

    exclus_path = HERE / "exclus.json"
    exclus = set(json.loads(exclus_path.read_text()).get("codes", [])) if exclus_path.exists() else set()
    candidates = {c: m for c, m in catalog.items() if c not in exclus}

    # 1) Méthode principale : le fichier complet d'Open Prices (tous les produits relevés en France)
    releves = None
    if raw is None:
        try:
            releves = releves_du_fichier(since, dump_dir)
            candidates.update(candidats_du_fichier(releves, candidates, exclus))
            # Stabilité : un produit déjà dans le jeu y reste tant qu'il a au moins 3 relevés en France sur 12 mois
            # (les règles « 2 magasins / relevé récent » ne s'appliquent qu'aux nouveaux venus).
            anciens = 0
            for p in precedents():
                c = p["code"]
                if c in candidates or c in exclus or c.startswith("insee-") or not ILLISIBLE_OK(p["name"]):
                    continue
                candidates[c] = {"name": p["name"], "detail": p["detail"], "rayon": p["rayon"], "qty": p.get("qty"),
                                 "unit": p["unit"], "auto": True, "ancien": True, "brand": ""}
                anciens += 1
            print(f"{anciens} produits déjà en jeu conservés avec leur fiche actuelle", file=sys.stderr)
        except Exception as e:
            releves = None
            print(f"Fichier complet Open Prices indisponible ({e}) : ancienne méthode (800 produits populaires)",
                  file=sys.stderr)
    # 2) Secours : l'ancienne méthode, produit par produit
    if raw is None and releves is None:
        for p in popular_codes(MAX_AUTO):
            meta = auto_meta(p)
            if meta and p["code"] not in candidates and p["code"] not in exclus:
                candidates[p["code"]] = meta

    products = []
    failures = 0
    started = time.time()
    lent = raw is None and releves is None
    for code, meta in candidates.items():
        if lent and time.time() - started > 50 * 60:
            print("  temps maximum atteint (50 min) : on s'arrête là", file=sys.stderr)
            break
        try:
            if raw is not None:
                prices, nshops, newest = raw.get(code, []), 99, date.today().isoformat()
            elif releves is not None:
                prices, nshops, newest = releves.get(code, ([], 0, ""))
            else:
                prices, nshops, newest = french_prices(code, since)
            failures = 0
        except Exception as e:  # un produit en erreur ne bloque plus toute la mise à jour
            failures += 1
            print(f"  erreur   {meta['name']} ({e})", file=sys.stderr)
            if failures >= 15:
                print("  l'API ne répond plus : on s'arrête là", file=sys.stderr)
                break
            continue
        if meta.get("auto") and not meta.get("ancien") and (nshops < MIN_MAGASINS or newest < (date.today() - timedelta(days=30 * RECENT_MOIS)).isoformat()):
            print(f"  ignoré  {meta['name']} ({nshops} magasin(s), dernier relevé {newest or '?'})", file=sys.stderr)
            continue
        s = summarize(prices)
        if not s:
            print(f"  ignoré  {meta['name']} ({len(prices)} relevés)", file=sys.stderr)
            continue
        per = round(s["median"] / meta["qty"], 2) if meta.get("qty") else None
        products.append({"code": code, **meta, **s, "per_unit": per})
        if not meta.get("auto") or lent:
            print(f"  ok      {meta['name']}: {s['median']} € (n={s['n']})", file=sys.stderr)
        if lent:
            time.sleep(0.5)

    # Garde-fous sur les produits automatiques : prix aberrants, doublons de nom, trop de produits d'une même marque.
    kept, per_brand, seen, n_auto = [], {}, set(), 0
    garde = {"prix trop haut ou poids faux": 0, "doublon de nom": 0, f"déjà {MAX_PAR_MARQUE} produits de la marque": 0,
             "plafond atteint": 0}
    for pr in sorted(products, key=lambda x: (not x.get("auto"), -x["n"]), reverse=False):
        if pr.get("auto"):
            per = pr.get("per_unit") or 0
            plancher = 0.10 if pr["unit"] == "L" else MIN_PAR_KILO
            if pr["median"] > MAX_PRIX or per > MAX_PAR_KILO or per < plancher:
                garde["prix trop haut ou poids faux"] += 1
                print(f"  écarté  {pr['name']} (prix {pr['median']} €, {pr.get('per_unit')} €/{pr['unit']})", file=sys.stderr)
                continue
            key = (pr["name"].lower(), pr["detail"])
            mots = [w for w in pr["name"].lower().split() if w not in ("la", "le", "les", "l'", "de", "du", "des")]
            b = pr.get("brand") or (mots[0] if mots else pr["name"].lower())
            if key in seen:
                garde["doublon de nom"] += 1; continue
            if per_brand.get(b, 0) >= MAX_PAR_MARQUE:
                garde[f"déjà {MAX_PAR_MARQUE} produits de la marque"] += 1; continue
            if n_auto >= MAX_AUTO_TOTAL:
                garde["plafond atteint"] += 1; continue
            per_brand[b] = per_brand.get(b, 0) + 1
            seen.add(key)
            n_auto += 1
        pr.pop("auto", None); pr.pop("brand", None); pr.pop("ancien", None)
        kept.append(pr)
    products = kept
    print(f"{n_auto} produits automatiques Open Prices gardés après les garde-fous", file=sys.stderr)
    for k, v in garde.items():
        if v:
            print(f"  écartés : {v} — {k}", file=sys.stderr)

    # Produits frais de l'Insee (s'ils ne répondent pas, on continue avec Open Prices seul)
    if raw is None or insee_xml is not None:
        try:
            frais = insee_products(paris_today(), insee_xml)
            frais = [f for f in frais if f["code"] not in exclus and f["code"].replace("insee-", "") not in exclus]
            products += frais
            print(f"{len(frais)} produits frais Insee ajoutés", file=sys.stderr)
        except Exception as e:
            print(f"Insee indisponible ({e}) : on continue sans les produits frais", file=sys.stderr)

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
    if not _FICHES and old and old.get("_fiches"):
        _FICHES.update(old["_fiches"])          # nuit de secours : on garde la mémoire existante
    text = json.dumps(out, ensure_ascii=False, indent=1)
    if _FICHES:                                 # mémoire des fiches, sur une seule ligne en fin de fichier
        text = text[:-2] + ',\n "_fiches": ' + json.dumps(_FICHES, ensure_ascii=False, separators=(",", ":")) + "\n}"
    path.write_text(text)
    print(f"{len(products)} produits prêts pour demain ({out['next']['from']}) ; "
          f"{len(current['products'])} produits en jeu aujourd'hui.", file=sys.stderr)
    return out


def precedents():
    """Produits de la liste jouée aujourd'hui."""
    try:
        old = json.loads((HERE / "products.json").read_text())
    except Exception:
        return []
    vus, out = set(), []
    for p in old.get("products", []):            # la liste réellement jouée aujourd'hui
        if p["code"] not in vus:
            vus.add(p["code"]); out.append(p)
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
    ap.add_argument("--insee-xml", help="fichier XML Insee pour un calcul hors ligne")
    ap.add_argument("--dump-dir", help="dossier contenant prices.jsonl.gz et locations.jsonl.gz (test hors ligne)")
    args = ap.parse_args()
    raw = json.loads(Path(args.from_raw).read_text()) if args.from_raw else None
    if raw:
        raw.pop("_source", None)
    build(raw, Path(args.insee_xml).read_text() if args.insee_xml else None, args.dump_dir)
