#!/usr/bin/env python3
"""Assemble index.html : en-tête complet (partage, icônes, appli installable) + jeu + données du jour."""
import json
from pathlib import Path

here = Path(__file__).parent
SITE = "https://es-tu-hors-sol.fr"
TITRE = "Hors-Sol · le jeu des prix du quotidien"
DESC = "Connaissez-vous mieux le prix des courses que nos ministres ? 5 produits par jour, de vrais prix, une fourchette à trouver."

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
<!-- Mesure d'audience sans cookie : décommenter une fois le compte Plausible créé
<script defer data-domain="es-tu-hors-sol.fr" src="https://plausible.io/js/script.js"></script>
<script>window.plausible=window.plausible||function(){{(window.plausible.q=window.plausible.q||[]).push(arguments)}}</script>
-->
<style>:root{{color-scheme:light;padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}}
body{{margin:0;font:14px/1.4 system-ui,-apple-system,sans-serif}}img{{max-width:100%}}[hidden]{{display:none!important}}</style>
"""

data = json.dumps(json.loads((here / "products.json").read_text()), ensure_ascii=False, separators=(",", ":"))
tpl = (here / "template.html").read_text().replace("__DATA__", data.replace("</", "<\\/"))
cut = tpl.index('<div class="wrap">')
head_part = tpl[:cut].replace("<title>Hors-Sol</title>", f"<title>{TITRE}</title>")
page = HEAD + head_part + "</head>\n<body>\n" + tpl[cut:] + "\n</body>\n</html>\n"
(here / "index.html").write_text(page)
print("index.html généré")
