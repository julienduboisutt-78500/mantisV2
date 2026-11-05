import datetime
from database import get_db, init_db
from auth import hash_password

def seed_initial_data():
    """Remplit la base avec un jeu de données complet si la base est vide."""
    init_db()
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Vérifier si déjà initialisé
        cursor.execute("SELECT COUNT(*) as count FROM users")
        if cursor.fetchone()["count"] > 0:
            return False  # Déjà des données

        now = datetime.datetime.now()
        now_str = now.strftime("%Y-%m-%d %H:%M:%S")

        # 1. Clients
        clients_data = [
            ("Acme Industries", "ACME", "contact@acme.com", "+33 1 40 00 00 01"),
            ("LogiTrans Group", "LOGI", "it@logitrans.com", "+33 4 72 00 00 02"),
            ("OmniRetail Global", "OMNI", "support@omniretail.com", "+33 5 56 00 00 03"),
            ("Client Interne CEGID", "CEGID", "interne@cegid.fr", "+33 4 26 00 00 04"),
        ]
        client_ids = {}
        for name, code, email, phone in clients_data:
            cursor.execute("""
                INSERT INTO clients (name, code, contact_email, contact_phone, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, (name, code, email, phone, now_str))
            client_ids[code] = cursor.lastrowid

        # 2. Utilisateurs
        users_data = [
            ("admin", hash_password("admin123"), "Administrateur Système", "admin@cegid.local", "Administrateur", None),
            ("manager", hash_password("manager123"), "Marc Gestionnaire", "m.gestion@cegid.local", "Gestionnaire", None),
            ("dev_alice", hash_password("dev123"), "Alice Développeuse", "alice.dev@cegid.local", "Développeur", None),
            ("dev_bob", hash_password("dev123"), "Bob Développeur", "bob.dev@cegid.local", "Développeur", None),
            ("qa_lucie", hash_password("user123"), "Lucie Testeuse (QA)", "lucie.qa@cegid.local", "Rapporteur", None),
            ("client_acme", hash_password("client123"), "Thomas Directeur (Acme)", "thomas@acme.com", "Client", client_ids["ACME"]),
            ("client_omni", hash_password("client123"), "Sophie Responsable (Omni)", "sophie@omniretail.com", "Client", client_ids["OMNI"]),
        ]
        user_ids = {}
        for username, pwd_hash, full_name, email, role, cid in users_data:
            cursor.execute("""
                INSERT INTO users (username, password_hash, full_name, email, role, client_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (username, pwd_hash, full_name, email, role, cid, now_str))
            user_ids[username] = cursor.lastrowid

        # 3. Projets parents et Sous-projets
        # Projet 1 : Suite ERP V2
        cursor.execute("""
            INSERT INTO projects (name, code, description, client_id, parent_project_id, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, ("ERP Enterprise Suite", "ERP", "Suite logicielle centrale de gestion d'entreprise", client_ids["ACME"], None, "Actif", now_str))
        p_erp = cursor.lastrowid

        # Sous-projets ERP
        cursor.execute("""
            INSERT INTO projects (name, code, description, client_id, parent_project_id, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, ("Module Finance & Facturation", "ERP-FIN", "Comptabilité et facturation client", client_ids["ACME"], p_erp, "Actif", now_str))
        sp_erp_fin = cursor.lastrowid

        cursor.execute("""
            INSERT INTO projects (name, code, description, client_id, parent_project_id, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, ("Module Stocks & Logistique", "ERP-LOG", "Gestion entrepôt et inventaire", client_ids["ACME"], p_erp, "Actif", now_str))
        sp_erp_log = cursor.lastrowid

        # Projet 2 : Portail B2B E-commerce
        cursor.execute("""
            INSERT INTO projects (name, code, description, client_id, parent_project_id, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, ("Portail B2B Web", "B2B", "Application web de commande pour clients finaux", client_ids["OMNI"], None, "Actif", now_str))
        p_b2b = cursor.lastrowid

        # Sous-projets B2B
        cursor.execute("""
            INSERT INTO projects (name, code, description, client_id, parent_project_id, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, ("Frontend & UX", "B2B-UI", "Interface utilisateur Streamlit / React", client_ids["OMNI"], p_b2b, "Actif", now_str))
        sp_b2b_ui = cursor.lastrowid

        cursor.execute("""
            INSERT INTO projects (name, code, description, client_id, parent_project_id, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, ("API & Intégrations EDI", "B2B-API", "Webservices REST et passerelles flux EDI", client_ids["OMNI"], p_b2b, "Actif", now_str))
        sp_b2b_api = cursor.lastrowid

        # Projet 3 : Outil Interne
        cursor.execute("""
            INSERT INTO projects (name, code, description, client_id, parent_project_id, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, ("Outils Internes PS", "OPS", "Outils d'automatisation des consultants", client_ids["CEGID"], None, "Actif", now_str))
        p_ops = cursor.lastrowid

        # 4. Catégories par défaut
        categories = ["Interface Graphique (UI)", "Base de données", "Webservice / API", "Performance", "Facturation", "Sécurité", "Général"]
        for cat in categories:
            cursor.execute("INSERT INTO categories (name, project_id) VALUES (?, NULL)", (cat,))

        # 5. Tickets d'exemples réalistes Mantis
        tickets_samples = [
            {
                "num": "TIK-000101",
                "project_id": sp_erp_fin,
                "client_id": client_ids["ACME"],
                "category": "Facturation",
                "reporter_id": user_ids["client_acme"],
                "assigned_id": user_ids["dev_alice"],
                "status": "En cours",
                "resolution": "Non résolu",
                "priority": "Haute",
                "severity": "Majeure",
                "reproducibility": "Toujours",
                "summary": "Écart d'arrondi de TVA sur les avoirs multi-lignes",
                "description": "Lors de la génération d'un avoir comportant plus de 5 lignes avec des taux de TVA mixtes (5.5% et 20%), le montant total TTC affiche un écart de 0.02€ par rapport au calcul légal attendu.",
                "steps_to_reproduce": "1. Aller dans Factures > Avoirs\n2. Créer un avoir avec 3 lignes à 20% et 2 lignes à 5.5%\n3. Valider la pièce comptable\n4. Constater l'écart de 2 centimes.",
                "additional_info": "Impact direct sur la clôture comptable mensuelle.",
                "days_ago": 4,
                "notes": [
                    (user_ids["manager"], "Pris en compte pour le sprint en cours. Alice, peux-tu regarder la fonction round_tax() ?", 0, 0.25),
                    (user_ids["dev_alice"], "Origine identifiée : calcul ligne par ligne au lieu du calcul global consolidé. En cours de refactoring.", 1, 1.5)
                ]
            },
            {
                "num": "TIK-000102",
                "project_id": sp_b2b_api,
                "client_id": client_ids["OMNI"],
                "category": "Webservice / API",
                "reporter_id": user_ids["qa_lucie"],
                "assigned_id": user_ids["dev_bob"],
                "status": "Nouveau",
                "resolution": "Non résolu",
                "priority": "Immédiate",
                "severity": "Bloquante",
                "reproducibility": "Aléatoire",
                "summary": "Erreur HTTP 504 Gateway Timeout lors de la synchro des commandes volumineuses",
                "description": "L'appel POST /api/v1/orders/sync répond en timeout 504 lorsque le payload contient plus de 250 commandes.",
                "steps_to_reproduce": "Exécuter le script de stress-test avec un batch de 300 commandes via Postman.",
                "additional_info": "Les clients n'arrivent pas à déverser leurs commandes du pic de nuit.",
                "days_ago": 1,
                "notes": []
            },
            {
                "num": "TIK-000103",
                "project_id": sp_b2b_ui,
                "client_id": client_ids["OMNI"],
                "category": "Interface Graphique (UI)",
                "reporter_id": user_ids["client_omni"],
                "assigned_id": user_ids["dev_bob"],
                "status": "Résolu",
                "resolution": "Corrigé",
                "priority": "Normale",
                "severity": "Mineure",
                "reproducibility": "Toujours",
                "summary": "Bouton d'export Excel masqué sur les écrans portables 13 pouces",
                "description": "Sur résolution 1366x768, la barre d'outils passe en overflow et le bouton 'Exporter XLS' n'est plus cliquable.",
                "steps_to_reproduce": "Réduire la fenêtre du navigateur sous 1400px de large.",
                "additional_info": "Correction apportée via Media Query CSS.",
                "days_ago": 10,
                "closed_days_ago": 2,
                "notes": [
                    (user_ids["dev_bob"], "Correction poussée sur le commit #8f12b. Mise en prod validée.", 0, 1.0)
                ]
            },
            {
                "num": "TIK-000104",
                "project_id": sp_erp_log,
                "client_id": client_ids["ACME"],
                "category": "Performance",
                "reporter_id": user_ids["manager"],
                "assigned_id": user_ids["dev_alice"],
                "status": "En attente retour",
                "resolution": "Non résolu",
                "priority": "Urgente",
                "severity": "Majeure",
                "reproducibility": "Parfois",
                "summary": "Ralentissement important lors de l'inventaire tournant de fin de trimestre",
                "description": "La requête d'extraction des stocks en stock_history prend plus de 45 secondes sur une table de 1.2M lignes.",
                "steps_to_reproduce": "Lancer l'inventaire sur le dépôt principal avec le filtre 'Tous articles'.",
                "additional_info": "Un index composite sur (depot_id, date_mvt) semble manquer.",
                "days_ago": 6,
                "notes": [
                    (user_ids["dev_alice"], "Index de test créé sur la préproduction. En attente du retour de volumétrie du client.", 0, 2.0)
                ]
            },
            {
                "num": "TIK-000105",
                "project_id": p_ops,
                "client_id": client_ids["CEGID"],
                "category": "Général",
                "reporter_id": user_ids["admin"],
                "assigned_id": user_ids["admin"],
                "status": "Fermé",
                "resolution": "Corrigé",
                "priority": "Normale",
                "severity": "Ajustement",
                "reproducibility": "N/A",
                "summary": "Mise en place de la sauvegarde automatique du répertoire OneDrive",
                "description": "Intégration du module de backup SQLite et pièces jointes directement dans l'outil de ticketing.",
                "steps_to_reproduce": "Vérifier le dossier onedrive_storage.",
                "additional_info": "Opérationnel.",
                "days_ago": 15,
                "closed_days_ago": 12,
                "notes": [
                    (user_ids["admin"], "Terminé et documenté dans le README.", 0, 0.5)
                ]
            }
        ]

        for s in tickets_samples:
            created_dt = now - datetime.timedelta(days=s["days_ago"])
            created_str = created_dt.strftime("%Y-%m-%d %H:%M:%S")
            closed_str = None
            if "closed_days_ago" in s:
                closed_dt = now - datetime.timedelta(days=s["closed_days_ago"])
                closed_str = closed_dt.strftime("%Y-%m-%d %H:%M:%S")

            cursor.execute("""
                INSERT INTO tickets (
                    ticket_number, project_id, client_id, category, reporter_id, assigned_id,
                    status, resolution, priority, severity, reproducibility, summary,
                    description, steps_to_reproduce, additional_info, estimated_hours, spent_hours,
                    created_at, updated_at, closed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                s["num"], s["project_id"], s["client_id"], s["category"], s["reporter_id"], s["assigned_id"],
                s["status"], s["resolution"], s["priority"], s["severity"], s["reproducibility"], s["summary"],
                s["description"], s["steps_to_reproduce"], s["additional_info"], 4.0, 1.5,
                created_str, now_str, closed_str
            ))
            t_id = cursor.lastrowid

            # Notes
            for uid, note_text, is_priv, time_sp in s["notes"]:
                cursor.execute("""
                    INSERT INTO ticket_notes (ticket_id, user_id, note, is_private, time_spent, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (t_id, uid, note_text, is_priv, time_sp, created_str))

            # Historique de création
            cursor.execute("""
                INSERT INTO ticket_history (ticket_id, user_id, field_changed, old_value, new_value, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (t_id, s["reporter_id"], "Création du ticket", "", s["status"], created_str))

        return True
