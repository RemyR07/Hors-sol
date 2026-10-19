# Mettre en ligne le serveur des ligues (Cloudflare, gratuit)

Environ 20 minutes, tout se fait dans le site de Cloudflare, sans rien installer.
Les menus de Cloudflare changent parfois de nom : en cas de doute, envoie une capture d'écran.

## 1. Créer le « Worker » (le programme qui reçoit les scores)
1. Sur dash.cloudflare.com, menu de gauche : **Workers & Pages** (parfois sous « Compute »).
2. **Create** → **Create Worker** (modèle « Hello World »).
3. Nom : `hors-sol-ligues` → **Deploy**.
4. Note l'adresse affichée, du genre `https://hors-sol-ligues.ton-nom.workers.dev`.

## 2. Créer la base de données
1. Menu de gauche : **Storage & Databases** → **D1 SQL Database** → **Create**.
2. Nom : `horssol` → **Create**. Pas besoin de créer de table : le serveur le fait tout seul.

## 3. Relier la base au Worker
1. Retourne sur le Worker `hors-sol-ligues` → onglet **Settings** → **Bindings** → **Add** → **D1 database**.
2. Variable name : `DB` (en majuscules, exactement), base : `horssol` → **Save** / **Deploy**.

## 4. Coller le code
1. Sur le Worker : **Edit code** (en haut à droite).
2. Efface tout le contenu du fichier `worker.js` (ou `index.js`).
3. Colle tout le contenu du fichier **`serveur-ligues-a-coller.js`**.
4. **Deploy**.

## 5. Vérifier
Ouvre l'adresse du Worker dans le navigateur : la page doit afficher
`Hors-Sol · serveur des ligues : OK`.

## 6. Brancher le site
Envoie l'adresse du Worker à Claude : il te renvoie un zip avec `config.json` rempli.
(Ou, sur GitHub, modifie `config.json` : `"api_ligues": "https://hors-sol-ligues.ton-nom.workers.dev"`,
puis lance **Actions → Prix du jour → Run workflow** pour reconstruire le site.)

## Plus tard
- Mettre à jour le serveur : refaire l'étape 4 avec le nouveau `serveur-ligues.js`.
- Voir les données : D1 → `horssol` → **Console** (lecture seule conseillée).
- Gratuit jusqu'à 100 000 requêtes par jour : très largement suffisant.

## 7. Le réveil du rappel de 18 h (une seule fois)
1. Worker `hors-sol-ligues` → onglet **Settings** → **Trigger events** (ou « Triggers »).
2. **Add** → **Cron Triggers**.
3. Colle cette expression : `*/10 16,17 * * *` → **Add** / **Save**.
   (C'est en heure universelle : le serveur vérifie lui-même qu'il est bien 18 h à Paris, été comme hiver.)
