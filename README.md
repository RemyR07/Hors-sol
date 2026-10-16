# Hors-Sol — le jeu des prix du quotidien

Chaque jour, 5 produits de supermarché. On donne une fourchette de prix : plus elle est serrée, plus ça rapporte.

## Comment les prix restent à jour tout seuls

```
Open Prices (API publique, gratuite)
        │   chaque nuit
        ▼
update_prices.py  ──►  products.json  ──►  build.py  ──►  index.html (le jeu)
```

1. **Quels produits ?** Ceux que les Français scannent le plus sur Open Prices.
   Un produit relevé des dizaines de fois est un produit que tout le monde achète :
   c'est le filtre « produits du quotidien », sans tri manuel.
   `catalog.json` permet d'ajouter un produit ou de soigner son libellé.
2. **Quel prix ?** La médiane des relevés en France, en euros, sur 12 mois.
   La médiane écarte les promos et les fautes de frappe.
3. **Garde-fous :** au moins 3 relevés, et pas de produit dont les prix partent dans tous les sens.

## Fichiers

| Fichier | Rôle |
|---|---|
| `update_prices.py` | Interroge l'API, calcule les médianes, écrit `products.json` |
| `catalog.json` | Libellés soignés (« Pot de 400 g », rayon, prix au kilo) |
| `products.json` | Données du jour |
| `template.html` + `build.py` | Le jeu ; `build.py` y injecte les données et produit `index.html` |
| `raw_prices.json` | Relevés utilisés pour la version de démo |
| `.github/workflows/prix-du-jour.yml` | Lance la mise à jour chaque nuit |
| `index.html` | Le site final (généré, ne pas modifier à la main) |
| `apropos.html` | Page « À propos » : sources, données, marques |
| `manifest.webmanifest`, `assets/` | Appli installable, icônes, image de partage |
| `CNAME` | Relie le site à es-tu-hors-sol.fr |
| `MISE-EN-LIGNE.md` | Le guide pas à pas pour publier |

## Lancer

```bash
python3 update_prices.py                       # vraies données, via l'API
python3 update_prices.py --from-raw raw_prices.json   # hors ligne
```

## Avant la mise en ligne

- Créditer **Open Prices / Open Food Facts (ODbL)** sur la page (déjà fait dans le pied de page).
- Aucune donnée personnelle collectée : la série de jours est stockée dans le navigateur du joueur.
- Pas de photos de produits ni de logos de marques.

## Pistes suivantes

- Plus de produits en abaissant `ECART_MAX` ou en élargissant le catalogue.
- Rayons à thème (apéro, rentrée, Noël) pour la version payante.
- Mode « prix d'hier » : comparer avec le prix d'il y a 5 ans (indices INSEE).

## Mesurer l'audience (sans compte, sans cookie)

Tableau de bord : **https://horssol.goatcounter.com** (visites, provenance, appareils + événements ci-dessous).

| Événement | Quand |
|---|---|
| `fin-partie` | un joueur termine les 5 produits |
| `fin-jour-1`, `fin-jour-2`, `fin-jour-3-6`, `fin-jour-7plus` | combien de jours ce joueur a déjà joué (compteur anonyme stocké dans son navigateur) |
| `serie-3-6`, `serie-7plus` | série de jours consécutifs en cours |
| `score-0-149` … `score-600plus` | tranche de score du jour |
| `partage` | un joueur partage son ticket |
| `idee-groupe`, `idee-themes`, `idee-retro`, `idee-plus`, `idee-marques` | idées cochées en fin de partie |

Taux de retour = (fin-jour-2 + fin-jour-3-6 + fin-jour-7plus) / fin-partie.

## Barème

Fourchette : Sûr de moi ±10 % = 100 pts, À peu près ±25 % = 50 pts, Au pif ±50 % = 20 pts, hors fourchette = 0.
Bonus de précision, quelle que soit la fourchette : à 2 % près +50 (Pile-poil), à 5 % près +20 (Tout proche). Maximum 750 pts.
