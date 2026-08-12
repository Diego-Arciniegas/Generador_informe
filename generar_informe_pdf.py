import argparse
import json
import re
from datetime import datetime
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.colors as mcolors
import matplotlib.font_manager as fm
import matplotlib.pyplot as plt
import pandas as pd
from PIL import Image as PILImage
from reportlab.lib import colors as rl
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as canvas_mod
from reportlab.platypus import (
    BaseDocTemplate, Frame, HRFlowable, Image, KeepTogether, ListFlowable,
    ListItem, NextPageTemplate, PageBreak, PageTemplate, Paragraph, Spacer,
    Table, TableStyle,
)

# ============================================================
# CONFIGURACION
# ============================================================

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_ROOT_DIR = BASE_DIR / "outputs"
FONTS_DIR = BASE_DIR / "fonts"
PERIOD_RE = re.compile(r"^20\d{2}-(0[1-9]|1[0-2])$")

# ------------------------------------------------------------
# Tipografia: Red Hat Display en todo el documento (portada, titulos,
# cuerpo y graficos), en pesos reales -- no negrita/italica sinteticas.
# ------------------------------------------------------------
FONT_REGULAR = "RedHatDisplay-Regular"
FONT_ITALIC = "RedHatDisplay-Italic"
FONT_MEDIUM = "RedHatDisplay-Medium"
FONT_SEMIBOLD = "RedHatDisplay-SemiBold"
FONT_BOLD = "RedHatDisplay-Bold"
FONT_BOLDITALIC = "RedHatDisplay-BoldItalic"
FONT_BLACK = "RedHatDisplay-Black"

_FONT_FILES = {
    FONT_REGULAR: "RedHatDisplay-Regular.ttf",
    FONT_ITALIC: "RedHatDisplay-Italic.ttf",
    FONT_MEDIUM: "RedHatDisplay-Medium.ttf",
    FONT_SEMIBOLD: "RedHatDisplay-SemiBold.ttf",
    FONT_BOLD: "RedHatDisplay-Bold.ttf",
    FONT_BOLDITALIC: "RedHatDisplay-BoldItalic.ttf",
    FONT_BLACK: "RedHatDisplay-Black.ttf",
}


def register_fonts():
    missing = [f for f in _FONT_FILES.values() if not (FONTS_DIR / f).exists()]
    if missing:
        raise FileNotFoundError(
            f"Faltan archivos de fuente en {FONTS_DIR}: {missing}. "
            "Red Hat Display (OFL) debe estar en la carpeta fonts/ del proyecto."
        )
    for font_name, filename in _FONT_FILES.items():
        pdfmetrics.registerFont(TTFont(font_name, str(FONTS_DIR / filename)))
    # Permite que las etiquetas <b>/<i> del markdown funcionen sobre el peso base.
    pdfmetrics.registerFontFamily(
        FONT_REGULAR, normal=FONT_REGULAR, bold=FONT_BOLD,
        italic=FONT_ITALIC, boldItalic=FONT_BOLDITALIC,
    )
    for weight in [FONT_MEDIUM, FONT_SEMIBOLD, FONT_BOLD, FONT_BLACK]:
        pdfmetrics.registerFontFamily(weight, normal=weight, bold=weight,
                                       italic=FONT_ITALIC, boldItalic=FONT_BOLDITALIC)
    # Mismo tipo de letra en los graficos (matplotlib), para que combinen con el PDF.
    for filename in _FONT_FILES.values():
        fm.fontManager.addfont(str(FONTS_DIR / filename))


register_fonts()

# Paleta (misma familia que el resto del proyecto: verde/ambar/rojo para
# Fortaleza/Oportunidad/Riesgo y Promotor/Neutral/Detractor).
GOOD = "#0ca30c"
WARNING = "#c98500"
CRITICAL = "#d03b3b"
BLUE = "#2a78d6"
BLUE_SEQ = ["#cde2fb", "#9ec5f4", "#5598e7", "#256abf", "#0d366b"]
FALLBACK_CATEGORICAL = ["#2a78d6", "#1baf7a", "#4a3aa7", "#e87ba4", "#eda100", "#008300"]

INK = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#898781"
GRID = "#e1e0d9"
SURFACE = "#ffffff"

STATUS_COLOR_BY_LABEL = {
    "fortaleza": GOOD, "oportunidad": WARNING, "riesgo": CRITICAL,
    "promotor": GOOD, "neutral": WARNING, "detractor": CRITICAL,
}
PREFERRED_VALENCIA_ORDER = ["fortaleza", "oportunidad", "riesgo"]


def status_color_for_flexible(label):
    """Color de una tarjeta individual segun a que segmento/valencia pertenece
    ('Promotores', 'Neutrales'...). Se excluyen etiquetas compuestas del cruce
    ('Promotor empresa / Detractor lider'), que mezclan dos segmentos distintos
    y no tienen un color unico correcto -- esas usan el color neutro de la seccion."""
    if "/" in label:
        return None
    norm = normalize_text(label)
    for key, color in STATUS_COLOR_BY_LABEL.items():
        if key in norm:
            return color
    return None

RL_GOOD = rl.HexColor(GOOD)
RL_WARNING = rl.HexColor(WARNING)
RL_CRITICAL = rl.HexColor(CRITICAL)
RL_BLUE = rl.HexColor(BLUE)
RL_INK = rl.HexColor(INK)
RL_INK_SECONDARY = rl.HexColor(INK_SECONDARY)
RL_INK_MUTED = rl.HexColor(INK_MUTED)
RL_GRID = rl.HexColor(GRID)
RL_SURFACE = rl.HexColor(SURFACE)
RL_COVER_BG = rl.HexColor("#0d1a12")
RL_COVER_ACCENT = rl.HexColor("#eda100")

plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Red Hat Display", "Segoe UI", "Arial", "DejaVu Sans"],
    "text.color": INK,
    "axes.edgecolor": GRID,
    "axes.labelcolor": INK_SECONDARY,
    "xtick.color": INK_SECONDARY,
    "ytick.color": INK_SECONDARY,
    "figure.facecolor": SURFACE,
    "axes.facecolor": SURFACE,
    "savefig.facecolor": SURFACE,
})
CHART_DPI = 220


# ============================================================
# UTILIDADES DE TEXTO
# ============================================================

def normalize_text(value):
    text = str(value).strip().lower()
    for a, b in {"á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u", "ñ": "n"}.items():
        text = text.replace(a, b)
    return re.sub(r"\s+", " ", text)


def fmt_n(value):
    return f"{int(value):,}".replace(",", ".")


def fmt_pct(value, decimals=1):
    return f"{value * 100:.{decimals}f}%"


class LabelColorAssigner:
    """Asigna colores estables: etiquetas conocidas (Fortaleza/Riesgo/...) usan la
    paleta semantica fija; etiquetas nuevas caen a una paleta categorica de reserva."""

    def __init__(self):
        self._fallback_index = {}

    def color_for(self, label):
        key = normalize_text(label)
        if key in STATUS_COLOR_BY_LABEL:
            return STATUS_COLOR_BY_LABEL[key]
        if label not in self._fallback_index:
            self._fallback_index[label] = len(self._fallback_index)
        idx = self._fallback_index[label] % len(FALLBACK_CATEGORICAL)
        return FALLBACK_CATEGORICAL[idx]


COLOR_ASSIGNER = LabelColorAssigner()


def ordered_labels(labels, counts=None):
    """Fortaleza/Oportunidad/Riesgo siempre en ese orden si son exactamente esas tres
    etiquetas; en cualquier otro caso, orden por volumen descendente."""
    norm_map = {}
    for l in labels:
        norm_map.setdefault(normalize_text(l), l)
    if set(norm_map) == set(PREFERRED_VALENCIA_ORDER):
        return [norm_map[k] for k in PREFERRED_VALENCIA_ORDER]
    if counts is not None:
        pairs = sorted(zip(labels, counts), key=lambda p: p[1], reverse=True)
        return [p[0] for p in pairs]
    return list(labels)


# ============================================================
# CARGA DE DATOS DE UN PERIODO
# ============================================================

def discover_periods(output_root):
    if not output_root.exists():
        return []
    return sorted(p.name for p in output_root.iterdir() if p.is_dir() and PERIOD_RE.match(p.name))


def load_period_data(output_root, period):
    if not period:
        return None
    period_dir = output_root / period
    tables_path = period_dir / "tablas_resumen.xlsx"
    payload_path = period_dir / "analysis_payload.json"
    report_path = period_dir / "resumen_ejecutivo.md"
    if not tables_path.exists():
        return None

    xls = pd.ExcelFile(tables_path)
    data = {"period": period, "dir": period_dir}

    dv = pd.read_excel(xls, "Distribucion_valencia")
    data["valencia_col"] = dv.columns[0]
    data["distribucion_valencia"] = dv

    if "Distribucion_agrupacion" in xls.sheet_names:
        da = pd.read_excel(xls, "Distribucion_agrupacion")
        if not da.empty:
            data["agrupacion_col"] = da.columns[0]
            data["distribucion_agrupacion"] = da
    data.setdefault("agrupacion_col", None)
    data.setdefault("distribucion_agrupacion", None)

    if data["agrupacion_col"] and "Agrupacion_x_Valencia" in xls.sheet_names:
        data["cruce_agrupacion_valencia"] = pd.read_excel(xls, "Agrupacion_x_Valencia")
    else:
        data["cruce_agrupacion_valencia"] = None

    for metric in ["eNPS", "LNPS"]:
        sheet = f"NPS_Distribucion_{metric}"
        if sheet in xls.sheet_names:
            data[f"nps_dist_{metric}"] = pd.read_excel(xls, sheet)

    if "NPS_Cruce_empresa_lider" in xls.sheet_names:
        data["nps_cruce"] = pd.read_excel(xls, "NPS_Cruce_empresa_lider")

    data["payload"] = json.loads(payload_path.read_text(encoding="utf-8")) if payload_path.exists() else None
    data["markdown"] = report_path.read_text(encoding="utf-8") if report_path.exists() else None
    return data


def valencia_pct_map(data):
    dv = data["distribucion_valencia"]
    col = data["valencia_col"]
    return {row[col]: row["Porcentaje"] for _, row in dv.iterrows()}


def valencia_count_map(data):
    dv = data["distribucion_valencia"]
    col = data["valencia_col"]
    return {row[col]: int(row["Cantidad"]) for _, row in dv.iterrows()}


def group_cross_map(data, max_groups=8):
    """{grupo: {"cantidades": {valencia: n}, "porcentajes": {valencia: pct}, "total": n}}
    ordenado por volumen de grupo descendente, limitado a max_groups."""
    cross = data.get("cruce_agrupacion_valencia")
    dist_g = data.get("distribucion_agrupacion")
    if cross is None or dist_g is None:
        return {}

    cols = list(cross.columns)
    grp_c, val_c = cols[0], cols[1]
    groups = dist_g[data["agrupacion_col"]].tolist()[:max_groups]

    result = {}
    for g in groups:
        sub = cross[cross[grp_c] == g]
        cantidades = {row[val_c]: int(row["Cantidad"]) for _, row in sub.iterrows()}
        total = sum(cantidades.values())
        porcentajes = {k: (v / total if total else 0) for k, v in cantidades.items()}
        result[g] = {"cantidades": cantidades, "porcentajes": porcentajes, "total": total}
    return result


def nps_summary(data):
    payload = data.get("payload")
    if not payload:
        return None
    nps = payload.get("analisis_nps_empresa_lider", {})
    if not nps.get("disponible"):
        return None

    out = {"cruce_empresa_vs_lider": nps.get("cruce_empresa_vs_lider", [])}
    for metric in ["eNPS", "LNPS"]:
        metric_data = nps.get("metricas", {}).get(metric)
        if not metric_data:
            continue
        seg = metric_data.get("segmentos", {})
        out[metric] = {
            "puntaje": metric_data.get("puntaje_nps"),
            "total_personas": metric_data.get("total_personas"),
            "segmentos": {
                k: {
                    "personas": v.get("personas"),
                    "porcentaje": v.get("porcentaje_sobre_metrica"),
                }
                for k, v in seg.items()
            },
        }
    return out if ("eNPS" in out or "LNPS" in out) else None


def top_categorias_for_valencia(data, valencia_label, top_n=6):
    payload = data.get("payload")
    if not payload:
        return None
    tops = payload.get("tops_por_valencia", {})
    for col_name in ["Categoria", "Categoría", "Tema"]:
        col_data = tops.get(col_name)
        if col_data and valencia_label in col_data and col_data[valencia_label]:
            items = col_data[valencia_label][:top_n]
            return {"columna": col_name, "items": items}
    return None


def find_label_like(labels, keyword):
    key = normalize_text(keyword)
    for l in labels:
        if key in normalize_text(l):
            return l
    return None


# ============================================================
# GRAFICOS (matplotlib)
# ============================================================

def _new_fig(figsize):
    return plt.subplots(figsize=figsize)


def _clean_axes(ax, hide=("top", "right", "bottom", "left")):
    for s in hide:
        ax.spines[s].set_visible(False)


def chart_distribucion_valencia(data, order, out_path):
    counts = valencia_count_map(data)
    pcts = valencia_pct_map(data)
    fig, ax = _new_fig((6.8, 0.9 + 0.62 * len(order)))
    y = list(range(len(order)))[::-1]
    for yi, label in zip(y, order):
        pct = pcts.get(label, 0) * 100
        color = COLOR_ASSIGNER.color_for(label)
        ax.barh(yi, pct, height=0.56, color=color, zorder=3)
        ax.text(pct + 1.5, yi, f"{pct:.1f}%  ({fmt_n(counts.get(label, 0))})",
                va="center", ha="left", fontsize=11, color=INK)
    ax.set_yticks(y)
    ax.set_yticklabels(order, fontsize=12, color=INK)
    ax.set_xlim(0, max(pcts.values(), default=0.5) * 100 * 1.32 + 5)
    ax.set_xticks([])
    _clean_axes(ax)
    ax.tick_params(left=False)
    ax.margins(y=0.25)
    fig.savefig(out_path, dpi=CHART_DPI, bbox_inches="tight", pad_inches=0.18)
    plt.close(fig)
    return out_path


def chart_comparativo_slope(data_actual, data_prev, order, out_path):
    pct_prev = valencia_pct_map(data_prev)
    pct_act = valencia_pct_map(data_actual)
    order = [l for l in order if l in pct_prev and l in pct_act]
    if not order:
        return None

    fig, ax = _new_fig((6.8, 0.55 + 0.62 * len(order)))
    xs = [0, 1]
    ymax = max(max(pct_prev.values()), max(pct_act.values())) * 100
    for label in order:
        color = COLOR_ASSIGNER.color_for(label)
        ys = [pct_prev[label] * 100, pct_act[label] * 100]
        ax.plot(xs, ys, color=color, linewidth=2.4, marker="o", markersize=6.5, zorder=3)
        ax.text(-0.06, ys[0], f"{label}\n{ys[0]:.1f}%", ha="right", va="center", fontsize=10.2, color=INK)
        delta = ys[1] - ys[0]
        arrow = "+" if delta > 0.05 else ("-" if delta < -0.05 else "=")
        ax.text(1.06, ys[1], f"{ys[1]:.1f}%  {arrow}", ha="left", va="center", fontsize=10.2,
                 color=INK, fontweight="bold")
    ax.set_xlim(-0.62, 1.34)
    ax.set_ylim(0, ymax * 1.08 + 2)
    ax.set_xticks(xs)
    ax.set_xticklabels([data_prev["period"], data_actual["period"]], fontsize=11.5, color=INK_SECONDARY)
    ax.set_yticks([])
    _clean_axes(ax, hide=("top", "right", "left"))
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(bottom=False)
    fig.savefig(out_path, dpi=CHART_DPI, bbox_inches="tight", pad_inches=0.18)
    plt.close(fig)
    return out_path


def chart_valencia_por_grupo(cross_map, order, out_path):
    if not cross_map:
        return None
    groups = list(cross_map.keys())
    fig, ax = _new_fig((7.0, 0.85 + 0.62 * len(groups)))
    y = list(range(len(groups)))[::-1]
    for yi, g in zip(y, groups):
        pct = cross_map[g]["porcentajes"]
        left = 0
        for label in order:
            width = pct.get(label, 0) * 100
            if width <= 0:
                continue
            color = COLOR_ASSIGNER.color_for(label)
            ax.barh(yi, width, left=left, height=0.6, color=color,
                    edgecolor=SURFACE, linewidth=1.4, zorder=3)
            if width > 6:
                ax.text(left + width / 2, yi, f"{width:.0f}%", ha="center", va="center",
                        fontsize=9.2, color="#ffffff", fontweight="bold")
            left += width
        ax.text(102, yi, f"n={fmt_n(cross_map[g]['total'])}", ha="left", va="center",
                fontsize=9.4, color=INK_SECONDARY)
    ax.set_yticks(y)
    ax.set_yticklabels(groups, fontsize=11.5, color=INK)
    ax.set_xlim(0, 122)
    ax.set_xticks([])
    _clean_axes(ax)
    ax.tick_params(left=False)
    ax.margins(y=0.18)
    fig.savefig(out_path, dpi=CHART_DPI, bbox_inches="tight", pad_inches=0.18)
    plt.close(fig)
    return out_path


def chart_comparativo_por_grupo(cross_prev, cross_act, order, period_prev, period_act, out_path, max_groups=6):
    if not cross_prev or not cross_act:
        return None
    groups = [g for g in cross_act.keys() if g in cross_prev][:max_groups]
    if not groups:
        return None

    n = len(groups)
    fig, axes = plt.subplots(n, 1, figsize=(7.0, 1.05 * n))
    if n == 1:
        axes = [axes]

    for ax, g in zip(axes, groups):
        rows = [(period_prev, cross_prev[g]), (period_act, cross_act[g])]
        y = [1, 0]
        for yi, (period_label, gdata) in zip(y, rows):
            left = 0
            for label in order:
                width = gdata["porcentajes"].get(label, 0) * 100
                if width <= 0:
                    continue
                color = COLOR_ASSIGNER.color_for(label)
                ax.barh(yi, width, left=left, height=0.62, color=color,
                        edgecolor=SURFACE, linewidth=1.2, zorder=3)
                left += width
        ax.set_yticks(y)
        ax.set_yticklabels([period_prev, period_act], fontsize=8.6, color=INK_SECONDARY)
        ax.set_xlim(0, 100)
        ax.set_xticks([])
        _clean_axes(ax)
        ax.tick_params(left=False)
        ax.set_title(f"{g}  ·  n={fmt_n(cross_prev[g]['total'])} -> {fmt_n(cross_act[g]['total'])}",
                      loc="left", fontsize=9.6, color=INK, fontweight="bold", pad=3)
        ax.margins(y=0.5)

    fig.subplots_adjust(hspace=0.85)
    fig.savefig(out_path, dpi=CHART_DPI, bbox_inches="tight", pad_inches=0.18)
    plt.close(fig)
    return out_path


def chart_top_categorias(top_data, valencia_label, out_path):
    if not top_data or not top_data["items"]:
        return None
    items = list(reversed(top_data["items"]))
    color = COLOR_ASSIGNER.color_for(valencia_label)
    fig, ax = _new_fig((6.6, 0.55 * len(items) + 0.5))
    y = list(range(len(items)))
    values = [it["cantidad"] for it in items]
    labels = [it["valor"] for it in items]
    ax.barh(y, values, height=0.6, color=color, zorder=3)
    for yi, v in zip(y, values):
        ax.text(v + max(values) * 0.02, yi, fmt_n(v), va="center", ha="left", fontsize=9.6, color=INK)
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=10, color=INK)
    ax.set_xticks([])
    _clean_axes(ax)
    ax.tick_params(left=False)
    ax.set_xlim(0, max(values) * 1.22)
    fig.savefig(out_path, dpi=CHART_DPI, bbox_inches="tight", pad_inches=0.18)
    plt.close(fig)
    return out_path


def chart_nps_segmentos(nps, out_path):
    metrics = [m for m in ["eNPS", "LNPS"] if m in nps]
    if not metrics:
        return None
    labels_map = {"eNPS": "eNPS  (empresa)", "LNPS": "LNPS  (líder inmediato)"}
    order = ["Promotor", "Neutral", "Detractor"]
    fig, ax = _new_fig((7.0, 0.9 + 0.7 * len(metrics)))
    y = list(range(len(metrics)))[::-1]
    for yi, metric in zip(y, metrics):
        seg = nps[metric]["segmentos"]
        left = 0
        for label in order:
            info = seg.get(label)
            if not info:
                continue
            pct = (info.get("porcentaje") or 0) * 100
            color = COLOR_ASSIGNER.color_for(label)
            ax.barh(yi, pct, left=left, height=0.56, color=color,
                    edgecolor=SURFACE, linewidth=1.4, zorder=3)
            if pct > 6:
                ax.text(left + pct / 2, yi, f"{pct:.0f}%", ha="center", va="center",
                        fontsize=9.6, color="#ffffff", fontweight="bold")
            left += pct
    ax.set_yticks(y)
    ax.set_yticklabels([labels_map[m] for m in metrics], fontsize=10.8, color=INK)
    ax.set_xlim(0, 100)
    ax.set_xticks([])
    _clean_axes(ax)
    ax.tick_params(left=False)
    ax.margins(y=0.55)
    fig.savefig(out_path, dpi=CHART_DPI, bbox_inches="tight", pad_inches=0.18)
    plt.close(fig)
    return out_path


def chart_nps_cruce_heatmap(nps, out_path):
    cruce = nps.get("cruce_empresa_vs_lider")
    if not cruce:
        return None
    order = ["Promotor", "Neutral", "Detractor"]
    grid = {(r["eNPS"], r["LNPS"]): (r["Personas"], r["Porcentaje"]) for r in cruce}
    max_p = max((v[0] for v in grid.values()), default=0)
    if max_p <= 0:
        return None

    from matplotlib.patches import FancyBboxPatch
    cmap = mcolors.LinearSegmentedColormap.from_list("blue_seq", BLUE_SEQ)
    norm = mcolors.PowerNorm(gamma=0.5, vmin=0, vmax=max_p)

    fig, ax = _new_fig((5.4, 4.4))
    for i, emp in enumerate(order):
        for j, lid in enumerate(order):
            personas, pct = grid.get((emp, lid), (0, 0))
            color = cmap(norm(personas))
            text_color = "#ffffff" if norm(personas) >= 0.62 else INK
            ax.add_patch(FancyBboxPatch((j, len(order) - 1 - i), 0.96, 0.96,
                                         boxstyle="round,pad=0,rounding_size=0.04",
                                         linewidth=0, facecolor=color, zorder=2))
            ax.text(j + 0.48, len(order) - 1 - i + 0.58, fmt_n(personas),
                    ha="center", va="center", fontsize=13, color=text_color, fontweight="bold")
            ax.text(j + 0.48, len(order) - 1 - i + 0.30, f"{pct * 100:.1f}%",
                    ha="center", va="center", fontsize=9.5, color=text_color)
    ax.set_xlim(0, len(order))
    ax.set_ylim(0, len(order))
    ax.set_xticks([i + 0.48 for i in range(len(order))])
    ax.set_xticklabels(order, fontsize=10.8, color=INK)
    ax.set_yticks([len(order) - 1 - i + 0.48 for i in range(len(order))])
    ax.set_yticklabels(order, fontsize=10.8, color=INK)
    ax.set_xlabel("Líder inmediato (LNPS)", fontsize=10.5, color=INK_SECONDARY, labelpad=8)
    ax.set_ylabel("Empresa (eNPS)", fontsize=10.5, color=INK_SECONDARY, labelpad=8)
    ax.set_aspect("equal")
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.tick_params(length=0)
    fig.savefig(out_path, dpi=CHART_DPI, bbox_inches="tight", pad_inches=0.18)
    plt.close(fig)
    return out_path


# ============================================================
# CONVERSOR MARKDOWN -> FLOWABLES DE REPORTLAB
# ============================================================

def esc(text):
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def inline_md(text):
    text = esc(text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"(?<!\*)\*([^*]+?)\*(?!\*)", r"<i>\1</i>", text)
    return text


HEADING_RE = re.compile(r"^(#{1,4})\s+(.*)$")
HRULE_RE = re.compile(r"^-{3,}$")
BOLD_ONLY_RE = re.compile(r"^\*\*(.+)\*\*$")
BULLET_RE = re.compile(r"^(\s*)-\s+(.*)$")
NUMBERED_RE = re.compile(r"^(\s*)\d+\.\s+(.*)$")


# ------------------------------------------------------------
# Escala tipografica -- Red Hat Display en todo el documento, con saltos
# de tamano/peso deliberados entre nivel y nivel (nada de tamanos casi
# iguales entre titulo, subtitulo y cuerpo).
# ------------------------------------------------------------
def build_paragraph_styles():
    s = {}
    s["h1"] = ParagraphStyle("h1", fontName=FONT_BOLD, fontSize=19, leading=23,
                              textColor=RL_INK, spaceBefore=0, spaceAfter=2)
    s["h2"] = ParagraphStyle("h2", fontName=FONT_SEMIBOLD, fontSize=13, leading=17,
                              textColor=RL_INK, spaceBefore=14, spaceAfter=6)
    s["label"] = ParagraphStyle("label", fontName=FONT_SEMIBOLD, fontSize=9, leading=13,
                                 textColor=RL_INK_SECONDARY, spaceBefore=12, spaceAfter=4)
    s["body"] = ParagraphStyle("body", fontName=FONT_REGULAR, fontSize=10, leading=15,
                                textColor=RL_INK, spaceBefore=0, spaceAfter=6, alignment=TA_JUSTIFY)
    s["bullet"] = ParagraphStyle("bullet", fontName=FONT_REGULAR, fontSize=10, leading=14.5,
                                  textColor=RL_INK, spaceBefore=0, spaceAfter=3, alignment=TA_JUSTIFY)
    s["caption"] = ParagraphStyle("caption", fontName=FONT_MEDIUM, fontSize=8.5, leading=11.5,
                                   textColor=RL_INK_MUTED, alignment=TA_CENTER, spaceBefore=5, spaceAfter=14)
    return s


STYLES = build_paragraph_styles()

# Color de acento por seccion (hex, para poder derivar tintes de chips/tarjetas):
# neutro por defecto, semantico cuando el titulo corresponde claramente a una
# valencia o a eNPS/LNPS. La barra del H1 y las tarjetas/chips de esa seccion
# comparten el mismo color -- es lo que amarra visualmente todo el documento.
H1_ACCENT_RULES = [
    (["principales fortalezas"], GOOD),
    (["principales oportunidades"], WARNING),
    (["principales riesgos"], CRITICAL),
    (["enps", "lnps"], BLUE),
]
DEFAULT_ACCENT_HEX = INK_SECONDARY


def h1_accent_hex(title):
    norm = normalize_text(title)
    for keywords, color in H1_ACCENT_RULES:
        if all(kw in norm for kw in keywords):
            return color
    return DEFAULT_ACCENT_HEX


def styled_h1(title_text, content_width, color=None):
    """Titulo de seccion con barra de acento a la izquierda (neutra o
    semantica) en vez de una regla horizontal -- misma idea en toda la pieza."""
    rl_color = rl.HexColor(color) if color else rl.HexColor(h1_accent_hex(title_text))
    para = Paragraph(inline_md(title_text), STYLES["h1"])
    tbl = Table([[para]], colWidths=[content_width])
    tbl.setStyle(TableStyle([
        ("LINEBEFORE", (0, 0), (0, 0), 3.2, rl_color),
        ("LEFTPADDING", (0, 0), (0, 0), 10),
        ("RIGHTPADDING", (0, 0), (0, 0), 0),
        ("TOPPADDING", (0, 0), (0, 0), 2),
        ("BOTTOMPADDING", (0, 0), (0, 0), 2),
    ]))
    return tbl


def hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def tint_hex(hex_color, amount=0.85):
    """Mezcla hacia blanco -- fondo pastel para chips/tarjetas."""
    r, g, b = hex_to_rgb(hex_color)
    r = int(r + (255 - r) * amount)
    g = int(g + (255 - g) * amount)
    b = int(b + (255 - b) * amount)
    return f"#{r:02x}{g:02x}{b:02x}"


def shade_hex(hex_color, amount=0.42):
    """Mezcla hacia negro -- texto legible sobre el fondo pastel de arriba."""
    r, g, b = hex_to_rgb(hex_color)
    r = int(r * (1 - amount))
    g = int(g * (1 - amount))
    b = int(b * (1 - amount))
    return f"#{r:02x}{g:02x}{b:02x}"


def strip_bold_markers(text):
    return re.sub(r"\*\*(.+?)\*\*", r"\1", text)


def chip_markup(term, bg_hex, fg_hex):
    """'Chip' visual para terminos cortos (categorias, emociones, palabras
    clave): resaltado de fondo inline -- reportlab no soporta bordes/radios
    en <span>, asi que el color de fondo solo ya da la lectura de etiqueta."""
    return (f'<span backColor="{bg_hex}" textColor="{fg_hex}" fontName="{FONT_SEMIBOLD}">'
            f'&#8201;{esc(strip_bold_markers(term))}&#8201;</span>')


PERSON_PCT_RE = re.compile(r"^([\d.,]+)\s*personas?\s*\(([\d.,]+%)\)$")


def mini_stat_card(label, value, color_hex, width):
    """Tarjeta compacta tipo KPI para rachas de '**Etiqueta:** valor' (eNPS,
    cruce empresa-lider...) -- la misma idea visual de las tarjetas de la
    portada, reutilizada dentro del cuerpo del informe."""
    color = rl.HexColor(color_hex)
    label = strip_bold_markers(label.strip())
    value = strip_bold_markers(value.strip())
    m = PERSON_PCT_RE.match(value)
    big, small = (m.group(2), f"{m.group(1)} personas") if m else (value, None)
    rows = [[Paragraph(esc(big), ParagraphStyle("v", fontName=FONT_BOLD, fontSize=15, leading=17,
                                                  alignment=TA_CENTER, textColor=color))]]
    if small:
        rows.append([Paragraph(esc(small), ParagraphStyle("s2", fontName=FONT_REGULAR, fontSize=7.2,
                                                             leading=9, alignment=TA_CENTER,
                                                             textColor=RL_INK_MUTED))])
    rows.append([Paragraph(esc(label.upper()), ParagraphStyle("l", fontName=FONT_MEDIUM, fontSize=7.2,
                                                                leading=9, alignment=TA_CENTER,
                                                                textColor=RL_INK_SECONDARY))])
    inner = Table(rows, colWidths=[width])
    inner.setStyle(TableStyle([
        ("TOPPADDING", (0, 0), (-1, 0), 8),
        ("BOTTOMPADDING", (0, -1), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -2), 1),
        ("LINEABOVE", (0, 0), (-1, 0), 2, color),
        ("BACKGROUND", (0, 0), (-1, -1), RL_SURFACE),
    ]))
    return inner


def status_legend():
    """Leyenda de color: que significa verde/ambar/rojo en tarjetas, chips y
    graficos. Se muestra una vez, junto al primer grafico de eNPS/LNPS.
    Un solo Paragraph con 'swatches' de color via <span backColor> -- evita la
    fragilidad de anchos de columna de una Table con celdas de tamano mixto."""
    entries = [("Promotor · Fortaleza", GOOD), ("Neutral · Oportunidad", WARNING),
               ("Detractor · Riesgo", CRITICAL)]
    parts = []
    for label, hex_color in entries:
        swatch = f'<span backColor="{hex_color}">&#160;&#160;</span>'
        parts.append(f"{swatch}&#160;{esc(label)}")
    text = ("&#160;" * 6).join(parts)
    style = ParagraphStyle("legend", fontName=FONT_REGULAR, fontSize=8.3, leading=14,
                            textColor=RL_INK_SECONDARY, spaceAfter=12)
    return Paragraph(text, style)


def quote_block(text, caption, color_hex, content_width):
    """Cita textual (comentario real de una persona), con barra de acento a la
    izquierda -- igual idea que styled_h1, aplicada a un bloque de cita."""
    quote_style = ParagraphStyle("quote", fontName=FONT_ITALIC, fontSize=9.6, leading=14,
                                  textColor=RL_INK_SECONDARY, alignment=TA_JUSTIFY, spaceAfter=2)
    cells = [[Paragraph(f"“{esc(text)}”", quote_style)]]
    if caption:
        cells.append([Paragraph(esc(caption), ParagraphStyle(
            "qcap", fontName=FONT_MEDIUM, fontSize=8, leading=10.5, textColor=RL_INK_MUTED))])
    tbl = Table(cells, colWidths=[content_width - 14])
    style_cmds = [
        ("LINEBEFORE", (0, 0), (0, -1), 2.6, rl.HexColor(color_hex)),
        ("LEFTPADDING", (0, 0), (0, -1), 12),
        ("TOPPADDING", (0, 0), (0, 0), 4),
        ("BOTTOMPADDING", (0, -1), (0, -1), 4),
    ]
    if caption:
        style_cmds.append(("TOPPADDING", (0, 1), (0, 1), 1))
    tbl.setStyle(TableStyle(style_cmds))
    return tbl


def build_quotes_block(data_actual, order, content_width, valencia_keyword="riesgo", max_quotes=3):
    """Comentarios textuales reales (no sintetizados por la IA), tomados del
    payload local -- por defecto los de Riesgo, para que 'Que dicen las
    personas' incluya voz directa y no solo la lectura interpretada."""
    payload = data_actual.get("payload") or {}
    comments_by_valencia = payload.get("comentarios_representativos_por_valencia", {})
    if not comments_by_valencia:
        return []
    target_label = find_label_like(order, valencia_keyword) or find_label_like(
        list(comments_by_valencia), valencia_keyword)
    items = comments_by_valencia.get(target_label, []) if target_label else []
    items = [it for it in items if (it.get("comentario") or "").strip()]
    seen, deduped = set(), []
    for it in items:
        key = it["comentario"].strip()
        if key not in seen:
            seen.add(key)
            deduped.append(it)
    items = deduped
    if not items:
        return []
    color_hex = COLOR_ASSIGNER.color_for(target_label) if target_label else CRITICAL

    flow = [Spacer(1, 6), Paragraph(f"Comentarios representativos · {esc(target_label)}", STYLES["h2"])]
    for item in items[:max_quotes]:
        text = item["comentario"].strip()
        extra_vals = [str(v) for k, v in item.items() if k != "comentario" and v][:2]
        caption = " · ".join(extra_vals) if extra_vals else None
        flow.append(quote_block(text, caption, color_hex, content_width))
        flow.append(Spacer(1, 6))
    return flow


# Palabras clave (normalizadas) para decidir que grafico va despues de cada encabezado.
CHART_TRIGGERS_H2 = [
    (["panorama general"], "dist_actual"),
    (["comparativo"], "comparativo"),
    (["lectura por agrupacion"], "grupo_actual"),
    (["principales fortalezas"], "top_fortaleza"),
    (["principales oportunidades"], "top_oportunidad"),
    (["principales riesgos"], "top_riesgo"),
    (["enps", "lnps"], "nps_segmentos"),
]
CHART_TRIGGERS_H3 = [
    (["cruce"], "nps_cruce"),
]
SKIP_H2_TITLES = ["periodo analizado"]

# Algunos graficos (el mapa de calor, casi cuadrado) se ven demasiado altos si
# se estiran al ancho completo del contenido -- se muestran mas angostos y
# centrados en vez de a lo ancho de la pagina.
CHART_WIDTH_FRACTION = {"nps_cruce": 0.58}


def place_chart_image(path, content_width, key=None):
    with PILImage.open(path) as im:
        w_px, h_px = im.size
    fraction = CHART_WIDTH_FRACTION.get(key, 1.0)
    width = content_width * fraction
    height = width * (h_px / w_px)
    img = Image(str(path), width=width, height=height)
    if fraction < 1.0:
        img.hAlign = "CENTER"
    return img

# Etiquetas cuyo contenido es comentario/interpretacion (no hechos puntuales):
# sus bullets se funden en un solo parrafo en vez de quedar como lista.
PARAGRAPH_LABELS = {
    "inferencia", "interpretacion", "lectura", "lectura ejecutiva", "lectura de negocio",
    "sintesis interpretativa", "conclusion", "conclusion comparativa", "acciones diferenciadas",
}

# '**Etiqueta:** valor corto' -- 3 o mas consecutivos se agrupan en tarjetas.
LABEL_VALUE_RE = re.compile(r"^\*\*(.+?):\*\*\s*(.+)$")


def match_triggers(title, rules):
    norm = normalize_text(title)
    matched = []
    for keywords, key in rules:
        if all(kw in norm for kw in keywords):
            matched.append(key)
    return matched


def render_markdown(md_text, chart_bank, content_width, data_actual=None, order=None):
    """Convierte el markdown del resumen ejecutivo en flowables, insertando graficos
    (de chart_bank, ya generados) justo despues del encabezado de la seccion asociada.

    En vez de volcar todo como vinetas parejas, cada corrida de items se separa en:
    - 3+ '**Etiqueta:** valor' consecutivos -> fila de tarjetas tipo KPI.
    - Bullet con hijos anidados cortos (categorias, emociones...) -> chips inline.
    - Bullets bajo una etiqueta interpretativa (Inferencia, Interpretacion...) ->
      un solo parrafo corrido, no una lista.
    - El resto -> vinetas normales (hechos puntuales de 'Evidencia')."""
    flow = []
    lines = md_text.splitlines()
    used_charts = set()

    pending_items = []  # [{"text": <html listo>, "raw": <markdown crudo>, "chips": [term, ...]}]
    numbered_counter = [0]
    active_label = [None]
    section_hex = [DEFAULT_ACCENT_HEX]

    def flush_list():
        nonlocal pending_items
        if not pending_items:
            return

        segments = []
        buf = []
        i, n = 0, len(pending_items)
        while i < n:
            item = pending_items[i]
            m = LABEL_VALUE_RE.match(item["raw"]) if not item["chips"] else None
            if m and len(m.group(2)) <= 40:
                run = []
                j = i
                while j < n:
                    mj = LABEL_VALUE_RE.match(pending_items[j]["raw"]) if not pending_items[j]["chips"] else None
                    if not (mj and len(mj.group(2)) <= 40):
                        break
                    run.append((mj.group(1), mj.group(2)))
                    j += 1
                if len(run) >= 3:
                    if buf:
                        segments.append(("text", buf))
                        buf = []
                    segments.append(("cards", run))
                    i = j
                    continue
            buf.append(item)
            i += 1
        if buf:
            segments.append(("text", buf))

        for kind, payload in segments:
            if kind == "cards":
                width = content_width / len(payload)
                cards = [
                    mini_stat_card(lbl, val, status_color_for_flexible(lbl) or section_hex[0], width)
                    for lbl, val in payload
                ]
                row = Table([cards], colWidths=[width] * len(cards))
                row.setStyle(TableStyle([
                    ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ]))
                flow.append(Spacer(1, 3))
                flow.append(row)
                flow.append(Spacer(1, 9))
                continue

            def chips_markup_for(item):
                if not item["chips"]:
                    return ""
                bg, fg = tint_hex(section_hex[0]), shade_hex(section_hex[0])
                return "  " + "  ".join(chip_markup(c, bg, fg) for c in item["chips"])

            if active_label[0] in PARAGRAPH_LABELS:
                parts = [it["text"] + chips_markup_for(it) for it in payload]
                flow.append(Paragraph(" ".join(parts), STYLES["body"]))
            else:
                lis = [ListItem(Paragraph(it["text"] + chips_markup_for(it), STYLES["bullet"]),
                                 bulletColor=RL_INK_MUTED) for it in payload]
                flow.append(ListFlowable(lis, bulletType="bullet", start="circle", leftIndent=13,
                                          bulletFontSize=5.6, spaceBefore=2, spaceAfter=6))
        pending_items = []

    def strip_trailing_comma(text):
        return text[:-1] if text.endswith(",") else text

    def insert_charts(keys):
        for key in keys:
            if key in used_charts:
                continue
            entry = chart_bank.get(key)
            if not entry:
                continue
            used_charts.add(key)
            for path, caption in entry:
                flow.append(place_chart_image(path, content_width, key))
                if caption:
                    flow.append(Paragraph(caption, STYLES["caption"]))

    skip_section = False
    first_h1_rendered = False
    h2_counter = [0]
    in_quotes_section = [False]

    def maybe_append_quotes():
        if in_quotes_section[0] and data_actual is not None:
            flow.extend(build_quotes_block(data_actual, order or [], content_width))

    for raw_line in lines:
        line = raw_line.rstrip()
        if not line.strip():
            flush_list()
            continue

        heading = HEADING_RE.match(line)
        if heading:
            flush_list()
            numbered_counter[0] = 0
            level, title = len(heading.group(1)), heading.group(2).strip()
            if level == 1:
                continue
            if level == 2:
                norm_title = normalize_text(title)
                skip_section = any(normalize_text(t) in norm_title for t in SKIP_H2_TITLES)
                if skip_section:
                    continue
                maybe_append_quotes()
                in_quotes_section[0] = "que dicen las personas" in norm_title
                if first_h1_rendered:
                    flow.append(PageBreak())
                first_h1_rendered = True
                h2_counter[0] += 1
                display_title = f"{h2_counter[0]}. {LEADING_NUMERAL_RE.sub('', title)}"
                section_hex[0] = h1_accent_hex(title)
                flow.append(Spacer(1, 4))
                flow.append(styled_h1(display_title, content_width, color=section_hex[0]))
                flow.append(Spacer(1, 10))
                insert_charts(match_triggers(title, CHART_TRIGGERS_H2))
                if "nps_segmentos" in match_triggers(title, CHART_TRIGGERS_H2):
                    flow.append(status_legend())
                continue
            if skip_section:
                continue
            if level == 3:
                flow.append(Paragraph(inline_md(title), STYLES["h2"]))
                insert_charts(match_triggers(title, CHART_TRIGGERS_H3))
                continue
            if level == 4:
                # La IA a veces usa "#### Etiqueta" en vez de "**Etiqueta**" -- se
                # trata igual que una etiqueta en negrilla (mismo estilo, misma logica).
                flush_list()
                active_label[0] = normalize_text(title)
                flow.append(Paragraph(esc(title.upper()), STYLES["label"]))
                continue

        if skip_section:
            continue

        if HRULE_RE.match(line.strip()):
            # Separador markdown "---" -- ya usamos la barra de acento del H1 y el
            # salto de pagina por seccion, no aporta nada visible aqui.
            flush_list()
            continue

        bold_only = BOLD_ONLY_RE.match(line.strip())
        if bold_only:
            flush_list()
            active_label[0] = normalize_text(bold_only.group(1))
            flow.append(Paragraph(esc(bold_only.group(1).upper()), STYLES["label"]))
            continue

        numbered = NUMBERED_RE.match(line)
        if numbered:
            flush_list()
            numbered_counter[0] += 1
            text = inline_md(strip_trailing_comma(numbered.group(2).strip()))
            flow.append(Paragraph(f"<b>{numbered_counter[0]}.</b> {text}",
                                   ParagraphStyle("num", parent=STYLES["body"], spaceBefore=5)))
            continue

        bullet = BULLET_RE.match(line)
        if bullet:
            indent = len(bullet.group(1))
            raw_content = strip_trailing_comma(bullet.group(2).strip())
            chip_worthy = (
                indent > 0 and pending_items and len(strip_bold_markers(raw_content)) <= 40
                and not LABEL_VALUE_RE.match(raw_content)
                and ":" not in raw_content
            )
            if chip_worthy:
                pending_items[-1]["chips"].append(raw_content)
            else:
                pending_items.append({"text": inline_md(raw_content), "raw": raw_content, "chips": []})
            continue

        flush_list()
        flow.append(Paragraph(inline_md(line.strip()), STYLES["body"]))

    flush_list()
    maybe_append_quotes()
    return flow, used_charts


# ============================================================
# ARMADO DEL PDF
# ============================================================

def kpi_card(label, value, color, width):
    inner = Table(
        [[Paragraph(value, ParagraphStyle("v", fontName=FONT_BOLD, fontSize=20,
                                           leading=23, alignment=TA_CENTER, textColor=color))],
         [Paragraph(esc(label.upper()),
                     ParagraphStyle("l", fontName=FONT_MEDIUM, fontSize=7.6,
                                    leading=10, alignment=TA_CENTER, textColor=RL_INK_SECONDARY))]],
        colWidths=[width],
    )
    inner.setStyle(TableStyle([
        ("TOPPADDING", (0, 0), (-1, 0), 10),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 1),
        ("BOTTOMPADDING", (0, 1), (-1, 1), 9),
        ("LINEABOVE", (0, 0), (-1, 0), 2.2, color),
        ("BACKGROUND", (0, 0), (-1, -1), RL_SURFACE),
    ]))
    return inner


def build_pdf(data_actual, data_prev, output_path, charts_dir):
    charts_dir.mkdir(parents=True, exist_ok=True)
    period = data_actual["period"]
    period_prev = data_prev["period"] if data_prev else None
    metadata = (data_actual.get("payload") or {}).get("metadata", {})

    labels = data_actual["distribucion_valencia"][data_actual["valencia_col"]].tolist()
    counts = data_actual["distribucion_valencia"]["Cantidad"].tolist()
    order = ordered_labels(labels, counts)

    # -------- generar graficos --------
    chart_bank = {}

    p = chart_distribucion_valencia(data_actual, order, charts_dir / "dist_actual.png")
    if p:
        chart_bank["dist_actual"] = [(p, f"Distribución de valencia emocional · {period}.")]

    comparativo_entries = []
    if data_prev:
        p = chart_comparativo_slope(data_actual, data_prev, order, charts_dir / "comparativo_slope.png")
        if p:
            comparativo_entries.append((p, f"Evolución de la valencia emocional: {period_prev} -> {period}."))
        cross_act = group_cross_map(data_actual)
        cross_prev = group_cross_map(data_prev)
        p = chart_comparativo_por_grupo(cross_prev, cross_act, order, period_prev, period,
                                         charts_dir / "comparativo_grupo.png")
        if p:
            comparativo_entries.append((p, f"Comparativo por agrupación de negocio: {period_prev} -> {period}."))
    if comparativo_entries:
        chart_bank["comparativo"] = comparativo_entries

    cross_act_full = group_cross_map(data_actual)
    p = chart_valencia_por_grupo(cross_act_full, order, charts_dir / "grupo_actual.png")
    if p:
        chart_bank["grupo_actual"] = [(p, f"Distribución de valencia por agrupación de negocio · {period}.")]

    for key, kw in [("top_fortaleza", "fortaleza"), ("top_oportunidad", "oportunidad"), ("top_riesgo", "riesgo")]:
        label = find_label_like(order, kw)
        if not label:
            continue
        top_data = top_categorias_for_valencia(data_actual, label)
        chart_path = chart_top_categorias(top_data, label, charts_dir / f"{key}.png")
        if chart_path:
            col_name = top_data["columna"]
            chart_bank[key] = [(chart_path, f"{col_name} más frecuentes en {label} · {period}.")]

    nps = nps_summary(data_actual)
    if nps:
        p = chart_nps_segmentos(nps, charts_dir / "nps_segmentos.png")
        if p:
            chart_bank["nps_segmentos"] = [(p, f"Distribución de personas por segmento · {period}.")]
        p = chart_nps_cruce_heatmap(nps, charts_dir / "nps_cruce.png")
        if p:
            chart_bank["nps_cruce"] = [(p, f"Cruce de personas por segmento de empresa y de líder · {period}.")]

    # -------- documento --------
    page_w, page_h = A4
    margin = 2.0 * cm
    content_w = page_w - 2 * margin

    doc_title = "Valencia Emocional en Encuestas de Retiro"
    subtitle = f"Informe técnico mensual · {period}"
    if period_prev:
        subtitle += f" (comparativo vs. {period_prev})"
    footer_text = "Informe técnico — Valencia emocional en encuestas de retiro · Confidencial, uso interno"

    def draw_cover(cnv, doc):
        cnv.saveState()
        cnv.setFillColor(RL_COVER_BG)
        cnv.rect(0, 0, page_w, page_h, fill=1, stroke=0)
        cnv.setFillColor(RL_COVER_ACCENT)
        cnv.rect(0, page_h - 0.32 * cm, page_w, 0.32 * cm, fill=1, stroke=0)
        cnv.setFillColor(rl.HexColor("#1a2e21"))
        cnv.rect(0, 0, page_w, 3.2 * cm, fill=1, stroke=0)
        cnv.setFillColor(rl.HexColor("#7fae86"))
        cnv.setFont(FONT_REGULAR, 8.4)
        cnv.drawString(margin, 1.35 * cm, f"Generado automáticamente · analisis_valencia_ai · {period}")
        cnv.drawString(margin, 1.0 * cm, "Documento de circulación interna. Datos agregados de encuestas de retiro.")
        cnv.restoreState()

    def draw_header_footer(cnv, doc):
        cnv.saveState()
        cnv.setStrokeColor(RL_GRID)
        cnv.setLineWidth(0.6)
        cnv.line(margin, page_h - 1.35 * cm, page_w - margin, page_h - 1.35 * cm)
        cnv.setFont(FONT_SEMIBOLD, 8.2)
        cnv.setFillColor(RL_INK_SECONDARY)
        cnv.drawString(margin, page_h - 1.15 * cm, doc_title)
        cnv.setFont(FONT_REGULAR, 8.2)
        cnv.setFillColor(RL_INK_MUTED)
        cnv.drawRightString(page_w - margin, page_h - 1.15 * cm, period)
        cnv.line(margin, 1.55 * cm, page_w - margin, 1.55 * cm)
        cnv.setFont(FONT_REGULAR, 7.5)
        cnv.setFillColor(RL_INK_MUTED)
        cnv.drawString(margin, 1.15 * cm, footer_text)
        cnv.drawRightString(page_w - margin, 1.15 * cm, f"Página {doc.page - 1}")
        cnv.restoreState()

    doc = BaseDocTemplate(str(output_path), pagesize=A4,
                           leftMargin=margin, rightMargin=margin,
                           topMargin=margin, bottomMargin=margin,
                           title=doc_title, author="People Analytics")
    frame_cover = Frame(margin, 4.2 * cm, content_w, page_h - 4.2 * cm - 4.6 * cm, id="cover")
    frame_content = Frame(margin, 1.9 * cm, content_w, page_h - 1.9 * cm - 1.9 * cm, id="content")
    doc.addPageTemplates([
        PageTemplate(id="Cover", frames=[frame_cover], onPage=draw_cover),
        PageTemplate(id="Content", frames=[frame_content], onPage=draw_header_footer),
    ])

    story = []
    story += [
        Spacer(1, 3.2 * cm),
        Paragraph("INFORME TÉCNICO · PEOPLE ANALYTICS", ParagraphStyle(
            "tag", fontName=FONT_SEMIBOLD, fontSize=9.5, textColor=RL_COVER_ACCENT, spaceAfter=16)),
        Paragraph(doc_title, ParagraphStyle("ct", fontName=FONT_BLACK, fontSize=30, leading=34,
                                             textColor=rl.white)),
        Spacer(1, 10),
        Paragraph(subtitle, ParagraphStyle("cs", fontName=FONT_MEDIUM, fontSize=13, leading=18,
                                            textColor=rl.HexColor("#d9e8dc"))),
        Spacer(1, 24),
    ]
    if metadata.get("total_filas"):
        story.append(Paragraph(
            f"Fuente: base de encuestas de retiro ({fmt_n(metadata['total_filas'])} respuestas)"
            + (" cruzada con eNPS / LNPS." if nps else "."),
            ParagraphStyle("cm", fontName=FONT_REGULAR, fontSize=9.3, leading=14, textColor=rl.HexColor("#a9c2ad"))))
    story.append(Paragraph(
        "Generado automáticamente con el pipeline analisis_valencia.py + generar_informe_pdf.py.",
        ParagraphStyle("cm2", fontName=FONT_REGULAR, fontSize=9.3, leading=14, textColor=rl.HexColor("#a9c2ad"))))

    story.append(NextPageTemplate("Content"))
    story.append(PageBreak())

    # -------- KPIs --------
    story.append(styled_h1("Panorama del mes, de un vistazo", content_w, color=INK))
    story.append(Spacer(1, 12))

    pcts = valencia_pct_map(data_actual)
    prev_pcts = valencia_pct_map(data_prev) if data_prev else {}
    cards = []
    n_cards = len(order) + (2 if nps else 0) + 1
    card_w = content_w / max(n_cards, 1)
    for label in order:
        pct = pcts.get(label, 0)
        color = rl.HexColor(COLOR_ASSIGNER.color_for(label))
        value = fmt_pct(pct)
        if label in prev_pcts:
            delta = (pct - prev_pcts[label]) * 100
            value = f"{fmt_pct(pct)}"
        cards.append(kpi_card(label, value, color, card_w))
    if nps:
        for metric in ["eNPS", "LNPS"]:
            if metric in nps:
                cards.append(kpi_card(f"{metric}", f"{nps[metric]['puntaje']:.1f}", RL_BLUE, card_w))
    cards.append(kpi_card("Respuestas", fmt_n(metadata.get("total_filas", 0)), RL_INK_SECONDARY, card_w))

    row = Table([cards], colWidths=[card_w] * len(cards))
    row.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    story.append(row)
    story.append(Spacer(1, 6))
    if data_prev:
        story.append(Paragraph(
            f"Comparado contra {period_prev}. Las secciones siguientes profundizan cada cifra con su "
            f"gráfico correspondiente.", STYLES["caption"]))
    else:
        story.append(Paragraph(
            "No hay periodo anterior disponible: este mes se trata como línea base.", STYLES["caption"]))
    story.append(Spacer(1, 4))

    # -------- metodologia breve --------
    story.append(styled_h1("Metodología y alcance", content_w, color=INK))
    story.append(Spacer(1, 10))
    cols_det = metadata.get("columnas_detectadas", {})
    meta_bits = [
        f"{fmt_n(metadata.get('total_filas', 0))} respuestas, {metadata.get('total_columnas', 'N/D')} columnas.",
        f"Columna de valencia: <i>{esc(str(metadata.get('columna_valencia', 'N/D')))}</i>.",
    ]
    if metadata.get("columna_agrupacion"):
        meta_bits.append(f"Columna de agrupación: <i>{esc(str(metadata['columna_agrupacion']))}</i>.")
    story.append(Paragraph(
        "El análisis detecta automáticamente la columna de valencia emocional y de agrupación de negocio, "
        "limpia el texto de preguntas y respuestas, y calcula distribuciones y cruces localmente antes de "
        "generar el resumen narrativo. " + " ".join(meta_bits), STYLES["body"]))
    if data_prev:
        story.append(Paragraph(
            f"El comparativo mensual usa el informe ejecutivo de <b>{period_prev}</b> como referencia previa.",
            STYLES["body"]))
    warnings = (data_actual.get("payload") or {}).get("advertencias_calidad_datos", [])
    if warnings:
        cols_txt = ", ".join(w["columna"] for w in warnings[:8])
        story.append(Paragraph(
            f"Advertencia de calidad de datos: {len(warnings)} columna(s) con menos del 5% de información "
            f"disponible ({esc(cols_txt)}); no se usaron para conclusiones.", STYLES["body"]))

    story.append(PageBreak())

    # -------- cuerpo (markdown del resumen ejecutivo, con graficos insertados) --------
    if data_actual.get("markdown"):
        rendered, used = render_markdown(data_actual["markdown"], chart_bank, content_w,
                                          data_actual=data_actual, order=order)
        story += rendered
        leftover = [k for k in chart_bank if k not in used]
        for key in leftover:
            for path, caption in chart_bank[key]:
                with PILImage.open(path) as im:
                    w_px, h_px = im.size
                width = content_w
                height = width * (h_px / w_px)
                story.append(Image(str(path), width=width, height=height))
                story.append(Paragraph(caption, STYLES["caption"]))
    else:
        story.append(Paragraph(
            "No se encontró resumen_ejecutivo.md para este periodo. Ejecuta analisis_valencia.py antes de "
            "generar el informe en PDF.", STYLES["body"]))

    story.append(Spacer(1, 14))
    story.append(HRFlowable(width="100%", thickness=0.6, color=RL_GRID))
    story.append(Paragraph(
        f"Fuente: outputs/{period}/ del proyecto analisis_valencia_ai (tablas_resumen.xlsx, "
        f"analysis_payload.json, resumen_ejecutivo.md). Generado el "
        f"{datetime.now().strftime('%d/%m/%Y')}.", STYLES["caption"]))

    doc.build(story)
    return output_path


# ============================================================
# PAGINA HTML LOCAL (companera del PDF, para abrir en el navegador)
# ============================================================

LEADING_NUMERAL_RE = re.compile(r"^\d+[.)]\s*")


def extract_toc_titles(markdown_text):
    titles = []
    for line in markdown_text.splitlines():
        m = HEADING_RE.match(line.rstrip())
        if m and len(m.group(1)) == 2:
            title = m.group(2).strip()
            if any(normalize_text(t) in normalize_text(title) for t in SKIP_H2_TITLES):
                continue
            titles.append(LEADING_NUMERAL_RE.sub("", title))
    return titles


def strip_trailing_comma_html(text):
    return text[:-1] if text.endswith(",") else text


def extract_label_bullets(markdown_text, label_name):
    """Primera aparicion de '**label_name**' seguida de bullets -- devuelve
    la lista de textos (sin '- ', sin ** de markdown, con inline_md aplicado)."""
    pattern = r"\*\*" + re.escape(label_name) + r"\*\*\s*\n((?:-.*\n?)+)"
    m = re.search(pattern, markdown_text)
    if not m:
        return []
    lines = [l for l in m.group(1).strip().splitlines() if l.strip()]
    out = []
    for line in lines:
        bm = BULLET_RE.match(line)
        text = bm.group(2).strip() if bm else line.lstrip("- ").strip()
        if len(line) - len(line.lstrip(" ")) > 0:
            continue  # bullet anidado (categoria suelta) -- no aporta como frase
        out.append(inline_md(strip_trailing_comma_html(text)))
    return out


def extract_panorama_context(markdown_text):
    """Inferencia + Lectura ejecutiva de la seccion 'Panorama general' (la
    primera del documento) -- da un poco de sustancia narrativa a la pagina,
    no solo los numeros de las tarjetas KPI."""
    parts = extract_label_bullets(markdown_text, "Inferencia")
    parts += extract_label_bullets(markdown_text, "Lectura ejecutiva")
    return " ".join(parts) if parts else None


HTML_TEMPLATE = """<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{doc_title} — {period}</title>
<style>
:root {{
  color-scheme: light;
  --bg:#f6f7f2; --surface:#ffffff; --surface-2:#eef0e7;
  --ink:#12160f; --ink-secondary:#4f5647; --ink-muted:#868c7c; --line:#dfe1d6;
  --accent:#b9790a; --accent-ink:#ffffff;
  --good:#0ca30c; --warning:#c98500; --critical:#d03b3b; --info:#2a78d6;
  --brand-deep:#14261a; --shadow: rgba(20,30,18,0.08);
}}
@media (prefers-color-scheme: dark) {{
  :root:where(:not([data-theme="light"])) {{
    color-scheme: dark;
    --bg:#0c0f0b; --surface:#151a13; --surface-2:#1b2118;
    --ink:#edf1e8; --ink-secondary:#b7bfae; --ink-muted:#7d8474; --line:#262d21;
    --accent:#e0a530; --accent-ink:#14200a;
    --good:#17b817; --warning:#fab219; --critical:#e66767; --info:#3987e5;
    --brand-deep:#0a120a; --shadow: rgba(0,0,0,0.35);
  }}
}}
:root[data-theme="dark"] {{
  color-scheme: dark;
  --bg:#0c0f0b; --surface:#151a13; --surface-2:#1b2118;
  --ink:#edf1e8; --ink-secondary:#b7bfae; --ink-muted:#7d8474; --line:#262d21;
  --accent:#e0a530; --accent-ink:#14200a;
  --good:#17b817; --warning:#fab219; --critical:#e66767; --info:#3987e5;
  --brand-deep:#0a120a; --shadow: rgba(0,0,0,0.35);
}}
:root[data-theme="light"] {{
  color-scheme: light;
  --bg:#f6f7f2; --surface:#ffffff; --surface-2:#eef0e7;
  --ink:#12160f; --ink-secondary:#4f5647; --ink-muted:#868c7c; --line:#dfe1d6;
  --accent:#b9790a; --accent-ink:#ffffff;
  --good:#0ca30c; --warning:#c98500; --critical:#d03b3b; --info:#2a78d6;
  --brand-deep:#14261a; --shadow: rgba(20,30,18,0.08);
}}
* {{ box-sizing:border-box; }}
html,body {{ margin:0; padding:0; }}
body {{
  background:var(--bg); color:var(--ink);
  font-family:"Segoe UI",-apple-system,BlinkMacSystemFont,"Helvetica Neue",Arial,sans-serif;
  line-height:1.55; -webkit-font-smoothing:antialiased;
}}
.mono {{ font-family: ui-monospace,"Cascadia Mono","SFMono-Regular",Consolas,"Roboto Mono",monospace; font-variant-numeric: tabular-nums; }}
.page {{ max-width:840px; margin:0 auto; padding:0 24px 72px; }}
.brandbar {{ height:6px; background:linear-gradient(90deg, var(--good) 0 33.3%, var(--warning) 33.3% 66.6%, var(--critical) 66.6% 100%); }}
header {{ padding:56px 0 30px; border-bottom:1px solid var(--line); }}
.eyebrow {{ font-family: ui-monospace,"Cascadia Mono","SFMono-Regular",Consolas,"Roboto Mono",monospace; font-size:12px; font-weight:600; letter-spacing:.12em; text-transform:uppercase; color:var(--accent); margin:0 0 16px; }}
h1 {{ font-family:Cambria,Georgia,"Iowan Old Style","Times New Roman",serif; font-weight:700; font-size:clamp(28px,4.4vw,42px); line-height:1.12; letter-spacing:-.01em; margin:0 0 14px; text-wrap:balance; max-width:20ch; }}
.dek {{ font-size:16px; color:var(--ink-secondary); max-width:64ch; margin:0 0 26px; }}
.metarow {{ display:flex; flex-wrap:wrap; gap:8px 22px; font-size:13px; color:var(--ink-muted); }}
.metarow b {{ color:var(--ink-secondary); font-weight:600; }}
.cta-block {{ display:flex; align-items:center; gap:18px; flex-wrap:wrap; margin:30px 0 8px; }}
.btn-download {{ display:inline-flex; align-items:center; gap:10px; background:var(--accent); color:var(--accent-ink); font-size:15.5px; font-weight:600; padding:14px 24px; border-radius:3px; text-decoration:none; box-shadow:0 6px 16px -6px var(--shadow); transition:transform .15s ease, box-shadow .15s ease; }}
.btn-download:hover {{ transform:translateY(-1px); box-shadow:0 10px 20px -8px var(--shadow); }}
.btn-download:focus-visible {{ outline:2px solid var(--info); outline-offset:3px; }}
.cta-meta {{ font-size:13px; color:var(--ink-muted); }}
.kpi-section {{ padding:40px 0 8px; }}
.kpi-label {{ font-size:12px; font-weight:600; letter-spacing:.08em; text-transform:uppercase; color:var(--ink-muted); margin:0 0 14px; }}
.kpi-grid {{ display:grid; grid-template-columns:repeat({n_kpi},1fr); gap:1px; background:var(--line); border:1px solid var(--line); }}
.kpi-tile {{ background:var(--surface); padding:18px 12px 16px; border-top:3px solid var(--tile-color, var(--ink-muted)); text-align:center; }}
.kpi-value {{ font-family: ui-monospace,"Cascadia Mono","SFMono-Regular",Consolas,"Roboto Mono",monospace; font-weight:700; font-size:21px; color:var(--tile-color, var(--ink)); display:block; }}
.kpi-name {{ font-size:11px; color:var(--ink-secondary); margin-top:4px; }}
@media (max-width:720px) {{ .kpi-grid {{ grid-template-columns:repeat(3,1fr); }} }}
@media (max-width:460px) {{ .kpi-grid {{ grid-template-columns:repeat(2,1fr); }} }}
.contents {{ padding:44px 0 8px; }}
h2 {{ font-family:Cambria,Georgia,"Iowan Old Style","Times New Roman",serif; font-weight:700; font-size:21px; margin:0 0 18px; }}
.section-body {{ padding:8px 0 8px; }}
.section-body p {{ font-size:14.5px; color:var(--ink-secondary); max-width:72ch; margin:0 0 10px; }}
.section-body p:last-child {{ margin-bottom:0; }}
.groups-list {{ list-style:none; margin:0; padding:0; }}
.groups-list li {{ display:flex; align-items:baseline; justify-content:space-between; gap:16px; padding:11px 0; border-bottom:1px solid var(--line); font-size:14.5px; }}
.groups-list li:first-child {{ border-top:1px solid var(--line); }}
.groups-list .gname {{ color:var(--ink); font-weight:600; }}
.groups-list .gmeta {{ display:flex; align-items:baseline; gap:14px; flex:none; }}
.groups-list .gpct {{ font-family: ui-monospace,"Cascadia Mono","SFMono-Regular",Consolas,"Roboto Mono",monospace; font-weight:700; color:var(--ink); font-size:15px; }}
.groups-list .gn {{ font-family: ui-monospace,"Cascadia Mono","SFMono-Regular",Consolas,"Roboto Mono",monospace; color:var(--ink-muted); font-size:12.5px; }}
.toc {{ display:grid; grid-template-columns:1fr 1fr; gap:10px 32px; list-style:none; margin:0; padding:0; }}
.toc li {{ display:flex; gap:12px; align-items:baseline; padding:12px 0; border-bottom:1px solid var(--line); font-size:14px; }}
.toc .n {{ font-family: ui-monospace,"Cascadia Mono","SFMono-Regular",Consolas,"Roboto Mono",monospace; color:var(--ink-muted); font-size:13px; flex:none; width:2ch; }}
@media (max-width:620px) {{ .toc {{ grid-template-columns:1fr; }} }}
.callout {{ margin:44px 0 8px; padding:22px 24px; background:var(--surface-2); border-left:3px solid var(--critical); border-radius:2px; }}
.callout p {{ margin:0; font-size:14.5px; color:var(--ink-secondary); }}
.callout b {{ color:var(--ink); }}
.preview {{ padding:44px 0 8px; }}
details.preview-box {{ border:1px solid var(--line); border-radius:4px; background:var(--surface); overflow:hidden; }}
details.preview-box summary {{ cursor:pointer; list-style:none; padding:16px 20px; font-size:14.5px; font-weight:600; display:flex; align-items:center; justify-content:space-between; gap:12px; }}
details.preview-box summary::-webkit-details-marker {{ display:none; }}
.chev {{ transition:transform .2s ease; color:var(--ink-muted); flex:none; }}
details.preview-box[open] .chev {{ transform:rotate(180deg); }}
.preview-frame-wrap {{ border-top:1px solid var(--line); background:var(--surface-2); }}
.preview-frame-wrap iframe {{ display:block; width:100%; height:78vh; min-height:480px; border:0; }}
footer {{ margin-top:56px; padding-top:22px; border-top:1px solid var(--line); font-size:12.5px; color:var(--ink-muted); display:flex; flex-wrap:wrap; justify-content:space-between; gap:10px; }}
@media (prefers-reduced-motion: reduce) {{ .btn-download {{ transition:none; }} }}
</style>
</head>
<body>
<div class="brandbar"></div>
<div class="page">
  <header>
    <p class="eyebrow">Informe técnico · People Analytics</p>
    <h1>{doc_title}</h1>
    <p class="dek">{dek}</p>
    <div class="metarow mono">{meta_items}</div>
    <div class="cta-block">
      <a class="btn-download" href="{pdf_filename}" download>
        <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3v13"/><path d="m7 12 5 5 5-5"/><path d="M4 20h16"/></svg>
        Descargar informe (PDF)
      </a>
      <span class="cta-meta">Archivo local: {pdf_filename}</span>
    </div>
  </header>

  <section class="kpi-section">
    <p class="kpi-label">Panorama del mes, de un vistazo</p>
    <div class="kpi-grid">{kpi_tiles}</div>
  </section>

  {panorama_block}

  <section class="section-body">
    <h2>Metodología y alcance</h2>
    {methodology_html}
  </section>

  {groups_block}

  <section class="contents">
    <h2>Qué incluye el informe</h2>
    <ol class="toc">{toc_items}</ol>
  </section>

  <section class="preview">
    <h2>Vista previa</h2>
    <details class="preview-box">
      <summary>Ver el documento completo aquí, sin descargarlo
        <svg class="chev" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="m6 9 6 6 6-6"/></svg>
      </summary>
      <div class="preview-frame-wrap"><iframe src="{pdf_filename}" title="Vista previa del informe PDF"></iframe></div>
    </details>
  </section>

  <footer>
    <span>Documento de circulación interna · Confidencial</span>
    <span>Fuente: pipeline <span class="mono">analisis_valencia.py + generar_informe_pdf.py</span> · outputs/{period}/</span>
  </footer>
</div>
</body>
</html>
"""


def build_html_page(data_actual, data_prev, pdf_path, html_path, order):
    period = data_actual["period"]
    period_prev = data_prev["period"] if data_prev else None
    metadata = (data_actual.get("payload") or {}).get("metadata", {})
    nps = nps_summary(data_actual)

    doc_title = "Valencia Emocional en Encuestas de Retiro"
    dek = f"Informe mensual — {period}"
    if period_prev:
        dek += f", comparativo contra {period_prev}"
    dek += ". Clasificación de cada respuesta de salida cruzada con eNPS y LNPS." if nps else "."

    meta_parts = [f"<span><b>{fmt_n(metadata.get('total_filas', 0))}</b> respuestas</span>"]
    if metadata.get("total_columnas"):
        meta_parts.append(f"<span><b>{metadata['total_columnas']}</b> columnas</span>")
    meta_parts.append(f"<span>Generado <b>{datetime.now().strftime('%d %b %Y')}</b></span>")
    meta_items = "".join(meta_parts)

    pcts = valencia_pct_map(data_actual)
    tiles = []
    role_var = {GOOD: "--good", WARNING: "--warning", CRITICAL: "--critical"}
    for label in order:
        color_hex = COLOR_ASSIGNER.color_for(label)
        css_var = role_var.get(color_hex, None)
        style = f"--tile-color:var({css_var})" if css_var else f"--tile-color:{color_hex}"
        tiles.append(
            f'<div class="kpi-tile" style="{style}"><span class="kpi-value mono">'
            f'{fmt_pct(pcts.get(label, 0))}</span><div class="kpi-name">{esc(label)}</div></div>'
        )
    if nps:
        for metric in ["eNPS", "LNPS"]:
            if metric in nps:
                tiles.append(
                    f'<div class="kpi-tile" style="--tile-color:var(--info)"><span class="kpi-value mono">'
                    f'{nps[metric]["puntaje"]:.1f}</span><div class="kpi-name">{metric}</div></div>'
                )
    tiles.append(
        f'<div class="kpi-tile" style="--tile-color:var(--ink-muted)"><span class="kpi-value mono">'
        f'{fmt_n(metadata.get("total_filas", 0))}</span><div class="kpi-name">Respuestas</div></div>'
    )

    toc_titles = extract_toc_titles(data_actual.get("markdown") or "")
    toc_items = "".join(
        f'<li><span class="n mono">{i:02d}</span>{esc(t)}</li>' for i, t in enumerate(toc_titles, start=1)
    )

    panorama_text = extract_panorama_context(data_actual.get("markdown") or "")
    panorama_block = (
        f'<div class="callout"><p><b>Panorama del mes:</b> {panorama_text}</p></div>'
        if panorama_text else ""
    )

    meta_bits = [
        f"{fmt_n(metadata.get('total_filas', 0))} respuestas, {metadata.get('total_columnas', 'N/D')} columnas.",
        f"Columna de valencia: <i>{esc(str(metadata.get('columna_valencia', 'N/D')))}</i>.",
    ]
    if metadata.get("columna_agrupacion"):
        meta_bits.append(f"Columna de agrupación: <i>{esc(str(metadata['columna_agrupacion']))}</i>.")
    methodology_paras = [
        "<p>El análisis detecta automáticamente la columna de valencia emocional y de agrupación de "
        "negocio, limpia el texto de preguntas y respuestas, y calcula distribuciones y cruces "
        "localmente antes de generar el resumen narrativo. " + " ".join(meta_bits) + "</p>"
    ]
    if period_prev:
        methodology_paras.append(
            f"<p>El comparativo mensual usa el informe ejecutivo de <b>{esc(period_prev)}</b> "
            f"como referencia previa.</p>"
        )
    warnings = (data_actual.get("payload") or {}).get("advertencias_calidad_datos", [])
    if warnings:
        cols_txt = ", ".join(w["columna"] for w in warnings[:8])
        methodology_paras.append(
            f"<p>Advertencia de calidad de datos: {len(warnings)} columna(s) con menos del 5% de "
            f"información disponible ({esc(cols_txt)}); no se usaron para conclusiones.</p>"
        )
    methodology_html = "".join(methodology_paras)

    groups_block = ""
    dist_g = data_actual.get("distribucion_agrupacion")
    if dist_g is not None and not dist_g.empty:
        rows = []
        for _, row in dist_g.iterrows():
            name = row[data_actual["agrupacion_col"]]
            rows.append(
                f'<li><span class="gname">{esc(str(name))}</span><span class="gmeta">'
                f'<span class="gn mono">{fmt_n(row["Cantidad"])} resp.</span>'
                f'<span class="gpct mono">{fmt_pct(row["Porcentaje"])}</span></span></li>'
            )
        groups_block = (
            '<section class="section-body"><h2>Agrupaciones de negocio</h2>'
            f'<ul class="groups-list">{"".join(rows)}</ul></section>'
        )

    html = HTML_TEMPLATE.format(
        doc_title=doc_title, period=period, dek=esc(dek), meta_items=meta_items,
        pdf_filename=pdf_path.name, kpi_tiles="".join(tiles), n_kpi=len(tiles),
        toc_items=toc_items, panorama_block=panorama_block,
        methodology_html=methodology_html, groups_block=groups_block,
    )
    html_path.write_text(html, encoding="utf-8")
    return html_path


# ============================================================
# MAIN
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="Genera un informe tecnico en PDF (con graficos) a partir de las salidas de "
                     "analisis_valencia.py en outputs/AAAA-MM/."
    )
    parser.add_argument("--periodo", default=None, help="Periodo a reportar, ej. 2026-07. Por defecto, el mas reciente.")
    parser.add_argument("--periodo-anterior", default=None, help="Periodo de comparacion. Por defecto, el anterior disponible.")
    parser.add_argument("--output-root", default=str(OUTPUT_ROOT_DIR), help="Carpeta raiz de outputs/.")
    parser.add_argument("--output", default=None, help="Ruta del PDF de salida. Por defecto outputs/<periodo>/Informe_Valencia_Emocional_<periodo>.pdf")
    args = parser.parse_args()

    output_root = Path(args.output_root)
    periodo = args.periodo or (discover_periods(output_root)[-1] if discover_periods(output_root) else None)
    if not periodo:
        raise SystemExit("No hay periodos en outputs/. Corre primero analisis_valencia.py.")

    data_actual = load_period_data(output_root, periodo)
    if not data_actual:
        raise SystemExit(f"No encontre tablas_resumen.xlsx para el periodo {periodo}.")

    periodo_anterior = args.periodo_anterior
    if not periodo_anterior:
        anteriores = [p for p in discover_periods(output_root) if p < periodo]
        periodo_anterior = anteriores[-1] if anteriores else None
    data_prev = load_period_data(output_root, periodo_anterior) if periodo_anterior else None

    output_path = Path(args.output) if args.output else (
        output_root / periodo / f"Informe_Valencia_Emocional_{periodo}.pdf"
    )
    charts_dir = output_root / periodo / "graficos"

    print(f"Periodo actual: {periodo}")
    print(f"Periodo anterior: {periodo_anterior or '(sin comparativo, se trata como linea base)'}")

    build_pdf(data_actual, data_prev, output_path, charts_dir)

    labels = data_actual["distribucion_valencia"][data_actual["valencia_col"]].tolist()
    counts = data_actual["distribucion_valencia"]["Cantidad"].tolist()
    order = ordered_labels(labels, counts)
    html_path = output_path.with_suffix(".html")
    build_html_page(data_actual, data_prev, output_path, html_path, order)

    print(f"\nInforme PDF generado: {output_path}")
    print(f"Pagina local generada: {html_path}")
    print(f"Graficos guardados en: {charts_dir}")
    print("\nAbre la pagina local haciendo doble clic sobre el archivo .html anterior.")


if __name__ == "__main__":
    main()
