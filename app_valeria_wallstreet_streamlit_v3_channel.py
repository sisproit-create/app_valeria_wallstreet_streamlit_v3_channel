#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
V3 profesional con interfaz Streamlit
-------------------------------------
Dashboard para rastrear contenido de:
- Valeria Gómez
- Cierre de Wall Street
- Negocios TV

Funciones:
- Buscar videos de YouTube
- Buscar videos recientes de un canal completo
- Guardar en SQLite
- Filtrar por fecha / tema / plataforma
- Cargar links manuales de LinkedIn
- Exportar CSV
- Generar reporte HTML
- Ver métricas y ranking de temas

Ejecución:
    pip install streamlit pandas requests
    streamlit run app_valeria_wallstreet_streamlit.py
"""
from __future__ import annotations

import csv
import datetime as dt
import html
import io
import os
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List
from urllib.parse import quote_plus

import pandas as pd
import requests
import streamlit as st

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
REPORTS_DIR = BASE_DIR / "reports"
DB_PATH = DATA_DIR / "valeria_wallstreet.db"
MANUAL_LINKS_CSV = DATA_DIR / "manual_links.csv"

YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "").strip()
REQUEST_TIMEOUT = 25
MAX_RESULTS_PER_QUERY = 15
DEFAULT_CHANNEL_HANDLE = "@NegociosTV"

SEARCH_QUERIES = [
    'Valeria Gómez "Cierre de Wall Street" "Negocios TV"',
    '"Cierre de Wall Street" "Valeria Gómez"',
    '"Negocios TV" "Valeria Gómez" Wall Street',
]

THEME_KEYWORDS = {
    "Fed / Tasas": ["fed", "tasas", "powell", "fomc", "inflación", "inflacion"],
    "Oro / Dólar": ["oro", "gold", "dólar", "dolar", "usd", "divisa"],
    "Crudo / Energía": ["crudo", "oil", "petróleo", "petroleo", "energía", "energia"],
    "Bitcoin / Cripto": ["bitcoin", "btc", "ethereum", "eth", "cripto", "crypto"],
    "Geopolítica": ["iran", "israel", "china", "rusia", "guerra", "geopol"],
    "Bolsas / Índices": ["nasdaq", "s&p", "sp500", "dow", "wall street", "bolsas", "índices", "indices"],
    "Recesión / Macro": ["recesión", "recesion", "empleo", "macro", "pmi", "ipc", "cpi"],
}

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


@dataclass
class VideoItem:
    platform: str
    video_id: str
    title: str
    published_at: str
    url: str
    channel_title: str
    description: str
    theme: str
    source_query: str


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)


def get_db() -> sqlite3.Connection:
    ensure_dirs()
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            platform TEXT NOT NULL,
            external_id TEXT NOT NULL,
            title TEXT NOT NULL,
            published_at TEXT,
            url TEXT NOT NULL,
            channel_title TEXT,
            description TEXT,
            theme TEXT,
            source_query TEXT,
            inserted_at TEXT NOT NULL,
            UNIQUE(platform, external_id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS manual_links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            url TEXT NOT NULL UNIQUE,
            note TEXT,
            added_at TEXT NOT NULL
        )
        """
    )
    conn.commit()
    return conn


def html_unescape(text: str) -> str:
    return html.unescape(text or "")


def extract_tag(entry: str, tag: str, attr: str | None = None) -> str | None:
    if attr:
        m = re.search(rf"<{re.escape(tag)}[^>]*{re.escape(attr)}=\"([^\"]+)\"[^>]*/?>", entry)
        return m.group(1) if m else None
    m = re.search(rf"<{re.escape(tag)}>(.*?)</{re.escape(tag)}>", entry, flags=re.S)
    return m.group(1).strip() if m else None


def classify_theme(text: str) -> str:
    t = (text or "").lower()
    scores: Dict[str, int] = {}
    for theme, keywords in THEME_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in t)
        if score:
            scores[theme] = score
    if not scores:
        return "General"
    return sorted(scores.items(), key=lambda x: (-x[1], x[0]))[0][0]


def youtube_search_official(query: str, max_results: int = 10) -> List[VideoItem]:
    if not YOUTUBE_API_KEY:
        return []
    url = "https://www.googleapis.com/youtube/v3/search"
    params = {
        "part": "snippet",
        "q": query,
        "type": "video",
        "maxResults": max_results,
        "order": "date",
        "key": YOUTUBE_API_KEY,
        "relevanceLanguage": "es",
    }
    r = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
    r.raise_for_status()
    data = r.json()

    items: List[VideoItem] = []
    for item in data.get("items", []):
        video_id = item["id"]["videoId"]
        snippet = item.get("snippet", {})
        title = snippet.get("title", "").strip()
        desc = snippet.get("description", "").strip()
        published = snippet.get("publishedAt", "")
        channel_title = snippet.get("channelTitle", "").strip()
        theme = classify_theme(f"{title}\n{desc}")
        items.append(
            VideoItem(
                platform="youtube",
                video_id=video_id,
                title=title,
                published_at=published,
                url=f"https://www.youtube.com/watch?v={video_id}",
                channel_title=channel_title,
                description=desc,
                theme=theme,
                source_query=query,
            )
        )
    return items


def youtube_search_rss_fallback(query: str, max_results: int = 10) -> List[VideoItem]:
    rss_url = f"https://www.youtube.com/feeds/videos.xml?search_query={quote_plus(query)}"
    headers = {"User-Agent": USER_AGENT}
    r = requests.get(rss_url, headers=headers, timeout=REQUEST_TIMEOUT)
    r.raise_for_status()
    xml_text = r.text

    entries = re.findall(r"<entry>(.*?)</entry>", xml_text, flags=re.S)
    items: List[VideoItem] = []

    for entry in entries[:max_results]:
        video_id = extract_tag(entry, "yt:videoId") or ""
        title = html_unescape(extract_tag(entry, "title") or "")
        published = extract_tag(entry, "published") or ""
        channel_title = html_unescape(extract_tag(entry, "name") or "")
        url = extract_tag(entry, "link", attr="href") or f"https://www.youtube.com/watch?v={video_id}"
        desc = ""
        theme = classify_theme(title)
        if video_id:
            items.append(
                VideoItem(
                    platform="youtube",
                    video_id=video_id,
                    title=title,
                    published_at=published,
                    url=url,
                    channel_title=channel_title,
                    description=desc,
                    theme=theme,
                    source_query=query,
                )
            )
    return items




def resolve_channel_id_from_api(channel_input: str):
    if not YOUTUBE_API_KEY:
        return None

    channel_input = (channel_input or "").strip()
    handle = channel_input
    if handle.startswith("https://www.youtube.com/"):
        m = re.search(r"/(@[^/?]+)", handle)
        if m:
            handle = m.group(1)

    url = "https://www.googleapis.com/youtube/v3/search"
    params = {
        "part": "snippet",
        "q": handle,
        "type": "channel",
        "maxResults": 5,
        "key": YOUTUBE_API_KEY,
    }
    r = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
    r.raise_for_status()
    data = r.json()
    items = data.get("items", [])
    if items:
        channel_id = items[0]["id"]["channelId"]
        title = items[0].get("snippet", {}).get("title", channel_input)
        return channel_id, title
    return None


def fetch_channel_videos_api(channel_input: str, max_results: int = 30) -> List[VideoItem]:
    if not YOUTUBE_API_KEY:
        return []

    resolved = resolve_channel_id_from_api(channel_input)
    if not resolved:
        return []

    channel_id, resolved_title = resolved
    url = "https://www.googleapis.com/youtube/v3/search"
    params = {
        "part": "snippet",
        "channelId": channel_id,
        "type": "video",
        "order": "date",
        "maxResults": min(max_results, 50),
        "key": YOUTUBE_API_KEY,
    }
    r = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
    r.raise_for_status()
    data = r.json()

    items: List[VideoItem] = []
    for item in data.get("items", []):
        video_id = item["id"]["videoId"]
        snippet = item.get("snippet", {})
        title = snippet.get("title", "").strip()
        desc = snippet.get("description", "").strip()
        published = snippet.get("publishedAt", "")
        channel_title = snippet.get("channelTitle", "").strip() or resolved_title
        theme = classify_theme(f"{title}\n{desc}")
        items.append(
            VideoItem(
                platform="youtube",
                video_id=video_id,
                title=title,
                published_at=published,
                url=f"https://www.youtube.com/watch?v={video_id}",
                channel_title=channel_title,
                description=desc,
                theme=theme,
                source_query=f"CANAL: {channel_input}",
            )
        )
    return items


def collect_channel_videos(channel_input: str, max_results: int = 30) -> List[VideoItem]:
    try:
        items = fetch_channel_videos_api(channel_input, max_results=max_results)
    except Exception:
        items = []
    return sorted(items, key=lambda x: x.published_at or "", reverse=True)


def collect_all_queries() -> List[VideoItem]:
    all_items: List[VideoItem] = []
    seen = set()
    for query in SEARCH_QUERIES:
        try:
            items = youtube_search_official(query, MAX_RESULTS_PER_QUERY)
            if not items:
                items = youtube_search_rss_fallback(query, MAX_RESULTS_PER_QUERY)
        except Exception:
            items = []
        for item in items:
            key = (item.platform, item.video_id)
            if key not in seen:
                all_items.append(item)
                seen.add(key)
    return sorted(all_items, key=lambda x: x.published_at or "", reverse=True)


def save_items(items: List[VideoItem]) -> int:
    conn = get_db()
    inserted = 0
    now = dt.datetime.now().isoformat(timespec="seconds")
    for item in items:
        cur = conn.execute(
            """
            INSERT OR IGNORE INTO items
            (platform, external_id, title, published_at, url, channel_title,
             description, theme, source_query, inserted_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item.platform,
                item.video_id,
                item.title,
                item.published_at,
                item.url,
                item.channel_title,
                item.description,
                item.theme,
                item.source_query,
                now,
            ),
        )
        if cur.rowcount > 0:
            inserted += 1
    conn.commit()
    conn.close()
    return inserted


def load_items_df() -> pd.DataFrame:
    conn = get_db()
    df = pd.read_sql_query(
        """
        SELECT platform, external_id, title, published_at, url, channel_title,
               description, theme, source_query, inserted_at
        FROM items
        ORDER BY COALESCE(published_at, inserted_at) DESC
        """,
        conn,
    )
    conn.close()
    if not df.empty:
        df["published_at"] = pd.to_datetime(df["published_at"], errors="coerce")
        df["inserted_at"] = pd.to_datetime(df["inserted_at"], errors="coerce")
    return df


def load_manual_links_df() -> pd.DataFrame:
    conn = get_db()
    df = pd.read_sql_query(
        """
        SELECT title, url, note, added_at
        FROM manual_links
        ORDER BY added_at DESC
        """,
        conn,
    )
    conn.close()
    if not df.empty:
        df["added_at"] = pd.to_datetime(df["added_at"], errors="coerce")
    return df


def import_manual_links_from_csv(file_bytes: bytes) -> tuple[int, int]:
    text = file_bytes.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    conn = get_db()
    inserted = 0
    skipped = 0
    now = dt.datetime.now().isoformat(timespec="seconds")
    for row in reader:
        title = (row.get("title") or "").strip()
        url = (row.get("url") or "").strip()
        note = (row.get("note") or "").strip()
        if not title or not url:
            skipped += 1
            continue
        cur = conn.execute(
            "INSERT OR IGNORE INTO manual_links (title, url, note, added_at) VALUES (?, ?, ?, ?)",
            (title, url, note, now),
        )
        if cur.rowcount > 0:
            inserted += 1
        else:
            skipped += 1
    conn.commit()
    conn.close()
    return inserted, skipped


def add_single_manual_link(title: str, url: str, note: str) -> bool:
    conn = get_db()
    now = dt.datetime.now().isoformat(timespec="seconds")
    cur = conn.execute(
        "INSERT OR IGNORE INTO manual_links (title, url, note, added_at) VALUES (?, ?, ?, ?)",
        (title.strip(), url.strip(), note.strip(), now),
    )
    conn.commit()
    ok = cur.rowcount > 0
    conn.close()
    return ok


def generate_html_report(items_df: pd.DataFrame, manual_df: pd.DataFrame) -> Path:
    ensure_dirs()
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    path = REPORTS_DIR / f"dashboard_valeria_wallstreet_{stamp}.html"

    def render_table(df: pd.DataFrame, columns: List[str]) -> str:
        if df.empty:
            return "<p>Sin datos.</p>"
        rows = []
        for _, row in df.iterrows():
            cells = []
            for col in columns:
                value = row.get(col, "")
                if pd.isna(value):
                    value = ""
                if col == "url" and value:
                    value = f'<a href="{html.escape(str(value))}" target="_blank">Abrir</a>'
                else:
                    value = html.escape(str(value))
                cells.append(f"<td>{value}</td>")
            rows.append("<tr>" + "".join(cells) + "</tr>")
        headers = "".join(f"<th>{html.escape(c)}</th>" for c in columns)
        return f"<table><thead><tr>{headers}</tr></thead><tbody>{''.join(rows)}</tbody></table>"

    stats = {
        "items": len(items_df),
        "manual_links": len(manual_df),
        "themes": int(items_df["theme"].nunique()) if not items_df.empty else 0,
        "channels": int(items_df["channel_title"].nunique()) if not items_df.empty else 0,
    }

    theme_block = "<p>Sin datos.</p>"
    if not items_df.empty:
        theme_counts = items_df["theme"].fillna("General").value_counts().reset_index()
        theme_counts.columns = ["Tema", "Cantidad"]
        theme_block = render_table(theme_counts, ["Tema", "Cantidad"])

    html_doc = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<title>Dashboard Valeria + Wall Street</title>
<style>
body {{ font-family: Arial, sans-serif; margin: 24px; background:#0f172a; color:#e5e7eb; }}
h1,h2,h3 {{ color:#f8fafc; }}
.card {{ display:inline-block; min-width:200px; margin:8px; padding:16px; border-radius:14px; background:#111827; border:1px solid #334155; }}
table {{ width:100%; border-collapse:collapse; margin-top:12px; background:#111827; }}
th, td {{ border:1px solid #334155; padding:10px; text-align:left; vertical-align:top; }}
th {{ background:#1f2937; }}
a {{ color:#93c5fd; }}
small {{ color:#94a3b8; }}
</style>
</head>
<body>
<h1>Dashboard Valeria + Wall Street</h1>
<p><small>Generado: {dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</small></p>

<div class="card"><h3>Items</h3><p>{stats["items"]}</p></div>
<div class="card"><h3>Links manuales</h3><p>{stats["manual_links"]}</p></div>
<div class="card"><h3>Temas</h3><p>{stats["themes"]}</p></div>
<div class="card"><h3>Canales</h3><p>{stats["channels"]}</p></div>

<h2>Ranking de temas</h2>
{theme_block}

<h2>Videos / publicaciones guardadas</h2>
{render_table(items_df.fillna(""), ["platform", "title", "published_at", "channel_title", "theme", "url"])}

<h2>Links manuales</h2>
{render_table(manual_df.fillna(""), ["title", "url", "note", "added_at"])}
</body>
</html>"""
    path.write_text(html_doc, encoding="utf-8")
    return path


def to_csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8-sig")


def apply_filters(df: pd.DataFrame, theme_filter: str, channel_filter: str, date_from, date_to) -> pd.DataFrame:
    out = df.copy()
    if out.empty:
        return out
    if theme_filter != "Todos":
        out = out[out["theme"].fillna("General") == theme_filter]
    if channel_filter != "Todos":
        out = out[out["channel_title"].fillna("") == channel_filter]
    if date_from is not None:
        out = out[out["published_at"].dt.date >= date_from]
    if date_to is not None:
        out = out[out["published_at"].dt.date <= date_to]
    return out



def extract_video_id(url: str) -> str:
    import re
    if not url:
        return ""
    m = re.search(r"[?&]v=([^&]+)", str(url))
    if m:
        return m.group(1)
    m = re.search(r"youtu\.be/([^?&/]+)", str(url))
    if m:
        return m.group(1)
    return ""


def render_video_preview(df):
    if df.empty:
        return

    st.markdown("## ▶️ Vista previa del video")

    opciones = df["title"].fillna("Video").tolist()
    selected = st.selectbox("Selecciona un video", opciones, key="preview_video_select")

    row = df[df["title"] == selected].iloc[0]

    st.write(f"**Título:** {row['title']}")
    st.write(f"**Canal:** {row['channel_title']}")

    video_id = extract_video_id(row["url"])

    if video_id:
        st.video(f"https://www.youtube.com/watch?v={video_id}")
    else:
        st.link_button("Abrir video", row["url"], use_container_width=True)


def render_open_buttons(df, limit: int = 15):
    if df.empty:
        return

    st.markdown("### 🔗 Abrir directo (modo móvil)")

    for _, row in df.head(limit).iterrows():
        col1, col2 = st.columns([5,1])

        col1.write(row["title"])

        col2.link_button(
            "Abrir",
            row["url"],
            use_container_width=True
        )


def main() -> None:
    st.set_page_config(page_title="Valeria + Wall Street", layout="wide")
    ensure_dirs()

    st.title("📺 Valeria + Wall Street — V3 con búsqueda por canal")
    st.caption("Monitoreo, base de datos, filtros, reporte HTML, búsquedas por consulta y videos recientes de un canal completo.")

    with st.sidebar:
        st.header("⚙️ Control")

        st.subheader("🔎 Búsqueda por consultas")
        if st.button("🔄 Buscar ahora en YouTube", use_container_width=True):
            with st.spinner("Buscando contenido..."):
                items = collect_all_queries()
                inserted = save_items(items)
            st.success(f"Búsqueda terminada. Encontrados: {len(items)} | Nuevos guardados: {inserted}")

        st.markdown("---")
        st.subheader("📺 Buscar videos del canal")
        channel_input = st.text_input("Canal objetivo", value=DEFAULT_CHANNEL_HANDLE, help="Puedes usar @NegociosTV, el nombre del canal o la URL del canal.")
        max_channel_results = st.slider("Cantidad de videos del canal", min_value=10, max_value=50, value=30, step=10)
        if st.button("📥 Buscar videos del canal", use_container_width=True):
            with st.spinner("Buscando videos del canal..."):
                channel_items = collect_channel_videos(channel_input, max_results=max_channel_results)
                inserted = save_items(channel_items)
            st.success(f"Canal procesado. Encontrados: {len(channel_items)} | Nuevos guardados: {inserted}")

        st.caption("Recomendado para este caso: @NegociosTV")

        st.markdown("---")
        st.subheader("📥 Importar links manuales")
        upload = st.file_uploader("Sube CSV de LinkedIn u otros links públicos", type=["csv"])
        if upload is not None:
            inserted, skipped = import_manual_links_from_csv(upload.getvalue())
            st.success(f"Importados: {inserted} | Omitidos: {skipped}")

        st.markdown("Formato CSV:")
        st.code("title,url,note", language="csv")

    items_df = load_items_df()
    manual_df = load_manual_links_df()

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Items guardados", len(items_df))
    col2.metric("Links manuales", len(manual_df))
    col3.metric("Temas detectados", int(items_df['theme'].nunique()) if not items_df.empty else 0)
    col4.metric("Canales", int(items_df['channel_title'].nunique()) if not items_df.empty else 0)

    st.markdown("## 📌 Filtros")
    left, mid, right, far = st.columns(4)
    themes = ["Todos"] + sorted(items_df["theme"].fillna("General").unique().tolist()) if not items_df.empty else ["Todos"]
    channels = ["Todos"] + sorted([c for c in items_df["channel_title"].fillna("").unique().tolist() if c]) if not items_df.empty else ["Todos"]

    theme_filter = left.selectbox("Tema", themes)
    channel_filter = mid.selectbox("Canal", channels)
    date_from = right.date_input("Desde", value=None)
    date_to = far.date_input("Hasta", value=None)

    filtered_df = apply_filters(items_df, theme_filter, channel_filter, date_from, date_to)

    tab1, tab2, tab3, tab4 = st.tabs(["🎥 Contenido", "📊 Temas", "🔗 Links manuales", "📄 Reporte"])

    with tab1:
        st.subheader("Contenido guardado")
        if filtered_df.empty:
            st.info("No hay registros todavía.")
        else:
            render_video_preview(filtered_df)
            show_df = filtered_df.copy()
            if "published_at" in show_df.columns:
                show_df["published_at"] = show_df["published_at"].dt.strftime("%Y-%m-%d %H:%M").fillna("")
            if "inserted_at" in show_df.columns:
                show_df["inserted_at"] = show_df["inserted_at"].dt.strftime("%Y-%m-%d %H:%M").fillna("")
            st.dataframe(
                show_df[["platform", "title", "published_at", "channel_title", "theme", "url", "source_query"]],
                use_container_width=True,
                hide_index=True,
            )
            render_open_buttons(filtered_df, limit=15)
            st.download_button(
                "⬇️ Descargar CSV filtrado",
                data=to_csv_bytes(show_df),
                file_name="valeria_wallstreet_filtrado.csv",
                mime="text/csv",
                use_container_width=True,
            )

    with tab2:
        st.subheader("Ranking de temas")
        if filtered_df.empty:
            st.info("Sin datos para graficar.")
        else:
            theme_counts = filtered_df["theme"].fillna("General").value_counts()
            st.bar_chart(theme_counts)
            st.dataframe(
                theme_counts.reset_index().rename(columns={"index": "Tema", "theme": "Cantidad"}),
                use_container_width=True,
                hide_index=True,
            )

    with tab3:
        st.subheader("Links manuales")
        form1, form2, form3 = st.columns([3, 3, 2])
        with st.form("manual_link_form", clear_on_submit=True):
            title = form1.text_input("Título")
            url = form2.text_input("URL")
            note = form3.text_input("Nota")
            submitted = st.form_submit_button("Guardar link manual")
            if submitted:
                if title and url:
                    ok = add_single_manual_link(title, url, note)
                    if ok:
                        st.success("Link guardado.")
                    else:
                        st.warning("Ese link ya existía o no se pudo guardar.")
                else:
                    st.error("Completa título y URL.")

        manual_df = load_manual_links_df()
        if manual_df.empty:
            st.info("No hay links manuales.")
        else:
            view_manual = manual_df.copy()
            view_manual["added_at"] = view_manual["added_at"].dt.strftime("%Y-%m-%d %H:%M").fillna("")
            st.dataframe(view_manual, use_container_width=True, hide_index=True)
            st.download_button(
                "⬇️ Descargar CSV de links manuales",
                data=to_csv_bytes(view_manual),
                file_name="links_manuales_valeria.csv",
                mime="text/csv",
                use_container_width=True,
            )

    with tab4:
        st.subheader("Generar reporte HTML")
        st.write("Crea un reporte listo para abrir en navegador o compartir internamente.")
        if st.button("🧾 Generar reporte ahora", use_container_width=True):
            path = generate_html_report(filtered_df, manual_df)
            st.success(f"Reporte generado: {path.name}")
            html_bytes = path.read_bytes()
            st.download_button(
                "⬇️ Descargar reporte HTML",
                data=html_bytes,
                file_name=path.name,
                mime="text/html",
                use_container_width=True,
            )
        st.markdown("### Recomendación")
        st.write("Usa la búsqueda por consultas para Valeria y la búsqueda por canal para traer más videos de Negocios TV u otros canales.")

    st.markdown("---")
    st.markdown("### 🚀 Cómo ejecutar")
    st.code("pip install streamlit pandas requests\nstreamlit run app_valeria_wallstreet_streamlit.py", language="bash")
    if not YOUTUBE_API_KEY:
        st.warning("No detecté YOUTUBE_API_KEY. La búsqueda por canal requiere la API oficial de YouTube para funcionar correctamente.")


if __name__ == "__main__":
    main()
