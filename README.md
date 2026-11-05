# 🎫 Mantis V2

Application professionnelle de gestion des incidents et demandes d'évolution conçue dans la philosophie de **Mantis Bug Tracker**, développée en **Streamlit (Python)** avec persistance centralisée des données.

---

## 🌟 Fonctionnalités Clés

### 1. Philosophie Mantis & Cycle de Vie des Tickets
- **Workflow complet** :
  - Statuts standardisés avec palette de couleurs officielle Mantis : `Nouveau`, `Reçu`, `Assigné`, `En cours`, `En attente retour`, `Résolu`, `Fermé`.
  - **Champs de qualification doubles** : `Qualification Client` et `Qualification Cegid` sous forme de menus déroulants dynamiques.
  - **Listes déroulantes entièrement personnalisables** : l'administrateur peut créer, modifier ou supprimer les options des qualifications, priorités, sévérités, résolutions et reproductibilités.
  - **Édition complète après création** : un ticket peut être complété et modifié à tout moment (titre, description, étapes de reproduction, client, projet, heures estimées).
  - Notes de suivi avec temps passé et distinction entre notes publiques et **notes internes privées**.
  - **Journal d'Audit Complet (Audit Trail)** : Traçabilité chronologique de chaque modification apportée à un ticket.

### 2. Import en Masse de Tickets (Excel & CSV)
- Menu dédié **📥 Import en Masse** pour les Gestionnaires et Administrateurs.
- Téléchargement direct des **modèles types d'import** pré-formatés (.xlsx et .csv).
- Détection et validation automatique ligne par ligne des projets et clients avant import.
- Génération séquentielle des numéros de tickets Mantis (`TIK-000XXX`) et journalisation.

### 3. Gestion Hiérarchique des Projets & Catégories
- Organisation en **Projets Parents** et **Sous-projets**.
- Modification et suppression sécurisée des projets avec option de transfert ou de suppression en cascade des tickets.
- **Catégories par projet** : Catégories globales applicables à tous les projets ou spécifiques à un projet précis.

### 4. Profils, Accès & Association Multi-Clients
- **Gestion Multi-Clients** : Les profils **Gestionnaire**, **Développeur**, **Rapporteur** et **Client** peuvent être rattachés à **1 ou plusieurs clients spécifiques**, ou rester transverses.
- Contrôle d'accès cloisonné selon les clients affectés.
- Suppression sécurisée des comptes utilisateurs par l'administrateur.

### 5. Notifications Automatiques par E-mail (SMTP)
- Envoi automatique d'un e-mail récapitulatif aux utilisateurs rattachés au client concerné lors de la **création** ou de la **mise à jour** d'un ticket.
- Paramétrage SMTP complet dans l'écran d'administration (serveur, port, TLS, compte, expéditeur).
- Bouton de test SMTP en direct pour valider la configuration.

### 6. Stockage Persistant & Sauvegardes
- Stockage de la base relationnelle SQLite et des pièces jointes dans un répertoire centralisé (OneDrive).
- Gestion réservée à l'administrateur avec outil de sauvegarde ZIP instantanée.

---

## 🚀 Démarrage Rapide

### Prérequis
- Python 3.10 ou supérieur.
- Dépendances : `streamlit`, `pandas`, `plotly`, `openpyxl`.

### Installation
```bash
pip install -r requirements.txt
```

### Lancement
Double-cliquez sur `run_app.bat` ou lancez :
```bash
streamlit run app.py
```
L'interface s'ouvre sur `http://localhost:8501`.
