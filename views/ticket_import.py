import io
import streamlit as st
import pandas as pd
import datetime
from database import (
    get_db, log_ticket_history, get_custom_list_values, sync_all_to_sharepoint_async
)
from auth import get_current_user, can_manage_projects
from utils import generate_next_ticket_number
from notifications import send_ticket_notification

SAMPLE_COLUMNS = [
    "summary",
    "description",
    "project",
    "client",
    "category",
    "priority",
    "severity",
    "qualification_client",
    "qualification_cegid",
    "steps_to_reproduce",
    "estimated_hours"
]

def generate_sample_templates():
    """Génère un fichier Excel et un fichier CSV d'exemple pour l'import."""
    sample_data = [
        {
            "summary": "Erreur lors du calcul de TVA multi-taux",
            "description": "Un écart de 2 centimes apparaît lors de l'édition d'une facture mixte 20% et 5.5%.",
            "project": "Projet One Pay",
            "client": "",
            "category": "Facturation",
            "priority": "Haute",
            "severity": "Majeure",
            "qualification_client": "En attente test client",
            "qualification_cegid": "Bug avéré (escalade R&D)",
            "steps_to_reproduce": "1. Créer facture\n2. Ajouter 3 lignes mixtes\n3. Valider",
            "estimated_hours": 2.5
        },
        {
            "summary": "Optimisation temps de réponse API commandes",
            "description": "L'appel de synchronisation POST /orders dépasse 10 secondes.",
            "project": "Projet One Pay",
            "client": "",
            "category": "Performance",
            "priority": "Normale",
            "severity": "Mineure",
            "qualification_client": "Non qualifié",
            "qualification_cegid": "Analyse technique en cours",
            "steps_to_reproduce": "Lancer batch 200 commandes",
            "estimated_hours": 4.0
        }
    ]
    df_sample = pd.DataFrame(sample_data)

    # Excel
    excel_buf = io.BytesIO()
    with pd.ExcelWriter(excel_buf, engine="openpyxl") as writer:
        df_sample.to_excel(writer, index=False, sheet_name="Modele_Import")
    excel_bytes = excel_buf.getvalue()

    # CSV
    csv_bytes = df_sample.to_csv(index=False, sep=";", encoding="utf-8-sig").encode("utf-8-sig")

    return excel_bytes, csv_bytes

def show_ticket_import():
    user = get_current_user()
    if not can_manage_projects(user):
        st.error("Accès réservé aux Administrateurs et Gestionnaires.")
        return

    st.title("📥 Import en Masse de Tickets (Excel / CSV)")
    st.caption("Importez des dizaines de tickets simultanément à partir d'un fichier Excel (.xlsx) ou CSV (.csv).")

    # Téléchargement des modèles
    with st.expander("📄 Télécharger le fichier modèle type (Template)", expanded=True):
        st.markdown("""
        Utilisez l'un des modèles ci-dessous pour préparer vos tickets.
        - **Colonnes obligatoires :** `summary` (titre), `description`, `project` (nom ou code du projet/sous-projet).
        - **Colonnes optionnelles :** `client`, `category`, `priority`, `severity`, `qualification_client`, `qualification_cegid`, `steps_to_reproduce`, `estimated_hours`.
        """)
        xlsx_tpl, csv_tpl = generate_sample_templates()
        c_tpl1, c_tpl2 = st.columns(2)
        with c_tpl1:
            st.download_button(
                label="📊 Télécharger le modèle Excel (.xlsx)",
                data=xlsx_tpl,
                file_name="modele_import_tickets.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )
        with c_tpl2:
            st.download_button(
                label="📥 Télécharger le modèle CSV (.csv)",
                data=csv_tpl,
                file_name="modele_import_tickets.csv",
                mime="text/csv",
                use_container_width=True
            )

    st.markdown("---")

    # Zone d'upload de fichier
    uploaded_file = st.file_uploader(
        "Sélectionnez votre fichier Excel (.xlsx) ou CSV (.csv) à importer :",
        type=["xlsx", "xls", "csv"]
    )

    if not uploaded_file:
        st.info("Veuillez sélectionner un fichier pour afficher la prévisualisation et lancer l'import.")
        return

    # Charger le fichier en DataFrame
    try:
        if uploaded_file.name.endswith(".csv"):
            try:
                df_raw = pd.read_csv(uploaded_file, sep=";", encoding="utf-8-sig")
            except Exception:
                uploaded_file.seek(0)
                df_raw = pd.read_csv(uploaded_file, sep=",", encoding="utf-8")
        else:
            df_raw = pd.read_excel(uploaded_file)
    except Exception as e_read:
        st.error(f"Erreur de lecture du fichier : {e_read}")
        return

    if df_raw.empty:
        st.warning("Le fichier sélectionné est vide.")
        return

    # Normalisation des noms de colonnes (minuscules sans espaces)
    df_raw.columns = [str(c).strip().lower().replace(" ", "_") for c in df_raw.columns]

    # Vérification des colonnes indispensables
    missing_cols = []
    if "summary" not in df_raw.columns and "titre" not in df_raw.columns:
        missing_cols.append("summary (ou titre)")
    if "project" not in df_raw.columns and "projet" not in df_raw.columns:
        missing_cols.append("project (ou projet)")

    if missing_cols:
        st.error(f"Colonnes obligatoires manquantes dans votre fichier : {', '.join(missing_cols)}")
        return

    # Mapping des synonymes de colonnes
    rename_map = {
        "titre": "summary",
        "projet": "project",
        "code_projet": "project",
        "projet_code": "project"
    }
    for old, new in rename_map.items():
        if old in df_raw.columns and new not in df_raw.columns:
            df_raw.rename(columns={old: new}, inplace=True)

    if "description" not in df_raw.columns:
        df_raw["description"] = df_raw["summary"]

    # Charger les projets et clients existants
    with get_db() as conn:
        projects_df = pd.read_sql_query("SELECT id, name, code, client_id FROM projects WHERE status = 'Actif'", conn)
        clients_df = pd.read_sql_query("SELECT id, name, code FROM clients WHERE is_active = 1", conn)

    # Dictionnaires de lookup insensibles à la casse
    proj_map_name = {r["name"].strip().lower(): r["id"] for _, r in projects_df.iterrows()}
    proj_map_code = {r["code"].strip().lower(): r["id"] for _, r in projects_df.iterrows()}
    client_map = {r["name"].strip().lower(): r["id"] for _, r in clients_df.iterrows()}

    # Validation ligne par ligne
    validation_status = []
    resolved_rows = []

    for idx, row in df_raw.iterrows():
        errors = []
        summary_val = str(row.get("summary") or "").strip()
        if not summary_val or summary_val.lower() == "nan":
            errors.append("Titre manquant")

        # Résolution projet
        proj_val = str(row.get("project") or "").strip()
        matched_pid = proj_map_name.get(proj_val.lower()) or proj_map_code.get(proj_val.lower())
        if not matched_pid:
            errors.append(f"Projet '{proj_val}' inconnu")

        # Résolution client
        client_val = str(row.get("client") or "").strip()
        matched_cid = client_map.get(client_val.lower()) if client_val and client_val.lower() != "nan" else None
        
        # Si aucun client spécifié mais le projet en a un
        if not matched_cid and matched_pid:
            p_client = projects_df[projects_df["id"] == matched_pid]["client_id"].values[0]
            if pd.notna(p_client):
                matched_cid = int(p_client)

        status_text = "✅ Valide" if not errors else f"❌ {', '.join(errors)}"
        validation_status.append(status_text)

        resolved_rows.append({
            "line": idx + 1,
            "summary": summary_val,
            "description": str(row.get("description") or summary_val).strip(),
            "project_id": matched_pid,
            "client_id": matched_cid,
            "category": str(row.get("category") or "Général").strip(),
            "priority": str(row.get("priority") or "Normale").strip(),
            "severity": str(row.get("severity") or "Mineure").strip(),
            "qualification_client": str(row.get("qualification_client") or "Non qualifié").strip(),
            "qualification_cegid": str(row.get("qualification_cegid") or "Non qualifié").strip(),
            "steps_to_reproduce": str(row.get("steps_to_reproduce") or "").strip() if pd.notna(row.get("steps_to_reproduce")) else "",
            "estimated_hours": float(row.get("estimated_hours") or 0.0) if pd.notna(row.get("estimated_hours")) else 0.0,
            "is_valid": len(errors) == 0,
            "errors": errors
        })

    df_preview = df_raw.copy()
    df_preview.insert(0, "Statut Validation", validation_status)

    valid_count = sum(1 for r in resolved_rows if r["is_valid"])
    invalid_count = len(resolved_rows) - valid_count

    st.markdown(f"#### 🔍 Aperçu de la validation : **{valid_count} ligne(s) valide(s)** / {invalid_count} erreur(s)")
    st.dataframe(df_preview, use_container_width=True, hide_index=True)

    if valid_count == 0:
        st.error("Aucune ligne valide à importer. Veuillez corriger votre fichier selon les indications ci-dessus.")
        return

    # Bouton de lancement de l'import
    st.markdown("---")
    col_act1, col_act2 = st.columns([2, 1])
    with col_act1:
        skip_invalid = st.checkbox("Ignorer les lignes en erreur et importer uniquement les lignes valides", value=True)

    with col_act2:
        btn_start_import = st.button(
            f"🚀 Importer {valid_count} ticket(s)",
            type="primary",
            use_container_width=True,
            disabled=(invalid_count > 0 and not skip_invalid)
        )

    if btn_start_import:
        imported_success = 0
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        with get_db() as conn:
            cursor = conn.cursor()
            for r in resolved_rows:
                if not r["is_valid"] and skip_invalid:
                    continue
                if not r["is_valid"]:
                    continue

                # Génération numéro Mantis
                t_number = generate_next_ticket_number()

                cursor.execute("""
                    INSERT INTO tickets (
                        ticket_number, project_id, client_id, category, reporter_id, assigned_id,
                        status, resolution, priority, severity, reproducibility,
                        qualification_client, qualification_cegid,
                        summary, description, steps_to_reproduce, additional_info,
                        estimated_hours, spent_hours, created_at, updated_at, closed_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    t_number, r["project_id"], r["client_id"], r["category"],
                    user["id"], None, "Nouveau", "Non résolu",
                    r["priority"], r["severity"], "Toujours",
                    r["qualification_client"], r["qualification_cegid"],
                    r["summary"], r["description"], r["steps_to_reproduce"], "Importé en masse via fichier",
                    r["estimated_hours"], 0.0, now_str, now_str, None
                ))
                new_tid = cursor.lastrowid
                log_ticket_history(conn, new_tid, user["id"], "Création", "", "Import en masse")
                imported_success += 1

                # Notification e-mail
                send_ticket_notification(
                    new_tid,
                    action_type="creation",
                    author_name=user["full_name"],
                    details=f"Créé via import en masse | Priorité : {r['priority']}"
                )

        if imported_success > 0:
            sync_all_to_sharepoint_async()

        st.success(f"🎉 Félicitations : {imported_success} ticket(s) ont été importés avec succès dans Mantis V2 !")
        if st.button("📋 Voir la liste des tickets ➔", type="primary"):
            st.session_state["current_page"] = "tickets_list"
            st.rerun()
