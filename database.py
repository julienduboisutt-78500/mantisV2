import sqlite3
import datetime
from pathlib import Path
from contextlib import contextmanager
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

def init_db():
    """Initialise les tables de la base de données et applique les migrations."""
    with get_db() as conn:
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
