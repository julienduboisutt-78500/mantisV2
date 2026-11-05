import io
import os
import shutil
from pathlib import Path
import pandas as pd
import streamlit as st
import config
from database import STATUS_COLORS, PRIORITY_COLORS, SEVERITY_COLORS, get_db

def generate_next_ticket_number() -> str:
    """Génère le prochain numéro de ticket au format Mantis TIK-000001."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM tickets ORDER BY id DESC LIMIT 1")
        row = cursor.fetchone()
        next_id = (row["id"] + 1) if row else 1
        return f"TIK-{next_id:06d}"

def badge_html(text: str, bg_color: str, text_color: str = "#ffffff") -> str:
    """Génère une puce / badge coloré Mantis en HTML."""
    return f"""
    <span style="
        background-color: {bg_color};
        color: {text_color};
        padding: 3px 8px;
        border-radius: 4px;
        font-size: 0.82rem;
        font-weight: 600;
        display: inline-block;
        box-shadow: 0 1px 2px rgba(0,0,0,0.1);
    ">{text}</span>
    """

def get_status_badge(status: str) -> str:
    bg = STATUS_COLORS.get(status, "#757575")
    # Pour les couleurs claires, texte sombre
    text_color = "#111827" if status in ["Nouveau", "Reçu", "Résolu", "Fermé"] else "#FFFFFF"
    return badge_html(status, bg, text_color)

def get_priority_badge(priority: str) -> str:
    bg = PRIORITY_COLORS.get(priority, "#757575")
    return badge_html(priority, bg, "#FFFFFF")

def get_severity_badge(severity: str) -> str:
    bg = SEVERITY_COLORS.get(severity, "#757575")
    return badge_html(severity, bg, "#FFFFFF")

def save_uploaded_file(uploaded_file, ticket_id: int, user_id: int) -> bool:
    """Sauvegarde le fichier uploadé dans le dossier OneDrive attachments et enregistre en base."""
    try:
        attachments_dir = config.get_attachments_dir()
        ticket_folder = attachments_dir / f"ticket_{ticket_id}"
        ticket_folder.mkdir(parents=True, exist_ok=True)

        original_filename = uploaded_file.name
        # Préfixe temporel pour unicité
        import time
        safe_filename = f"{int(time.time())}_{original_filename.replace(' ', '_')}"
        dest_path = ticket_folder / safe_filename

        with open(dest_path, "wb") as f:
            f.write(uploaded_file.get_buffer())

        filesize = dest_path.stat().st_size

        with get_db() as conn:
            conn.execute("""
                INSERT INTO ticket_attachments (ticket_id, user_id, filename, stored_filename, filesize, created_at)
                VALUES (?, ?, ?, ?, ?, datetime('now', 'localtime'))
            """, (ticket_id, user_id, original_filename, str(dest_path), filesize))

        return True
    except Exception as e:
        st.error(f"Erreur d'enregistrement de la pièce jointe : {e}")
        return False

def format_file_size(bytes_size: int) -> str:
    for unit in ['o', 'Ko', 'Mo', 'Go']:
        if bytes_size < 1024.0:
            return f"{bytes_size:.1f} {unit}"
        bytes_size /= 1024.0
    return f"{bytes_size:.1f} To"

def export_tickets_to_dataframe(df: pd.DataFrame) -> tuple[bytes, bytes]:
    """Exporte un DataFrame de tickets en CSV et Excel (bytes)."""
    # CSV
    csv_bytes = df.to_csv(index=False, sep=";", encoding="utf-8-sig").encode("utf-8-sig")
    
    # Excel
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine=None) as writer:
        df.to_excel(writer, index=False, sheet_name="Tickets")
    excel_bytes = output.getvalue()

    return csv_bytes, excel_bytes
