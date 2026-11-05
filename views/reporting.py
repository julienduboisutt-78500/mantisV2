import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from database import get_db, STATUS_COLORS, PRIORITY_COLORS, SEVERITY_COLORS
from auth import get_current_user, filter_tickets_query_for_user

def show_reporting():
    user = get_current_user()
    st.title("📈 Rapports & Analyse Décisionnelle (Reporting)")
    st.caption("Visualisez les indicateurs de performance, les métriques SLA et la charge de travail.")

    # Requête de base pour récupérer les données analytiques
    with get_db() as conn:
        base_query = """
            SELECT t.id, t.ticket_number, t.summary, t.status, t.priority, t.severity,
                   t.category, t.resolution, t.spent_hours,
                   t.created_at, t.updated_at, t.closed_at,
                   p.name as project_name,
                   parent_p.name as parent_project_name,
                   c.name as client_name,
                   u_rep.full_name as reporter_name,
                   COALESCE(u_ass.full_name, 'Non assigné') as assigned_name
            FROM tickets t
            JOIN projects p ON t.project_id = p.id
            LEFT JOIN projects parent_p ON p.parent_project_id = parent_p.id
            JOIN clients c ON t.client_id = c.id
            JOIN users u_rep ON t.reporter_id = u_rep.id
            LEFT JOIN users u_ass ON t.assigned_id = u_ass.id
        """
        query, params = filter_tickets_query_for_user(user, base_query, [])
        df = pd.read_sql_query(query, conn, params=params)

    if df.empty:
        st.info("Aucune donnée disponible pour générer les rapports.")
        return

    # Conversion des colonnes de dates
    df["created_dt"] = pd.to_datetime(df["created_at"])
    df["closed_dt"] = pd.to_datetime(df["closed_at"])
    
    # Filtres de reporting en haut
    f1, f2 = st.columns(2)
    with f1:
        clients_list = ["Tous"] + sorted(df["client_name"].unique().tolist())
        sel_client = st.selectbox("Filtrer par Client", clients_list, index=0)
    with f2:
        projects_list = ["Tous"] + sorted(df["project_name"].unique().tolist())
        sel_proj = st.selectbox("Filtrer par Projet", projects_list, index=0)

    filtered_df = df.copy()
    if sel_client != "Tous":
        filtered_df = filtered_df[filtered_df["client_name"] == sel_client]
    if sel_proj != "Tous":
        filtered_df = filtered_df[filtered_df["project_name"] == sel_proj]

    # KPIs globaux
    total_count = len(filtered_df)
    closed_count = len(filtered_df[filtered_df["status"].isin(["Résolu", "Fermé"])])
    resolution_rate = (closed_count / total_count * 100) if total_count > 0 else 0
    total_spent_hours = filtered_df["spent_hours"].sum()

    # Calcul du temps moyen de résolution (jours)
    closed_tickets = filtered_df[filtered_df["closed_dt"].notna()].copy()
    if not closed_tickets.empty:
        closed_tickets["duration_days"] = (closed_tickets["closed_dt"] - closed_tickets["created_dt"]).dt.total_seconds() / 86400.0
        avg_resolution_days = closed_tickets["duration_days"].mean()
    else:
        avg_resolution_days = 0

    k1, k2, k3, k4 = st.columns(4)
    with k1:
        st.metric("Total des tickets", total_count)
    with k2:
        st.metric("Taux de résolution", f"{resolution_rate:.1f} %")
    with k3:
        st.metric("Temps moyen de résolution", f"{avg_resolution_days:.1f} jours" if avg_resolution_days > 0 else "N/A")
    with k4:
        st.metric("Temps passé cumulé", f"{total_spent_hours:.1f} h")

    st.markdown("---")

    # 1. Deux premiers graphiques : Statut (Donut) & Sévérité/Priorité
    g1, g2 = st.columns(2)

    with g1:
        st.markdown("##### 🍩 Répartition par Statut")
        status_counts = filtered_df["status"].value_counts().reset_index()
        status_counts.columns = ["status", "count"]
        # Associer les couleurs Mantis
        color_map = {st_name: STATUS_COLORS.get(st_name, "#999999") for st_name in status_counts["status"]}
        fig_status = px.pie(
            status_counts,
            names="status",
            values="count",
            hole=0.45,
            color="status",
            color_discrete_map=color_map
        )
        fig_status.update_layout(margin=dict(t=10, b=10, l=10, r=10), legend_title="Statuts")
        st.plotly_chart(fig_status, use_container_width=True)

    with g2:
        st.markdown("##### ⚠️ Répartition par Sévérité & Priorité")
        sev_prio = filtered_df.groupby(["severity", "priority"]).size().reset_index(name="count")
        fig_sev = px.bar(
            sev_prio,
            x="severity",
            y="count",
            color="priority",
            barmode="stack",
            color_discrete_map=PRIORITY_COLORS,
            labels={"severity": "Sévérité", "count": "Nombre de tickets", "priority": "Priorité"}
        )
        fig_sev.update_layout(margin=dict(t=10, b=10, l=10, r=10))
        st.plotly_chart(fig_sev, use_container_width=True)

    # 2. Deuxième rangée : Répartition par Client & Charge par Développeur
    g3, g4 = st.columns(2)

    with g3:
        st.markdown("##### 🏢 Volume de tickets par Client")
        client_counts = filtered_df["client_name"].value_counts().reset_index()
        client_counts.columns = ["client_name", "count"]
        fig_client = px.bar(
            client_counts,
            x="count",
            y="client_name",
            orientation="h",
            color="count",
            color_continuous_scale="Blues",
            labels={"client_name": "Client", "count": "Tickets"}
        )
        fig_client.update_layout(margin=dict(t=10, b=10, l=10, r=10), showlegend=False)
        st.plotly_chart(fig_client, use_container_width=True)

    with g4:
        st.markdown("##### 👥 Charge de travail par Développeur / Assigné")
        dev_counts = filtered_df.groupby(["assigned_name", "status"]).size().reset_index(name="count")
        fig_dev = px.bar(
            dev_counts,
            x="assigned_name",
            y="count",
            color="status",
            barmode="stack",
            color_discrete_map=STATUS_COLORS,
            labels={"assigned_name": "Intervenant", "count": "Tickets", "status": "Statut"}
        )
        fig_dev.update_layout(margin=dict(t=10, b=10, l=10, r=10))
        st.plotly_chart(fig_dev, use_container_width=True)

    # 3. Répartition Hiérarchique Projet / Sous-projet
    st.markdown("##### 📁 Répartition Hiérarchique Projet > Sous-Projet")
    # Construire la hiérarchie pour le Sunburst ou Treemap
    filtered_df["parent_display"] = filtered_df["parent_project_name"].fillna(filtered_df["project_name"])
    filtered_df["sub_display"] = filtered_df.apply(
        lambda r: r["project_name"] if pd.notna(r["parent_project_name"]) else "Projet Principal",
        axis=1
    )
    
    sun_df = filtered_df.groupby(["parent_display", "sub_display", "status"]).size().reset_index(name="count")
    fig_sun = px.sunburst(
        sun_df,
        path=["parent_display", "sub_display", "status"],
        values="count",
        color="status",
        color_discrete_map=STATUS_COLORS
    )
    fig_sun.update_layout(margin=dict(t=10, b=10, l=10, r=10))
    st.plotly_chart(fig_sun, use_container_width=True)
