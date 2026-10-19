#!/usr/bin/env python3
"""Assemble index.html : en-tête complet (partage, icônes, appli installable) + jeu + données du jour."""
import json
from pathlib import Path

here = Path(__file__).parent
SITE = "https://es-tu-hors-sol.fr"
TITRE = "Hors-Sol · le jeu des prix du quotidien"
DESC = "Connaissez-vous mieux le prix des courses que nos ministres ? Un mini-jeu par jour sur les prix des courses, avec de vrais prix relevés en magasin."

HEAD = f"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="description" content="{DESC}">
<meta name="theme-color" content="#FFD21F">
<link rel="canonical" href="{SITE}/">
<link rel="manifest" href="manifest.webmanifest">
<link rel="icon" type="image/png" sizes="32x32" href="assets/icon-32.png">
<link rel="apple-touch-icon" href="assets/icon-180.png">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="Hors-Sol">
<meta property="og:type" content="website">
<meta property="og:locale" content="fr_FR">
<meta property="og:url" content="{SITE}/">
<meta property="og:title" content="{TITRE}">
<meta property="og:description" content="{DESC}">
<meta property="og:image" content="{SITE}/assets/og.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:image" content="{SITE}/assets/og.png">
<!-- Mesure d'audience sans cookie : GoatCounter (tableau de bord : https://horssol.goatcounter.com) -->
<script data-goatcounter="https://horssol.goatcounter.com/count" async src="//gc.zgo.at/count.js"></script>
<style>:root{{color-scheme:light;padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}}
body{{margin:0;font:14px/1.4 system-ui,-apple-system,sans-serif}}img{{max-width:100%}}[hidden]{{display:none!important}}</style>
"""

# Ligues : le noyau commun est injecté dans le jeu (maquette) et dans le serveur à coller sur Cloudflare.
core = (here / "ligues-core.js").read_text()
(here / "serveur-ligues-a-coller.js").write_text(
    "// Fichier à coller tel quel dans le Worker Cloudflare (généré par build.py, ne pas modifier à la main).\n"
    + core + "\n" + (here / "ligues-serveur.js").read_text())
cfg_path = here / "config.json"
cfg = json.loads(cfg_path.read_text()) if cfg_path.exists() else {}
api = (cfg.get("api_ligues") or "").rstrip("/")

data = json.dumps(json.loads((here / "products.json").read_text()), ensure_ascii=False, separators=(",", ":"))
tpl = (here / "template.html").read_text().replace("__DATA__", data.replace("</", "<\\/"))
tpl = tpl.replace("/*__LIGUES_CORE__*/", core).replace("__API_LIGUES__", api)
tpl = tpl.replace("__CONTACT_KEY__", (cfg.get("contact_key") or "").strip())
# Service worker du rappel de 18 h (doit être à la racine du site)
(here / "sw.js").write_text((here / "sw-source.js").read_text().replace("__API_LIGUES__", api))
cut = tpl.index('<div class="wrap">')
head_part = tpl[:cut].replace("<title>Hors-Sol</title>", f"<title>{TITRE}</title>")
page = HEAD + head_part + "</head>\n<body>\n" + tpl[cut:] + "\n</body>\n</html>\n"
(here / "index.html").write_text(page)
print("index.html généré")
