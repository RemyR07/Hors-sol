# Hors-Sol — le jeu des prix du quotidien

Chaque jour, 5 produits de supermarché. On donne une fourchette de prix : plus elle est serrée, plus ça rapporte.

## Comment les prix restent à jour tout seuls

```
Open Prices (API publique, gratuite)
        │   chaque nuit
        ▼
update_prices.py  ──►  products.json  ──►  build.py  ──►  index.html (le jeu)
```

1. **Quels produits ?** Tous les produits relevés en France dans le fichier complet d'Open Prices (publié chaque nuit), s'ils passent les règles de fiabilité ci-dessous.
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

## Équité des jeux (vérifié sur 150 jours simulés)

- Trio : place du plus cher au kilo tirée à part (1/3 chacune, max 2 fois la même place par jour) ; dès le 26/10, « le paquet le plus cher » n'est la bonne réponse qu'1 fois sur 3.
- Caddie Drop : prix rangés du moins cher au plus cher, rang du vrai prix au hasard (max 2 fois la même place par jour), faux prix aux centimes « naturels ».
- Intrus : place du faux au hasard, faux prix aux centimes « naturels » (imitent les vrais : beaucoup de ,99 / ,49).
- Fourchette : prix de départ du curseur différent pour chaque produit (0,60 € à 9 €).
- Rangement et Mise en rayon : ordres de départ au hasard (vérifié).

## Produits frais : l'Insee

- `insee.json` : 44 séries « Prix moyens mensuels de vente au détail en métropole » (fruits, légumes, viandes, poissons, baguette), avec la portion affichée (ex. entrecôte : barquette de 500 g = prix au kilo × 0,5).
- Récupérées chaque nuit par `update_prices.py` (accès SDMX libre, sans clé : `bdm.insee.fr/series/sdmx/data/SERIES_BDM/...`). Une série n'est gardée que si son dernier prix a moins de 4 mois (fruits de saison). Si l'Insee ne répond pas, le jeu continue avec Open Prices seul.
- Dans le jeu : « Prix moyen relevé par l'Insee en métropole (mois année) ». Crédit dans le pied de page et la page À propos.

## Variété (depuis le 26/10)

- Anti-répétition : un produit vu dans les 14 derniers jours passe en fin de liste (3 jours avant le 26/10).
- Open Prices (maj18) : le script télécharge le **fichier complet** (`prices.openfoodfacts.org/data/prices.jsonl.gz`) au lieu d'interroger 800 produits un par un. Secours automatique sur l'ancienne méthode si le fichier est indisponible.
- Règles pour un produit ajouté automatiquement : au moins 3 relevés en France sur 12 mois, dans au moins 2 magasins, dont un de moins de 6 mois, prix peu dispersés ; **nom en français** sur Open Food Facts ; nom lisible (pas de code, pas d'adresse web) ; pas d'alcool, complément alimentaire, produit bébé ou animal ; prix ≤ 20 € ; entre 0,30 et 60 €/kg (0,10 €/L pour les boissons) ; 3 produits par marque au maximum ; 1 000 produits automatiques au maximum.
- Stabilité : un produit déjà en jeu y reste tant qu'il a au moins 3 relevés en France sur 12 mois (les règles « 2 magasins / relevé récent » ne visent que les nouveaux).
- Noms : marque complète (« Old El Paso », « Marque Repère »), première marque seulement si plusieurs ; un nom qui finit sur « & », « Les », « Old »… est considéré comme coupé et écarté.
- Rayon affiché : d'après les catégories Open Food Facts, sinon d'après le nom.
- Mémoire des fiches Open Food Facts déjà lues, rangée dans `products.json` (clé `_fiches`, retirée du jeu par `build.py`) (relues tous les 3 mois). Le premier lancement lit jusqu'à 1 500 fiches (≈ 30 min), les suivants seulement les nouveaux produits.
- `exclus.json` : liste de codes (code-barres ou code Insee) à ne jamais utiliser. À modifier directement sur GitHub.

## Cœur du caddie et bouton « inconnu au bataillon » (maj19)
- Chaque nuit, `update_prices.py` note chaque produit Open Prices : popularité sur Open Food Facts (les 1 500 produits les plus scannés, via l'API Open Prices `order_by=-unique_scans_n`), nombre de relevés, malus pour les produits de niche (liste `NICHE`). Les 300 mieux notés + le catalogue + l'Insee reçoivent `"core": true`.
- Dans le jeu, à partir du lundi 2/11 (`CORE_V3`) : 4 produits sur 5 viennent du cœur, 1 sur 5 est une « découverte ». Les jours précédents ne changent pas (vérifié jour par jour du 16/10 au 1/11).
- Fin de partie : bloc « ❓ Un produit inconnu au bataillon ? ». Le téléphone envoie au serveur des ligues (`POST /avis`) les produits vus et ceux signalés, avec un identifiant anonyme aléatoire (`horssol:anon`).
- Bilan : `GET /inconnus`. Chaque dimanche (liste du lundi), un produit vu par au moins 8 joueurs et inconnu de plus de 50 % d'entre eux sort du jeu. La liste des produits sortis est gardée dans `products.json` (clé `_inconnus`, retirée du jeu par `build.py`). Pour en faire revenir un : supprimer sa ligne dans `_inconnus`.
- Avis gardés 6 mois sur le serveur.
- Pendant la partie : petit bouton « ❓ Connais pas » sous chaque produit (tous les jeux). Il ne change pas le score ; le bloc de fin de partie arrive déjà coché. Les avis partent au serveur à la fin de la partie.

## Pop-up du lundi (maj19)
- Une fois par semaine, à la première ouverture : verdict de la semaine passée dans les ligues (place, points, jours joués) avec une punchline selon le rang (1er, 2e, 3e, autre, dernier si au moins 4 joueurs, « absent » si 2 jours joués ou moins), puis une phrase de remise à zéro (une par semaine, en rotation).
- Sans ligue : invitation à créer une ligue.
- Calcul : `lgView` renvoie `lastWeek` (serveur : `prevScores`, seulement si la ligue existait la semaine dernière). Textes : `LUNDI_RESET` et `LUNDI_VERDICT` dans `template.html`.

## Mise en rayon
- À la correction, le prix d'une étiquette mal posée n'est plus barré : fond rouge et « vrai : x,xx € » bien lisible.
