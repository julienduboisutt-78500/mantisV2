import streamlit as st
import os
import shutil
import zipfile
import io
import datetime
from pathlib import Path
import config
from auth import get_current_user, can_manage_all
from database import (
    get_email_settings, save_email_settings,
    export_database_to_sharepoint_mirror, restore_database_from_json, sync_all_to_sharepoint
)
from notifications import send_test_email

def show_settings():
    user = get_current_user()
    if not can_manage_all(user):
        st.error("Accès réservé aux Administrateurs.")
        return

    st.title("⚙️ Paramètres Système (Administration)")
    st.caption("Configuration du stockage persistant OneDrive / SharePoint et des notifications e-mail.")

    tab_onedrive, tab_emails = st.tabs(["📂 Stockage & Sauvegardes OneDrive", "✉️ Notifications E-mail (SMTP)"])

    current_path = config.get_storage_path()
    sharepoint_url = config.get_sharepoint_url()
    db_path = config.get_db_path()
    attachments_dir = config.get_attachments_dir()

    # ==========================================
    # --- TAB 1 : STOCKAGE ONEDRIVE / SHAREPOINT ---
    # ==========================================
    with tab_onedrive:
        # PANNEAU 1 : ESPACE SHAREPOINT & FICHIERS ACCESSIBLES EN DIRECT
        with st.container(border=True):
            st.markdown("### 🌐 Espace SharePoint & Fichiers Directement Accessibles")
            st.caption("Conformément au standard de l'application Scout, l'intégralité des données est répliquée dans SharePoint sous formats Excel et JSON directement consultables en ligne.")

            excel_p = current_path / "Export_MantisV2_Complet.xlsx"
            json_p = current_path / "mantis_data.json"
            bak_p = current_path / "ticketing.db.bak"

            if sharepoint_url:
                st.markdown(f"🔗 **Dossier SharePoint en ligne :**")
                st.code(sharepoint_url, language=None)
                col_btn_sp, col_sync_now = st.columns([1.5, 2])
                with col_btn_sp:
                    st.link_button("🌐 Ouvrir dans SharePoint Web ➔", sharepoint_url, use_container_width=True)
                with col_sync_now:
                    if st.button("🔄 Synchroniser les fichiers SharePoint maintenant", use_container_width=True, type="primary"):
                        if export_database_to_sharepoint_mirror():
                            st.success("Miroir SharePoint mis à jour avec succès (Excel + JSON + Base) !")
                            st.rerun()
                        else:
                            st.error("Erreur lors de la synchronisation.")

            st.markdown("---")
            st.markdown("##### 📄 Fichiers présents dans l'espace SharePoint :")
            
            c_f1, c_f2, c_f3 = st.columns(3)
            with c_f1:
                st.markdown("📊 **Classeur Excel Multi-Onglets**")
                st.caption("`Export_MantisV2_Complet.xlsx`")
                if excel_p.exists():
                    sz_kb = excel_p.stat().st_size / 1024.0
                    mtime = datetime.datetime.fromtimestamp(excel_p.stat().st_mtime).strftime("%d/%m/%Y %H:%M")
                    st.success(f"Disponible ({sz_kb:.1f} Ko)\n\n*MàJ : {mtime}*")
                    with open(excel_p, "rb") as f_ex:
                        st.download_button("⬇️ Télécharger Excel (.xlsx)", data=f_ex.read(), file_name="Export_MantisV2_Complet.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)
                else:
                    st.warning("Non généré")
                    if st.button("Générer Excel", key="gen_ex"):
                        export_database_to_sharepoint_mirror()
                        st.rerun()

            with c_f2:
                st.markdown("💾 **Snapshot JSON Miroir**")
                st.caption("`mantis_data.json`")
                if json_p.exists():
                    sz_kb = json_p.stat().st_size / 1024.0
                    mtime = datetime.datetime.fromtimestamp(json_p.stat().st_mtime).strftime("%d/%m/%Y %H:%M")
                    st.success(f"Disponible ({sz_kb:.1f} Ko)\n\n*MàJ : {mtime}*")
                    with open(json_p, "rb") as f_js:
                        st.download_button("⬇️ Télécharger JSON (.json)", data=f_js.read(), file_name="mantis_data.json", mime="application/json", use_container_width=True)
                else:
                    st.warning("Non généré")
                    if st.button("Générer JSON", key="gen_js"):
                        export_database_to_sharepoint_mirror()
                        st.rerun()

            with c_f3:
                st.markdown("🗄️ **Base SQLite & Backup**")
                st.caption("`ticketing.db` + `.bak`")
                if db_path.exists():
                    sz_kb = db_path.stat().st_size / 1024.0
                    st.info(f"Base active : {sz_kb:.1f} Ko\n\nBackup sécurité : {'Présent' if bak_p.exists() else 'En attente'}")
                else:
                    st.error("Base introuvable")

        # PANNEAU 2 : GARANTIE ANTI-ÉCRASEMENT & RESTAURATION
        with st.container(border=True):
            st.markdown("### 🛡️ Protection Anti-Écrasement (Streamlit Cloud)")
            st.success("""
            ✅ **Protection Active & Permanente** :
            - Lors des redémarrages du serveur Streamlit ou d'un redéploiement, l'application recharge automatiquement les données depuis le miroir `mantis_data.json` / base SQLite.
            - **Aucune fausse donnée ou donnée de test** n'est jamais injectée.
            - Vos clients, projets (Projet One Pay, TF1), utilisateurs et tickets sont 100% préservés et ne peuvent pas être écrasés.
            """)

            with st.expander("📤 Restaurer la base depuis un fichier de sauvegarde (JSON)", expanded=False):
                st.caption("Utilisez cette option si vous souhaitez restaurer l'intégralité de vos tickets et projets depuis une sauvegarde JSON.")
                uploaded_json = st.file_uploader("Fichier mantis_data.json :", type=["json"], key="restore_json_uploader")
                if uploaded_json is not None:
                    if st.button("🚀 Confirmer la restauration complète", type="primary"):
                        try:
                            # Écrire dans un fichier temporaire puis restaurer
                            tmp_restore = current_path / "_temp_restore.json"
                            with open(tmp_restore, "wb") as f_tmp:
                                f_tmp.write(uploaded_json.getvalue())
                            ok_res, msg_res = restore_database_from_json(tmp_restore)
                            if tmp_restore.exists():
                                tmp_restore.unlink()
                            if ok_res:
                                st.success("Restauration effectuée avec succès !")
                                st.rerun()
                            else:
                                st.error(msg_res)
                        except Exception as e_res:
                            st.error(f"Erreur restauration : {e_res}")

        # PANNEAU 3 : CONFIGURATION DU STOCKAGE LOCAL
        with st.container(border=True):
            st.markdown("### 📁 Emplacement du Stockage Local Synchronisé")
            st.markdown(f"💻 **Dossier local sur ce PC :** `{current_path}`")
            st.caption("ℹ️ *Le client OneDrive Entreprise de votre PC assure la synchronisation automatique et continue de ce dossier vers votre SharePoint en ligne.*")

            # Formulaire de modification
            default_input_value = sharepoint_url if sharepoint_url else str(current_path)
            with st.form("onedrive_config_form"):
                new_input = st.text_input(
                    "Lien SharePoint Web (https://...) ou Chemin local OneDrive :",
                    value=default_input_value,
                    help="Vous pouvez coller directement l'URL web de votre dossier SharePoint (ex: https://cegidgroup-my.sharepoint.com/:f:/g/personal/...) ou le chemin absolu du dossier sur votre disque (ex: C:\\Users\\...\\OneDrive - CEGID\\...)"
                )
                migrate_checkbox = st.checkbox("Transférer / Copier les données existantes vers ce nouvel emplacement", value=True)
                submit_config = st.form_submit_button("💾 Enregistrer et appliquer", type="primary")

                if submit_config:
                    if not new_input.strip():
                        st.error("Veuillez renseigner un chemin ou un lien SharePoint valide.")
                    else:
                        old_path = current_path.resolve()
                        success, msg, new_path = config.set_storage_path(new_input.strip())

                        if success:
                            if migrate_checkbox and old_path.exists() and old_path != new_path.resolve():
                                try:
                                    if (old_path / "ticketing.db").exists():
                                        shutil.copy2(old_path / "ticketing.db", new_path / "ticketing.db")
                                    if (old_path / "mantis_data.json").exists():
                                        shutil.copy2(old_path / "mantis_data.json", new_path / "mantis_data.json")
                                    if (old_path / "Export_MantisV2_Complet.xlsx").exists():
                                        shutil.copy2(old_path / "Export_MantisV2_Complet.xlsx", new_path / "Export_MantisV2_Complet.xlsx")
                                    if (old_path / "attachments").exists():
                                        dest_att = new_path / "attachments"
                                        dest_att.mkdir(parents=True, exist_ok=True)
                                        for item in (old_path / "attachments").glob("*"):
                                            if item.is_dir():
                                                shutil.copytree(item, dest_att / item.name, dirs_exist_ok=True)
                                    st.success("Migration des fichiers effectuée avec succès !")
                                except Exception as e_mig:
                                    st.warning(f"Chemin mis à jour mais erreur lors du transfert : {e_mig}")
                            
                            st.success(msg)
                            st.rerun()
                        else:
                            st.error(msg)

        # PANNEAU 4 : SANTÉ DU STOCKAGE & STATISTIQUES
        with st.container(border=True):
            st.markdown("### 📊 État & Santé du Stockage")

            db_exists = db_path.exists()
            db_size_kb = (db_path.stat().st_size / 1024.0) if db_exists else 0
            
            att_count = 0
            att_total_bytes = 0
            if attachments_dir.exists():
                for root, _, files in os.walk(attachments_dir):
                    for f in files:
                        att_count += 1
                        att_total_bytes += os.path.getsize(os.path.join(root, f))

            c1, c2, c3, c4 = st.columns(4)
            with c1:
                st.metric("Base SQLite", "Connectée" if db_exists else "Introuvable")
            with c2:
                st.metric("Taille BDD", f"{db_size_kb:.1f} Ko")
            with c3:
                st.metric("Pièces Jointes", f"{att_count} fichier(s)")
            with c4:
                st.metric("Volume Fichiers", f"{(att_total_bytes / (1024*1024)):.2f} Mo")

        # PANNEAU 5 : ARCHIVE ZIP COMPLÈTE
        with st.container(border=True):
            st.markdown("### 🗄️ Sauvegarde / Export d'Archive Complète (.zip)")
            st.caption("Téléchargez une archive ZIP contenant la base SQLite, le miroir JSON, l'export Excel et toutes les pièces jointes.")

            if st.button("📦 Générer le ZIP de sauvegarde"):
                try:
                    zip_buffer = io.BytesIO()
                    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
                        if db_path.exists():
                            zip_file.write(db_path, arcname="ticketing.db")
                        if json_p.exists():
                            zip_file.write(json_p, arcname="mantis_data.json")
                        if excel_p.exists():
                            zip_file.write(excel_p, arcname="Export_MantisV2_Complet.xlsx")
                        if attachments_dir.exists():
                            for root, _, files in os.walk(attachments_dir):
                                for file in files:
                                    full_file_path = Path(root) / file
                                    rel_path = full_file_path.relative_to(current_path)
                                    zip_file.write(full_file_path, arcname=str(rel_path))

                    zip_buffer.seek(0)
                    st.download_button(
                        label="⬇️ Télécharger l'archive ZIP (.zip)",
                        data=zip_buffer.getvalue(),
                        file_name=f"ticketing_backup_{current_path.name}.zip",
                        mime="application/zip",
                        type="primary"
                    )
                except Exception as e_zip:
                    st.error(f"Erreur lors de la génération de la sauvegarde : {e_zip}")

    # ==========================================
    # --- TAB 2 : NOTIFICATIONS PAR EMAIL ---
    # ==========================================
    with tab_emails:
        st.subheader("Configuration du Serveur E-mail SMTP")
        st.caption("Activez l'envoi automatique de notifications par e-mail aux utilisateurs rattachés au client lors de la création ou mise à jour d'un ticket.")

        email_cfg = get_email_settings()

        with st.form("smtp_settings_form"):
            enable_email = st.checkbox("Activer l'envoi automatique des notifications e-mail", value=bool(email_cfg.get("is_enabled", 0)))

            col_s1, col_s2 = st.columns(2)
            with col_s1:
                smtp_server = st.text_input("Serveur SMTP (ex: smtp.office365.com, smtp.gmail.com) :", value=email_cfg.get("smtp_server", ""))
                smtp_port = st.number_input("Port SMTP :", value=int(email_cfg.get("smtp_port") or 587), step=1)
                use_tls = st.checkbox("Activer TLS (StartTLS)", value=bool(email_cfg.get("use_tls", 1)))

            with col_s2:
                smtp_user = st.text_input("Nom d'utilisateur / Compte SMTP :", value=email_cfg.get("smtp_user", ""))
                smtp_pwd = st.text_input("Mot de passe SMTP / App Password :", type="password", value=email_cfg.get("smtp_password", ""))
                sender_email = st.text_input("Adresse e-mail expéditrice :", value=email_cfg.get("sender_email", ""))
                sender_name = st.text_input("Nom de l'expéditeur affiché :", value=email_cfg.get("sender_name", "Mantis V2"))

            submit_smtp = st.form_submit_button("💾 Enregistrer la configuration SMTP", type="primary")

            if submit_smtp:
                new_settings = {
                    "is_enabled": 1 if enable_email else 0,
                    "smtp_server": smtp_server.strip(),
                    "smtp_port": smtp_port,
                    "smtp_user": smtp_user.strip(),
                    "smtp_password": smtp_pwd.strip(),
                    "use_tls": 1 if use_tls else 0,
                    "sender_email": sender_email.strip(),
                    "sender_name": sender_name.strip()
                }
                save_email_settings(new_settings)
                st.success("Paramètres e-mail enregistrés avec succès !")
                st.rerun()

        # Outil de test SMTP
        st.markdown("---")
        st.markdown("#### 🧪 Tester l'envoi d'un e-mail")
        with st.form("test_email_form"):
            test_recipient = st.text_input("Adresse e-mail de réception pour le test :", placeholder="votre.email@cegid.com")
            submit_test = st.form_submit_button("📨 Envoyer l'e-mail de test")

            if submit_test:
                if not test_recipient.strip() or "@" not in test_recipient:
                    st.warning("Veuillez renseigner une adresse email valide.")
                else:
                    success, msg = send_test_email(test_recipient.strip())
                    if success:
                        st.success(msg)
                    else:
                        st.error(msg)
