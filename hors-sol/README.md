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

## Mesurer l'intérêt (sans compte, sans cookie)

Le jeu envoie des événements à **Plausible** s'il est installé sur le site (script Plausible dans la page), sinon rien :

| Événement | Quand | Détail |
|---|---|---|
| `partage` | un joueur partage | `type` = `defi` (score seul) ou `ticket` (ticket complet) |
| `idee` | un joueur envoie son avis en fin de partie | `idee` = `groupe`, `themes`, `retro`, `plus`, `marques` |

Le nombre de clics sur chaque idée dit quoi construire ensuite, sans jamais parler d'argent.
Pour activer Plausible : décommenter les deux lignes dans `build.py`.
