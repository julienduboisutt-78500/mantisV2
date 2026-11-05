import streamlit as st
import pandas as pd
from database import get_db, STATUS_COLORS
from auth import get_current_user, filter_tickets_query_for_user
from utils import get_status_badge, get_priority_badge, get_severity_badge

def show_dashboard():
    user = get_current_user()
    st.title("📊 Tableau de Bord")
    st.caption(f"Connecté en tant que **{user['full_name']}** ({user['role']})")

    # Charger les statistiques des tickets autorisés pour l'utilisateur
    with get_db() as conn:
        base_query = """
            SELECT t.id, t.ticket_number, t.summary, t.status, t.priority, t.severity,
                   t.created_at, t.updated_at,
                   p.name as project_name,
                   parent_p.name as parent_project_name,
                   c.name as client_name,
                   u_rep.full_name as reporter_name,
                   u_ass.full_name as assigned_name
            FROM tickets t
            JOIN projects p ON t.project_id = p.id
            LEFT JOIN projects parent_p ON p.parent_project_id = parent_p.id
            JOIN clients c ON t.client_id = c.id
            JOIN users u_rep ON t.reporter_id = u_rep.id
            LEFT JOIN users u_ass ON t.assigned_id = u_ass.id
        """
        query, params = filter_tickets_query_for_user(user, base_query, [])
        query += " ORDER BY t.updated_at DESC"
        
        df = pd.read_sql_query(query, conn, params=params)

    total_tickets = len(df)
    new_tickets = len(df[df["status"] == "Nouveau"])
    in_progress = len(df[df["status"].isin(["Reçu", "Assigné", "En cours", "En attente retour"])])
    resolved_closed = len(df[df["status"].isin(["Résolu", "Fermé"])])
    blockers = len(df[(df["severity"] == "Bloquante") & (~df["status"].isin(["Résolu", "Fermé"]))])

    # Affichage des KPIs
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.metric("Total Tickets", total_tickets)
    with col2:
        st.metric("Nouveaux", new_tickets, delta=f"{new_tickets} à qualifier" if new_tickets else None, delta_color="inverse")
    with col3:
        st.metric("En cours", in_progress)
    with col4:
        st.metric("Résolus / Fermés", resolved_closed)
    with col5:
        st.metric("Bloquants actifs", blockers, delta="Urgent" if blockers > 0 else "Aucun", delta_color="inverse")

    st.markdown("---")

    # Actions rapides
    c_btn1, c_btn2, c_btn3 = st.columns([1, 1, 2])
    with c_btn1:
        if st.button("➕ Nouveau Ticket", use_container_width=True, type="primary"):
            st.session_state["current_page"] = "ticket_create"
            st.rerun()
    with c_btn2:
        if st.button("📋 Tous les tickets", use_container_width=True):
            st.session_state["current_page"] = "tickets_list"
            st.rerun()

    st.markdown("### 🔥 Tickets Récents & Prioritaires")
    if df.empty:
        st.info("Aucun ticket disponible pour votre profil.")
        return

    # Tableau synthétique des tickets récents
    recent_df = df.head(10).copy()
    
    # Construction de l'affichage HTML / Streamlit
    for _, row in recent_df.iterrows():
        with st.container(border=True):
            cols = st.columns([1.5, 3.5, 2, 1.5, 1.5])
            with cols[0]:
                st.markdown(f"**{row['ticket_number']}**")
                st.caption(f"{row['created_at'][:10]}")
            with cols[1]:
                st.markdown(f"**{row['summary']}**")
                proj_label = f"{row['parent_project_name']} > {row['project_name']}" if row['parent_project_name'] else row['project_name']
                st.caption(f"🏢 {row['client_name']} | 📁 {proj_label}")
            with cols[2]:
                st.markdown(get_status_badge(row['status']), unsafe_allow_html=True)
                st.caption(f"👤 {row['assigned_name'] or 'Non assigné'}")
            with cols[3]:
                st.markdown(get_severity_badge(row['severity']), unsafe_allow_html=True)
                st.markdown(get_priority_badge(row['priority']), unsafe_allow_html=True)
            with cols[4]:
                if st.button("Ouvrir ➔", key=f"dash_open_{row['id']}", use_container_width=True):
                    st.session_state["selected_ticket_id"] = row["id"]
                    st.session_state["current_page"] = "ticket_detail"
                    st.rerun()
