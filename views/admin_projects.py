import streamlit as st
import pandas as pd
import datetime
import shutil
from pathlib import Path
import config
from database import get_db, LIST_TYPE_LABELS
from auth import get_current_user, can_manage_all, can_manage_projects

def show_admin_projects():
    user = get_current_user()
    if not can_manage_projects(user):
        st.error("Accès réservé aux Administrateurs et Gestionnaires.")
        return

    is_admin = can_manage_all(user)

    st.title("🏢 Administration des Clients, Projets & Catégories")
    st.caption("Gérez la hiérarchie des clients, des projets parents, des sous-projets et leurs catégories.")

    tab_clients, tab_projects, tab_categories, tab_custom_lists = st.tabs([
        "👥 Clients & Organisations",
        "📁 Projets & Sous-projets",
        "🏷️ Catégories par Projet",
        "🎛️ Listes des Champs"
    ])

    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # ==========================================
    # --- TAB 1 : CLIENTS & ORGANISATIONS ---
    # ==========================================
    with tab_clients:
        st.subheader("Clients enregistrés")
        with get_db() as conn:
            clients_df = pd.read_sql_query("""
                SELECT c.id, c.name, c.code, c.contact_email, c.contact_phone, c.is_active, c.created_at,
                       (SELECT COUNT(*) FROM projects WHERE client_id = c.id) as project_count,
                       (SELECT COUNT(*) FROM tickets WHERE client_id = c.id) as ticket_count
                FROM clients c
                ORDER BY c.name
            """, conn)

        st.dataframe(clients_df, use_container_width=True, hide_index=True)

        col_c_create, col_c_edit = st.columns(2)

        # 1. Création Client
        with col_c_create:
            with st.container(border=True):
                st.markdown("#### ➕ Créer un nouveau Client")
                with st.form("new_client_form"):
                    c_name = st.text_input("Nom du Client / Organisation *")
                    c_code = st.text_input("Code court (ex: ACME, OMNI)")
                    c_email = st.text_input("Email de contact")
                    c_phone = st.text_input("Téléphone de contact")
                    sub_c = st.form_submit_button("Ajouter le Client", type="primary", use_container_width=True)

                    if sub_c:
                        if not c_name.strip():
                            st.error("Le nom du client est requis.")
                        else:
                            try:
                                with get_db() as conn:
                                    conn.execute("""
                                        INSERT INTO clients (name, code, contact_email, contact_phone, created_at)
                                        VALUES (?, ?, ?, ?, ?)
                                    """, (c_name.strip(), c_code.strip().upper(), c_email.strip(), c_phone.strip(), now_str))
                                st.success(f"Client '{c_name}' ajouté avec succès !")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Erreur : {e}")

        # 2. Modification & Suppression Client (réservé à l'Admin)
        with col_c_edit:
            with st.container(border=True):
                st.markdown("#### ✏️ Modifier ou Supprimer un Client")
                if clients_df.empty:
                    st.info("Aucun client existant.")
                else:
                    client_choices = [f"{r['name']} (ID: {r['id']})" for _, r in clients_df.iterrows()]
                    selected_c_choice = st.selectbox("Sélectionner un Client :", client_choices)
                    selected_c_id = int(selected_c_choice.split("ID: ")[1].replace(")", ""))
                    client_row = clients_df[clients_df["id"] == selected_c_id].iloc[0]

                    with st.form("edit_client_form"):
                        e_c_name = st.text_input("Nom du client", value=client_row["name"])
                        e_c_code = st.text_input("Code court", value=client_row["code"] or "")
                        e_c_email = st.text_input("Email", value=client_row["contact_email"] or "")
                        e_c_phone = st.text_input("Téléphone", value=client_row["contact_phone"] or "")
                        e_c_active = st.checkbox("Client actif", value=bool(client_row["is_active"]))

                        sub_edit_c = st.form_submit_button("💾 Enregistrer les modifications", use_container_width=True)

                        if sub_edit_c:
                            if not e_c_name.strip():
                                st.error("Le nom ne peut pas être vide.")
                            else:
                                try:
                                    with get_db() as conn:
                                        conn.execute("""
                                            UPDATE clients
                                            SET name = ?, code = ?, contact_email = ?, contact_phone = ?, is_active = ?
                                            WHERE id = ?
                                        """, (e_c_name.strip(), e_c_code.strip().upper(), e_c_email.strip(), e_c_phone.strip(), 1 if e_c_active else 0, selected_c_id))
                                    st.success(f"Client '{e_c_name}' mis à jour avec succès !")
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Erreur de modification : {e}")

                    # Suppression Client (réservée Admin)
                    if is_admin:
                        st.markdown("---")
                        st.markdown("##### 🗑️ Suppression du Client")
                        st.caption(f"Impact : {client_row['project_count']} projet(s) et {client_row['ticket_count']} ticket(s) rattaché(s).")
                        confirm_del_c = st.checkbox(f"Confirmer la suppression définitive du client '{client_row['name']}'", key=f"del_c_check_{selected_c_id}")
                        if st.button("🗑️ Supprimer définitivement ce Client", key=f"btn_del_c_{selected_c_id}", type="primary", disabled=not confirm_del_c):
                            try:
                                with get_db() as conn:
                                    # Mettre à null les liens dans projets et tickets ou supprimer
                                    conn.execute("UPDATE projects SET client_id = NULL WHERE client_id = ?", (selected_c_id,))
                                    conn.execute("UPDATE tickets SET client_id = NULL WHERE client_id = ?", (selected_c_id,))
                                    conn.execute("UPDATE users SET client_id = NULL WHERE client_id = ?", (selected_c_id,))
                                    conn.execute("DELETE FROM clients WHERE id = ?", (selected_c_id,))
                                st.success(f"Client '{client_row['name']}' supprimé avec succès !")
                                st.rerun()
                            except Exception as e_del:
                                st.error(f"Erreur de suppression : {e_del}")

    # ==========================================
    # --- TAB 2 : PROJETS & SOUS-PROJETS ---
    # ==========================================
    with tab_projects:
        st.subheader("Arborescence des Projets et Sous-projets")
        with get_db() as conn:
            proj_df = pd.read_sql_query("""
                SELECT p.id, p.name, p.code, p.description, p.status, p.parent_project_id, p.client_id,
                       c.name as client_name,
                       parent.name as parent_project_name,
                       (SELECT COUNT(*) FROM tickets WHERE project_id = p.id) as ticket_count,
                       (SELECT COUNT(*) FROM projects WHERE parent_project_id = p.id) as subproject_count
                FROM projects p
                LEFT JOIN clients c ON p.client_id = c.id
                LEFT JOIN projects parent ON p.parent_project_id = parent.id
                ORDER BY COALESCE(parent.name, p.name), p.parent_project_id IS NOT NULL, p.name
            """, conn)

            all_clients_p = pd.read_sql_query("SELECT id, name FROM clients WHERE is_active = 1 ORDER BY name", conn)
            parent_candidates = pd.read_sql_query("SELECT id, name FROM projects WHERE parent_project_id IS NULL ORDER BY name", conn)

        st.dataframe(proj_df[[
            "id", "name", "code", "parent_project_name", "client_name", "status", "ticket_count", "subproject_count"
        ]], use_container_width=True, hide_index=True)

        col_p_create, col_p_edit = st.columns(2)

        # 1. Création Projet ou Sous-projet
        with col_p_create:
            with st.container(border=True):
                st.markdown("#### ➕ Créer un Projet ou Sous-projet")
                with st.form("new_proj_form"):
                    p_name = st.text_input("Nom du Projet ou Sous-projet *")
                    p_code = st.text_input("Code court unique (ex: ERP-FIN) *")

                    parent_opts = ["(Aucun - Projet Principal / Parent)"] + parent_candidates["name"].tolist()
                    sel_parent = st.selectbox("Projet Parent (Optionnel pour sous-projet)", parent_opts)

                    client_opts = ["(Aucun client assigné)"] + all_clients_p["name"].tolist()
                    sel_client = st.selectbox("Client rattaché", client_opts)

                    p_status = st.selectbox("Statut", ["Actif", "En pause", "Archivé"], index=0)
                    p_desc = st.text_area("Description du projet / périmètre")

                    sub_p = st.form_submit_button("Créer le Projet", type="primary", use_container_width=True)

                    if sub_p:
                        if not p_name.strip() or not p_code.strip():
                            st.error("Le nom et le code court sont obligatoires.")
                        else:
                            parent_id = None
                            if sel_parent != "(Aucun - Projet Principal / Parent)":
                                parent_id = int(parent_candidates[parent_candidates["name"] == sel_parent]["id"].values[0])

                            client_id = None
                            if sel_client != "(Aucun client assigné)":
                                client_id = int(all_clients_p[all_clients_p["name"] == sel_client]["id"].values[0])

                            try:
                                with get_db() as conn:
                                    conn.execute("""
                                        INSERT INTO projects (name, code, description, client_id, parent_project_id, status, created_at)
                                        VALUES (?, ?, ?, ?, ?, ?, ?)
                                    """, (p_name.strip(), p_code.strip().upper(), p_desc.strip(), client_id, parent_id, p_status, now_str))
                                st.success(f"Projet '{p_name}' créé avec succès !")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Erreur d'enregistrement : {e}")

        # 2. Modification & Suppression Projet / Sous-projet
        with col_p_edit:
            with st.container(border=True):
                st.markdown("#### ✏️ Modifier ou Supprimer un Projet / Sous-projet")
                if proj_df.empty:
                    st.info("Aucun projet existant.")
                else:
                    proj_choices = []
                    for _, r in proj_df.iterrows():
                        kind = f"Sous-projet de {r['parent_project_name']}" if pd.notna(r["parent_project_id"]) else "Projet Parent"
                        proj_choices.append(f"{r['name']} [{r['code']}] - ({kind}, ID: {r['id']})")

                    sel_p_choice = st.selectbox("Sélectionner le projet à modifier :", proj_choices)
                    selected_p_id = int(sel_p_choice.split("ID: ")[1].replace(")", ""))
                    p_row = proj_df[proj_df["id"] == selected_p_id].iloc[0]

                    with st.form("edit_proj_form"):
                        e_p_name = st.text_input("Nom", value=p_row["name"])
                        e_p_code = st.text_input("Code court", value=p_row["code"])

                        # Parents éligibles (exclure le projet lui-même pour éviter cycle)
                        valid_parents = parent_candidates[parent_candidates["id"] != selected_p_id]
                        e_parent_opts = ["(Aucun - Projet Principal / Parent)"] + valid_parents["name"].tolist()
                        cur_parent_idx = 0
                        if pd.notna(p_row["parent_project_id"]):
                            for idx, pname in enumerate(valid_parents["name"].tolist()):
                                if valid_parents.iloc[idx]["id"] == p_row["parent_project_id"]:
                                    cur_parent_idx = idx + 1
                                    break
                        e_sel_parent = st.selectbox("Projet Parent", e_parent_opts, index=cur_parent_idx)

                        # Client rattaché
                        e_client_opts = ["(Aucun client assigné)"] + all_clients_p["name"].tolist()
                        cur_client_idx = 0
                        if pd.notna(p_row["client_id"]):
                            for idx, cname in enumerate(all_clients_p["name"].tolist()):
                                if all_clients_p.iloc[idx]["id"] == p_row["client_id"]:
                                    cur_client_idx = idx + 1
                                    break
                        e_sel_client = st.selectbox("Client rattaché", e_client_opts, index=cur_client_idx)

                        statuses = ["Actif", "En pause", "Archivé"]
                        cur_st_idx = statuses.index(p_row["status"]) if p_row["status"] in statuses else 0
                        e_status = st.selectbox("Statut", statuses, index=cur_st_idx)
                        e_desc = st.text_area("Description", value=p_row["description"] or "")

                        sub_edit_p = st.form_submit_button("💾 Enregistrer les modifications", use_container_width=True)

                        if sub_edit_p:
                            if not e_p_name.strip() or not e_p_code.strip():
                                st.error("Le nom et le code court sont obligatoires.")
                            else:
                                new_parent_id = None
                                if e_sel_parent != "(Aucun - Projet Principal / Parent)":
                                    new_parent_id = int(valid_parents[valid_parents["name"] == e_sel_parent]["id"].values[0])

                                new_client_id = None
                                if e_sel_client != "(Aucun client assigné)":
                                    new_client_id = int(all_clients_p[all_clients_p["name"] == e_sel_client]["id"].values[0])

                                try:
                                    with get_db() as conn:
                                        conn.execute("""
                                            UPDATE projects
                                            SET name = ?, code = ?, description = ?, client_id = ?, parent_project_id = ?, status = ?
                                            WHERE id = ?
                                        """, (e_p_name.strip(), e_p_code.strip().upper(), e_desc.strip(), new_client_id, new_parent_id, e_status, selected_p_id))
                                    st.success(f"Projet '{e_p_name}' mis à jour avec succès !")
                                    st.rerun()
                                except Exception as e_up:
                                    st.error(f"Erreur : {e_up}")

                    # Suppression Projet / Sous-projet (réservé Admin)
                    if is_admin:
                        st.markdown("---")
                        st.markdown("##### 🗑️ Suppression du Projet")
                        ticket_cnt = int(p_row['ticket_count'])
                        subproj_cnt = int(p_row['subproject_count'])

                        if ticket_cnt > 0:
                            st.warning(f"⚠️ Ce projet contient **{ticket_cnt} ticket(s)** actif(s) ou archivé(s).")
                            other_projects = proj_df[proj_df["id"] != selected_p_id]
                            
                            del_action = st.radio(
                                "Que souhaitez-vous faire des tickets de ce projet ?",
                                [
                                    "Supprimer définitivement le projet ET tous ses tickets (avec pièces jointes OneDrive)",
                                    "Transférer les tickets vers un autre projet avant la suppression"
                                ],
                                key=f"rad_del_action_{selected_p_id}"
                            )

                            target_proj_id = None
                            if del_action.startswith("Transférer"):
                                if other_projects.empty:
                                    st.error("Aucun autre projet n'est disponible pour recevoir les tickets.")
                                else:
                                    t_choices = [f"{r['name']} [{r['code']}] (ID: {r['id']})" for _, r in other_projects.iterrows()]
                                    sel_target = st.selectbox("Projet de destination pour les tickets :", t_choices, key=f"sel_target_{selected_p_id}")
                                    target_proj_id = int(sel_target.split("ID: ")[1].replace(")", ""))
                        else:
                            del_action = "Supprimer"
                            target_proj_id = None

                        if subproj_cnt > 0:
                            st.info(f"ℹ️ Ce projet a {subproj_cnt} sous-projet(s). Ils seront automatiquement détachés et transformés en projets principaux.")

                        confirm_del_p = st.checkbox(f"Confirmer la suppression irréversible de '{p_row['name']}'", key=f"del_p_check_{selected_p_id}")
                        
                        can_submit_del = confirm_del_p
                        if ticket_cnt > 0 and del_action.startswith("Transférer") and not target_proj_id:
                            can_submit_del = False

                        if st.button("🗑️ Supprimer définitivement ce Projet", key=f"btn_del_p_{selected_p_id}", type="primary", disabled=not can_submit_del):
                            try:
                                with get_db() as conn:
                                    cursor = conn.cursor()

                                    # 1. Gestion des tickets associés
                                    cursor.execute("SELECT id FROM tickets WHERE project_id = ?", (selected_p_id,))
                                    ticket_rows = cursor.fetchall()
                                    t_ids = [r["id"] for r in ticket_rows]

                                    if t_ids:
                                        if del_action.startswith("Transférer") and target_proj_id:
                                            # Transférer vers le projet cible
                                            conn.execute("UPDATE tickets SET project_id = ? WHERE project_id = ?", (target_proj_id, selected_p_id))
                                        else:
                                            # Supprimer les pièces jointes sur OneDrive et en base
                                            attachments_dir = config.get_attachments_dir()
                                            for tid in t_ids:
                                                ticket_att_dir = attachments_dir / f"ticket_{tid}"
                                                if ticket_att_dir.exists() and ticket_att_dir.is_dir():
                                                    shutil.rmtree(ticket_att_dir, ignore_errors=True)

                                            placeholders = ",".join(["?"] * len(t_ids))
                                            conn.execute(f"DELETE FROM ticket_attachments WHERE ticket_id IN ({placeholders})", t_ids)
                                            conn.execute(f"DELETE FROM ticket_notes WHERE ticket_id IN ({placeholders})", t_ids)
                                            conn.execute(f"DELETE FROM ticket_history WHERE ticket_id IN ({placeholders})", t_ids)
                                            conn.execute("DELETE FROM tickets WHERE project_id = ?", (selected_p_id,))

                                    # 2. Supprimer les droits d'accès
                                    conn.execute("DELETE FROM user_project_access WHERE project_id = ?", (selected_p_id,))

                                    # 3. Supprimer les catégories rattachées à ce projet
                                    conn.execute("DELETE FROM categories WHERE project_id = ?", (selected_p_id,))

                                    # 4. Détacher les sous-projets
                                    conn.execute("UPDATE projects SET parent_project_id = NULL WHERE parent_project_id = ?", (selected_p_id,))

                                    # 5. Supprimer le projet lui-même
                                    conn.execute("DELETE FROM projects WHERE id = ?", (selected_p_id,))

                                st.success(f"Projet '{p_row['name']}' supprimé avec succès !")
                                st.rerun()
                            except Exception as e_del_p:
                                st.error(f"Erreur lors de la suppression : {e_del_p}")

    # ==========================================
    # --- TAB 3 : CATÉGORIES PAR PROJET ---
    # ==========================================
    with tab_categories:
        st.subheader("Catégories de tickets (Globales & Personnalisées par Projet)")
        with get_db() as conn:
            cat_df = pd.read_sql_query("""
                SELECT c.id, c.name, c.project_id,
                       COALESCE(p.name, '🌐 Globale (tous les projets)') as project_name,
                       (SELECT COUNT(*) FROM tickets WHERE category = c.name) as ticket_count
                FROM categories c
                LEFT JOIN projects p ON c.project_id = p.id
                ORDER BY c.project_id IS NOT NULL, p.name, c.name
            """, conn)
            
            all_projects_cat = pd.read_sql_query("SELECT id, name FROM projects ORDER BY name", conn)

        st.dataframe(cat_df[["id", "name", "project_name", "ticket_count"]], use_container_width=True, hide_index=True)

        col_cat_c, col_cat_e = st.columns(2)

        # 1. Ajouter une Catégorie
        with col_cat_c:
            with st.container(border=True):
                st.markdown("#### ➕ Ajouter une Catégorie")
                with st.form("new_cat_form"):
                    new_cat_name = st.text_input("Nom de la catégorie *", placeholder="ex: Interface Graphique, API, Sécurité...")
                    cat_scope_opts = ["🌐 Globale (tous les projets)"] + all_projects_cat["name"].tolist()
                    sel_cat_scope = st.selectbox("Périmètre du projet *", cat_scope_opts)
                    sub_new_cat = st.form_submit_button("Ajouter la Catégorie", type="primary", use_container_width=True)

                    if sub_new_cat:
                        if not new_cat_name.strip():
                            st.error("Le nom de la catégorie est obligatoire.")
                        else:
                            cat_proj_id = None
                            if sel_cat_scope != "🌐 Globale (tous les projets)":
                                cat_proj_id = int(all_projects_cat[all_projects_cat["name"] == sel_cat_scope]["id"].values[0])
                            try:
                                with get_db() as conn:
                                    conn.execute("INSERT INTO categories (name, project_id) VALUES (?, ?)", (new_cat_name.strip(), cat_proj_id))
                                st.success(f"Catégorie '{new_cat_name}' ajoutée !")
                                st.rerun()
                            except Exception as e_cat:
                                st.error(f"Erreur : {e_cat}")

        # 2. Modifier & Supprimer une Catégorie
        with col_cat_e:
            with st.container(border=True):
                st.markdown("#### ✏️ Modifier ou Supprimer une Catégorie")
                if cat_df.empty:
                    st.info("Aucune catégorie enregistrée.")
                else:
                    cat_choices = [f"{r['name']} ({r['project_name']}, ID: {r['id']})" for _, r in cat_df.iterrows()]
                    sel_cat_choice = st.selectbox("Sélectionner la catégorie :", cat_choices)
                    selected_cat_id = int(sel_cat_choice.split("ID: ")[1].replace(")", ""))
                    cat_row = cat_df[cat_df["id"] == selected_cat_id].iloc[0]

                    with st.form("edit_cat_form"):
                        e_cat_name = st.text_input("Nom de la catégorie", value=cat_row["name"])
                        e_scope_opts = ["🌐 Globale (tous les projets)"] + all_projects_cat["name"].tolist()
                        cur_scope_idx = 0
                        if pd.notna(cat_row["project_id"]):
                            for idx, p_name in enumerate(all_projects_cat["name"].tolist()):
                                if all_projects_cat.iloc[idx]["id"] == cat_row["project_id"]:
                                    cur_scope_idx = idx + 1
                                    break
                        e_sel_scope = st.selectbox("Projet rattaché", e_scope_opts, index=cur_scope_idx)
                        sub_edit_cat = st.form_submit_button("💾 Enregistrer la Catégorie", use_container_width=True)

                        if sub_edit_cat:
                            if not e_cat_name.strip():
                                st.error("Le nom ne peut pas être vide.")
                            else:
                                new_cat_pid = None
                                if e_sel_scope != "🌐 Globale (tous les projets)":
                                    new_cat_pid = int(all_projects_cat[all_projects_cat["name"] == e_sel_scope]["id"].values[0])
                                try:
                                    with get_db() as conn:
                                        conn.execute("UPDATE categories SET name = ?, project_id = ? WHERE id = ?", (e_cat_name.strip(), new_cat_pid, selected_cat_id))
                                    st.success("Catégorie mise à jour !")
                                    st.rerun()
                                except Exception as e_ucat:
                                    st.error(f"Erreur : {e_ucat}")

                    # Suppression Catégorie
                    st.markdown("---")
                    st.markdown("##### 🗑️ Supprimer cette Catégorie")
                    confirm_del_cat = st.checkbox(f"Confirmer la suppression de '{cat_row['name']}'", key=f"del_cat_check_{selected_cat_id}")
                    if st.button("🗑️ Supprimer définitivement", key=f"btn_del_cat_{selected_cat_id}", type="primary", disabled=not confirm_del_cat):
                        try:
                            with get_db() as conn:
                                conn.execute("DELETE FROM categories WHERE id = ?", (selected_cat_id,))
                            st.success("Catégorie supprimée avec succès !")
                            st.rerun()
                        except Exception as e_dcat:
                            st.error(f"Erreur de suppression : {e_dcat}")

    # ==========================================
    # --- TAB 4 : LISTES DES CHAMPS PERSONNALISABLES ---
    # ==========================================
    with tab_custom_lists:
        st.subheader("Paramétrage des Listes Déroulantes des Tickets")
        st.caption("Ajoutez, modifiez ou supprimez les options disponibles dans les différents menus déroulants des tickets.")

        list_type_keys = list(LIST_TYPE_LABELS.keys())
        list_type_display = [f"{LIST_TYPE_LABELS[k]} ({k})" for k in list_type_keys]
        
        sel_display = st.selectbox("Sélectionner le champ à personnaliser :", list_type_display)
        active_list_type = list_type_keys[list_type_display.index(sel_display)]
        active_label = LIST_TYPE_LABELS[active_list_type]

        with get_db() as conn:
            items_df = pd.read_sql_query("""
                SELECT id, value, sort_order, is_active
                FROM custom_lists
                WHERE list_type = ?
                ORDER BY sort_order ASC, id ASC
            """, conn, params=(active_list_type,))

        st.markdown(f"##### Valeurs actuelles pour : **{active_label}**")
        st.dataframe(items_df, use_container_width=True, hide_index=True)

        col_l_add, col_l_edit = st.columns(2)

        # 1. Ajouter une valeur
        with col_l_add:
            with st.container(border=True):
                st.markdown(f"#### ➕ Ajouter une option à '{active_label}'")
                with st.form(f"add_val_form_{active_list_type}"):
                    new_val_text = st.text_input("Valeur à ajouter *")
                    sub_add_val = st.form_submit_button("Ajouter cette option", type="primary", use_container_width=True)

                    if sub_add_val:
                        if not new_val_text.strip():
                            st.error("La valeur ne peut pas être vide.")
                        else:
                            val_clean = new_val_text.strip()
                            # Vérifier doublon
                            if val_clean.lower() in [v.lower() for v in items_df["value"].tolist()]:
                                st.warning("Cette valeur existe déjà dans cette liste.")
                            else:
                                next_order = len(items_df)
                                with get_db() as conn:
                                    conn.execute("""
                                        INSERT INTO custom_lists (list_type, value, sort_order, is_active)
                                        VALUES (?, ?, ?, 1)
                                    """, (active_list_type, val_clean, next_order))
                                st.success(f"Option '{val_clean}' ajoutée avec succès !")
                                st.rerun()

        # 2. Modifier ou Supprimer une valeur
        with col_l_edit:
            with st.container(border=True):
                st.markdown(f"#### ✏️ Modifier ou Supprimer une option")
                if items_df.empty:
                    st.info("Aucune valeur dans cette liste.")
                else:
                    opt_choices = [f"{r['value']} (ID: {r['id']})" for _, r in items_df.iterrows()]
                    sel_opt = st.selectbox("Option à modifier :", opt_choices)
                    selected_val_id = int(sel_opt.split("ID: ")[1].replace(")", ""))
                    val_row = items_df[items_df["id"] == selected_val_id].iloc[0]

                    with st.form(f"edit_val_form_{selected_val_id}"):
                        e_val_text = st.text_input("Nouvelle valeur", value=val_row["value"])
                        sub_edit_val = st.form_submit_button("💾 Enregistrer la modification", use_container_width=True)

                        if sub_edit_val:
                            if not e_val_text.strip():
                                st.error("La valeur ne peut pas être vide.")
                            else:
                                with get_db() as conn:
                                    conn.execute("UPDATE custom_lists SET value = ? WHERE id = ?", (e_val_text.strip(), selected_val_id))
                                st.success("Option mise à jour !")
                                st.rerun()

                    # Suppression
                    st.markdown("---")
                    confirm_del_val = st.checkbox(f"Confirmer la suppression de '{val_row['value']}'", key=f"del_val_check_{selected_val_id}")
                    if st.button("🗑️ Supprimer définitivement cette option", key=f"btn_del_val_{selected_val_id}", type="primary", disabled=not confirm_del_val, use_container_width=True):
                        with get_db() as conn:
                            conn.execute("DELETE FROM custom_lists WHERE id = ?", (selected_val_id,))
                        st.success("Option supprimée !")
                        st.rerun()
