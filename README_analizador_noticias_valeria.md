
# Analizador Automático de Noticias tipo Valeria

Esta versión te permite pegar frases, párrafos o transcripciones de noticias y obtener:

- Sesgo: Bullish / Bearish / Mixto
- Régimen: Risk-On / Risk-Off / Transición
- Resumen inteligente
- Implicaciones de mercado
- Setup operativo tipo A/B/C
- Glosario automático
- Historial en SQLite
- Exportación a CSV

## Instalación

```bash
pip install streamlit pandas
streamlit run app_analizador_noticias_valeria.py
```

## Archivos

- app_analizador_noticias_valeria.py
- Base de datos automática: valeria_news_analyzer.db
- Exportación CSV: analisis_valeria_historial.csv

## Cómo usarlo

1. Abre la app.
2. Pega la noticia o transcripción.
3. Haz clic en Analizar.
4. Revisa el resumen, las señales y el setup.
5. Consulta el historial para comparar distintas narrativas.

## Mejora futura sugerida

La V2 futura puede incluir:
- carga directa de URL de YouTube
- transcripción automática
- score macro diario
- integración con tu dashboard de trading
