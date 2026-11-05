import hashlib
import os
import streamlit as st
from database import get_db

def hash_password(password: str, salt: str = None) -> str:
    """Génère un hash salé sécurisé pour le mot de passe."""
    if not salt:
        salt = os.urandom(16).hex()
    hashed = hashlib.sha256((salt + password).encode('utf-8')).hexdigest()
    return f"{salt}${hashed}"

def verify_password(stored_password_hash: str, password_attempt: str) -> bool:
    """Vérifie un mot de passe par rapport au hash salé stocké."""
    try:
        salt, hashed = stored_password_hash.split("$")
        check = hashlib.sha256((salt + password_attempt).encode('utf-8')).hexdigest()
        return check == hashed
    except Exception:
        return False

def authenticate_user(username: str, password: str):
    """Authentifie un utilisateur et renvoie son dictionnaire d'informations si valide."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT u.id, u.username, u.password_hash, u.full_name, u.email, u.role, u.client_id, u.is_active,
                   c.name as client_name
            FROM users u
            LEFT JOIN clients c ON u.client_id = c.id
            WHERE LOWER(u.username) = LOWER(?)
        """, (username.strip(),))
        row = cursor.fetchone()
        
        if not row:
            return None
        
        if not row["is_active"]:
            return "INACTIVE"
        
        if verify_password(row["password_hash"], password):
            user_data = dict(row)
            del user_data["password_hash"]
            
            # Charger les projets autorisés
            cursor.execute("SELECT project_id FROM user_project_access WHERE user_id = ?", (user_data["id"],))
            user_data["allowed_project_ids"] = [r["project_id"] for r in cursor.fetchall()]

            # Charger les clients associés (multi-clients)
            cursor.execute("SELECT client_id FROM user_client_access WHERE user_id = ?", (user_data["id"],))
            c_rows = [r["client_id"] for r in cursor.fetchall()]
            if not c_rows and user_data.get("client_id"):
                c_rows = [user_data["client_id"]]
            user_data["allowed_client_ids"] = c_rows

            return user_data
        
    return None

def get_current_user():
    return st.session_state.get("user")

def is_logged_in() -> bool:
    return "user" in st.session_state and st.session_state["user"] is not None

def logout():
    st.session_state["user"] = None
    st.session_state["current_page"] = "dashboard"
    st.rerun()

def can_manage_all(user) -> bool:
    return user and user.get("role") in ["Administrateur"]

def can_manage_projects(user) -> bool:
    return user and user.get("role") in ["Administrateur", "Gestionnaire"]

def can_assign_and_resolve(user) -> bool:
    return user and user.get("role") in ["Administrateur", "Gestionnaire", "Développeur"]

def can_see_private_notes(user) -> bool:
    return user and user.get("role") in ["Administrateur", "Gestionnaire", "Développeur"]

def can_delete_ticket(user) -> bool:
    return user and user.get("role") == "Administrateur"

def can_edit_ticket(user, ticket=None) -> bool:
    """Détermine si l'utilisateur a le droit de modifier les informations d'un ticket."""
    if not user:
        return False
    role = user.get("role")
    if role in ["Administrateur", "Gestionnaire", "Développeur", "Rapporteur"]:
        return True
    if role == "Client":
        if ticket is None:
            return True
        allowed_cids = user.get("allowed_client_ids", [])
        if not allowed_cids and user.get("client_id"):
            allowed_cids = [user.get("client_id")]
        ticket_cid = ticket["client_id"] if isinstance(ticket, dict) else getattr(ticket, "client_id", None)
        if not allowed_cids or ticket_cid in allowed_cids or ticket_cid is None:
            return True
    return False

def filter_tickets_query_for_user(user, base_query: str, params: list = None) -> tuple[str, list]:
    """Adapte une requête SQL selon les restrictions de rôle et de clients associés de l'utilisateur."""
    if params is None:
        params = []
    
    if not user:
        return "SELECT * FROM tickets WHERE 1=0", []
    
    role = user.get("role")
    client_ids = user.get("allowed_client_ids", [])
    
    # 1. Administrateur : accès absolu
    if role == "Administrateur":
        return base_query, params

    # 2. Rôle Client : strictement restreint à ses clients associés
    if role == "Client":
        if not client_ids:
            return "SELECT * FROM tickets WHERE 1=0", []
        placeholders = ",".join(["?"] * len(client_ids))
        clause = f"t.client_id IN ({placeholders})"
        if "WHERE" in base_query.upper():
            query = base_query + f" AND {clause}"
        else:
            query = base_query + f" WHERE {clause}"
        params.extend(client_ids)
        return query, params

    # 3. Gestionnaire, Développeur, Rapporteur :
    # Si des clients spécifiques leur sont affectés, restreindre aux tickets de ces clients
    if client_ids:
        placeholders = ",".join(["?"] * len(client_ids))
        clause = f"(t.client_id IN ({placeholders}) OR t.reporter_id = ? OR t.assigned_id = ?)"
        if "WHERE" in base_query.upper():
            query = base_query + f" AND {clause}"
        else:
            query = base_query + f" WHERE {clause}"
        params.extend(client_ids)
        params.append(user["id"])
        params.append(user["id"])
        return query, params

    # Sinon (aucun client spécifique affecté) : accès transverse
    return base_query, params
