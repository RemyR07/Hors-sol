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
   Produits ajoutés automatiquement : nom nettoyé (marque répétée, poids, emojis), noms étrangers écartés, plus de 20 € ou de 60 €/kg écartés, poids des packs corrigé (4x100 g = 400 g), 3 produits maximum par marque, rayon deviné d'après le nom.
4. **Une série par jour, la même pour tous :** les prix calculés dans la nuit (ou par un lancement manuel) sont rangés dans `next` et n'entrent en jeu qu'au minuit suivant. La liste du jour ne change jamais en cours de journée.
5. **Changement de jour :** si la page est restée ouverte, le jeu se recharge tout seul à minuit ou au retour sur l'onglet.

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
| `score-0-99` … `score-400-500` | tranche du score du jour (sur 500, hors bonus) |
| `bonus-precision`, `boss-du-rayon` | au moins un bonus de précision / au moins 2 Pile-poil |
| `partage` | un joueur partage son ticket |
| `idee-groupe`, `idee-themes`, `idee-retro`, `idee-plus`, `idee-marques` | idées cochées en fin de partie |

Taux de retour = (fin-jour-2 + fin-jour-3-6 + fin-jour-7plus) / fin-partie.

## Les 5 jeux et le calendrier

| Lun | Mar | Mer | Jeu | Ven | Sam | Dim |
|---|---|---|---|---|---|---|
| Trio au kilo | Fourchette | Rangement | Caddie Drop | L'Intrus | Mise en rayon | 🏛️ 49.3 |

Dimanche « décidé au 49.3 » : l'un des 6 jeux, tiré au sort à chances égales (le même pour tout le monde, car le tirage dépend de la date), annoncé par une phrase de décret.

Calendrier modifiable dans `template.html` (constante `WEEK`). Tous les jeux donnent un score sur 500 (titres et punchlines communs), des bonus à part et un badge « Boss du rayon ».

| Jeu | Règle | Points | Bonus | Boss du rayon |
|---|---|---|---|---|
| 🎯 La Fourchette | 5 produits, un prix + une fourchette (±15 / ±35 / ±60 %) | 100 / 50 / 20 selon la fourchette | Pile-poil (3 %) +50, Tout proche (7 %) +20 | 2 Pile-poil |
| 💰 Le Caddie Drop | 5 produits, 100 jetons à répartir sur 4 prix (au moins une trappe vide) | 1 pt par jeton sur le bon prix | Tout sur la bonne +20 | 3 « Tout sur la bonne » |
| ⚖️ Le Trio au kilo | 5 manches, 3 produits : le plus cher au kilo | 100 par bonne réponse | Sans-faute +50 | 5/5 |
| 🛒 Le Rangement | 3 caddies (4, 5, 5 produits) à classer | 35-36 par produit bien placé, moitié à une place près | Caddie parfait +30 | 2 caddies parfaits |
| 🔎 L'Intrus | 5 manches, 5 prix dont 1 faux, 2 essais | 100 (1er coup) / 40 (2e) | Flair « trop cher / trop bas » +20, pour tous, avant de voir le vrai prix | 5 du 1er coup |
| 🏷️ La Mise en rayon | 2 rayons, 5 étiquettes à coller | 50 par étiquette | Rayon parfait +50 | 2 rayons parfaits |

Anti-répétition : un produit sorti dans les 3 jours précédents ne revient pas (sauf si le catalogue est trop petit pour faire autrement).

Écarts minimum garantis : Rangement 50 % / 30 % / 20 % (et au moins 0,30 €), Mise en rayon 12 % (et 0,15 €), Trio : le gagnant au moins 15 % plus cher au kilo.

Pour tester un autre jeu que celui du jour : ajouter `#trio`, `#rangement`, `#drop`, `#intrus`, `#rayon` ou `#fourchette` à l'adresse.

Bandeau « Mise à jour » : modifier le texte dans `template.html` (bloc `news`) et changer `UPDATE_ID` pour qu'il réapparaisse chez tout le monde. Événement `maj-lue` quand un joueur l'ouvre.

Événements GoatCounter en plus : `jeu-<nom>` à chaque fin de partie, `bonus-<nom>` si un bonus a été gagné.

## Barème

Fourchette : Sûr de moi ±15 % = 100 pts, À peu près ±35 % = 50 pts, Au pif ±60 % = 20 pts, hors fourchette = 0.
Score du jour sur 500 (points de fourchette). Bonus de précision affichés à part : à 3 % près +50 (Pile-poil), à 7 % près +20 (Tout proche). 2 Pile-poil ou plus : badge « Boss du rayon ». Le titre de fin dépend du score sur 500.

## Les ligues entre proches (multijoueur sans compte)

- Le jeu crée une identité anonyme sur le téléphone (`horssol:me` : identifiant + clé secrète + prénom).
- Le serveur (Cloudflare Worker + base D1) reçoit les parties terminées de la semaine et calcule les classements.
- Une partie par jour, qui compte dans toutes les ligues du joueur (10 ligues max, 30 joueurs max par ligue).
- Semaine du lundi au dimanche : points + bonus, jour non joué = 0, « 5/7 j » affiché. Égalité : le moins de jours joués passe devant. Gagnant du jour 👑 (ex aequo possibles), champion de la semaine annoncé le lundi, palmarès.
- Scores du jour des autres cachés tant qu'on n'a pas joué ; tickets visibles pour les jours qu'on a joués.
- Lien d'invitation : `https://es-tu-hors-sol.fr/#l-<id>` ; lien de récupération (changer de téléphone) : `#moi-<id>.<clé>`.
- Données : prénom + scores, détail effacé après 4 semaines.

| Fichier | Rôle |
|---|---|
| `ligues-core.js` | Calcul des classements (partagé par le serveur et la maquette) |
| `ligues-serveur.js` | Le serveur |
| `serveur-ligues-a-coller.js` | Fichier complet à coller dans Cloudflare (généré par `build.py`) |
| `config.json` | `api_ligues` : adresse du serveur. Vide = ligues désactivées sur le site |
| `MISE-EN-LIGNE-LIGUES.md` | Le guide Cloudflare pas à pas |

Événements GoatCounter : `ligue-ouverte`, `ligue-creee`, `ligue-rejointe`, `ligue-invitation`.

## Fenêtre de mise à jour, contact, sondage

- Fenêtre « Hors-Sol a changé ! » : montrée une fois par mise à jour (`UPDATE_ID` dans `template.html`), uniquement aux joueurs qui avaient déjà joué. Événement `maj-lue`.
- Contact : formulaire « Nous écrire » (bug / commentaire) envoyé via Web3Forms ; l'adresse email n'apparaît jamais dans le site. Clé à mettre dans `config.json` (`contact_key`). Sans clé, le lien Contact est caché. Événements `contact-bug`, `contact-msg`.
- Sondage de fin : en pause (`SHOW_SURVEY = false` dans `template.html`).

## Installer sur l'écran d'accueil + rappel de 18 h

- Fenêtre « Oui / Non » 1 seconde après la fin de la partie, à partir du 2e jour joué, sur téléphone : 1) ajouter Hors-Sol à l'écran d'accueil (bouton natif sur Android, tuto sur iPhone), 2) le rappel de 18 h. Chaque question n'est posée qu'une fois (`horssol:ask`). Événements en plus : `appli-refusee`, `rappel-refuse`.
- Rappel « 🔔 Me prévenir à 18 h si j'oublie ma partie » : notification envoyée uniquement aux joueurs qui ne l'ont pas encore faite ce jour-là. Sur iPhone, seulement une fois le jeu installé.
- `sw-source.js` → `sw.js` (généré par `build.py`) : reçoit la notification et va chercher le texte du jour sur `/rappel`.
- Serveur : table `push_subs`, clés VAPID créées automatiquement (table `settings`), déclencheur Cron `*/10 16,17 * * *` qui n'agit qu'entre 18 h et 18 h 59 à Paris (40 notifications max par passage, 6 passages = 240/jour sur l'offre gratuite). Arrêt automatique : pas de rappel si aucune partie dans les 7 derniers jours.
- Événements GoatCounter : `appli-proposee`, `appli-tuto`, `appli-installee`, `appli-ouverte`, `rappel-active`, `rappel-coupe`, `rappel-ouvert`.
