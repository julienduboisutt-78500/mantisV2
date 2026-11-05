import streamlit as st
import pandas as pd
import datetime
from database import get_db, ROLES_LIST, get_user_client_ids, set_user_client_ids
from auth import get_current_user, can_manage_all, hash_password

def show_admin_users():
    user = get_current_user()
    if not can_manage_all(user):
        st.error("Accès réservé aux Administrateurs.")
        return

    st.title("👥 Gestion des Utilisateurs & Profils d'Accès")
    st.caption("Gérez les comptes, les niveaux d'accès et l'affectation à 1 ou plusieurs clients.")

    with get_db() as conn:
        users_df = pd.read_sql_query("""
            SELECT u.id, u.username, u.full_name, u.email, u.role,
                   u.is_active, u.created_at,
                   (
                       SELECT GROUP_CONCAT(c.name, ', ')
                       FROM user_client_access uca
                       JOIN clients c ON uca.client_id = c.id
                       WHERE uca.user_id = u.id
                   ) as associated_clients
            FROM users u
            ORDER BY u.role, u.full_name
        """, conn)

        clients_df = pd.read_sql_query("SELECT id, name FROM clients WHERE is_active = 1 ORDER BY name", conn)

    # Affichage du listing des utilisateurs
    users_display_df = users_df.copy()
    users_display_df["associated_clients"] = users_display_df["associated_clients"].fillna("(Tous / Transverse)")
    st.dataframe(users_display_df, use_container_width=True, hide_index=True)

    tab_new, tab_edit = st.tabs(["➕ Créer un Utilisateur", "🔑 Modifier / Réinitialiser un Compte"])

    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # --- TAB 1 : NOUVEAU COMPTE ---
    with tab_new:
        with st.form("create_user_form"):
            u_c1, u_c2 = st.columns(2)
            with u_c1:
                new_username = st.text_input("Identifiant de connexion (Username) *")
                new_fullname = st.text_input("Nom complet de l'utilisateur *")
                new_email = st.text_input("Adresse Email *")
            with u_c2:
                new_pwd = st.text_input("Mot de passe temporaire *", type="password")
                new_role = st.selectbox("Rôle / Profil Mantis *", ROLES_LIST, index=3)
                
                # Affectation à 1 ou plusieurs clients
                all_client_names = clients_df["name"].tolist()
                sel_clients = st.multiselect(
                    "Clients associés (1 ou X clients)",
                    all_client_names,
                    help="Permet de restreindre ou d'associer un Gestionnaire, Développeur, Rapporteur ou Client à un ou plusieurs clients spécifiques. Laisser vide pour un profil transverse."
                )

            sub_u = st.form_submit_button("Créer le compte", type="primary")

            if sub_u:
                if not new_username.strip() or not new_fullname.strip() or not new_pwd.strip():
                    st.error("L'identifiant, le nom complet et le mot de passe sont obligatoires.")
                elif new_role == "Client" and not sel_clients:
                    st.error("Un utilisateur avec le profil 'Client' doit obligatoirement être rattaché à au moins une entreprise cliente.")
                else:
                    client_ids = [int(clients_df[clients_df["name"] == cname]["id"].values[0]) for cname in sel_clients]
                    main_cid = client_ids[0] if client_ids else None
                    pwd_hash = hash_password(new_pwd.strip())

                    try:
                        with get_db() as conn:
                            cursor = conn.cursor()
                            cursor.execute("""
                                INSERT INTO users (username, password_hash, full_name, email, role, client_id, is_active, created_at)
                                VALUES (?, ?, ?, ?, ?, ?, 1, ?)
                            """, (new_username.strip(), pwd_hash, new_fullname.strip(), new_email.strip(), new_role, main_cid, now_str))
                            new_uid = cursor.lastrowid

                        # Enregistrer les liaisons multi-clients
                        set_user_client_ids(new_uid, client_ids)

                        st.success(f"Utilisateur '{new_username}' créé avec succès !")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erreur lors de la création : {e}")

    # --- TAB 2 : MODIFIER / REINITIALISER ---
    with tab_edit:
        st.subheader("Modifier un compte existant")
        user_list = [f"{u['username']} ({u['full_name']} - {u['role']})" for _, u in users_df.iterrows()]
        sel_u_label = st.selectbox("Sélectionner l'utilisateur à modifier", user_list)
        sel_username = sel_u_label.split(" (")[0]
        selected_row = users_df[users_df["username"] == sel_username].iloc[0]
        selected_uid = int(selected_row["id"])

        # Récupérer les clients actuellement associés
        current_client_ids = get_user_client_ids(selected_uid)
        current_client_names = [clients_df[clients_df["id"] == cid]["name"].values[0] for cid in current_client_ids if cid in clients_df["id"].values]

        with st.form("edit_user_form"):
            e_c1, e_c2 = st.columns(2)
            with e_c1:
                e_fullname = st.text_input("Nom complet", value=selected_row["full_name"])
                e_email = st.text_input("Email", value=selected_row["email"])
                e_is_active = st.checkbox("Compte actif", value=bool(selected_row["is_active"]))
            with e_c2:
                cur_role_idx = ROLES_LIST.index(selected_row["role"]) if selected_row["role"] in ROLES_LIST else 0
                e_role = st.selectbox("Rôle", ROLES_LIST, index=cur_role_idx)
                
                # Modification multi-clients
                all_client_names = clients_df["name"].tolist()
                e_sel_clients = st.multiselect(
                    "Clients associés (1 ou X clients)",
                    all_client_names,
                    default=current_client_names,
                    help="Associez cet utilisateur à un ou plusieurs clients."
                )

                new_pwd_reset = st.text_input("Nouveau mot de passe (laisser vide pour ne pas changer)", type="password")

            sub_e = st.form_submit_button("Enregistrer les modifications")

            if sub_e:
                if e_role == "Client" and not e_sel_clients:
                    st.error("Un utilisateur avec le profil 'Client' doit obligatoirement être rattaché à au moins un client.")
                else:
                    new_client_ids = [int(clients_df[clients_df["name"] == cname]["id"].values[0]) for cname in e_sel_clients]
                    main_cid = new_client_ids[0] if new_client_ids else None
                    try:
                        with get_db() as conn:
                            if new_pwd_reset.strip():
                                new_h = hash_password(new_pwd_reset.strip())
                                conn.execute("""
                                    UPDATE users
                                    SET full_name = ?, email = ?, role = ?, client_id = ?, is_active = ?, password_hash = ?
                                    WHERE id = ?
                                """, (e_fullname.strip(), e_email.strip(), e_role, main_cid, 1 if e_is_active else 0, new_h, selected_uid))
                            else:
                                conn.execute("""
                                    UPDATE users
                                    SET full_name = ?, email = ?, role = ?, client_id = ?, is_active = ?
                                    WHERE id = ?
                                """, (e_fullname.strip(), e_email.strip(), e_role, main_cid, 1 if e_is_active else 0, selected_uid))

                        # Mettre à jour liaisons multi-clients
                        set_user_client_ids(selected_uid, new_client_ids)

                        st.success("Compte mis à jour avec succès !")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erreur : {e}")

        # Section SUPPRESSION DE L'UTILISATEUR (réservée Administrateur)
        st.markdown("---")
        st.markdown("##### 🗑️ Supprimer définitivement cet Utilisateur")
        
        target_uid = int(selected_row["id"])
        
        if target_uid == user["id"]:
            st.warning("⚠️ Vous ne pouvez pas supprimer votre propre compte actuellement connecté.")
        else:
            with get_db() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) as nb FROM tickets WHERE reporter_id = ?", (target_uid,))
                rep_count = cursor.fetchone()["nb"]
                cursor.execute("SELECT COUNT(*) as nb FROM tickets WHERE assigned_id = ?", (target_uid,))
                ass_count = cursor.fetchone()["nb"]
                cursor.execute("SELECT COUNT(*) as nb FROM ticket_notes WHERE user_id = ?", (target_uid,))
                notes_count = cursor.fetchone()["nb"]

            st.caption(f"Impact : {rep_count} ticket(s) créé(s), {ass_count} ticket(s) assigné(s), {notes_count} note(s) rédigée(s).")
            st.info("ℹ️ Lors de la suppression, les tickets créés et notes seront réaffectés à votre compte administrateur, et les assignations en cours seront libérées.")

            confirm_del_u = st.checkbox(f"Confirmer la suppression irréversible du compte '{selected_row['username']}'", key=f"del_u_check_{target_uid}")
            if st.button("🗑️ Supprimer définitivement cet Utilisateur", key=f"btn_del_u_{target_uid}", type="primary", disabled=not confirm_del_u):
                try:
                    with get_db() as conn:
                        conn.execute("UPDATE tickets SET assigned_id = NULL WHERE assigned_id = ?", (target_uid,))
                        conn.execute("UPDATE tickets SET reporter_id = ? WHERE reporter_id = ?", (user["id"], target_uid))
                        conn.execute("UPDATE ticket_notes SET user_id = ? WHERE user_id = ?", (user["id"], target_uid))
                        conn.execute("UPDATE ticket_history SET user_id = ? WHERE user_id = ?", (user["id"], target_uid))
                        conn.execute("DELETE FROM user_client_access WHERE user_id = ?", (target_uid,))
                        conn.execute("DELETE FROM user_project_access WHERE user_id = ?", (target_uid,))
                        conn.execute("DELETE FROM users WHERE id = ?", (target_uid,))

                    st.success(f"Utilisateur '{selected_row['username']}' supprimé avec succès !")
                    st.rerun()
                except Exception as e_delu:
                    st.error(f"Erreur lors de la suppression de l'utilisateur : {e_delu}")
