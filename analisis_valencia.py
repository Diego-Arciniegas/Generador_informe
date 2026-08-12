import argparse
import json
import os
import re
from datetime import datetime
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from prompts import build_executive_prompt


# ============================================================
# CONFIGURACION DEL PROYECTO
# ============================================================

# La carpeta del proyecto se toma automaticamente desde la ubicacion del script.
BASE_DIR = Path(__file__).resolve().parent

# Archivos predeterminados. Se pueden cambiar desde PowerShell con --input y --nps-file.
INPUT_FILE = BASE_DIR / "base_retiros_analisis_valencia.xlsx"
NPS_FILE = BASE_DIR / "NPS -EVA.xlsx"

# Carpeta de resultados. Se crea una subcarpeta por periodo: outputs/AAAA-MM/
OUTPUT_ROOT_DIR = BASE_DIR / "outputs"

# Nombres estandar de salida por periodo.
OUTPUT_REPORT_NAME = "resumen_ejecutivo.md"
OUTPUT_TABLES_NAME = "tablas_resumen.xlsx"
OUTPUT_PAYLOAD_NAME = "analysis_payload.json"

# Nombres que el script intentara usar como informe anterior si no pasas --previous-report.
DEFAULT_PREVIOUS_REPORT_NAMES = [
    "resumen_ejecutivo_anterior.md",
    "resumen_ejecutivo.md",
    "informe_anterior.md",
]


# ============================================================
# UTILIDADES DE TEXTO Y COLUMNAS
# ============================================================

def normalize_text(value):
    if value is None:
        return ""
    text = str(value).strip().lower()
    replacements = {
        "á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u",
        "Á": "a", "É": "e", "Í": "i", "Ó": "o", "Ú": "u",
        "ñ": "n", "Ñ": "n",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    text = re.sub(r"\s+", " ", text)
    return text


def clean_value(value):
    if pd.isna(value):
        return None
    text = str(value).strip()
    if text == "" or text.lower() in {"nan", "none", "null", "nat"}:
        return None
    return text


def find_column(df, candidates):
    normalized_columns = {normalize_text(col): col for col in df.columns}

    for candidate in candidates:
        key = normalize_text(candidate)
        if key in normalized_columns:
            return normalized_columns[key]

    for candidate in candidates:
        key = normalize_text(candidate)
        for normalized_col, original_col in normalized_columns.items():
            if key in normalized_col or normalized_col in key:
                return original_col

    return None


def detect_valencia_column(df, forced_col=None):
    if forced_col:
        if forced_col not in df.columns:
            raise ValueError(f"La columna forzada '{forced_col}' no existe en el Excel.")
        return forced_col

    candidates = [
        "Valencia emocional",
        "Valencia Final",
        "Equivalencia emocional",
        "Equivalencia emocional final",
        "Clasificacion emocional",
        "Clasificación emocional",
        "Categoria emocional",
        "Categoría emocional",
        "Resultado emocional",
        "Tipo emocional",
        "Valencia",
        "Equivalencia",
    ]

    found = find_column(df, candidates)
    if found:
        return found

    keywords = ["valencia", "equivalencia", "emocional", "sentimiento"]
    possible = []
    for col in df.columns:
        col_norm = normalize_text(col)
        score = sum(1 for kw in keywords if kw in col_norm)
        if score >= 2:
            possible.append((score, col))

    if possible:
        possible.sort(reverse=True)
        return possible[0][1]

    raise ValueError(
        "No pude detectar automaticamente la columna de Valencia/Equivalencia emocional. "
        "Ejecuta el script con --valencia-col \"Nombre exacto de la columna\"."
    )


def detect_agrupacion_column(df, forced_col=None):
    if forced_col:
        if forced_col not in df.columns:
            raise ValueError(f"La columna de agrupacion forzada '{forced_col}' no existe en el Excel.")
        return forced_col

    return find_column(
        df,
        [
            "Retiros - Agrupacion",
            "Retiros - Agrupación",
            "Agrupacion",
            "Agrupación",
            "Grupo",
            "Segmento",
        ],
    )



NPS_SEGMENTS = ["Promotor", "Neutral", "Detractor"]


def normalize_identifier(value):
    value = clean_value(value)
    if value is None:
        return None
    return re.sub(r"\s+", "", str(value)).upper()


def normalize_nps_segment(value):
    value = clean_value(value)
    if value is None:
        return None

    key = normalize_text(value)
    mapping = {
        "promotor": "Promotor",
        "promoter": "Promotor",
        "neutral": "Neutral",
        "pasivo": "Neutral",
        "passive": "Neutral",
        "detractor": "Detractor",
    }
    return mapping.get(key, str(value).strip().title())


def resolve_project_path(value, base_dir):
    if value is None:
        return None
    path = Path(value)
    if not path.is_absolute():
        path = base_dir / path
    return path


def detect_id_column(df, forced_col=None):
    if forced_col:
        if forced_col not in df.columns:
            raise ValueError(f"La columna de ID forzada '{forced_col}' no existe.")
        return forced_col

    found = find_column(
        df,
        [
            "Id",
            "ID",
            "Id Respuesta",
            "ID Respuesta",
            "Response Id",
            "Response ID",
            "Answer Id",
            "AnswerId",
        ],
    )
    if not found:
        raise ValueError("No pude detectar la columna de ID para cruzar la base con NPS.")
    return found


def load_and_merge_nps(df, nps_file, base_id_col=None, nps_id_col=None):
    metadata = {
        "disponible": False,
        "archivo": str(nps_file) if nps_file else None,
        "motivo_no_disponible": None,
    }

    if not nps_file:
        metadata["motivo_no_disponible"] = "No se indico archivo NPS."
        return df, metadata

    nps_file = Path(nps_file)
    if not nps_file.exists():
        metadata["motivo_no_disponible"] = f"No se encontro el archivo NPS: {nps_file}"
        return df, metadata

    nps_df = pd.read_excel(nps_file)
    base_id_col = detect_id_column(df, forced_col=base_id_col)
    nps_id_col = detect_id_column(nps_df, forced_col=nps_id_col)

    enps_col = find_column(nps_df, ["eNPS", "ENPS", "NPS Empresa", "Recomendacion Empresa"])
    lnps_col = find_column(nps_df, ["LNPS", "lNPS", "NPS Lider", "NPS Líder", "Recomendacion Lider"])

    if not enps_col and not lnps_col:
        raise ValueError("El archivo NPS no contiene columnas eNPS ni LNPS.")

    base = df.copy()
    nps = nps_df.copy()
    base["__nps_join_id"] = base[base_id_col].apply(normalize_identifier)
    nps["__nps_join_id"] = nps[nps_id_col].apply(normalize_identifier)
    nps = nps.dropna(subset=["__nps_join_id"])

    metric_source_cols = {}
    if enps_col:
        nps["eNPS"] = nps[enps_col].apply(normalize_nps_segment)
        metric_source_cols["eNPS"] = enps_col
    if lnps_col:
        nps["LNPS"] = nps[lnps_col].apply(normalize_nps_segment)
        metric_source_cols["LNPS"] = lnps_col

    metric_cols = list(metric_source_cols)
    conflicts = {}
    for metric in metric_cols:
        conflict_count = int((nps.groupby("__nps_join_id")[metric].nunique(dropna=True) > 1).sum())
        conflicts[metric] = conflict_count

    nps_small = nps[["__nps_join_id"] + metric_cols].drop_duplicates(
        subset=["__nps_join_id"], keep="first"
    )

    # Evita columnas duplicadas si la base ya tenia eNPS o LNPS.
    base = base.drop(columns=[c for c in metric_cols if c in base.columns], errors="ignore")
    merged = base.merge(nps_small, on="__nps_join_id", how="left", validate="many_to_one")

    base_ids = set(base["__nps_join_id"].dropna().unique())
    nps_ids = set(nps_small["__nps_join_id"].dropna().unique())
    matched_ids = base_ids & nps_ids

    metadata.update(
        {
            "disponible": True,
            "columna_id_base": base_id_col,
            "columna_id_nps": nps_id_col,
            "columnas_metricas": metric_source_cols,
            "personas_base": int(len(base_ids)),
            "personas_archivo_nps": int(len(nps_ids)),
            "personas_cruzadas": int(len(matched_ids)),
            "cobertura_sobre_base": round(len(matched_ids) / len(base_ids), 4) if base_ids else 0,
            "ids_nps_sin_base": int(len(nps_ids - base_ids)),
            "ids_base_sin_nps": int(len(base_ids - nps_ids)),
            "conflictos_por_id": conflicts,
        }
    )
    return merged, metadata


def get_run_period(df, forced_period=None):
    """El periodo es siempre el mes en que se corre el analisis, no una fecha
    dentro de los datos: la base es historica y acumulativa (incluye filas de
    meses anteriores mas las nuevas), asi que ninguna columna de fecha en el
    Excel identifica de forma confiable "el mes de esta corrida". Usa
    --periodo para forzar un valor especifico (por ejemplo, para reprocesar
    un mes anterior)."""
    if forced_period:
        return forced_period
    return datetime.now().strftime("%Y-%m")


def safe_sheet_name(name, used_names):
    cleaned = re.sub(r"[\[\]\*\?/\\:]", "_", str(name))
    cleaned = cleaned.strip() or "Hoja"
    cleaned = cleaned[:31]

    base = cleaned
    i = 2
    while cleaned in used_names:
        suffix = f"_{i}"
        cleaned = (base[: 31 - len(suffix)] + suffix)[:31]
        i += 1

    used_names.add(cleaned)
    return cleaned


# ============================================================
# TABLAS Y RESUMENES
# ============================================================

def value_counts_table(df, group_col, target_col=None, top_n=50):
    if not group_col or group_col not in df.columns:
        return pd.DataFrame()

    if target_col is None:
        temp = df[group_col].apply(clean_value).dropna()
        if temp.empty:
            return pd.DataFrame()
        table = temp.value_counts().head(top_n).reset_index()
        table.columns = [group_col, "Cantidad"]
        total = table["Cantidad"].sum()
        table["Porcentaje_sobre_top"] = table["Cantidad"] / total if total else 0
        return table

    if not target_col or target_col not in df.columns:
        return pd.DataFrame()

    temp = df[[group_col, target_col]].copy()
    temp[group_col] = temp[group_col].apply(clean_value)
    temp[target_col] = temp[target_col].apply(clean_value)
    temp = temp.dropna()

    if temp.empty:
        return pd.DataFrame()

    table = (
        temp.groupby([group_col, target_col])
        .size()
        .reset_index(name="Cantidad")
        .sort_values("Cantidad", ascending=False)
        .head(top_n)
    )
    total = table["Cantidad"].sum()
    table["Porcentaje_sobre_top"] = table["Cantidad"] / total if total else 0
    return table


def distribution_table(df, col, total_rows=None, top_n=None):
    if not col or col not in df.columns:
        return pd.DataFrame()

    total_rows = total_rows or len(df)
    counts = df[col].apply(clean_value).dropna().value_counts()
    if top_n:
        counts = counts.head(top_n)

    table = counts.reset_index()
    table.columns = [col, "Cantidad"]
    table["Porcentaje"] = table["Cantidad"] / total_rows if total_rows else 0
    return table


def get_top_by_valencia(df, valencia_col, analysis_col, top_n=12):
    if not analysis_col or analysis_col not in df.columns:
        return {}

    result = {}
    valencias = sorted(df[valencia_col].dropna().astype(str).unique())

    for valencia in valencias:
        sub = df[df[valencia_col].astype(str) == valencia]
        counts = (
            sub[analysis_col]
            .apply(clean_value)
            .dropna()
            .value_counts()
            .head(top_n)
        )
        result[str(valencia)] = [
            {"valor": str(idx), "cantidad": int(count)} for idx, count in counts.items()
        ]

    return result


def get_top_by_valencia_and_group(df, valencia_col, agrupacion_col, analysis_col, top_n=8, max_groups=12):
    if not agrupacion_col or agrupacion_col not in df.columns:
        return {}
    if not analysis_col or analysis_col not in df.columns:
        return {}

    top_groups = (
        df[agrupacion_col]
        .apply(clean_value)
        .dropna()
        .value_counts()
        .head(max_groups)
        .index
        .tolist()
    )

    result = {}
    valencias = sorted(df[valencia_col].dropna().astype(str).unique())

    for valencia in valencias:
        result[str(valencia)] = {}
        for agrupacion in top_groups:
            sub = df[
                (df[valencia_col].astype(str) == str(valencia))
                & (df[agrupacion_col].astype(str) == str(agrupacion))
            ]
            if sub.empty:
                continue

            counts = (
                sub[analysis_col]
                .apply(clean_value)
                .dropna()
                .value_counts()
                .head(top_n)
            )
            if counts.empty:
                continue

            result[str(valencia)][str(agrupacion)] = [
                {"valor": str(idx), "cantidad": int(count)} for idx, count in counts.items()
            ]

    return result


def representative_comments(df, valencia_col, text_col, extra_cols, comments_per_valencia=18):
    if not text_col or text_col not in df.columns:
        return {}

    result = {}
    valencias = sorted(df[valencia_col].dropna().astype(str).unique())

    for valencia in valencias:
        sub = df[df[valencia_col].astype(str) == str(valencia)].copy()
        sub[text_col] = sub[text_col].apply(clean_value)
        sub = sub.dropna(subset=[text_col])

        if sub.empty:
            result[str(valencia)] = []
            continue

        sub["__text_len"] = sub[text_col].astype(str).str.len()
        sub = sub.sort_values("__text_len", ascending=False).head(comments_per_valencia * 3)

        if len(sub) > comments_per_valencia:
            sub = sub.sample(n=comments_per_valencia, random_state=42)

        items = []
        for _, row in sub.iterrows():
            item = {"comentario": str(row[text_col])[:1200]}
            for col in extra_cols:
                if col and col in df.columns:
                    val = clean_value(row.get(col))
                    if val:
                        item[col] = val
            items.append(item)

        result[str(valencia)] = items

    return result


def representative_comments_by_group(
    df,
    valencia_col,
    agrupacion_col,
    text_col,
    extra_cols,
    comments_per_pair=5,
    max_groups=8,
):
    if not agrupacion_col or agrupacion_col not in df.columns:
        return {}
    if not text_col or text_col not in df.columns:
        return {}

    top_groups = (
        df[agrupacion_col]
        .apply(clean_value)
        .dropna()
        .value_counts()
        .head(max_groups)
        .index
        .tolist()
    )

    result = {}
    valencias = sorted(df[valencia_col].dropna().astype(str).unique())

    for valencia in valencias:
        result[str(valencia)] = {}
        for agrupacion in top_groups:
            sub = df[
                (df[valencia_col].astype(str) == str(valencia))
                & (df[agrupacion_col].astype(str) == str(agrupacion))
            ].copy()

            sub[text_col] = sub[text_col].apply(clean_value)
            sub = sub.dropna(subset=[text_col])

            if sub.empty:
                continue

            sub["__text_len"] = sub[text_col].astype(str).str.len()
            sub = sub.sort_values("__text_len", ascending=False).head(comments_per_pair * 3)

            if len(sub) > comments_per_pair:
                sub = sub.sample(n=comments_per_pair, random_state=42)

            items = []
            for _, row in sub.iterrows():
                item = {"comentario": str(row[text_col])[:1000]}
                for col in extra_cols:
                    if col and col in df.columns:
                        val = clean_value(row.get(col))
                        if val:
                            item[col] = val
                items.append(item)

            result[str(valencia)][str(agrupacion)] = items

    return result



def metric_question_mask(df, question_col, metric):
    if not question_col or question_col not in df.columns:
        return pd.Series(True, index=df.index)

    normalized = df[question_col].fillna("").apply(normalize_text)
    if metric == "eNPS":
        return (
            normalized.str.contains("por que le asignaste esa calificacion", regex=False)
            & ~normalized.str.contains("jefe", regex=False)
            & ~normalized.str.contains("lider", regex=False)
        )

    if metric == "LNPS":
        return (
            normalized.str.contains("jefe inmediato", regex=False)
            | normalized.str.contains("calificacion que asignaste a tu jefe", regex=False)
            | normalized.str.contains("lider inmediato", regex=False)
        )

    return pd.Series(True, index=df.index)


def unique_person_mentions_table(df, id_col, target_col, segment_people, top_n=12):
    if not target_col or target_col not in df.columns or not id_col or id_col not in df.columns:
        return pd.DataFrame()

    temp = df[[id_col, target_col]].copy()
    temp[id_col] = temp[id_col].apply(normalize_identifier)
    temp[target_col] = temp[target_col].apply(clean_value)
    temp = temp.dropna().drop_duplicates()
    if temp.empty:
        return pd.DataFrame()

    table = (
        temp.groupby(target_col)[id_col]
        .nunique()
        .sort_values(ascending=False)
        .head(top_n)
        .reset_index(name="Personas")
    )
    table["Porcentaje_personas_segmento"] = (
        table["Personas"] / segment_people if segment_people else 0
    )
    return table


def unique_response_valencia_table(df, id_col, question_col, answer_col, valencia_col):
    required = [c for c in [id_col, valencia_col] if c and c in df.columns]
    if len(required) < 2:
        return pd.DataFrame()

    keys = [id_col]
    for col in [question_col, answer_col, valencia_col]:
        if col and col in df.columns and col not in keys:
            keys.append(col)

    temp = df[keys].copy()
    temp[id_col] = temp[id_col].apply(normalize_identifier)
    temp[valencia_col] = temp[valencia_col].apply(clean_value)
    temp = temp.dropna(subset=[id_col, valencia_col]).drop_duplicates()
    if temp.empty:
        return pd.DataFrame()

    table = temp[valencia_col].value_counts().reset_index()
    table.columns = [valencia_col, "Respuestas_unicas"]
    total = int(table["Respuestas_unicas"].sum())
    table["Porcentaje_respuestas"] = table["Respuestas_unicas"] / total if total else 0
    return table


def representative_nps_comments(
    df,
    id_col,
    valencia_col,
    question_col,
    answer_col,
    extra_cols,
    max_per_valencia=5,
):
    if not answer_col or answer_col not in df.columns:
        return {}

    keys = [c for c in [id_col, question_col, answer_col, valencia_col] if c and c in df.columns]
    temp = df.copy()
    temp[answer_col] = temp[answer_col].apply(clean_value)
    temp = temp.dropna(subset=[answer_col])
    if keys:
        temp = temp.drop_duplicates(subset=keys)

    return representative_comments(
        temp,
        valencia_col,
        answer_col,
        extra_cols,
        comments_per_valencia=max_per_valencia,
    )


def build_nps_analysis(df, id_col, valencia_col, agrupacion_col, nps_metadata):
    if not nps_metadata.get("disponible"):
        return {
            "disponible": False,
            "motivo_no_disponible": nps_metadata.get("motivo_no_disponible"),
        }, {}

    available_metrics = [metric for metric in ["eNPS", "LNPS"] if metric in df.columns]
    if not available_metrics:
        return {"disponible": False, "motivo_no_disponible": "No hay metricas NPS cruzadas."}, {}

    id_col = detect_id_column(df)
    question_col = find_column(df, ["Question", "Pregunta"])
    answer_col = find_column(df, ["Answer", "Respuesta", "Comentario", "Comentarios"])
    categoria_col = find_column(df, ["Categoria", "Categoría"])
    tema_col = find_column(df, ["Tema"])
    sentimiento_col = find_column(df, ["IA.Sentimiento", "Sentimiento"])
    emocion_col = find_column(df, ["IA.Emocion", "IA.Emoción", "Emocion", "Emoción"])
    palabras_col = find_column(df, ["IA.Palabras clave", "Palabras clave", "Keywords"])
    alerta_col = find_column(df, ["Alerta"])
    area_col = find_column(df, ["Area", "Área", "UEN/AREA-d", "UEN/ÁREA-d"])
    subarea_col = find_column(df, ["Subarea", "Subárea"])

    respondent_cols = [id_col] + available_metrics
    respondents = df[respondent_cols].copy()
    respondents[id_col] = respondents[id_col].apply(normalize_identifier)
    respondents = respondents.dropna(subset=[id_col]).drop_duplicates(subset=[id_col])

    tables = {}
    metrics_analysis = {}

    for metric in available_metrics:
        metric_people = respondents.dropna(subset=[metric]).copy()
        distribution = metric_people[metric].value_counts().reindex(NPS_SEGMENTS, fill_value=0)
        total_people = int(distribution.sum())
        distribution_table_nps = distribution.reset_index()
        distribution_table_nps.columns = ["Segmento", "Personas"]
        distribution_table_nps["Porcentaje"] = (
            distribution_table_nps["Personas"] / total_people if total_people else 0
        )
        promoters = int(distribution.get("Promotor", 0))
        detractors = int(distribution.get("Detractor", 0))
        nps_score = round(((promoters - detractors) / total_people) * 100, 1) if total_people else None
        tables[f"NPS_Distribucion_{metric}"] = distribution_table_nps

        metric_data = {
            "significado": (
                "Recomendacion de la empresa" if metric == "eNPS" else "Recomendacion del jefe o lider inmediato"
            ),
            "total_personas": total_people,
            "puntaje_nps": nps_score,
            "distribucion_personas": distribution_table_nps.to_dict(orient="records"),
            "pregunta_directa_detectada": bool(metric_question_mask(df, question_col, metric).any()),
            "segmentos": {},
        }

        category_tables = []
        valencia_tables = []
        direct_mask = metric_question_mask(df, question_col, metric)

        for segment in NPS_SEGMENTS:
            segment_all = df[df[metric] == segment].copy()
            segment_direct = segment_all[direct_mask.loc[segment_all.index]].copy()
            if segment_direct.empty:
                segment_direct = segment_all.copy()

            segment_people = int(segment_all[id_col].apply(normalize_identifier).nunique())
            direct_people = int(segment_direct[id_col].apply(normalize_identifier).nunique())

            direct_targets = {
                "categorias": categoria_col,
                "temas": tema_col,
                "sentimientos": sentimiento_col,
                "emociones": emocion_col,
                "palabras_clave": palabras_col,
                "alertas": alerta_col,
                "agrupaciones": agrupacion_col,
                "areas": area_col,
                "subareas": subarea_col,
            }
            direct_tops = {}
            for label, col in direct_targets.items():
                table = unique_person_mentions_table(
                    segment_direct, id_col, col, direct_people, top_n=12
                )
                direct_tops[label] = table.to_dict(orient="records") if not table.empty else []
                if label == "categorias" and not table.empty:
                    temp = table.copy()
                    temp.insert(0, "Segmento", segment)
                    category_tables.append(temp)

            valencia_response = unique_response_valencia_table(
                segment_direct, id_col, question_col, answer_col, valencia_col
            )
            if not valencia_response.empty:
                temp = valencia_response.copy()
                temp.insert(0, "Segmento", segment)
                valencia_tables.append(temp)

            general_categories = unique_person_mentions_table(
                segment_all, id_col, categoria_col, segment_people, top_n=12
            )
            general_emotions = unique_person_mentions_table(
                segment_all, id_col, emocion_col, segment_people, top_n=10
            )

            extra_comment_cols = [
                question_col,
                categoria_col,
                valencia_col,
                sentimiento_col,
                emocion_col,
                palabras_col,
                agrupacion_col,
                area_col,
                subarea_col,
                alerta_col,
            ]
            extra_comment_cols = [c for c in extra_comment_cols if c and c in df.columns]

            metric_data["segmentos"][segment] = {
                "personas": segment_people,
                "porcentaje_sobre_metrica": round(segment_people / total_people, 4) if total_people else 0,
                "personas_con_comentario_directo": direct_people,
                "lectura_directa_calificacion": {
                    "distribucion_respuestas_por_valencia": (
                        valencia_response.to_dict(orient="records") if not valencia_response.empty else []
                    ),
                    "tops": direct_tops,
                    "comentarios_representativos_por_valencia": representative_nps_comments(
                        segment_direct,
                        id_col,
                        valencia_col,
                        question_col,
                        answer_col,
                        extra_comment_cols,
                        max_per_valencia=5,
                    ),
                },
                "contexto_general_del_retiro": {
                    "categorias_mencionadas_por_personas": (
                        general_categories.to_dict(orient="records") if not general_categories.empty else []
                    ),
                    "emociones_mencionadas_por_personas": (
                        general_emotions.to_dict(orient="records") if not general_emotions.empty else []
                    ),
                },
            }

        neutral_direct = df[(df[metric] == "Neutral") & direct_mask].copy()
        if neutral_direct.empty:
            neutral_direct = df[df[metric] == "Neutral"].copy()
        neutral_people = int(neutral_direct[id_col].apply(normalize_identifier).nunique())

        neutral_focus = {}
        focus_labels = {
            "Fortaleza": "fortalezas_para_reforzar",
            "Oportunidad": "oportunidades_para_convertir",
            "Riesgo": "riesgos_de_caida_a_detractor",
        }
        for valencia_name, output_key in focus_labels.items():
            filtered = neutral_direct[
                neutral_direct[valencia_col].apply(clean_value).astype(str).str.lower()
                == valencia_name.lower()
            ]
            table = unique_person_mentions_table(
                filtered, id_col, categoria_col, neutral_people, top_n=12
            )
            neutral_focus[output_key] = table.to_dict(orient="records") if not table.empty else []

        neutral_emotions = unique_person_mentions_table(
            neutral_direct, id_col, emocion_col, neutral_people, top_n=12
        )
        neutral_focus["emociones_y_senales"] = (
            neutral_emotions.to_dict(orient="records") if not neutral_emotions.empty else []
        )
        metric_data["analisis_especial_neutrales"] = neutral_focus
        metrics_analysis[metric] = metric_data

        if category_tables:
            tables[f"NPS_Categorias_{metric}"] = pd.concat(category_tables, ignore_index=True)
        if valencia_tables:
            tables[f"NPS_Valencia_{metric}"] = pd.concat(valencia_tables, ignore_index=True)

        neutral_rows = []
        for key, rows in neutral_focus.items():
            if key == "emociones_y_senales":
                continue
            for row in rows:
                neutral_rows.append({"Tipo_foco": key, **row})
        if neutral_rows:
            tables[f"NPS_Neutrales_{metric}"] = pd.DataFrame(neutral_rows)

    cross_analysis = []
    critical_segments = {}
    if "eNPS" in available_metrics and "LNPS" in available_metrics:
        cross = respondents.dropna(subset=["eNPS", "LNPS"]).copy()
        cross_table = (
            cross.groupby(["eNPS", "LNPS"])[id_col]
            .nunique()
            .reset_index(name="Personas")
        )
        cross_total = int(cross_table["Personas"].sum())
        cross_table["Porcentaje"] = cross_table["Personas"] / cross_total if cross_total else 0
        tables["NPS_Cruce_empresa_lider"] = cross_table
        cross_analysis = cross_table.to_dict(orient="records")

        combinations = {
            "promotor_empresa_y_lider": ("Promotor", "Promotor"),
            "neutral_en_ambos": ("Neutral", "Neutral"),
            "promotor_empresa_detractor_lider": ("Promotor", "Detractor"),
            "detractor_empresa_promotor_lider": ("Detractor", "Promotor"),
            "detractor_en_ambos": ("Detractor", "Detractor"),
            "neutral_empresa_promotor_lider": ("Neutral", "Promotor"),
            "promotor_empresa_neutral_lider": ("Promotor", "Neutral"),
        }
        for label, (company_segment, leader_segment) in combinations.items():
            count = int(
                cross.loc[
                    (cross["eNPS"] == company_segment) & (cross["LNPS"] == leader_segment),
                    id_col,
                ].nunique()
            )
            critical_segments[label] = {
                "personas": count,
                "porcentaje": round(count / cross_total, 4) if cross_total else 0,
            }

    analysis = {
        "disponible": True,
        "cobertura_cruce": nps_metadata,
        "regla_de_conteo": (
            "Las distribuciones NPS cuentan personas unicas. Los temas y categorias cuentan personas unicas "
            "que mencionan cada elemento, para evitar inflar resultados por filas repetidas de categorizacion IA."
        ),
        "metricas": metrics_analysis,
        "cruce_empresa_vs_lider": cross_analysis,
        "segmentos_cruzados_relevantes": critical_segments,
    }
    return analysis, tables


def save_excel_tables(tables, output_file):
    used_names = set()
    with pd.ExcelWriter(output_file, engine="openpyxl") as writer:
        for raw_sheet_name, table in tables.items():
            if table is None or table.empty:
                continue
            sheet_name = safe_sheet_name(raw_sheet_name, used_names)
            table.to_excel(writer, index=False, sheet_name=sheet_name)


def read_markdown_file(path):
    if not path:
        return None
    path = Path(path)
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")


def previous_period_from_outputs(output_root_dir, current_period):
    if not output_root_dir.exists():
        return None

    period_pattern = re.compile(r"^20\d{2}-(0[1-9]|1[0-2])$")
    candidates = []

    for child in output_root_dir.iterdir():
        if child.is_dir() and period_pattern.match(child.name) and child.name < current_period:
            report = child / OUTPUT_REPORT_NAME
            if report.exists():
                candidates.append((child.name, report))

    if not candidates:
        return None

    candidates.sort(key=lambda x: x[0])
    return candidates[-1][1]


def resolve_previous_report_path(base_dir, output_root_dir, current_period, previous_report_arg=None, previous_period_arg=None):
    # 1. Ruta exacta pasada por parametro.
    if previous_report_arg:
        path = Path(previous_report_arg)
        if not path.is_absolute():
            path = base_dir / path
        return path if path.exists() else None

    # 2. Carpeta del periodo anterior especificado.
    if previous_period_arg:
        path = output_root_dir / previous_period_arg / OUTPUT_REPORT_NAME
        return path if path.exists() else None

    # 3. Archivos en la raiz del proyecto.
    for name in DEFAULT_PREVIOUS_REPORT_NAMES:
        path = base_dir / name
        if path.exists():
            return path

    # 4. Ultima carpeta mensual anterior disponible.
    return previous_period_from_outputs(output_root_dir, current_period)


def build_current_analysis(df, valencia_col, agrupacion_col, periodo, nps_metadata=None):
    total_rows = len(df)

    id_col = detect_id_column(df)
    question_col = find_column(df, ["Question", "Pregunta"])
    answer_col = find_column(df, ["Answer", "Respuesta", "Comentario", "Comentarios"])
    tema_col = find_column(df, ["Tema"])
    categoria_col = find_column(df, ["Categoria", "Categoría"])
    attribute_col = find_column(df, ["Attribute", "Atributo"])
    pais_col = find_column(df, ["Retiros - Pais", "Retiros - País", "Pais", "País", "Country"])
    rls_col = find_column(df, ["RLS"])
    area_col = find_column(df, ["Area", "Área", "UEN/AREA-d", "UEN/ÁREA-d"])
    subarea_col = find_column(df, ["Subarea", "Subárea"])
    alerta_col = find_column(df, ["Alerta"])
    estado_col = find_column(df, ["Estado"])
    sentimiento_col = find_column(df, ["IA.Sentimiento", "Sentimiento"])
    emocion_col = find_column(df, ["IA.Emocion", "IA.Emoción", "Emocion", "Emoción"])
    palabras_col = find_column(df, ["IA.Palabras clave", "Palabras clave", "Keywords"])
    ia_categorias_col = find_column(df, ["IA.Categorias", "IA.Categorías", "Categorias IA", "Categorías IA"])

    valencia_distribution = distribution_table(df, valencia_col, total_rows=total_rows)
    agrupacion_distribution = distribution_table(df, agrupacion_col, total_rows=total_rows) if agrupacion_col else pd.DataFrame()

    tables = {
        "Distribucion_valencia": valencia_distribution,
        "Distribucion_agrupacion": agrupacion_distribution,
    }

    if agrupacion_col:
        tables["Valencia_x_Agrupacion"] = value_counts_table(
            df, valencia_col, agrupacion_col, top_n=200
        )
        tables["Agrupacion_x_Valencia"] = value_counts_table(
            df, agrupacion_col, valencia_col, top_n=200
        )

    cross_columns = [
        agrupacion_col,
        tema_col,
        categoria_col,
        attribute_col,
        pais_col,
        rls_col,
        area_col,
        subarea_col,
        alerta_col,
        estado_col,
        sentimiento_col,
        emocion_col,
        palabras_col,
        ia_categorias_col,
        question_col,
    ]
    cross_columns = [c for c in cross_columns if c and c in df.columns]

    for col in cross_columns:
        tables[f"Valencia_x_{col}"] = value_counts_table(df, valencia_col, col, top_n=100)

    resumen_por_valencia = {}
    for valencia in sorted(df[valencia_col].dropna().astype(str).unique()):
        sub = df[df[valencia_col].astype(str) == str(valencia)]
        resumen_por_valencia[str(valencia)] = {
            "cantidad": int(len(sub)),
            "porcentaje": round(len(sub) / total_rows, 4) if total_rows else 0,
        }

    resumen_por_agrupacion = {}
    if agrupacion_col:
        agrupaciones = sorted(df[agrupacion_col].dropna().astype(str).unique())
        for agrupacion in agrupaciones:
            sub = df[df[agrupacion_col].astype(str) == str(agrupacion)]
            total_group = len(sub)
            dist = distribution_table(sub, valencia_col, total_rows=total_group)
            resumen_por_agrupacion[str(agrupacion)] = {
                "cantidad": int(total_group),
                "porcentaje_sobre_total": round(total_group / total_rows, 4) if total_rows else 0,
                "distribucion_valencia": dist.to_dict(orient="records"),
            }

    top_sections = {}
    for col in cross_columns:
        top_sections[col] = get_top_by_valencia(df, valencia_col, col, top_n=12)

    top_sections_group = {}
    if agrupacion_col:
        cols_group_detail = [
            tema_col,
            categoria_col,
            attribute_col,
            pais_col,
            rls_col,
            sentimiento_col,
            emocion_col,
            palabras_col,
            ia_categorias_col,
            alerta_col,
            question_col,
        ]
        cols_group_detail = [c for c in cols_group_detail if c and c in df.columns]
        for col in cols_group_detail:
            top_sections_group[col] = get_top_by_valencia_and_group(
                df, valencia_col, agrupacion_col, col, top_n=8, max_groups=12
            )

    extra_comment_cols = [
        question_col,
        agrupacion_col,
        tema_col,
        categoria_col,
        attribute_col,
        pais_col,
        rls_col,
        area_col,
        subarea_col,
        sentimiento_col,
        emocion_col,
        palabras_col,
        ia_categorias_col,
        alerta_col,
    ]
    extra_comment_cols = [c for c in extra_comment_cols if c and c in df.columns]

    comments_by_valencia = representative_comments(
        df, valencia_col, answer_col, extra_comment_cols, comments_per_valencia=18
    ) if answer_col else {}

    comments_by_group = representative_comments_by_group(
        df,
        valencia_col,
        agrupacion_col,
        answer_col,
        extra_comment_cols,
        comments_per_pair=5,
        max_groups=8,
    ) if answer_col and agrupacion_col else {}

    nps_analysis, nps_tables = build_nps_analysis(
        df=df,
        id_col=id_col,
        valencia_col=valencia_col,
        agrupacion_col=agrupacion_col,
        nps_metadata=nps_metadata or {"disponible": False, "motivo_no_disponible": "Sin archivo NPS."},
    )
    tables.update(nps_tables)

    data_quality = []
    for col in df.columns:
        pct_non_null = df[col].notna().sum() / total_rows if total_rows else 0
        if pct_non_null < 0.05:
            data_quality.append({
                "columna": col,
                "porcentaje_no_vacio": round(pct_non_null, 4),
                "nota": "Columna con muy poca informacion; evitar conclusiones fuertes.",
            })

    analysis = {
        "metadata": {
            "periodo_analisis": periodo,
            "total_filas": int(total_rows),
            "total_columnas": int(len(df.columns)),
            "columna_valencia": valencia_col,
            "columna_agrupacion": agrupacion_col,
            "columnas_detectadas": {
                "id": id_col,
                "pregunta": question_col,
                "respuesta": answer_col,
                "tema": tema_col,
                "categoria": categoria_col,
                "atributo": attribute_col,
                "pais": pais_col,
                "rls": rls_col,
                "area": area_col,
                "subarea": subarea_col,
                "alerta": alerta_col,
                "estado": estado_col,
                "sentimiento": sentimiento_col,
                "emocion": emocion_col,
                "palabras_clave": palabras_col,
                "categorias_ia": ia_categorias_col,
            },
            "valencias_detectadas": valencia_distribution.to_dict(orient="records"),
            "agrupaciones_detectadas": agrupacion_distribution.to_dict(orient="records") if not agrupacion_distribution.empty else [],
        },
        "resumen_por_valencia": resumen_por_valencia,
        "resumen_por_agrupacion": resumen_por_agrupacion,
        "tops_por_valencia": top_sections,
        "tops_por_valencia_y_agrupacion": top_sections_group,
        "comentarios_representativos_por_valencia": comments_by_valencia,
        "comentarios_representativos_por_valencia_y_agrupacion": comments_by_group,
        "analisis_nps_empresa_lider": nps_analysis,
        "advertencias_calidad_datos": data_quality[:30],
    }

    return analysis, tables


# ============================================================
# OPENAI
# ============================================================

def call_openai(prompt, model):
    from openai import OpenAI

    client = OpenAI()
    response = client.responses.create(
        model=model,
        input=prompt,
        store=False,
    )
    return response.output_text


# ============================================================
# MAIN
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="Analisis mensual de valencia emocional con comparativo contra informe anterior en Markdown."
    )

    parser.add_argument(
        "--input",
        default=str(INPUT_FILE),
        help="Ruta del Excel mensual de respuestas.",
    )
    parser.add_argument(
        "--nps-file",
        default=str(NPS_FILE),
        help="Ruta del Excel con Id, eNPS y LNPS. Usa una cadena vacia para omitirlo.",
    )
    parser.add_argument(
        "--output-root",
        default=str(OUTPUT_ROOT_DIR),
        help="Carpeta raiz de salidas.",
    )
    parser.add_argument(
        "--base-id-col",
        default=None,
        help="Nombre exacto de la columna ID en la base principal.",
    )
    parser.add_argument(
        "--nps-id-col",
        default=None,
        help="Nombre exacto de la columna ID en el archivo NPS.",
    )
    parser.add_argument(
        "--model",
        default="gpt-5.4-mini",
        help="Modelo OpenAI a usar.",
    )
    parser.add_argument(
        "--periodo",
        default=None,
        help="Periodo del analisis. Ejemplo: 2026-07. Si no se indica, se intenta detectar desde el Excel.",
    )
    parser.add_argument(
        "--periodo-anterior",
        default=None,
        help="Periodo anterior para buscar outputs/AAAA-MM/resumen_ejecutivo.md. Ejemplo: 2026-06.",
    )
    parser.add_argument(
        "--previous-report",
        default=None,
        help="Ruta del informe ejecutivo anterior en Markdown. Puede ser absoluta o relativa a BASE_DIR.",
    )
    parser.add_argument(
        "--valencia-col",
        default=None,
        help="Nombre exacto de la columna de valencia si quieres forzarlo.",
    )
    parser.add_argument(
        "--agrupacion-col",
        default=None,
        help='Nombre exacto de la columna de agrupacion. Por defecto intenta "Retiros - Agrupacion".',
    )
    parser.add_argument(
        "--no-api",
        action="store_true",
        help="Solo genera tablas locales, sin llamar a OpenAI.",
    )

    args = parser.parse_args()

    load_dotenv(BASE_DIR / ".env")

    input_file = resolve_project_path(args.input, BASE_DIR)
    nps_file = resolve_project_path(args.nps_file, BASE_DIR) if args.nps_file else None
    output_root_dir = resolve_project_path(args.output_root, BASE_DIR)

    if not input_file.exists():
        raise FileNotFoundError(
            f"No encontre el Excel de entrada en:\n{input_file}\n\n"
            "Pon el archivo en esa carpeta o usa --input con la ruta correcta."
        )

    output_root_dir.mkdir(parents=True, exist_ok=True)

    print("Leyendo archivo:")
    print(input_file)

    df = pd.read_excel(input_file)
    print(f"Filas leidas: {len(df):,}")
    print(f"Columnas leidas: {len(df.columns):,}")

    df, nps_metadata = load_and_merge_nps(
        df=df,
        nps_file=nps_file,
        base_id_col=args.base_id_col,
        nps_id_col=args.nps_id_col,
    )
    if nps_metadata.get("disponible"):
        print(
            "Cruce NPS: "
            f"{nps_metadata['personas_cruzadas']:,} de {nps_metadata['personas_base']:,} personas "
            f"({nps_metadata['cobertura_sobre_base'] * 100:.1f}%)."
        )
    else:
        print(f"Analisis NPS omitido: {nps_metadata.get('motivo_no_disponible')}")

    valencia_col = detect_valencia_column(df, forced_col=args.valencia_col)
    agrupacion_col = detect_agrupacion_column(df, forced_col=args.agrupacion_col)

    print(f"Columna de valencia detectada: {valencia_col}")
    if agrupacion_col:
        print(f"Columna de agrupacion detectada: {agrupacion_col}")
    else:
        print("No se detecto columna de agrupacion. El analisis se hara solo por valencia.")

    df[valencia_col] = df[valencia_col].apply(clean_value)
    if agrupacion_col:
        df[agrupacion_col] = df[agrupacion_col].apply(clean_value)

    periodo = get_run_period(df, forced_period=args.periodo)
    print(f"Periodo de analisis: {periodo}")

    output_dir = output_root_dir / periodo
    output_dir.mkdir(exist_ok=True)

    output_tables_file = output_dir / OUTPUT_TABLES_NAME
    output_report_file = output_dir / OUTPUT_REPORT_NAME
    output_payload_file = output_dir / OUTPUT_PAYLOAD_NAME

    previous_report_path = resolve_previous_report_path(
        base_dir=BASE_DIR,
        output_root_dir=output_root_dir,
        current_period=periodo,
        previous_report_arg=args.previous_report,
        previous_period_arg=args.periodo_anterior,
    )

    previous_report_text = None
    if previous_report_path:
        previous_report_text = read_markdown_file(previous_report_path)
        print(f"Informe anterior usado para comparacion: {previous_report_path}")
    else:
        print("No se encontro informe anterior. Este periodo se tratara como linea base.")

    analysis, tables = build_current_analysis(
        df=df,
        valencia_col=valencia_col,
        agrupacion_col=agrupacion_col,
        periodo=periodo,
        nps_metadata=nps_metadata,
    )

    output_payload_file.write_text(
        json.dumps(analysis, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    save_excel_tables(tables, output_tables_file)

    print("\nValencias detectadas:")
    for item in analysis["metadata"]["valencias_detectadas"]:
        porcentaje = item["Porcentaje"] * 100
        print(f"- {item[valencia_col]}: {item['Cantidad']:,} ({porcentaje:.1f}%)")

    if analysis["metadata"]["agrupaciones_detectadas"]:
        print("\nAgrupaciones detectadas:")
        for item in analysis["metadata"]["agrupaciones_detectadas"][:20]:
            porcentaje = item["Porcentaje"] * 100
            print(f"- {item[agrupacion_col]}: {item['Cantidad']:,} ({porcentaje:.1f}%)")

    print("\nArchivos locales generados:")
    print(output_payload_file)
    print(output_tables_file)

    if args.no_api:
        print("\nModo --no-api activo. No se llamo a OpenAI ni se genero resumen ejecutivo.")
        return

    if not os.getenv("OPENAI_API_KEY"):
        raise EnvironmentError(
            "No encontre OPENAI_API_KEY. Crea un archivo .env en la carpeta del proyecto con:\n"
            "OPENAI_API_KEY=tu_clave_aqui"
        )

    prompt = build_executive_prompt(
        current_analysis=analysis,
        previous_report_text=previous_report_text,
    )

    print("\nGenerando resumen ejecutivo con OpenAI...")
    summary = call_openai(prompt, model=args.model)

    output_report_file.write_text(summary, encoding="utf-8")

    print("\nResumen ejecutivo generado:")
    print(output_report_file)


if __name__ == "__main__":
    main()