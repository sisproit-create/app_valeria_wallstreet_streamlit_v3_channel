# V2 profesional con interfaz Streamlit

## Archivos
- `app_valeria_wallstreet_streamlit.py` → dashboard principal
- `sistema_valeria_wallstreet.py` → versión base por consola

## Qué incluye esta V2
- Interfaz profesional en Streamlit
- Búsqueda manual en YouTube desde la app
- Guardado en SQLite
- Filtros por tema, canal y fechas
- Carga de links manuales de LinkedIn vía CSV
- Registro manual de links desde la interfaz
- Ranking de temas
- Exportación CSV
- Generación de reporte HTML

## Instalación
```bash
pip install streamlit pandas requests
```

## Ejecución
```bash
streamlit run app_valeria_wallstreet_streamlit.py
```

## API oficial de YouTube
Si quieres mejor resultado, configura una API key:

### Windows
```bash
set YOUTUBE_API_KEY=TU_API_KEY
streamlit run app_valeria_wallstreet_streamlit.py
```

### macOS / Linux
```bash
export YOUTUBE_API_KEY=TU_API_KEY
streamlit run app_valeria_wallstreet_streamlit.py
```

## CSV para links manuales
Puedes subir un CSV con este formato:

```csv
title,url,note
Jueves negro en Wall Street,https://es.linkedin.com/posts/...,Post público
Cierre de Wall Street,https://www.linkedin.com/posts/...,Valeria Gómez
```

## Estructura esperada
La app crea automáticamente:
- `data/valeria_wallstreet.db`
- `reports/`
- `data/manual_links.csv` si decides gestionarlo manualmente aparte

## Idea para V3
- análisis de palabras clave
- score de sentimiento macro
- alertas por email
- resumen diario automático
- conexión con tu dashboard de trading
