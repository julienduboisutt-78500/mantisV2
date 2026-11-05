import streamlit as st
import os
import shutil
import zipfile
import io
from pathlib import Path
import config
from auth import get_current_user, can_manage_all
from database import get_email_settings, save_email_settings
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
        with st.container(border=True):
            st.markdown("### 📂 Configuration du Stockage OneDrive / SharePoint")
            
            # Affichage de l'état actuel
            if sharepoint_url:
                st.markdown(f"🌐 **Lien SharePoint configuré :**")
                st.code(sharepoint_url, language=None)
                col_btn_sp, _ = st.columns([1.5, 3])
                with col_btn_sp:
                    st.link_button("🌐 Ouvrir dans SharePoint Web ➔", sharepoint_url, use_container_width=True)

                st.markdown(f"💻 **Dossier local synchronisé sur ce PC :** `{current_path}`")
                st.caption("ℹ️ *Les fichiers enregistrés par Mantis V2 (base relationnelle et pièces jointes) sont stockés dans ce dossier local et sont automatiquement répliqués en continu vers votre espace SharePoint en ligne par le client OneDrive Entreprise.*")
            else:
                st.info(f"📁 **Chemin local actuel :** `{current_path}`")

            st.markdown("---")

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

        # PANNEAU 2 : SANTÉ DU STOCKAGE & STATISTIQUES
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

        # PANNEAU 3 : SAUVEGARDE & ARCHIVAGE MANUEL
        with st.container(border=True):
            st.markdown("### 🗄️ Sauvegarde / Export d'Archive Complète")
            st.caption("Téléchargez une archive ZIP contenant la base de données et l'intégralité des pièces jointes stockées sur OneDrive.")

            if st.button("📦 Générer le ZIP de sauvegarde"):
                try:
                    zip_buffer = io.BytesIO()
                    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
                        if db_path.exists():
                            zip_file.write(db_path, arcname="ticketing.db")
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
