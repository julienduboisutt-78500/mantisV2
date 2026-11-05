import streamlit as st
import pandas as pd
import datetime
import shutil
from pathlib import Path
import config
from database import (
    get_db, STATUS_LIST, log_ticket_history, get_custom_list_values
)
from auth import (
    get_current_user, can_assign_and_resolve, can_see_private_notes, can_delete_ticket
)
from utils import (
    get_status_badge, get_priority_badge, get_severity_badge,
    save_uploaded_file, format_file_size
)
from notifications import send_ticket_notification

def show_ticket_detail():
    user = get_current_user()
    ticket_id = st.session_state.get("selected_ticket_id")

    if not ticket_id:
        st.warning("Aucun ticket sélectionné.")
        if st.button("⬅ Retour à la liste"):
            st.session_state["current_page"] = "tickets_list"
            st.rerun()
        return

    # Bouton retour en haut
    if st.button("⬅ Retour à la liste des tickets"):
        st.session_state["current_page"] = "tickets_list"
        st.rerun()

    # Charger les informations complètes du ticket
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT t.*,
                   p.name as project_name,
                   p.parent_project_id,
                   parent_p.name as parent_project_name,
                   c.name as client_name,
                   u_rep.full_name as reporter_name,
                   u_ass.full_name as assigned_name
            FROM tickets t
            JOIN projects p ON t.project_id = p.id
            LEFT JOIN projects parent_p ON p.parent_project_id = parent_p.id
            LEFT JOIN clients c ON t.client_id = c.id
            JOIN users u_rep ON t.reporter_id = u_rep.id
            LEFT JOIN users u_ass ON t.assigned_id = u_ass.id
            WHERE t.id = ?
        """, (ticket_id,))
        ticket = cursor.fetchone()

        if not ticket:
            st.error("Ticket introuvable.")
            return

        # Vérification des droits pour profil Client
        if user["role"] == "Client" and ticket["client_id"] != user["client_id"]:
            st.error("Accès refusé : vous n'êtes pas autorisé à consulter ce ticket.")
            return

        ticket = dict(ticket)

        # Listes dynamiques configurables
        priority_list = get_custom_list_values("priority")
        severity_list = get_custom_list_values("severity")
        resolution_list = get_custom_list_values("resolution")
        qualif_client_list = get_custom_list_values("qualification_client")
        qualif_cegid_list = get_custom_list_values("qualification_cegid")

        # Charger la liste des catégories applicables (globales + propres au projet)
        cursor.execute("""
            SELECT name FROM categories
            WHERE project_id IS NULL OR project_id = ?
            ORDER BY project_id IS NOT NULL, name
        """, (ticket["project_id"],))
        avail_cats = [r["name"] for r in cursor.fetchall()]
        if ticket["category"] and ticket["category"] not in avail_cats:
            avail_cats.append(ticket["category"])
        if not avail_cats:
            avail_cats = ["Général", "Bug", "Évolution"]

        # Charger la liste des utilisateurs pour réassignation
        cursor.execute("SELECT id, full_name, role FROM users WHERE is_active = 1 ORDER BY full_name")
        all_users = [dict(r) for r in cursor.fetchall()]

        # Charger la liste des projets et clients pour modification
        cursor.execute("SELECT id, name, parent_project_id FROM projects WHERE status = 'Actif' ORDER BY name")
        all_projects = [dict(r) for r in cursor.fetchall()]

        cursor.execute("SELECT id, name FROM clients WHERE is_active = 1 ORDER BY name")
        all_clients = [dict(r) for r in cursor.fetchall()]

        # Charger les pièces jointes
        cursor.execute("""
            SELECT a.*, u.full_name as author_name
            FROM ticket_attachments a
            JOIN users u ON a.user_id = u.id
            WHERE a.ticket_id = ?
            ORDER BY a.created_at DESC
        """, (ticket_id,))
        attachments = [dict(r) for r in cursor.fetchall()]

        # Charger les notes / commentaires
        cursor.execute("""
            SELECT n.*, u.full_name as author_name, u.role as author_role
            FROM ticket_notes n
            JOIN users u ON n.user_id = u.id
            WHERE n.ticket_id = ?
            ORDER BY n.created_at ASC
        """, (ticket_id,))
        all_notes = [dict(r) for r in cursor.fetchall()]

        # Charger l'historique d'audit
        cursor.execute("""
            SELECT h.*, u.full_name as user_name
            FROM ticket_history h
            JOIN users u ON h.user_id = u.id
            WHERE h.ticket_id = ?
            ORDER BY h.created_at DESC
        """, (ticket_id,))
        history = [dict(r) for r in cursor.fetchall()]

    # Affichage du bandeau supérieur
    st.markdown(f"## `{ticket['ticket_number']}` : {ticket['summary']}")
    
    header_cols = st.columns([2, 2, 2, 2])
    with header_cols[0]:
        st.markdown(f"**Statut :** {get_status_badge(ticket['status'])}", unsafe_allow_html=True)
    with header_cols[1]:
        st.markdown(f"**Priorité :** {get_priority_badge(ticket['priority'])}", unsafe_allow_html=True)
    with header_cols[2]:
        st.markdown(f"**Sévérité :** {get_severity_badge(ticket['severity'])}", unsafe_allow_html=True)
    with header_cols[3]:
        st.markdown(f"**Résolution :** `{ticket['resolution']}`")

    st.markdown("---")

    # Mise en page en 2 colonnes : Gauche (Détails & Notes) / Droite (Workflow & Métadonnées)
    col_left, col_right = st.columns([2.2, 1.1])

    with col_right:
        # Boîte d'informations Mantis
        with st.container(border=True):
            st.markdown("#### 📌 Propriétés du Ticket")
            st.markdown(f"**Client :** {ticket['client_name'] or '*(Aucun client)*'}")
            proj_str = f"{ticket['parent_project_name']} > {ticket['project_name']}" if ticket['parent_project_name'] else ticket['project_name']
            st.markdown(f"**Projet :** {proj_str}")
            st.markdown(f"**Catégorie :** {ticket['category']}")
            st.markdown(f"**Qualif. Client :** `{ticket.get('qualification_client') or 'Non qualifié'}`")
            st.markdown(f"**Qualif. Cegid :** `{ticket.get('qualification_cegid') or 'Non qualifié'}`")
            st.markdown(f"**Reproductibilité :** {ticket['reproducibility']}")
            st.markdown(f"**Rapporteur :** {ticket['reporter_name']}")
            st.markdown(f"**Assigné à :** {ticket['assigned_name'] or '*(Non assigné)*'}")
            st.markdown(f"**Date création :** {ticket['created_at']}")
            st.markdown(f"**Dernière MAJ :** {ticket['updated_at']}")
            if ticket['closed_at']:
                st.markdown(f"**Fermé le :** {ticket['closed_at']}")

        # Panneau de Cycle de vie (si l'utilisateur a les droits)
        if can_assign_and_resolve(user):
            with st.container(border=True):
                st.markdown("#### ⚡ Gestion du Cycle de Vie")
                with st.form("workflow_form"):
                    new_status = st.selectbox(
                        "Statut",
                        STATUS_LIST,
                        index=STATUS_LIST.index(ticket["status"]) if ticket["status"] in STATUS_LIST else 0
                    )
                    
                    cur_res = ticket["resolution"] if ticket["resolution"] in resolution_list else (resolution_list[0] if resolution_list else "Non résolu")
                    cur_res_idx = resolution_list.index(cur_res) if cur_res in resolution_list else 0
                    new_resolution = st.selectbox("Résolution", resolution_list, index=cur_res_idx)

                    # Choix assignation
                    user_opts = ["(Non assigné)"] + [u["full_name"] for u in all_users]
                    cur_assigned_idx = 0
                    if ticket["assigned_name"]:
                        for idx, u in enumerate(all_users):
                            if u["id"] == ticket["assigned_id"]:
                                cur_assigned_idx = idx + 1
                                break

                    new_assigned_name = st.selectbox("Assigner à", user_opts, index=cur_assigned_idx)

                    # Qualifications Client et Cegid
                    cur_qc = ticket.get("qualification_client")
                    cur_qc_idx = qualif_client_list.index(cur_qc) if cur_qc in qualif_client_list else 0
                    new_qualif_client = st.selectbox("Qualification Client", qualif_client_list, index=cur_qc_idx)

                    cur_qcegid = ticket.get("qualification_cegid")
                    cur_qcegid_idx = qualif_cegid_list.index(cur_qcegid) if cur_qcegid in qualif_cegid_list else 0
                    new_qualif_cegid = st.selectbox("Qualification Cegid", qualif_cegid_list, index=cur_qcegid_idx)

                    # Catégorie modifiable
                    cur_cat_idx = avail_cats.index(ticket["category"]) if ticket["category"] in avail_cats else 0
                    new_cat = st.selectbox("Catégorie (adaptée au projet)", avail_cats, index=cur_cat_idx)
                    
                    cur_prio = ticket["priority"] if ticket["priority"] in priority_list else (priority_list[0] if priority_list else "Normale")
                    cur_prio_idx = priority_list.index(cur_prio) if cur_prio in priority_list else 0
                    new_priority = st.selectbox("Priorité", priority_list, index=cur_prio_idx)
                    
                    cur_sev = ticket["severity"] if ticket["severity"] in severity_list else (severity_list[0] if severity_list else "Mineure")
                    cur_sev_idx = severity_list.index(cur_sev) if cur_sev in severity_list else 0
                    new_severity = st.selectbox("Sévérité", severity_list, index=cur_sev_idx)

                    submit_wf = st.form_submit_button("💾 Mettre à jour le ticket", type="primary", use_container_width=True)

                    if submit_wf:
                        new_assigned_id = None
                        if new_assigned_name != "(Non assigné)":
                            for u in all_users:
                                if u["full_name"] == new_assigned_name:
                                    new_assigned_id = u["id"]
                                    break

                        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        closed_at = now_str if new_status in ["Résolu", "Fermé"] else None

                        with get_db() as conn:
                            log_ticket_history(conn, ticket["id"], user["id"], "Statut", ticket["status"], new_status)
                            log_ticket_history(conn, ticket["id"], user["id"], "Résolution", ticket["resolution"], new_resolution)
                            log_ticket_history(conn, ticket["id"], user["id"], "Assigné à", ticket["assigned_name"] or "Non assigné", new_assigned_name)
                            log_ticket_history(conn, ticket["id"], user["id"], "Catégorie", ticket["category"], new_cat)
                            log_ticket_history(conn, ticket["id"], user["id"], "Priorité", ticket["priority"], new_priority)
                            log_ticket_history(conn, ticket["id"], user["id"], "Sévérité", ticket["severity"], new_severity)
                            log_ticket_history(conn, ticket["id"], user["id"], "Qualif. Client", ticket.get("qualification_client", ""), new_qualif_client)
                            log_ticket_history(conn, ticket["id"], user["id"], "Qualif. Cegid", ticket.get("qualification_cegid", ""), new_qualif_cegid)

                            conn.execute("""
                                UPDATE tickets
                                SET status = ?, resolution = ?, assigned_id = ?, category = ?, priority = ?, severity = ?,
                                    qualification_client = ?, qualification_cegid = ?,
                                    updated_at = ?, closed_at = COALESCE(?, closed_at)
                                WHERE id = ?
                            """, (new_status, new_resolution, new_assigned_id, new_cat, new_priority, new_severity,
                                  new_qualif_client, new_qualif_cegid, now_str, closed_at, ticket["id"]))

                        # Notification e-mail aux utilisateurs rattachés au client
                        send_ticket_notification(
                            ticket["id"],
                            action_type="update",
                            author_name=user["full_name"],
                            details=f"Statut : {new_status} | Priorité : {new_priority} | Assigné à : {new_assigned_name}"
                        )

                        st.success("Ticket mis à jour avec succès !")
                        st.rerun()

        # Zone d'administration : SUPPRESSION DU TICKET (Administrateur uniquement)
        if can_delete_ticket(user):
            with st.container(border=True):
                st.markdown("#### 🗑️ Administration : Supprimer")
                st.caption("Suppression définitive du ticket, de ses pièces jointes, notes et historique.")
                confirm_del_ticket = st.checkbox(
                    f"Confirmer la suppression irréversible de {ticket['ticket_number']}",
                    key=f"check_del_t_{ticket['id']}"
                )
                if st.button("🗑️ Supprimer définitivement ce ticket", key=f"btn_del_t_{ticket['id']}", type="primary", disabled=not confirm_del_ticket, use_container_width=True):
                    try:
                        # 1. Supprimer le dossier de pièces jointes sur OneDrive
                        att_folder = config.get_attachments_dir() / f"ticket_{ticket['id']}"
                        if att_folder.exists() and att_folder.is_dir():
                            shutil.rmtree(att_folder, ignore_errors=True)

                        # 2. Supprimer en base de données
                        with get_db() as conn:
                            conn.execute("DELETE FROM ticket_attachments WHERE ticket_id = ?", (ticket["id"],))
                            conn.execute("DELETE FROM ticket_notes WHERE ticket_id = ?", (ticket["id"],))
                            conn.execute("DELETE FROM ticket_history WHERE ticket_id = ?", (ticket["id"],))
                            conn.execute("DELETE FROM tickets WHERE id = ?", (ticket["id"],))

                        st.session_state["selected_ticket_id"] = None
                        st.session_state["current_page"] = "tickets_list"
                        st.success(f"Ticket {ticket['ticket_number']} supprimé avec succès !")
                        st.rerun()
                    except Exception as e_delt:
                        st.error(f"Erreur lors de la suppression : {e_delt}")

    with col_left:
        # Description et étapes de reproduction
        with st.container(border=True):
            st.markdown("### 📝 Description")
            st.markdown(ticket["description"])

            if ticket.get("steps_to_reproduce"):
                st.markdown("#### 🔬 Étapes pour reproduire :")
                st.info(ticket["steps_to_reproduce"])

            if ticket.get("additional_info"):
                st.markdown("#### ℹ️ Informations complémentaires :")
                st.caption(ticket["additional_info"])

            # Formulaire de modification complète des informations du ticket
            with st.expander("✏️ **Modifier ou compléter les informations de ce ticket**", expanded=False):
                with st.form("edit_ticket_content_form"):
                    new_summary = st.text_input("Titre / Résumé du ticket *", value=ticket["summary"])
                    new_desc = st.text_area("Description détaillée *", value=ticket["description"], height=120)
                    new_steps = st.text_area("Étapes pour reproduire", value=ticket.get("steps_to_reproduce") or "", height=80)
                    new_add_info = st.text_area("Informations complémentaires", value=ticket.get("additional_info") or "", height=60)

                    c_ed1, c_ed2, c_ed3 = st.columns(3)
                    with c_ed1:
                        # Client
                        client_opts = ["(Aucun client)"] + [c["name"] for c in all_clients]
                        cur_c_idx = 0
                        if ticket["client_name"]:
                            for idx, c in enumerate(all_clients):
                                if c["id"] == ticket["client_id"]:
                                    cur_c_idx = idx + 1
                                    break
                        sel_c_name = st.selectbox("Client rattaché", client_opts, index=cur_c_idx)

                    with c_ed2:
                        # Projet
                        proj_opts = [p["name"] for p in all_projects]
                        cur_p_idx = 0
                        for idx, p in enumerate(all_projects):
                            if p["id"] == ticket["project_id"]:
                                cur_p_idx = idx
                                break
                        sel_p_name = st.selectbox("Projet rattaché", proj_opts, index=cur_p_idx)

                    with c_ed3:
                        new_est_hours = st.number_input("Temps estimé (h)", min_value=0.0, step=0.5, value=float(ticket.get("estimated_hours") or 0.0))

                    submit_edit_content = st.form_submit_button("💾 Enregistrer les informations du ticket", type="primary", use_container_width=True)

                    if submit_edit_content:
                        if not new_summary.strip() or not new_desc.strip():
                            st.error("Le résumé et la description détaillée sont obligatoires.")
                        else:
                            new_cid = None
                            if sel_c_name != "(Aucun client)":
                                for c in all_clients:
                                    if c["name"] == sel_c_name:
                                        new_cid = c["id"]
                                        break

                            new_pid = ticket["project_id"]
                            for p in all_projects:
                                if p["name"] == sel_p_name:
                                    new_pid = p["id"]
                                    break

                            now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                            with get_db() as conn:
                                log_ticket_history(conn, ticket["id"], user["id"], "Titre", ticket["summary"], new_summary.strip())
                                log_ticket_history(conn, ticket["id"], user["id"], "Projet", ticket["project_name"], sel_p_name)
                                log_ticket_history(conn, ticket["id"], user["id"], "Client", ticket["client_name"] or "Aucun", sel_c_name)

                                conn.execute("""
                                    UPDATE tickets
                                    SET summary = ?, description = ?, steps_to_reproduce = ?, additional_info = ?,
                                        client_id = ?, project_id = ?, estimated_hours = ?, updated_at = ?
                                    WHERE id = ?
                                """, (new_summary.strip(), new_desc.strip(), new_steps.strip(), new_add_info.strip(),
                                      new_cid, new_pid, new_est_hours, now_str, ticket["id"]))

                            # Notification
                            send_ticket_notification(
                                ticket["id"],
                                action_type="update",
                                author_name=user["full_name"],
                                details="Informations du ticket complétées / modifiées"
                            )

                            st.success("Informations du ticket mises à jour avec succès !")
                            st.rerun()

        # Pièces Jointes
        with st.container(border=True):
            st.markdown("### 📎 Pièces Jointes")
            if attachments:
                for att in attachments:
                    att_path = Path(att["stored_filename"])
                    c_att1, c_att2 = st.columns([3, 1.5])
                    with c_att1:
                        st.markdown(f"📄 **{att['filename']}** ({format_file_size(att['filesize'])})")
                        st.caption(f"Ajouté par {att['author_name']} le {att['created_at']}")
                    with c_att2:
                        if att_path.exists():
                            with open(att_path, "rb") as f_att:
                                st.download_button(
                                    label="⬇️ Télécharger",
                                    data=f_att.read(),
                                    file_name=att['filename'],
                                    key=f"dl_att_{att['id']}",
                                    use_container_width=True
                                )
                        else:
                            st.caption("Fichier introuvable")
                    st.divider()
            else:
                st.caption("Aucune pièce jointe.")

            # Formulaire d'upload de nouvelle pièce jointe
            with st.expander("➕ Ajouter une pièce jointe"):
                uploaded = st.file_uploader("Sélectionner un fichier", key="att_uploader")
                if uploaded and st.button("Sauvegarder la pièce jointe"):
                    if save_uploaded_file(uploaded, ticket["id"], user["id"]):
                        with get_db() as conn:
                            log_ticket_history(conn, ticket["id"], user["id"], "Pièce jointe", "", uploaded.name)
                        st.success(f"Fichier '{uploaded.name}' sauvegardé avec succès !")
                        st.rerun()

        # Notes et Commentaires de suivi Mantis
        with st.container(border=True):
            st.markdown("### 💬 Notes de Suivi & Commentaires")

            can_see_priv = can_see_private_notes(user)
            visible_notes = [n for n in all_notes if not n["is_private"] or can_see_priv]

            if visible_notes:
                for n in visible_notes:
                    is_priv = n["is_private"] == 1
                    with st.container(border=True):
                        top_c1, top_c2 = st.columns([3, 1])
                        with top_c1:
                            priv_tag = "🔒 **[Note Interne Privée]** " if is_priv else ""
                            st.markdown(f"{priv_tag}**{n['author_name']}** ({n['author_role']})")
                        with top_c2:
                            st.caption(f"{n['created_at']}")
                        st.markdown(n["note"])
                        if n.get("time_spent") and n["time_spent"] > 0:
                            st.caption(f"⏱️ Temps passé saisi : {n['time_spent']}h")
            else:
                st.caption("Aucun commentaire pour le moment.")

            st.markdown("---")
            st.markdown("#### ✍️ Ajouter une note")
            with st.form("add_note_form"):
                note_text = st.text_area("Votre commentaire / analyse technique :", height=100)
                n_c1, n_c2 = st.columns(2)
                with n_c1:
                    is_private_input = False
                    if can_see_priv:
                        is_private_input = st.checkbox("🔒 Note interne (invisible pour le client)", value=False)
                with n_c2:
                    time_spent_input = st.number_input("Temps passé (en heures) :", min_value=0.0, max_value=24.0, step=0.25, value=0.0)

                submit_note = st.form_submit_button("Envoyer la note", use_container_width=True)

                if submit_note:
                    if not note_text.strip():
                        st.warning("Veuillez saisir un texte pour la note.")
                    else:
                        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        with get_db() as conn:
                            conn.execute("""
                                INSERT INTO ticket_notes (ticket_id, user_id, note, is_private, time_spent, created_at)
                                VALUES (?, ?, ?, ?, ?, ?)
                            """, (ticket["id"], user["id"], note_text.strip(), 1 if is_private_input else 0, time_spent_input, now_str))

                            conn.execute("""
                                UPDATE tickets
                                SET spent_hours = spent_hours + ?, updated_at = ?
                                WHERE id = ?
                            """, (time_spent_input, now_str, ticket["id"]))

                            log_ticket_history(conn, ticket["id"], user["id"], "Ajout Note", "", f"Note ajoutée ({time_spent_input}h)")

                        # Notification e-mail
                        send_ticket_notification(
                            ticket["id"],
                            action_type="update",
                            author_name=user["full_name"],
                            details=f"Nouvelle note ajoutée ({time_spent_input}h)"
                        )

                        st.success("Note ajoutée !")
                        st.rerun()

        # Journal d'audit Mantis (Historique)
        with st.expander("📜 **Journal d'activité complet (Audit Trail Mantis)**", expanded=False):
            if history:
                hist_records = []
                for h in history:
                    hist_records.append({
                        "Date": h["created_at"],
                        "Utilisateur": h["user_name"],
                        "Champ modifié": h["field_changed"],
                        "Ancienne valeur": h["old_value"],
                        "Nouvelle valeur": h["new_value"],
                    })
                st.dataframe(pd.DataFrame(hist_records), use_container_width=True, hide_index=True)
            else:
                st.caption("Aucun historique disponible.")
