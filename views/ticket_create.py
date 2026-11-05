import streamlit as st
import pandas as pd
import datetime
from database import (
    get_db, log_ticket_history, get_custom_list_values
)
from auth import get_current_user, can_assign_and_resolve
from utils import generate_next_ticket_number, save_uploaded_file
from notifications import send_ticket_notification

def show_ticket_create():
    user = get_current_user()
    st.title("➕ Créer un Nouveau Ticket")
    st.caption("Remplissez les détails du signalement selon les standards Mantis.")

    # Récupérer les listes dynamiques configurables
    priority_list = get_custom_list_values("priority")
    severity_list = get_custom_list_values("severity")
    reproducibility_list = get_custom_list_values("reproducibility")
    qualif_client_list = get_custom_list_values("qualification_client")
    qualif_cegid_list = get_custom_list_values("qualification_cegid")

    # Récupérer les données de base
    with get_db() as conn:
        clients_df = pd.read_sql_query("SELECT id, name FROM clients WHERE is_active = 1 ORDER BY name", conn)
        projects_df = pd.read_sql_query("SELECT id, name, parent_project_id, client_id FROM projects WHERE status = 'Actif' ORDER BY name", conn)
        users_df = pd.read_sql_query("SELECT id, full_name, role FROM users WHERE is_active = 1 ORDER BY full_name", conn)

    if projects_df.empty:
        st.warning("Aucun projet actif n'a été créé. Veuillez d'abord créer un projet dans 'Projets & Clients'.")
        return

    # Sélection interactive du Client et du Projet pour charger les catégories correspondantes
    c_sel1, c_sel2, c_sel3 = st.columns(3)

    # 1. Client
    with c_sel1:
        if user["role"] == "Client":
            selected_client_id = user["client_id"]
            st.text_input("Client / Organisation", value=user["client_name"], disabled=True)
        else:
            client_names = clients_df["name"].tolist() if not clients_df.empty else ["(Aucun client)"]
            sel_client_name = st.selectbox("Client / Organisation *", client_names, key="create_client_sel")
            if not clients_df.empty and sel_client_name in clients_df["name"].values:
                selected_client_id = int(clients_df[clients_df["name"] == sel_client_name]["id"].values[0])
            else:
                selected_client_id = None

    # 2. Projet Parent
    with c_sel2:
        parent_projects = projects_df[projects_df["parent_project_id"].isna()]
        if parent_projects.empty:
            parent_projects = projects_df
        parent_names = parent_projects["name"].tolist()
        sel_parent_name = st.selectbox("Projet Parent *", parent_names, key="create_parent_proj_sel")
        parent_id = int(parent_projects[parent_projects["name"] == sel_parent_name]["id"].values[0])

    # 3. Sous-projet
    with c_sel3:
        sub_projects = projects_df[projects_df["parent_project_id"] == parent_id]
        if not sub_projects.empty:
            sub_names = ["(Projet Principal)"] + sub_projects["name"].tolist()
            sel_sub_name = st.selectbox("Sous-projet concerné", sub_names, key="create_sub_proj_sel")
            if sel_sub_name != "(Projet Principal)":
                chosen_project_id = int(sub_projects[sub_projects["name"] == sel_sub_name]["id"].values[0])
            else:
                chosen_project_id = parent_id
        else:
            st.text_input("Sous-projet", value="(Aucun sous-projet)", disabled=True)
            chosen_project_id = parent_id

    # Charger les catégories personnalisées pour ce projet + les catégories globales
    with get_db() as conn:
        cat_df = pd.read_sql_query("""
            SELECT name FROM categories
            WHERE project_id IS NULL OR project_id = ?
            ORDER BY project_id IS NOT NULL, name
        """, conn, params=(chosen_project_id,))

    cat_list = cat_df["name"].tolist() if not cat_df.empty else ["Général", "Bug", "Évolution"]

    st.markdown("---")

    # Formulaire de contenu du ticket
    with st.form("create_ticket_details_form"):
        col3, col4, col5 = st.columns(3)
        with col3:
            selected_category = st.selectbox("Catégorie (adaptée au projet) *", cat_list)

        with col4:
            selected_severity = st.selectbox("Sévérité *", severity_list, index=1 if len(severity_list) > 1 else 0)

        with col5:
            selected_priority = st.selectbox("Priorité *", priority_list, index=1 if len(priority_list) > 1 else 0)

        # Qualifications Client & Cegid
        q_col1, q_col2 = st.columns(2)
        with q_col1:
            selected_qualif_client = st.selectbox("🔍 Qualification Client", qualif_client_list, index=0)

        with q_col2:
            selected_qualif_cegid = st.selectbox("🏢 Qualification Cegid", qualif_cegid_list, index=0)

        col6, col7 = st.columns(2)
        with col6:
            selected_repro = st.selectbox("Reproductibilité", reproducibility_list, index=0)

        with col7:
            if can_assign_and_resolve(user):
                assign_opts = ["(Non assigné)"] + users_df["full_name"].tolist()
                sel_assign_name = st.selectbox("Assigner à", assign_opts)
                if sel_assign_name != "(Non assigné)":
                    chosen_assigned_id = int(users_df[users_df["full_name"] == sel_assign_name]["id"].values[0])
                else:
                    chosen_assigned_id = None
            else:
                chosen_assigned_id = None
                st.text_input("Assignation", value="Automatique selon règles projet", disabled=True)

        st.markdown("---")
        summary = st.text_input("Résumé / Titre du ticket *", placeholder="Ex: Erreur lors du calcul de TVA sur facture avoir...")
        description = st.text_area("Description détaillée du problème ou besoin *", height=120, placeholder="Détaillez le comportement observé par rapport au comportement attendu...")
        steps = st.text_area("Étapes pour reproduire (recommandé pour les bugs)", height=80, placeholder="1. Ouvrir le module...\n2. Saisir les données...\n3. Constater l'erreur...")
        additional_info = st.text_area("Informations complémentaires", height=60, placeholder="Environnement de test, navigateur, version...")

        uploaded_files = st.file_uploader("📎 Pièces jointes", accept_multiple_files=True)

        submitted = st.form_submit_button("🚀 Créer le ticket", type="primary", use_container_width=True)

        if submitted:
            if not summary.strip():
                st.error("Le résumé (titre) est obligatoire.")
                return
            if not description.strip():
                st.error("La description détaillée est obligatoire.")
                return

            ticket_num = generate_next_ticket_number()
            now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            with get_db() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO tickets (
                        ticket_number, project_id, client_id, category, reporter_id, assigned_id,
                        status, resolution, priority, severity, reproducibility,
                        qualification_client, qualification_cegid,
                        summary, description, steps_to_reproduce, additional_info,
                        estimated_hours, spent_hours, created_at, updated_at, closed_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    ticket_num, chosen_project_id, selected_client_id, selected_category,
                    user["id"], chosen_assigned_id, "Nouveau", "Non résolu",
                    selected_priority, selected_severity, selected_repro,
                    selected_qualif_client, selected_qualif_cegid,
                    summary.strip(), description.strip(), steps.strip(), additional_info.strip(),
                    0.0, 0.0, now_str, now_str, None
                ))
                new_ticket_id = cursor.lastrowid

                # Historique de création
                log_ticket_history(conn, new_ticket_id, user["id"], "Création", "", "Nouveau")

            # Sauvegarde des pièces jointes
            if uploaded_files:
                for f in uploaded_files:
                    save_uploaded_file(f, new_ticket_id, user["id"])

            # Notification e-mail aux utilisateurs rattachés au client
            send_ticket_notification(
                new_ticket_id,
                action_type="creation",
                author_name=user["full_name"],
                details=f"Priorité : {selected_priority} | Catégorie : {selected_category}"
            )

            st.success(f"Ticket {ticket_num} créé avec succès !")
            st.session_state["selected_ticket_id"] = new_ticket_id
            st.session_state["current_page"] = "ticket_detail"
            st.rerun()
