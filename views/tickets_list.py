import streamlit as st
import pandas as pd
from database import get_db, STATUS_LIST, get_custom_list_values
from auth import get_current_user, filter_tickets_query_for_user
from utils import get_status_badge, get_priority_badge, get_severity_badge, export_tickets_to_dataframe

def show_tickets_list():
    user = get_current_user()
    st.title("📋 Gestion des Tickets (Vue Mantis)")
    st.caption("Filtrez, recherchez et gérez le cycle de vie de l'ensemble des demandes.")

    # Récupérer les listes configurables
    priority_list = get_custom_list_values("priority")
    severity_list = get_custom_list_values("severity")
    qualif_client_list = get_custom_list_values("qualification_client")
    qualif_cegid_list = get_custom_list_values("qualification_cegid")

    # Récupérer les listes pour les filtres
    with get_db() as conn:
        clients_df = pd.read_sql_query("SELECT id, name FROM clients WHERE is_active = 1 ORDER BY name", conn)
        projects_df = pd.read_sql_query("SELECT id, name, parent_project_id FROM projects WHERE status = 'Actif' ORDER BY name", conn)
        users_df = pd.read_sql_query("SELECT id, full_name FROM users WHERE is_active = 1 ORDER BY full_name", conn)

    # Zone de filtres repliable ou en panneau
    with st.expander("🔍 **Filtres de recherche avancés**", expanded=True):
        f_col1, f_col2, f_col3, f_col4 = st.columns(4)

        with f_col1:
            if user["role"] == "Client":
                client_options = [user["client_name"]]
                selected_client = user["client_name"]
                st.text_input("Client", value=user["client_name"], disabled=True)
            else:
                client_options = ["Tous"] + clients_df["name"].tolist()
                selected_client = st.selectbox("Client", client_options, index=0)

        with f_col2:
            parent_projects = projects_df[projects_df["parent_project_id"].isna()]
            parent_proj_options = ["Tous"] + parent_projects["name"].tolist()
            selected_parent_proj = st.selectbox("Projet Parent", parent_proj_options, index=0)

        with f_col3:
            if selected_parent_proj != "Tous":
                parent_id = parent_projects[parent_projects["name"] == selected_parent_proj]["id"].values[0]
                sub_projects = projects_df[projects_df["parent_project_id"] == parent_id]
                sub_proj_options = ["Tous"] + sub_projects["name"].tolist()
            else:
                sub_projects = projects_df[projects_df["parent_project_id"].notna()]
                sub_proj_options = ["Tous"] + sub_projects["name"].tolist()
            selected_sub_proj = st.selectbox("Sous-projet", sub_proj_options, index=0)

        with f_col4:
            status_options = ["Tous"] + STATUS_LIST
            selected_status = st.selectbox("Statut", status_options, index=0)

        f_col5, f_col6, f_col7, f_col8 = st.columns(4)
        with f_col5:
            priority_options = ["Toutes"] + priority_list
            selected_priority = st.selectbox("Priorité", priority_options, index=0)

        with f_col6:
            severity_options = ["Toutes"] + severity_list
            selected_severity = st.selectbox("Sévérité", severity_options, index=0)

        with f_col7:
            assigned_options = ["Tous", "Non assigné"] + users_df["full_name"].tolist()
            selected_assigned = st.selectbox("Assigné à", assigned_options, index=0)

        with f_col8:
            search_query = st.text_input("Recherche libre", placeholder="ex: TIK-000101, arrondi, API...")

        f_col9, f_col10 = st.columns(2)
        with f_col9:
            qc_options = ["Toutes"] + qualif_client_list
            selected_qc = st.selectbox("Qualification Client", qc_options, index=0)
        with f_col10:
            qcegid_options = ["Toutes"] + qualif_cegid_list
            selected_qcegid = st.selectbox("Qualification Cegid", qcegid_options, index=0)

    # Construction de la requête SQL filtrée
    query = """
        SELECT t.id, t.ticket_number, t.summary, t.status, t.priority, t.severity,
               t.qualification_client, t.qualification_cegid,
               t.category, t.created_at, t.updated_at,
               p.id as project_id, p.name as project_name,
               parent_p.name as parent_project_name,
               c.id as client_id, c.name as client_name,
               u_rep.full_name as reporter_name,
               u_ass.id as assigned_id, u_ass.full_name as assigned_name
        FROM tickets t
        JOIN projects p ON t.project_id = p.id
        LEFT JOIN projects parent_p ON p.parent_project_id = parent_p.id
        LEFT JOIN clients c ON t.client_id = c.id
        JOIN users u_rep ON t.reporter_id = u_rep.id
        LEFT JOIN users u_ass ON t.assigned_id = u_ass.id
        WHERE 1=1
    """
    params = []

    # Application des filtres
    if selected_client != "Tous" and user["role"] != "Client":
        query += " AND c.name = ?"
        params.append(selected_client)

    if selected_parent_proj != "Tous":
        query += " AND (parent_p.name = ? OR (parent_p.name IS NULL AND p.name = ?))"
        params.extend([selected_parent_proj, selected_parent_proj])

    if selected_sub_proj != "Tous":
        query += " AND p.name = ?"
        params.append(selected_sub_proj)

    if selected_status != "Tous":
        query += " AND t.status = ?"
        params.append(selected_status)

    if selected_priority != "Toutes":
        query += " AND t.priority = ?"
        params.append(selected_priority)

    if selected_severity != "Toutes":
        query += " AND t.severity = ?"
        params.append(selected_severity)

    if selected_qc != "Toutes":
        query += " AND t.qualification_client = ?"
        params.append(selected_qc)

    if selected_qcegid != "Toutes":
        query += " AND t.qualification_cegid = ?"
        params.append(selected_qcegid)

    if selected_assigned == "Non assigné":
        query += " AND t.assigned_id IS NULL"
    elif selected_assigned != "Tous":
        query += " AND u_ass.full_name = ?"
        params.append(selected_assigned)

    if search_query.strip():
        q_term = f"%{search_query.strip()}%"
        query += " AND (t.ticket_number LIKE ? OR t.summary LIKE ? OR t.description LIKE ?)"
        params.extend([q_term, q_term, q_term])
        params.append(selected_severity)

    if selected_assigned == "Non assigné":
        query += " AND t.assigned_id IS NULL"
    elif selected_assigned != "Tous":
        query += " AND u_ass.full_name = ?"
        params.append(selected_assigned)

    if search_query.strip():
        q_term = f"%{search_query.strip()}%"
        query += " AND (t.ticket_number LIKE ? OR t.summary LIKE ? OR t.description LIKE ?)"
        params.extend([q_term, q_term, q_term])

    # Filtrage par rôle utilisateur
    query, params = filter_tickets_query_for_user(user, query, params)
    query += " ORDER BY t.id DESC"

    with get_db() as conn:
        df = pd.read_sql_query(query, conn, params=params)

    # Barre de résumé & Actions export
    st.markdown("---")
    r_col1, r_col2, r_col3 = st.columns([2, 1, 1])
    with r_col1:
        st.markdown(f"**{len(df)} ticket(s) trouvé(s)**")

    if not df.empty:
        csv_data, xlsx_data = export_tickets_to_dataframe(df)
        with r_col2:
            st.download_button(
                label="📥 Export CSV",
                data=csv_data,
                file_name="tickets_mantis_export.csv",
                mime="text/csv",
                use_container_width=True
            )
        with r_col3:
            st.download_button(
                label="📊 Export Excel",
                data=xlsx_data,
                file_name="tickets_mantis_export.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )

    if df.empty:
        st.info("Aucun ticket ne correspond aux critères sélectionnés.")
        return

    # Affichage du listing de tickets style Mantis
    for _, row in df.iterrows():
        with st.container(border=True):
            cols = st.columns([1.2, 3.8, 1.8, 1.6, 1.6])
            
            with cols[0]:
                st.markdown(f"### `{row['ticket_number']}`")
                st.caption(f"📅 {row['created_at'][:10]}")

            with cols[1]:
                st.markdown(f"**{row['summary']}**")
                proj_hierarchy = f"{row['parent_project_name']} > {row['project_name']}" if row['parent_project_name'] else row['project_name']
                st.caption(f"🏢 **{row['client_name']}** | 📁 {proj_hierarchy} | 🏷️ {row['category']}")
                st.caption(f"🔍 Qualif. Client : `{row.get('qualification_client') or 'Non qualifié'}` | 🏢 Qualif. Cegid : `{row.get('qualification_cegid') or 'Non qualifié'}`")

            with cols[2]:
                st.markdown(get_status_badge(row['status']), unsafe_allow_html=True)
                st.caption(f"👤 Assigné : {row['assigned_name'] or '*(Non assigné)*'}")
                st.caption(f"✍️ Rapporteur : {row['reporter_name']}")

            with cols[3]:
                st.markdown(f"**Sévérité :** {get_severity_badge(row['severity'])}", unsafe_allow_html=True)
                st.markdown(f"**Priorité :** {get_priority_badge(row['priority'])}", unsafe_allow_html=True)

            with cols[4]:
                st.write("")
                if st.button("✏️ Ouvrir / Modifier ➔", key=f"btn_open_{row['id']}", use_container_width=True):
                    st.session_state["selected_ticket_id"] = row["id"]
                    st.session_state["current_page"] = "ticket_detail"
                    st.rerun()
