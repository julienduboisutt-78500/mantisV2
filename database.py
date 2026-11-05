import sqlite3
import datetime
import os
import json
import shutil
import threading
from pathlib import Path
from contextlib import contextmanager
import pandas as pd
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
import config

STATUS_LIST = [
    "Nouveau",
    "Reçu",
    "Assigné",
    "En cours",
    "En attente retour",
    "Résolu",
    "Fermé",
]

STATUS_COLORS = {
    "Nouveau": "#FFA07A",         # Saumon clair (Mantis orange/rose)
    "Reçu": "#FFD700",            # Or / Jaune
    "Assigné": "#87CEEB",         # Bleu ciel
    "En cours": "#1E90FF",        # Bleu royal
    "En attente retour": "#DA70D6",# Orchidée / Violet
    "Résolu": "#90EE90",          # Vert clair
    "Fermé": "#D3D3D3",           # Gris clair
}

PRIORITY_LIST = ["Basse", "Normale", "Haute", "Urgente", "Immédiate"]
PRIORITY_COLORS = {
    "Basse": "#9E9E9E",
    "Normale": "#2196F3",
    "Haute": "#FF9800",
    "Urgente": "#F44336",
    "Immédiate": "#9C27B0"
}

SEVERITY_LIST = ["Ajustement", "Mineure", "Majeure", "Bloquante"]
SEVERITY_COLORS = {
    "Ajustement": "#4CAF50",
    "Mineure": "#03A9F4",
    "Majeure": "#FF9800",
    "Bloquante": "#E91E63"
}

REPRODUCIBILITY_LIST = ["Toujours", "Parfois", "Aléatoire", "Non testé", "N/A"]
RESOLUTION_LIST = ["Non résolu", "Corrigé", "Non reproductible", "Ne sera pas corrigé", "Doublon", "Suspendu"]
ROLES_LIST = ["Administrateur", "Gestionnaire", "Développeur", "Rapporteur", "Client"]

DEFAULT_CUSTOM_LISTS = {
    "qualification_client": [
        "Non qualifié",
        "En attente test client",
        "Validé en recette",
        "Refusé / Non conforme",
        "Demande d'informations complémentaires"
    ],
    "qualification_cegid": [
        "Non qualifié",
        "Analyse technique en cours",
        "Bug avéré (escalade R&D)",
        "Demande d'évolution",
        "Assistance / Formation client",
        "Incident infrastructure / Réseau",
        "Comportement standard conforme"
    ],
    "priority": PRIORITY_LIST,
    "severity": SEVERITY_LIST,
    "resolution": RESOLUTION_LIST,
    "reproducibility": REPRODUCIBILITY_LIST
}

LIST_TYPE_LABELS = {
    "qualification_client": "Qualification Client",
    "qualification_cegid": "Qualification Cegid",
    "priority": "Priorité",
    "severity": "Sévérité",
    "resolution": "Résolution",
    "reproducibility": "Reproductibilité"
}

def get_connection():
    db_path = config.get_db_path()
    conn = sqlite3.connect(str(db_path), timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = TRUNCATE;")
    conn.execute("PRAGMA busy_timeout = 5000;")
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

@contextmanager
def get_db():
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def init_db(target_db_path: Path = None):
    """Initialise les tables de la base de données et applique les migrations."""
    db_p = target_db_path or config.get_db_path()
    conn = sqlite3.connect(str(db_p), timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = TRUNCATE;")
    conn.execute("PRAGMA busy_timeout = 5000;")
    try:
        cursor = conn.cursor()

        # 1. Clients
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS clients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                code TEXT,
                contact_email TEXT,
                contact_phone TEXT,
                is_active INTEGER DEFAULT 1,
                created_at TEXT NOT NULL
            );
        """)

        # 2. Projets et Sous-projets (parent_project_id)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                code TEXT NOT NULL UNIQUE,
                description TEXT,
                client_id INTEGER REFERENCES clients(id) ON DELETE SET NULL,
                parent_project_id INTEGER REFERENCES projects(id) ON DELETE SET NULL,
                status TEXT DEFAULT 'Actif',
                created_at TEXT NOT NULL
            );
        """)

        # 3. Utilisateurs
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                full_name TEXT NOT NULL,
                email TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'Rapporteur',
                client_id INTEGER REFERENCES clients(id) ON DELETE SET NULL,
                is_active INTEGER DEFAULT 1,
                created_at TEXT NOT NULL
            );
        """)

        # 4. Droits d'accès par projet pour les utilisateurs
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_project_access (
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                PRIMARY KEY (user_id, project_id)
            );
        """)

        # 4 bis. Liaison utilisateurs multi-clients
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_client_access (
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                client_id INTEGER NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
                PRIMARY KEY (user_id, client_id)
            );
        """)

        # 5. Catégories
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE
            );
        """)

        # 6. Tickets
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_number TEXT NOT NULL UNIQUE,
                project_id INTEGER NOT NULL REFERENCES projects(id),
                client_id INTEGER REFERENCES clients(id),
                category TEXT DEFAULT 'Général',
                reporter_id INTEGER NOT NULL REFERENCES users(id),
                assigned_id INTEGER REFERENCES users(id),
                status TEXT NOT NULL DEFAULT 'Nouveau',
                resolution TEXT NOT NULL DEFAULT 'Non résolu',
                priority TEXT NOT NULL DEFAULT 'Normale',
                severity TEXT NOT NULL DEFAULT 'Mineure',
                reproducibility TEXT NOT NULL DEFAULT 'Toujours',
                qualification_client TEXT DEFAULT 'Non qualifié',
                qualification_cegid TEXT DEFAULT 'Non qualifié',
                summary TEXT NOT NULL,
                description TEXT NOT NULL,
                steps_to_reproduce TEXT,
                additional_info TEXT,
                estimated_hours REAL DEFAULT 0,
                spent_hours REAL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                closed_at TEXT
            );
        """)

        # 7. Notes / Commentaires
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ticket_notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_id INTEGER NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
                user_id INTEGER NOT NULL REFERENCES users(id),
                note TEXT NOT NULL,
                is_private INTEGER DEFAULT 0,
                time_spent REAL DEFAULT 0,
                created_at TEXT NOT NULL
            );
        """)

        # 8. Pièces jointes
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ticket_attachments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_id INTEGER NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
                user_id INTEGER NOT NULL REFERENCES users(id),
                filename TEXT NOT NULL,
                stored_filename TEXT NOT NULL,
                filesize INTEGER NOT NULL,
                created_at TEXT NOT NULL
            );
        """)

        # 9. Historique / Journal d'activité Mantis
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ticket_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_id INTEGER NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
                user_id INTEGER NOT NULL REFERENCES users(id),
                field_changed TEXT NOT NULL,
                old_value TEXT,
                new_value TEXT,
                created_at TEXT NOT NULL
            );
        """)

        # 10. Listes personnalisables pour les champs des tickets
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS custom_lists (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                list_type TEXT NOT NULL,
                value TEXT NOT NULL,
                sort_order INTEGER DEFAULT 0,
                is_active INTEGER DEFAULT 1
            );
        """)

        # 11. Paramètres de notification par email SMTP
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS email_settings (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                is_enabled INTEGER DEFAULT 0,
                smtp_server TEXT DEFAULT '',
                smtp_port INTEGER DEFAULT 587,
                smtp_user TEXT DEFAULT '',
                smtp_password TEXT DEFAULT '',
                use_tls INTEGER DEFAULT 1,
                sender_email TEXT DEFAULT '',
                sender_name TEXT DEFAULT 'Mantis V2'
            );
        """)

        # Initialiser email_settings si vide
        cursor.execute("SELECT COUNT(*) as nb FROM email_settings WHERE id = 1")
        if cursor.fetchone()["nb"] == 0:
            cursor.execute("""
                INSERT INTO email_settings (id, is_enabled, smtp_server, smtp_port, smtp_user, smtp_password, use_tls, sender_email, sender_name)
                VALUES (1, 0, '', 587, '', '', 1, '', 'Mantis V2')
            """)

        # --- MIGRATIONS AUTOMATIQUES ---
        cursor.execute("PRAGMA table_info(tickets);")
        columns = [col["name"] for col in cursor.fetchall()]

        if "qualification_client" not in columns:
            cursor.execute("ALTER TABLE tickets ADD COLUMN qualification_client TEXT DEFAULT 'Non qualifié';")
        if "qualification_cegid" not in columns:
            cursor.execute("ALTER TABLE tickets ADD COLUMN qualification_cegid TEXT DEFAULT 'Non qualifié';")

        # Migration des anciens liens client_id vers user_client_access
        cursor.execute("""
            INSERT OR IGNORE INTO user_client_access (user_id, client_id)
            SELECT id, client_id FROM users WHERE client_id IS NOT NULL;
        """)

        # Initialiser les valeurs par défaut de custom_lists si vide
        cursor.execute("SELECT COUNT(*) as count FROM custom_lists")
        if cursor.fetchone()["count"] == 0:
            for l_type, val_list in DEFAULT_CUSTOM_LISTS.items():
                for idx, val in enumerate(val_list):
                    cursor.execute("""
                        INSERT INTO custom_lists (list_type, value, sort_order, is_active)
                        VALUES (?, ?, ?, 1)
                    """, (l_type, val, idx))

        conn.commit()
    finally:
        conn.close()

def get_user_client_ids(user_id: int) -> list[int]:
    """Renvoie la liste des identifiants des clients associés à un utilisateur."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT client_id FROM user_client_access WHERE user_id = ?", (user_id,))
        return [r["client_id"] for r in cursor.fetchall()]

def set_user_client_ids(user_id: int, client_ids: list[int]):
    """Définit la liste des clients associés à un utilisateur."""
    with get_db() as conn:
        conn.execute("DELETE FROM user_client_access WHERE user_id = ?", (user_id,))
        for cid in client_ids:
            conn.execute("INSERT OR IGNORE INTO user_client_access (user_id, client_id) VALUES (?, ?)", (user_id, cid))
        # Synchroniser client_id principal pour rétro-compatibilité
        main_cid = client_ids[0] if client_ids else None
        conn.execute("UPDATE users SET client_id = ? WHERE id = ?", (main_cid, user_id))

def get_custom_list_values(list_type: str) -> list[str]:
    """Renvoie la liste ordonnée des valeurs actives pour un type de champ donné."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT value FROM custom_lists
            WHERE list_type = ? AND is_active = 1
            ORDER BY sort_order ASC, id ASC
        """, (list_type,))
        rows = cursor.fetchall()
        if rows:
            return [r["value"] for r in rows]
        return DEFAULT_CUSTOM_LISTS.get(list_type, [])

def get_email_settings() -> dict:
    """Récupère les paramètres de configuration SMTP."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM email_settings WHERE id = 1")
        row = cursor.fetchone()
        return dict(row) if row else {}

def save_email_settings(settings: dict):
    """Enregistre les paramètres de configuration SMTP."""
    with get_db() as conn:
        conn.execute("""
            UPDATE email_settings
            SET is_enabled = ?, smtp_server = ?, smtp_port = ?, smtp_user = ?,
                smtp_password = ?, use_tls = ?, sender_email = ?, sender_name = ?
            WHERE id = 1
        """, (
            1 if settings.get("is_enabled") else 0,
            settings.get("smtp_server", "").strip(),
            int(settings.get("smtp_port", 587)),
            settings.get("smtp_user", "").strip(),
            settings.get("smtp_password", "").strip(),
            1 if settings.get("use_tls") else 0,
            settings.get("sender_email", "").strip(),
            settings.get("sender_name", "Mantis V2").strip()
        ))

def log_ticket_history(conn, ticket_id: int, user_id: int, field_changed: str, old_val: str, new_val: str):
    """Enregistre un événement dans le journal d'activité d'un ticket."""
    if old_val != new_val:
        conn.execute("""
            INSERT INTO ticket_history (ticket_id, user_id, field_changed, old_value, new_value, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            ticket_id,
            user_id,
            field_changed,
            str(old_val) if old_val is not None else "",
            str(new_val) if new_val is not None else "",
            datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ))

# =========================================================================
# --- SYNCHRONISATION & MIROIR SHAREPOINT / ONEDRIVE (ANTI-ÉCRASEMENT) ---
# =========================================================================

def export_database_to_sharepoint_mirror(db_path: Path = None, output_dir: Path = None) -> bool:
    """
    Exporte l'intégralité de la base SQLite vers :
    1. Un classeur Excel multi-onglets 'Export_MantisV2_Complet.xlsx' lisible en direct dans SharePoint / Excel Online
    2. Un fichier JSON miroir 'mantis_data.json' pour la persistance et la restauration sans perte
    3. Une copie de sécurité 'ticketing.db.bak'
    """
    try:
        db_p = db_path or config.get_db_path()
        out_p = output_dir or config.get_storage_path()
        out_p.mkdir(parents=True, exist_ok=True)

        if not db_p.exists():
            return False

        # Copie de sauvegarde .bak
        try:
            shutil.copy2(db_p, out_p / "ticketing.db.bak")
        except Exception:
            pass

        conn = sqlite3.connect(str(db_p), timeout=15.0)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        # 1. Extraction JSON miroir
        tables = [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name != 'sqlite_sequence'").fetchall()]
        data_json = {
            "version": "Mantis V2",
            "exported_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "tables": {}
        }
        for t in tables:
            rows = cur.execute(f"SELECT * FROM [{t}]").fetchall()
            data_json["tables"][t] = [dict(r) for r in rows]

        json_file = out_p / "mantis_data.json"
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(data_json, f, ensure_ascii=False, indent=2)

        # 2. Création du classeur Excel SharePoint
        excel_file = out_p / "Export_MantisV2_Complet.xlsx"

        tickets_query = """
            SELECT 
                t.ticket_number AS [N° Ticket],
                t.summary AS [Titre / Résumé],
                c.name AS [Client],
                p.name AS [Projet],
                t.category AS [Catégorie],
                t.status AS [Statut],
                t.priority AS [Priorité],
                t.severity AS [Sévérité],
                t.reproducibility AS [Reproductibilité],
                t.resolution AS [Résolution],
                t.qualification_client AS [Qualification Client],
                t.qualification_cegid AS [Qualification Cegid],
                u_rep.full_name AS [Rapporteur],
                u_ass.full_name AS [Assigné à],
                t.created_at AS [Date Création],
                t.updated_at AS [Dernière MàJ],
                t.closed_at AS [Date Clôture],
                t.estimated_hours AS [Heures Estimées],
                t.spent_hours AS [Heures Passées],
                t.description AS [Description]
            FROM tickets t
            LEFT JOIN clients c ON t.client_id = c.id
            LEFT JOIN projects p ON t.project_id = p.id
            LEFT JOIN users u_rep ON t.reporter_id = u_rep.id
            LEFT JOIN users u_ass ON t.assigned_id = u_ass.id
            ORDER BY t.id DESC
        """
        df_tickets = pd.read_sql_query(tickets_query, conn)

        projects_query = """
            SELECT 
                p.id AS [ID],
                p.name AS [Nom Projet],
                p.code AS [Code],
                c.name AS [Client],
                parent.name AS [Sous-projet de],
                p.status AS [Statut],
                p.description AS [Description]
            FROM projects p
            LEFT JOIN clients c ON p.client_id = c.id
            LEFT JOIN projects parent ON p.parent_project_id = parent.id
            ORDER BY p.name ASC
        """
        df_projects = pd.read_sql_query(projects_query, conn)

        clients_query = """
            SELECT 
                id AS [ID],
                name AS [Nom Client],
                code AS [Code],
                contact_email AS [Email Contact],
                contact_phone AS [Téléphone],
                created_at AS [Date Création]
            FROM clients
            ORDER BY name ASC
        """
        df_clients = pd.read_sql_query(clients_query, conn)

        users_query = """
            SELECT 
                u.id AS [ID],
                u.username AS [Identifiant],
                u.full_name AS [Nom Complet],
                u.role AS [Rôle],
                u.email AS [Email],
                GROUP_CONCAT(c.name, ', ') AS [Clients Rattachés]
            FROM users u
            LEFT JOIN user_client_access uca ON u.id = uca.user_id
            LEFT JOIN clients c ON uca.client_id = c.id
            GROUP BY u.id
            ORDER BY u.role, u.full_name ASC
        """
        df_users = pd.read_sql_query(users_query, conn)

        notes_query = """
            SELECT 
                t.ticket_number AS [N° Ticket],
                t.summary AS [Titre Ticket],
                tn.created_at AS [Date],
                u.full_name AS [Auteur],
                CASE WHEN tn.is_private = 1 THEN 'Note Interne' ELSE 'Note Publique' END AS [Type],
                tn.time_spent AS [Temps Passé (h)],
                tn.note AS [Commentaire]
            FROM ticket_notes tn
            JOIN tickets t ON tn.ticket_id = t.id
            LEFT JOIN users u ON tn.user_id = u.id
            ORDER BY tn.created_at DESC
        """
        df_notes = pd.read_sql_query(notes_query, conn)

        lists_query = """
            SELECT 
                list_type AS [Type de Liste],
                value AS [Valeur],
                sort_order AS [Ordre],
                is_active AS [Actif]
            FROM custom_lists
            ORDER BY list_type, sort_order ASC
        """
        df_lists = pd.read_sql_query(lists_query, conn)

        conn.close()

        # Écriture Excel
        with pd.ExcelWriter(excel_file, engine="openpyxl") as writer:
            df_tickets.to_excel(writer, sheet_name="Tickets", index=False)
            df_projects.to_excel(writer, sheet_name="Projets", index=False)
            df_clients.to_excel(writer, sheet_name="Clients", index=False)
            df_users.to_excel(writer, sheet_name="Utilisateurs", index=False)
            df_notes.to_excel(writer, sheet_name="Commentaires", index=False)
            df_lists.to_excel(writer, sheet_name="Paramètres Listes", index=False)

        # Stylisation pour SharePoint Online
        wb = openpyxl.load_workbook(excel_file)
        header_fill = PatternFill(start_color="1E3A8A", end_color="1E3A8A", fill_type="solid")
        header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
        thin_border = Border(
            left=Side(style='thin', color='E2E8F0'),
            right=Side(style='thin', color='E2E8F0'),
            top=Side(style='thin', color='E2E8F0'),
            bottom=Side(style='thin', color='E2E8F0')
        )

        for sheet in wb.worksheets:
            sheet.views.sheetView[0].showGridLines = True
            for col in range(1, sheet.max_column + 1):
                cell = sheet.cell(row=1, column=col)
                cell.fill = header_fill
                cell.font = header_font
                cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

            for col in sheet.columns:
                col_letter = get_column_letter(col[0].column)
                max_len = 0
                for cell in col:
                    cell.border = thin_border
                    val_str = str(cell.value or "")
                    if len(val_str) > max_len:
                        max_len = len(val_str)
                sheet.column_dimensions[col_letter].width = min(max(max_len + 3, 12), 50)
                
            sheet.auto_filter.ref = sheet.dimensions

        wb.save(excel_file)
        return True
    except Exception as e:
        print(f"Erreur export SharePoint : {e}")
        return False

def sync_all_to_sharepoint_async():
    """Déclenche la mise à jour des miroirs SharePoint (Excel + JSON) en arrière-plan sans ralentir l'UI."""
    try:
        t = threading.Thread(target=export_database_to_sharepoint_mirror, daemon=True)
        t.start()
    except Exception:
        export_database_to_sharepoint_mirror()

def sync_all_to_sharepoint():
    """Déclenche la mise à jour des miroirs SharePoint de façon synchrone."""
    return export_database_to_sharepoint_mirror()

def restore_database_from_json(json_file_path: Path = None, db_path: Path = None) -> tuple[bool, str]:
    """
    Restaure intégralement la base SQLite depuis un fichier JSON miroir sans perte de données.
    """
    try:
        json_p = json_file_path
        if not json_p:
            # Recherche automatique
            candidates = [
                config.get_storage_path() / "mantis_data.json",
                Path(__file__).parent / "mantis_data.json",
                Path.cwd() / "mantis_data.json"
            ]
            for c in candidates:
                if c.exists():
                    json_p = c
                    break

        if not json_p or not json_p.exists():
            return False, "Fichier de sauvegarde JSON introuvable."

        with open(json_p, "r", encoding="utf-8") as f:
            data = json.load(f)

        tables = data.get("tables", {})
        if not tables:
            return False, "Le fichier JSON ne contient aucune table."

        db_p = db_path or config.get_db_path()
        init_db(db_p)

        conn = sqlite3.connect(str(db_p), timeout=15.0)
        conn.execute("PRAGMA foreign_keys = OFF;")
        cur = conn.cursor()

        insertion_order = [
            "clients", "users", "projects", "categories", "custom_lists",
            "user_client_access", "user_project_access", "email_settings",
            "tickets", "ticket_notes", "ticket_attachments", "ticket_history"
        ]

        for tbl in insertion_order:
            rows = tables.get(tbl, [])
            if not rows:
                continue
            cur.execute(f"DELETE FROM [{tbl}];")
            for row in rows:
                cols = list(row.keys())
                placeholders = ", ".join(["?"] * len(cols))
                col_names = ", ".join([f"[{c}]" for c in cols])
                vals = [row[c] for c in cols]
                cur.execute(f"INSERT OR REPLACE INTO [{tbl}] ({col_names}) VALUES ({placeholders})", vals)

        conn.commit()
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.close()

        # Rafraîchir les miroirs
        export_database_to_sharepoint_mirror(db_p)
        return True, "Restauration terminée avec succès."
    except Exception as e:
        return False, f"Erreur lors de la restauration : {e}"

def ensure_database_ready():
    """
    GARANTIE ANTI-ÉCRASEMENT :
    Vérifie l'état de la base au démarrage.
    1. Si des données existent déjà dans SQLite -> Conserve absolument tout. Ne jamais écraser !
    2. Si SQLite est vide (ex: redémarrage d'un conteneur Streamlit Cloud) :
       Recharge immédiatement les données depuis mantis_data.json.
    3. Si aucun fichier JSON n'existe, initialise uniquement le compte admin de base.
    """
    init_db()
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as count FROM users")
        user_count = cursor.fetchone()["count"]

    storage_p = config.get_storage_path()
    excel_file = storage_p / "Export_MantisV2_Complet.xlsx"
    json_file = storage_p / "mantis_data.json"

    if user_count > 0:
        # Données présentes et actives. Si les miroirs SharePoint manquent, les générer sans toucher à la BDD.
        if not excel_file.exists() or not json_file.exists():
            export_database_to_sharepoint_mirror()
        return True

    # La base est vide -> tenter la restauration depuis le JSON miroir
    success, _ = restore_database_from_json()
    if success:
        return True

    # Si vraiment aucune donnée nulle part, créer uniquement l'admin initial par défaut
    from auth import hash_password
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_db() as conn:
        conn.execute("""
            INSERT OR IGNORE INTO users (id, username, password_hash, full_name, email, role, is_active, created_at)
            VALUES (1, 'admin', ?, 'Administrateur Système', 'admin@cegid.local', 'Administrateur', 1, ?)
        """, (hash_password("admin123"), now_str))

    export_database_to_sharepoint_mirror()
    return True

