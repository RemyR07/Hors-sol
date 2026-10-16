# Mettre Hors-Sol en ligne sur es-tu-hors-sol.fr

Compter 20 à 30 minutes, de préférence sur un ordinateur. Tout est gratuit, sauf le domaine.

## 1. Déposer le site sur GitHub

1. Connecte-toi à github.com avec ton compte « studio ».
2. En haut à droite : **+** → **New repository**.
   - Repository name : `hors-sol`
   - Coche **Public** (obligatoire pour l'hébergement gratuit)
   - Ne coche rien d'autre → **Create repository**.
3. Sur la page du dépôt vide, clique sur **uploading an existing file**.
4. Dézippe `hors-sol.zip` sur ton ordinateur, ouvre le dossier, sélectionne **tout son contenu**
   (y compris le dossier `.github` : sur Mac, `Cmd + Maj + .` affiche les fichiers cachés)
   et glisse-le dans la page → **Commit changes**.

> Si le dossier `.github` ne passe pas au glisser-déposer : **Add file → Create new file**,
> tape `.github/workflows/prix-du-jour.yml` comme nom, colle le contenu du fichier, puis **Commit**.

## 2. Activer l'hébergement

1. Dans le dépôt : **Settings** → **Pages** (menu de gauche).
2. Source : **Deploy from a branch** → branche **main**, dossier **/ (root)** → **Save**.
3. Après 1 à 2 minutes, le site répond à `https://TON-PSEUDO.github.io/hors-sol/`.

## 3. Autoriser la mise à jour des prix chaque nuit

1. **Settings** → **Actions** → **General**.
2. Tout en bas, « Workflow permissions » : coche **Read and write permissions** → **Save**.
3. Onglet **Actions** → « Prix du jour » → **Run workflow** pour un premier essai.
   Une coche verte = les prix sont à jour. Ensuite, ça tourne tout seul chaque nuit.

## 4. Brancher le domaine es-tu-hors-sol.fr (chez OVH)

1. Espace client OVH → **Noms de domaine** → `es-tu-hors-sol.fr` → onglet **Zone DNS**.
2. Supprime les lignes de type **A** et **AAAA** déjà présentes pour `es-tu-hors-sol.fr` (sans sous-domaine).
3. Ajoute ces 4 lignes de type **A** (sous-domaine vide) :

   | Type | Sous-domaine | Cible |
   |---|---|---|
   | A | *(vide)* | 185.199.108.153 |
   | A | *(vide)* | 185.199.109.153 |
   | A | *(vide)* | 185.199.110.153 |
   | A | *(vide)* | 185.199.111.153 |

4. Ajoute (ou modifie) la ligne **CNAME** du sous-domaine `www` :

   | Type | Sous-domaine | Cible |
   |---|---|---|
   | CNAME | www | TON-PSEUDO.github.io. |

5. Retour sur GitHub : **Settings → Pages → Custom domain** : `es-tu-hors-sol.fr` → **Save**.
6. Patiente (de quelques minutes à quelques heures), puis coche **Enforce HTTPS**.

Le site est en ligne sur **https://es-tu-hors-sol.fr**. Il ne reste qu'à envoyer le lien.

## Vérifier avant de partager

- Ouvre le site sur ton téléphone et fais une partie complète.
- Envoie-toi le lien sur WhatsApp : une carte jaune « Hors-Sol » doit s'afficher.
- Sur iPhone : Partager → **Sur l'écran d'accueil**. Sur Android : menu ⋮ → **Installer l'application**.

## Plus tard

- **Mesure d'audience** : crée un compte Plausible pour `es-tu-hors-sol.fr`, puis décommente
  les deux lignes Plausible dans `build.py`. Les partages et les avis seront comptés automatiquement.
- **Mentions légales** : à ajouter dans `apropos.html` avant un lancement public.
