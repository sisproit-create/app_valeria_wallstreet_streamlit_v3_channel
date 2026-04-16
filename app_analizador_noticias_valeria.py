
import re
import sqlite3
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

DB_PATH = Path("valeria_news_analyzer.db")

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS analyses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT,
            source TEXT,
            title TEXT,
            raw_text TEXT,
            cleaned_text TEXT,
            sentiment TEXT,
            risk_mode TEXT,
            confidence INTEGER,
            summary TEXT,
            implications TEXT,
            setups TEXT,
            glossary_json TEXT,
            signals_json TEXT,
            themes_json TEXT
        )
    """)
    conn.commit()
    conn.close()

def save_analysis(payload: dict):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO analyses (
            created_at, source, title, raw_text, cleaned_text,
            sentiment, risk_mode, confidence, summary, implications,
            setups, glossary_json, signals_json, themes_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        payload["created_at"],
        payload["source"],
        payload["title"],
        payload["raw_text"],
        payload["cleaned_text"],
        payload["sentiment"],
        payload["risk_mode"],
        payload["confidence"],
        payload["summary"],
        payload["implications"],
        payload["setups"],
        payload["glossary_json"],
        payload["signals_json"],
        payload["themes_json"],
    ))
    conn.commit()
    conn.close()

def load_history() -> pd.DataFrame:
    conn = sqlite3.connect(DB_PATH)
    try:
        df = pd.read_sql_query(
            "SELECT id, created_at, source, title, sentiment, risk_mode, confidence, summary FROM analyses ORDER BY id DESC",
            conn
        )
    finally:
        conn.close()
    return df

def load_full_record(record_id: int):
    conn = sqlite3.connect(DB_PATH)
    try:
        df = pd.read_sql_query(
            "SELECT * FROM analyses WHERE id = ?",
            conn,
            params=(record_id,)
        )
    finally:
        conn.close()
    return df.iloc[0].to_dict() if not df.empty else None

GLOSSARY = {
    "tipos de interés": "Costo del dinero fijado o influido por el banco central. Si suben, suele haber menos liquidez.",
    "rendimientos del tesoro": "Rentabilidad de los bonos del gobierno de EE.UU. Si suben fuerte, suelen presionar acciones.",
    "high yield": "Bonos corporativos de mayor riesgo. Pagan más, pero son sensibles a miedo financiero.",
    "spread": "Diferencia de rendimiento entre un bono riesgoso y uno más seguro.",
    "risk-off": "Mercado defensivo. El dinero sale de activos riesgosos y entra a refugios.",
    "risk-on": "Mercado con apetito por riesgo. El dinero entra a acciones, tecnológicas o cripto.",
    "liquidez": "Facilidad y disponibilidad de dinero en el sistema financiero.",
    "inflación": "Subida persistente de precios. Puede obligar a tasas más altas.",
    "fed": "Reserva Federal de EE.UU., clave para tasas y liquidez.",
    "tesoro": "Deuda emitida por el gobierno de EE.UU., usada como referencia de seguridad.",
    "bonos corporativos": "Deuda emitida por empresas para financiarse.",
    "deuda corporativa": "Obligaciones financieras de empresas en el mercado.",
    "volatilidad": "Intensidad de los movimientos del mercado.",
    "recesión": "Desaceleración fuerte de la economía.",
    "disrupción": "Cambio que altera un sector o modelo de negocio existente.",
    "inteligencia artificial": "Tecnología que puede beneficiar a unos sectores y perjudicar a otros.",
    "apetito por riesgo": "Disposición de los inversionistas a comprar activos más volátiles.",
    "ajuste ordenado": "Caída o deterioro sin señales de pánico total.",
    "pánico financiero": "Venta acelerada y desordenada por miedo extremo."
}

THEME_PATTERNS = {
    "Fed / tasas": [r"\bfed\b", r"tipos de interés", r"tasas", r"banco central", r"política monetaria"],
    "Bonos / rendimiento": [r"rendimientos? del tesoro", r"\btreasury\b", r"\bbonos?\b", r"yield", r"rentabilidades"],
    "Crédito corporativo": [r"deuda corporativa", r"bonos corporativos", r"high yield", r"grado de inversión", r"spread"],
    "Riesgo de mercado": [r"risk[- ]off", r"risk[- ]on", r"apetito por el riesgo", r"miedo", r"aversión al riesgo"],
    "IA / disrupción": [r"inteligencia artificial", r"\bia\b", r"disrupción", r"boom de la inteligencia artificial"],
    "Inflación / petróleo": [r"inflación", r"petróleo", r"crudo", r"energía", r"commodities"],
    "Acciones / Wall Street": [r"wall street", r"s&p", r"nasdaq", r"dow", r"acciones", r"bolsa"],
    "Refugios": [r"oro", r"dólar", r"tesoro", r"activos de refugio", r"activos seguros"],
}

POSITIVE_MARKERS = [
    "rebote", "mejora", "alivio", "optimismo", "sube", "subida ordenada",
    "ajuste ordenado", "sin pánico", "confianza", "fortaleza", "apoya"
]

NEGATIVE_MARKERS = [
    "cae", "caída", "presión", "temor", "miedo", "en negativo", "peor trimestre",
    "disrupción", "enfría", "pánico", "deterioro", "aversión al riesgo", "estrés",
    "volatilidad", "default", "debilidad", "ventas"
]

RISK_OFF_MARKERS = [
    "bonos del tesoro", "oro", "dólar", "miedo", "temor", "aversión al riesgo",
    "risk-off", "caída", "high yield en negativo", "rendimientos del tesoro"
]

RISK_ON_MARKERS = [
    "risk-on", "rebote", "optimismo", "liquidez", "confianza", "mejora",
    "subida de acciones", "apetito por riesgo"
]

def normalize_text(text: str) -> str:
    text = text.strip()
    text = re.sub(r"\s+", " ", text)
    return text

def find_glossary_terms(text: str):
    found = {}
    lower = text.lower()
    for term, meaning in GLOSSARY.items():
        if term in lower:
            found[term] = meaning
    return found

def detect_themes(text: str):
    found = []
    lower = text.lower()
    for theme, patterns in THEME_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, lower):
                found.append(theme)
                break
    return found

def score_markers(text: str, markers):
    lower = text.lower()
    return sum(lower.count(m) for m in markers)

def infer_sentiment_and_risk(text: str):
    pos = score_markers(text, POSITIVE_MARKERS)
    neg = score_markers(text, NEGATIVE_MARKERS)
    risk_off = score_markers(text, RISK_OFF_MARKERS)
    risk_on = score_markers(text, RISK_ON_MARKERS)

    if neg > pos + 1:
        sentiment = "Bearish"
    elif pos > neg + 1:
        sentiment = "Bullish"
    else:
        sentiment = "Neutral / Mixto"

    if risk_off > risk_on + 1:
        risk_mode = "Risk-Off"
    elif risk_on > risk_off + 1:
        risk_mode = "Risk-On"
    else:
        risk_mode = "Mixto / Transición"

    total = pos + neg + risk_off + risk_on
    confidence = min(95, 45 + total * 6)
    return sentiment, risk_mode, confidence

def extract_signals(text: str):
    lower = text.lower()
    signals = []

    def add_if(condition, title, meaning, trading):
        if condition:
            signals.append({
                "señal": title,
                "qué_significa": meaning,
                "lectura_trading": trading
            })

    add_if("high yield" in lower or "alto rendimiento" in lower,
           "Deterioro en high yield",
           "El mercado exige más prima para prestar a empresas más riesgosas.",
           "Cuidado con activos de riesgo; suelen sufrir primero los nombres más débiles.")

    add_if("rendimientos del tesoro" in lower or "rentabilidades" in lower or "yield" in lower,
           "Subida de yields",
           "Sube el costo del dinero y compite contra acciones.",
           "Suele presionar tecnológicas y múltiplos altos.")

    add_if("sin pánico" in lower or "ajuste ordenado" in lower,
           "No hay capitulación",
           "Hay deterioro, pero todavía no es un evento de venta forzada descontrolada.",
           "Favorece rebotes tácticos, aunque no implica cambio de tendencia.")

    add_if("inteligencia artificial" in lower or "ia" in lower,
           "Disrupción por IA",
           "El mercado teme ganadores y perdedores por cambios tecnológicos rápidos.",
           "Puede generar rotación sectorial, no necesariamente caída total de mercado.")

    add_if("apetito por el riesgo" in lower or "activos de riesgo" in lower,
           "Menor apetito por riesgo",
           "Los inversionistas se vuelven más defensivos.",
           "Menos persecución de rallies; más selectividad.")

    return signals

def build_summary(text: str, sentiment: str, risk_mode: str, themes):
    lower = text.lower()
    pieces = []

    if "deuda corporativa" in lower:
        pieces.append("La noticia apunta a deterioro en el crédito corporativo estadounidense.")
    if "high yield" in lower or "alto rendimiento" in lower:
        pieces.append("Los bonos de empresas más riesgosas están bajo presión y pierden atractivo.")
    if "rendimientos del tesoro" in lower or "rentabilidades" in lower:
        pieces.append("El repunte de los rendimientos del Tesoro endurece las condiciones financieras.")
    if "inteligencia artificial" in lower or "ia" in lower:
        pieces.append("También aparece el riesgo de disrupción por inteligencia artificial y rotación sectorial.")
    if "sin pánico" in lower or "ajuste ordenado" in lower:
        pieces.append("El movimiento parece una corrección ordenada, no un pánico financiero pleno.")

    if not pieces:
        pieces.append("La noticia mezcla mercado, macro y flujo de dinero entre activos de riesgo y refugio.")

    pieces.append(f"Sesgo detectado: {sentiment}. Régimen de mercado: {risk_mode}.")
    if themes:
        pieces.append("Temas dominantes: " + ", ".join(themes) + ".")
    return " ".join(pieces)

def build_implications(text: str, sentiment: str, risk_mode: str):
    lower = text.lower()
    notes = []

    if "high yield" in lower:
        notes.append("Si el high yield empeora, puede anticipar más debilidad en acciones cíclicas y nombres especulativos.")
    if "rendimientos del tesoro" in lower or "rentabilidades" in lower:
        notes.append("Yields al alza suelen castigar valoraciones altas, sobre todo tecnología.")
    if "oro" in lower or "tesoro" in lower:
        notes.append("Flujo hacia refugios suele reforzar el modo defensivo.")
    if "ajuste ordenado" in lower:
        notes.append("Un ajuste ordenado permite rebotes tácticos, pero no invalida la prudencia.")
    if not notes:
        notes.append("La clave es distinguir si la noticia implica miedo real de crédito o solo una rotación temporal.")

    notes.append(f"Lectura base: {risk_mode}.")
    return " ".join(notes)

def build_setups(sentiment: str, risk_mode: str):
    if risk_mode == "Risk-Off" and sentiment == "Bearish":
        return (
            "Setup A: buscar rechazo en resistencias, VWAP o rebotes débiles. "
            "Setup B: evitar perseguir largos salvo recuperación clara con volumen. "
            "Setup C: vigilar capitulación si aparecen señales de pánico real."
        )
    if risk_mode == "Risk-On" and sentiment == "Bullish":
        return (
            "Setup A: continuación alcista en líderes. "
            "Setup B: compra en retrocesos controlados hacia soportes. "
            "Setup C: ruptura con confirmación de volumen."
        )
    return (
        "Setup A: esperar confirmación antes de entrar. "
        "Setup B: operar solo niveles claros. "
        "Setup C: reducir tamaño y evitar sobreinterpretar titulares aislados."
    )

def analyze_text(raw_text: str, source: str, title: str):
    cleaned = normalize_text(raw_text)
    themes = detect_themes(cleaned)
    glossary = find_glossary_terms(cleaned)
    sentiment, risk_mode, confidence = infer_sentiment_and_risk(cleaned)
    signals = extract_signals(cleaned)

    summary = build_summary(cleaned, sentiment, risk_mode, themes)
    implications = build_implications(cleaned, sentiment, risk_mode)
    setups = build_setups(sentiment, risk_mode)

    payload = {
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source": source,
        "title": title.strip() or "Sin título",
        "raw_text": raw_text,
        "cleaned_text": cleaned,
        "sentiment": sentiment,
        "risk_mode": risk_mode,
        "confidence": confidence,
        "summary": summary,
        "implications": implications,
        "setups": setups,
        "glossary_json": pd.Series(glossary).to_json(force_ascii=False),
        "signals_json": pd.DataFrame(signals).to_json(force_ascii=False, orient="records"),
        "themes_json": pd.Series(themes).to_json(force_ascii=False),
    }
    return payload

def export_history_to_csv():
    df = load_history()
    out = Path("analisis_valeria_historial.csv")
    df.to_csv(out, index=False, encoding="utf-8-sig")
    return out

st.set_page_config(
    page_title="Analizador Automático de Noticias tipo Valeria",
    page_icon="📊",
    layout="wide"
)

init_db()

st.title("📊 Analizador Automático de Noticias tipo Valeria")
st.caption("Pega un titular, párrafo o transcripción y el sistema interpreta el contexto macro, crédito, riesgo y lectura de trading.")

tab1, tab2, tab3 = st.tabs(["🧠 Analizar noticia", "📚 Historial", "📘 Guía rápida"])

with tab1:
    col_a, col_b = st.columns([2, 1])

    with col_a:
        source = st.text_input("Fuente", value="Valeria / Negocios TV")
        title = st.text_input("Título o referencia", value="")
        raw_text = st.text_area(
            "Pega aquí la noticia, frase o transcripción",
            height=250,
            placeholder="Ejemplo: La deuda corporativa estadounidense vive su peor trimestre desde 2022..."
        )

        analyze_btn = st.button("Analizar", type="primary", use_container_width=True)

    with col_b:
        st.markdown("### Ideas que detecta")
        st.markdown(
            "- Sesgo: bullish / bearish / mixto\n"
            "- Régimen: risk-on / risk-off\n"
            "- Temas: Fed, bonos, high yield, IA, inflación\n"
            "- Glosario automático\n"
            "- Lectura operativa tipo Setup A/B/C"
        )

    if analyze_btn:
        if not raw_text.strip():
            st.warning("Pega primero una noticia o transcripción.")
        else:
            result = analyze_text(raw_text, source, title)
            save_analysis(result)

            st.success("Análisis guardado correctamente.")

            c1, c2, c3 = st.columns(3)
            c1.metric("Sesgo", result["sentiment"])
            c2.metric("Régimen", result["risk_mode"])
            c3.metric("Confianza", f'{result["confidence"]}%')

            st.markdown("## 🧠 Resumen inteligente")
            st.write(result["summary"])

            st.markdown("## 📊 Implicaciones de mercado")
            st.write(result["implications"])

            st.markdown("## 🎯 Setup operativo")
            st.write(result["setups"])

            st.markdown("## 🧩 Temas detectados")
            themes = pd.read_json(result["themes_json"], typ="series")
            if len(themes) > 0:
                for t in themes.tolist():
                    st.markdown(f"- {t}")
            else:
                st.write("No se detectaron temas dominantes.")

            st.markdown("## 🚨 Señales clave")
            signals_df = pd.read_json(result["signals_json"])
            if not signals_df.empty:
                st.dataframe(signals_df, use_container_width=True, hide_index=True)
            else:
                st.write("No se detectaron señales específicas.")

            st.markdown("## 📘 Glosario encontrado")
            glossary_series = pd.read_json(result["glossary_json"], typ="series")
            if len(glossary_series) > 0:
                glossary_df = glossary_series.reset_index()
                glossary_df.columns = ["Término", "Significado"]
                st.dataframe(glossary_df, use_container_width=True, hide_index=True)
            else:
                st.write("No se detectaron términos del glosario en este texto.")

with tab2:
    history = load_history()
    if history.empty:
        st.info("Aún no hay análisis guardados.")
    else:
        st.dataframe(history, use_container_width=True, hide_index=True)

        col1, col2 = st.columns([1, 1])
        with col1:
            selected_id = st.number_input(
                "ID para ver detalle",
                min_value=int(history["id"].min()),
                max_value=int(history["id"].max()),
                value=int(history["id"].max())
            )
        with col2:
            if st.button("Exportar historial a CSV", use_container_width=True):
                out = export_history_to_csv()
                st.success(f"CSV exportado: {out}")

        detail = load_full_record(int(selected_id))
        if detail:
            st.markdown("---")
            st.markdown(f"## Detalle del análisis #{detail['id']}")
            st.write(f"**Fecha:** {detail['created_at']}")
            st.write(f"**Fuente:** {detail['source']}")
            st.write(f"**Título:** {detail['title']}")
            st.write(f"**Sesgo:** {detail['sentiment']} | **Régimen:** {detail['risk_mode']} | **Confianza:** {detail['confidence']}%")

            st.markdown("### Texto original")
            st.write(detail["raw_text"])

            st.markdown("### Resumen")
            st.write(detail["summary"])

            st.markdown("### Implicaciones")
            st.write(detail["implications"])

            st.markdown("### Setups")
            st.write(detail["setups"])

with tab3:
    st.markdown("""
### Cómo usarlo bien

1. Pega una frase o párrafo del video o noticia.  
2. El sistema detecta si el mensaje es defensivo, alcista o mixto.  
3. Traduce el lenguaje financiero a lectura operativa.  
4. Guarda el análisis para que puedas comparar narrativas con el tiempo.

### Qué interpreta mejor
- Crédito corporativo
- Bonos y rendimientos
- Fed y tipos de interés
- Riesgo / refugio
- IA como factor de rotación o disrupción

### Limitaciones
- Es un analizador basado en reglas, no un modelo entrenado con audio o video.
- Funciona mejor con texto ya transcrito o párrafos claros.
- No sustituye validación con precio, volumen y contexto del mercado.
""")
