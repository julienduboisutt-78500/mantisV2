import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from database import get_db, get_email_settings

def send_test_email(recipient_email: str) -> tuple[bool, str]:
    """Envoie un email de test pour valider la configuration SMTP."""
    cfg = get_email_settings()
    if not cfg or not cfg.get("smtp_server"):
        return False, "Le serveur SMTP n'est pas renseigné."

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = "🧪 Test de notification - Mantis V2"
        msg["From"] = f"{cfg.get('sender_name', 'Mantis V2')} <{cfg.get('sender_email')}>"
        msg["To"] = recipient_email

        html_body = f"""
        <div style="font-family: Arial, sans-serif; padding: 20px; color: #333;">
            <h2 style="color: #1E88E5;">🎫 Mantis V2 - Test de Notification</h2>
            <p>Bonjour,</p>
            <p>La configuration de votre serveur SMTP est <strong>opérationnelle</strong>.</p>
            <p>Ce test confirme que les notifications par e-mail pourront être transmises aux utilisateurs rattachés aux clients lors de la création ou de la mise à jour des tickets.</p>
            <hr style="border: none; border-top: 1px solid #eee; margin: 20px 0;">
            <small style="color: #888;">Notification automatique émise par Mantis V2</small>
        </div>
        """
        msg.attach(MIMEText(html_body, "html"))

        server = smtplib.SMTP(cfg["smtp_server"], int(cfg.get("smtp_port", 587)), timeout=10)
        if cfg.get("use_tls", 1):
            server.starttls()
        if cfg.get("smtp_user") and cfg.get("smtp_password"):
            server.login(cfg["smtp_user"], cfg["smtp_password"])

        server.sendmail(cfg.get("sender_email"), [recipient_email], msg.as_string())
        server.quit()
        return True, f"Email de test envoyé avec succès à {recipient_email} !"
    except Exception as e:
        return False, f"Échec de l'envoi SMTP : {e}"

def send_ticket_notification(ticket_id: int, action_type: str = "update", author_name: str = "Système", details: str = ""):
    """
    Envoie un email de notification aux utilisateurs rattachés au client du ticket.
    action_type: 'creation' ou 'update'
    """
    cfg = get_email_settings()
    if not cfg or not cfg.get("is_enabled"):
        return  # Notifications désactivées

    if not cfg.get("smtp_server") or not cfg.get("sender_email"):
        return

    try:
        # 1. Charger les infos du ticket et du client
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT t.id, t.ticket_number, t.summary, t.status, t.priority, t.severity,
                       t.category, t.qualification_client, t.qualification_cegid,
                       c.id as client_id, c.name as client_name,
                       u_ass.full_name as assigned_name, u_ass.email as assigned_email
                FROM tickets t
                LEFT JOIN clients c ON t.client_id = c.id
                LEFT JOIN users u_ass ON t.assigned_id = u_ass.id
                WHERE t.id = ?
            """, (ticket_id,))
            ticket = cursor.fetchone()
            if not ticket:
                return

            client_id = ticket["client_id"]

            # 2. Identifier tous les utilisateurs rattachés à ce client (ou assigné)
            recipients = set()

            if client_id:
                cursor.execute("""
                    SELECT u.email FROM users u
                    JOIN user_client_access uca ON u.id = uca.user_id
                    WHERE uca.client_id = ? AND u.is_active = 1 AND u.email LIKE '%@%'
                """, (client_id,))
                for r in cursor.fetchall():
                    if r["email"]:
                        recipients.add(r["email"].strip())

            # Ajouter l'intervenant assigné s'il existe
            if ticket["assigned_email"] and "@" in ticket["assigned_email"]:
                recipients.add(ticket["assigned_email"].strip())

        if not recipients:
            return

        # 3. Préparer l'email
        action_label = "Nouveau ticket créé" if action_type == "creation" else "Ticket mis à jour"
        client_label = ticket["client_name"] or "Sans client"
        subject = f"[Mantis V2 - {client_label}] {ticket['ticket_number']} : {ticket['summary']} ({action_label})"

        html_content = f"""
        <div style="font-family: Arial, sans-serif; max-width: 650px; margin: auto; padding: 20px; border: 1px solid #e0e0e0; border-radius: 8px;">
            <div style="border-bottom: 2px solid #1E88E5; padding-bottom: 10px; margin-bottom: 15px;">
                <h2 style="color: #1E88E5; margin: 0;">🎫 Mantis V2</h2>
                <span style="color: #666; font-size: 0.9em;">Notification d'activité de ticketing</span>
            </div>

            <div style="background-color: #f8f9fa; padding: 15px; border-radius: 6px; margin-bottom: 15px;">
                <h3 style="margin-top: 0; color: #2c3e50;">{ticket['ticket_number']} - {ticket['summary']}</h3>
                <p><strong>Action :</strong> {action_label} par <em>{author_name}</em></p>
                {f'<p style="color: #444;"><strong>Détails :</strong> {details}</p>' if details else ''}
            </div>

            <table style="width: 100%; border-collapse: collapse; margin-bottom: 20px; font-size: 0.95em;">
                <tr>
                    <td style="padding: 6px; border: 1px solid #ddd; background: #fafafa; width: 35%;"><strong>Client</strong></td>
                    <td style="padding: 6px; border: 1px solid #ddd;">{client_label}</td>
                </tr>
                <tr>
                    <td style="padding: 6px; border: 1px solid #ddd; background: #fafafa;"><strong>Statut</strong></td>
                    <td style="padding: 6px; border: 1px solid #ddd;">{ticket['status']}</td>
                </tr>
                <tr>
                    <td style="padding: 6px; border: 1px solid #ddd; background: #fafafa;"><strong>Priorité / Sévérité</strong></td>
                    <td style="padding: 6px; border: 1px solid #ddd;">{ticket['priority']} / {ticket['severity']}</td>
                </tr>
                <tr>
                    <td style="padding: 6px; border: 1px solid #ddd; background: #fafafa;"><strong>Assigné à</strong></td>
                    <td style="padding: 6px; border: 1px solid #ddd;">{ticket['assigned_name'] or 'Non assigné'}</td>
                </tr>
                <tr>
                    <td style="padding: 6px; border: 1px solid #ddd; background: #fafafa;"><strong>Qualif. Client</strong></td>
                    <td style="padding: 6px; border: 1px solid #ddd;">{ticket['qualification_client']}</td>
                </tr>
                <tr>
                    <td style="padding: 6px; border: 1px solid #ddd; background: #fafafa;"><strong>Qualif. Cegid</strong></td>
                    <td style="padding: 6px; border: 1px solid #ddd;">{ticket['qualification_cegid']}</td>
                </tr>
            </table>

            <p style="font-size: 0.85em; color: #7f8c8d; text-align: center; margin-top: 25px;">
                Vous recevez cette notification car vous êtes rattaché au client <strong>{client_label}</strong> dans Mantis V2.
            </p>
        </div>
        """

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"{cfg.get('sender_name', 'Mantis V2')} <{cfg.get('sender_email')}>"
        msg["Bcc"] = ", ".join(recipients)
        msg.attach(MIMEText(html_content, "html"))

        # Envoi SMTP
        server = smtplib.SMTP(cfg["smtp_server"], int(cfg.get("smtp_port", 587)), timeout=10)
        if cfg.get("use_tls", 1):
            server.starttls()
        if cfg.get("smtp_user") and cfg.get("smtp_password"):
            server.login(cfg["smtp_user"], cfg["smtp_password"])

        server.sendmail(cfg.get("sender_email"), list(recipients), msg.as_string())
        server.quit()
    except Exception as e:
        # Ne bloque jamais l'application
        print(f"[Notifications Email] Erreur d'envoi de notification pour le ticket {ticket_id} : {e}")
