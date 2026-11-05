# 🚀 Guide de Déploiement sur Streamlit Cloud (share.streamlit.io)

Ce répertoire contient **l'exact ensemble des fichiers requis** pour déployer l'application **Mantis V2** sur la plateforme officielle **Streamlit Community Cloud** (hébergement cloud sécurisé, gratuit et sans serveur à gérer).

---

## 📋 Prérequis

1. Un compte [GitHub](https://github.com/) (gratuit).
2. Un compte sur [Streamlit Community Cloud](https://share.streamlit.io/) connecté à votre GitHub.

---

## ⚡ Déploiement en 3 Étapes Rapides

### Étape 1 : Pousser ce répertoire sur un dépôt GitHub

1. Créez un nouveau dépôt vide sur votre compte GitHub (ex: `mantis-v2-cegid`).
2. Ouvrez une invite de commande dans ce répertoire (`repertoire_deploiement_streamlit`) et lancez :

```powershell
git init
git branch -M main
git add .
git commit -m "feat: Déploiement Streamlit Cloud"
git remote add origin https://github.com/VOTRE_COMPTE/mantis-v2-cegid.git
git push -u origin main
```

---

### Étape 2 : Lancer le déploiement sur Streamlit Cloud

1. Rendez-vous sur [share.streamlit.io](https://share.streamlit.io/).
2. Cliquez sur le bouton bleu **"New app"** (ou **"Create app"**).
3. Renseignez les 3 champs :
   - **Repository** : `VOTRE_COMPTE/mantis-v2-cegid`
   - **Branch** : `main`
   - **Main file path** : `app.py`
4. *(Optionnel)* Cliquez sur **"Advanced settings..."** si vous souhaitez sélectionner Python 3.12.
5. Cliquez sur **"Deploy!"**.

---

### Étape 3 : Accéder à votre application

En moins de 2 minutes :
- Streamlit Cloud installe automatiquement les dépendances indiquées dans `requirements.txt`.
- Il initialise la base SQLite intégrée et charge le jeu d'essai si la base est vierge.
- Votre application est en ligne avec une URL HTTPS permanente et partageable (ex: `https://mantis-v2-cegid.streamlit.app`).

---

## 📂 Contenu de ce Répertoire pour Streamlit

| Fichier / Dossier | Rôle sur Streamlit Cloud |
|---|---|
| **`app.py`** | Point d'entrée principal analysé par Streamlit Cloud au lancement. |
| **`requirements.txt`** | Liste des packages Python que Streamlit Cloud installe automatiquement (`streamlit`, `pandas`, `plotly`, `openpyxl`). |
| **`.streamlit/config.toml`** | Paramètres serveur optimisés pour le cloud (port, mode sans télémétrie, thème corporate). |
| **`.streamlit/secrets.toml.example`** | Modèle pour renseigner d'éventuels secrets dans l'interface de Streamlit Cloud (*Settings > Secrets*). |
| **`views/`** | Ensemble des écrans modulaires (Tableau de bord, Tickets, Import en masse, Reporting, Administration). |
| **`auth.py`**, **`config.py`**, **`database.py`**, **`notifications.py`**, **`utils.py`**, **`seed_data.py`** | Modules cœur de Mantis V2 (authentification, persistance, notifications SMTP, imports/exports). |
| **`.gitignore`** | Protège contre l'envoi de fichiers locaux temporaires ou de données sensibles. |
