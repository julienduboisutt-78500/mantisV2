import streamlit as st
from pathlib import Path
import config
from database import init_db
from seed_data import seed_initial_data
from auth import (
    authenticate_user, is_logged_in, get_current_user, logout,
    can_manage_all, can_manage_projects
)
from views.dashboard import show_dashboard
from views.tickets_list import show_tickets_list
from views.ticket_detail import show_ticket_detail
from views.ticket_create import show_ticket_create
from views.ticket_import import show_ticket_import
from views.reporting import show_reporting
from views.admin_projects import show_admin_projects
from views.admin_users import show_admin_users
from views.settings import show_settings

# Configuration globale Streamlit
st.set_page_config(
    page_title="Mantis V2 - Outils PS",
    page_icon="🎫",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Initialisation sécurisée de la BDD (garantie anti-écrasement SharePoint)
from database import ensure_database_ready

if "db_initialized" not in st.session_state:
    ensure_database_ready()
    st.session_state["db_initialized"] = True

# Gestion de la page active dans la session
if "current_page" not in st.session_state:
    st.session_state["current_page"] = "dashboard"

def show_login_page():
    st.markdown("<br><br>", unsafe_allow_html=True)
    c_left, c_mid, c_right = st.columns([1, 1.8, 1])
    with c_mid:
        with st.container(border=True):
            st.markdown("## 🎫 **Mantis V2**")
            st.markdown("#### *Système de suivi d'incidents & demandes*")
            st.markdown("---")

            with st.form("login_form"):
                username = st.text_input("Identifiant :", placeholder="ex: identifiant utilisateur")
                password = st.text_input("Mot de passe :", type="password")
                submit_login = st.form_submit_button("Se connecter ➔", type="primary", use_container_width=True)

                if submit_login:
                    if not username.strip() or not password.strip():
                        st.warning("Veuillez saisir votre identifiant et votre mot de passe.")
                    else:
                        auth_res = authenticate_user(username.strip(), password.strip())
                        if auth_res == "INACTIVE":
                            st.error("Ce compte est désactivé. Veuillez contacter un administrateur.")
                        elif auth_res:
                            st.session_state["user"] = auth_res
                            st.session_state["current_page"] = "dashboard"
                            st.success(f"Bienvenue, {auth_res['full_name']} !")
                            st.rerun()
                        else:
                            st.error("Identifiant ou mot de passe incorrect.")

def render_sidebar():
    user = get_current_user()
    with st.sidebar:
        st.markdown("### 🎫 Mantis V2")
        st.caption("Outils Professionnels Services")
        st.markdown("---")

        # Informations utilisateur connecté
        with st.container(border=True):
            st.markdown(f"**👤 {user['full_name']}**")
            st.markdown(f"🏷️ Rôle : `{user['role']}`")
            if user.get("client_name"):
                st.markdown(f"🏢 Client : **{user['client_name']}**")
            
            if st.button("🚪 Déconnexion", use_container_width=True):
                logout()

        st.markdown("---")

        # Menu de navigation
        nav_options = [
            ("📊 Tableau de Bord", "dashboard"),
            ("📋 Liste des Tickets", "tickets_list"),
            ("➕ Créer un Ticket", "ticket_create"),
        ]

        if can_manage_projects(user):
            nav_options.append(("📥 Import en Masse", "ticket_import"))

        nav_options.append(("📈 Rapports & Analyse", "reporting"))

        if can_manage_projects(user):
            nav_options.append(("🏢 Projets & Clients", "admin_projects"))

        if can_manage_all(user):
            nav_options.append(("👥 Utilisateurs & Droits", "admin_users"))
            nav_options.append(("⚙️ Paramètres Système", "settings"))

        st.markdown("**Navigation**")
        for label, page_key in nav_options:
            is_active = (st.session_state["current_page"] == page_key)
            btn_type = "primary" if is_active else "secondary"
            if st.button(label, key=f"nav_{page_key}", use_container_width=True, type=btn_type):
                st.session_state["current_page"] = page_key
                st.rerun()

def main():
    if not is_logged_in():
        show_login_page()
    else:
        render_sidebar()
        page = st.session_state.get("current_page", "dashboard")

        if page == "dashboard":
            show_dashboard()
        elif page == "tickets_list":
            show_tickets_list()
        elif page == "ticket_detail":
            show_ticket_detail()
        elif page == "ticket_create":
            show_ticket_create()
        elif page == "ticket_import":
            show_ticket_import()
        elif page == "reporting":
            show_reporting()
        elif page == "admin_projects":
            show_admin_projects()
        elif page == "admin_users":
            show_admin_users()
        elif page == "settings":
            show_settings()
        else:
            show_dashboard()

if __name__ == "__main__":
    main()
