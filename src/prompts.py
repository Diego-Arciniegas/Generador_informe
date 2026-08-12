"""Prompts para el análisis mensual de Valencia Emocional.

Todo el texto instruccional para GPT vive en este archivo.
El script principal solo prepara los datos y llama estas funciones.
"""

import json
from typing import Any, Dict, Optional


def _fmt_pct(value: Any) -> str:
    try:
        return f"{float(value) * 100:.1f}%"
    except Exception:
        return "N/D"


def _fmt_table_rows(rows, columns, max_rows=30) -> str:
    if not rows:
        return "Sin datos disponibles."

    selected = rows[:max_rows]
    header = "| " + " | ".join(columns) + " |"
    separator = "| " + " | ".join(["---"] * len(columns)) + " |"
    body = []

    for row in selected:
        values = []
        for col in columns:
            value = row.get(col, "")
            if isinstance(value, float) and ("porcentaje" in col.lower() or col.lower() in {"%", "pct"}):
                value = _fmt_pct(value)
            values.append(str(value))
        body.append("| " + " | ".join(values) + " |")

    return "\n".join([header, separator] + body)


def _fmt_top_section(title: str, data: Dict[str, Any], max_items_per_valencia: int = 10) -> str:
    if not data:
        return f"### {title}\nSin datos disponibles."

    parts = [f"### {title}"]
    for valencia, items in data.items():
        parts.append(f"\n**{valencia}**")
        if not items:
            parts.append("- Sin datos.")
            continue
        for item in items[:max_items_per_valencia]:
            valor = item.get("valor", "N/D")
            cantidad = item.get("cantidad", "N/D")
            parts.append(f"- {valor}: {cantidad}")
    return "\n".join(parts)


def _fmt_comments(comments: Dict[str, Any], max_comments_per_valencia: int = 12) -> str:
    if not comments:
        return "Sin comentarios representativos disponibles."

    parts = []
    for valencia, rows in comments.items():
        parts.append(f"### {valencia}")
        if not rows:
            parts.append("Sin comentarios.")
            continue

        for i, row in enumerate(rows[:max_comments_per_valencia], start=1):
            comentario = str(row.get("comentario", "")).replace("\n", " ").strip()
            contexto = []
            for key, value in row.items():
                if key == "comentario":
                    continue
                contexto.append(f"{key}: {value}")
            contexto_txt = " | ".join(contexto)
            if contexto_txt:
                parts.append(f"{i}. {comentario}\n   Contexto: {contexto_txt}")
            else:
                parts.append(f"{i}. {comentario}")
    return "\n".join(parts)


def _fmt_group_summary(groups: Dict[str, Any], max_groups: int = 20) -> str:
    if not groups:
        return "Sin columna de agrupación o sin datos de agrupación disponibles."

    parts = []
    for group_name, group_data in list(groups.items())[:max_groups]:
        cantidad = group_data.get("cantidad", 0)
        pct_total = _fmt_pct(group_data.get("porcentaje_sobre_total", 0))
        parts.append(f"### {group_name}")
        parts.append(f"Total respuestas: {cantidad} ({pct_total} del total)")

        dist = group_data.get("distribucion_valencia", [])
        if dist:
            parts.append(_fmt_table_rows(dist, ["Valencia", "Cantidad", "Porcentaje"], max_rows=10))
        else:
            parts.append("Sin distribución de valencia para esta agrupación.")
    return "\n".join(parts)


def _fmt_current_month_context(payload: Dict[str, Any]) -> str:
    metadata = payload.get("metadata", {})

    valencias = metadata.get("valencias_detectadas", [])
    agrupaciones = metadata.get("agrupaciones_detectadas", [])

    parts = [
        "# Datos estructurados del mes actual",
        "",
        f"Periodo analizado: **{metadata.get('periodo_analisis', 'N/D')}**",
        f"Total filas analizadas: **{metadata.get('total_filas', 'N/D')}**",
        f"Columna de valencia detectada: **{metadata.get('columnas_detectadas', {}).get('columna_valencia', 'N/D')}**",
        f"Columna de agrupación detectada: **{metadata.get('columnas_detectadas', {}).get('columna_agrupacion', 'N/D')}**",
        "",
        "## Distribución de valencias",
        _fmt_table_rows(valencias, ["Valencia", "Cantidad", "Porcentaje"], max_rows=20),
        "",
        "## Distribución de agrupaciones",
        _fmt_table_rows(agrupaciones, ["Agrupacion", "Cantidad", "Porcentaje"], max_rows=20),
        "",
        "## Resumen por agrupación",
        _fmt_group_summary(payload.get("resumen_por_agrupacion", {})),
        "",
        "## Tops por valencia",
    ]

    friendly_names = {
        "Tema": "Temas",
        "Categoria": "Categorías",
        "Categoría": "Categorías",
        "Attribute": "Atributos",
        "Retiros - Pais": "Países",
        "RLS": "RLS",
        "Retiros - Agrupación": "Agrupaciones",
        "Retiros - Agrupacion": "Agrupaciones",
        "IA.Sentimiento": "Sentimientos IA",
        "IA.Emoción": "Emociones IA",
        "IA.Emocion": "Emociones IA",
        "IA.Palabras clave": "Palabras clave IA",
        "IA.Categorías": "Categorías IA",
        "IA.Categorias": "Categorías IA",
        "Alerta": "Alertas",
        "Question": "Preguntas",
    }

    for column_name, top_data in payload.get("tops_por_valencia", {}).items():
        title = friendly_names.get(column_name, column_name)
        parts.append(_fmt_top_section(title, top_data, max_items_per_valencia=10))
        parts.append("")

    parts.extend([
        "## Comentarios representativos por valencia",
        _fmt_comments(payload.get("comentarios_representativos_por_valencia", {}), max_comments_per_valencia=10),
        "",
        "## Detalle por valencia y agrupación",
        "El siguiente bloque resume hallazgos por combinación Valencia x Agrupación. Úsalo para hacer lectura segmentada.",
        json.dumps(payload.get("tops_por_valencia_y_agrupacion", {}), ensure_ascii=False, indent=2)[:40000],
        "",
        "## Comentarios por valencia y agrupación",
        json.dumps(payload.get("comentarios_representativos_por_valencia_y_agrupacion", {}), ensure_ascii=False, indent=2)[:40000],
        "",
        "## Advertencias de calidad de datos",
        json.dumps(payload.get("advertencias_calidad_datos", []), ensure_ascii=False, indent=2),
    ])

    return "\n".join(parts)


def build_executive_prompt(
    current_payload: Dict[str, Any],
    previous_report_text: Optional[str] = None,
    previous_report_path: Optional[str] = None,
) -> str:
    """Construye el prompt final para OpenAI.

    El script principal NO debe tener instrucciones largas de prompt.
    Cualquier cambio de tono, estructura o reglas del informe se ajusta aquí.
    """

    current_context = _fmt_current_month_context(current_payload)

    if previous_report_text:
        previous_block = f"""
# Informe ejecutivo del mes anterior

Fuente del informe anterior: {previous_report_path or 'No especificada'}

Usa este informe como referencia para comparar tendencias, mejorías, deterioros o estabilidad.
No lo reescribas completo. Extrae de él únicamente los puntos necesarios para comparar contra el mes actual.

```markdown
{previous_report_text[:60000]}
```
""".strip()
    else:
        previous_block = """
# Informe ejecutivo del mes anterior

No se encontró informe anterior. El mes actual debe tratarse como línea base.
No afirmes mejoría ni deterioro histórico si no hay informe anterior disponible.
""".strip()

    return f"""
Eres un consultor senior de People Analytics, experiencia del empleado y análisis de rotación.

Vas a generar un RESUMEN EJECUTIVO MENSUAL de Valencia Emocional a partir de:
1. Datos estructurados del mes actual.
2. El informe ejecutivo del mes anterior, si existe.

Reglas críticas:
- No inventes datos.
- Usa el periodo indicado en los datos del mes actual.
- La comparación mensual debe hacerse contra el informe anterior proporcionado.
- Si no hay informe anterior, declara que este mes queda como línea base.
- No menciones que recibiste JSON ni payload; redacta como consultor de negocio.
- La variable principal es la valencia o equivalencia emocional.
- Además de analizar por valencia, debes separar la lectura por la columna de agrupación detectada, especialmente "Retiros - Agrupación".
- Identifica automáticamente las valencias existentes. No asumas que siempre se llaman Fortaleza, Oportunidad y Riesgo.
- Si existen Fortaleza, Oportunidad y Riesgo, interpreta así:
  - Fortaleza: aspecto positivo a preservar, amplificar o replicar.
  - Oportunidad: aspecto mejorable y accionable.
  - Riesgo: foco crítico que requiere intervención prioritaria.
- Si las valencias tienen otros nombres, adapta la interpretación.
- Relaciona la valencia con lo que contestaron las personas, temas, categorías, emociones, palabras clave, país, RLS, área/subárea si existen y agrupación.
- Si una columna tiene poca información, dilo explícitamente y evita conclusiones fuertes desde esa variable.
- No hagas una lista mecánica de tablas. Interpreta patrones y construye conclusiones.
- En el comparativo mensual, señala mejoría, empeoramiento o estabilidad solo cuando el informe anterior permita sostenerlo.
- Usa lenguaje ejecutivo, claro y accionable.

Estructura obligatoria del informe:

# Resumen Ejecutivo Mensual de Valencia Emocional

## 1. Periodo analizado
Indica el periodo, volumen de respuestas, columna de valencia y columna de agrupación.

## 2. Panorama general de valencias
Describe la distribución general y la lectura global del mes.

## 3. Comparativo frente al informe anterior
Compara contra el informe anterior si existe.
Identifica cambios de mejoría, deterioro o estabilidad en:
- distribución de valencias
- riesgos principales
- oportunidades recurrentes
- fortalezas preservadas
- agrupaciones con señales de cambio
Si no hay informe anterior, indica que este mes queda como línea base.

## 4. Lectura por agrupación
Analiza cada agrupación relevante.
Para cada una, explica:
- valencias predominantes
- temas que explican fortalezas
- oportunidades principales
- riesgos principales
- emociones o palabras clave relevantes
- señales de mejora o deterioro si el informe anterior lo permite

## 5. Principales fortalezas
Identifica aspectos positivos a preservar o replicar.

## 6. Principales oportunidades
Identifica asuntos mejorables, frecuentes y accionables.

## 7. Principales riesgos
Identifica señales críticas, emociones negativas, alertas o segmentos que requieren intervención.

## 8. Qué dicen las personas
Sintetiza patrones narrativos de los comentarios representativos. No copies todos los comentarios.

## 9. Recomendaciones priorizadas
Divide en:
### Acción inmediata
### Corto plazo
### Acción estratégica

## 10. Conclusión general
Cierra con una conclusión ejecutiva conectando evidencia emocional, agrupaciones y evolución mensual.

{previous_block}

{current_context}
""".strip()
