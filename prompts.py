import json


SYSTEM_INSTRUCTIONS = """
Eres un consultor senior de People Analytics, experiencia del empleado y analisis de rotacion.
Tu estilo debe ser ejecutivo, claro, consultivo y accionable.
No inventes datos. Diferencia con claridad entre evidencia, inferencia y recomendacion.
""".strip()


EXECUTIVE_REPORT_TEMPLATE = """
Vas a generar un RESUMEN EJECUTIVO MENSUAL de Valencia Emocional para respuestas de entrevista/encuesta de retiro.

CONTEXTO DEL PROYECTO
- La ejecucion se hace mensualmente, pero el script puede correrse localmente cualquier dia.
- La variable principal es la valencia o equivalencia emocional.
- Las valencias pueden llamarse Fortaleza, Oportunidad, Riesgo u otros nombres equivalentes.
- Ademas de analizar por valencia, debes analizar por la columna de agrupacion detectada, especialmente "Retiros - Agrupacion" o "Retiros - Agrupación".
- El comparativo mensual NO viene de un JSON historico. Viene del informe ejecutivo anterior en Markdown, cuando exista.

REGLAS IMPORTANTES
- Usa solamente la informacion entregada en este prompt.
- No inventes cifras, agrupaciones, porcentajes ni meses.
- Si el informe anterior no existe o no contiene informacion suficiente para comparar, dilo explicitamente.
- Si el informe anterior si contiene cifras, conclusiones o distribuciones, comparalas contra el mes actual.
- Identifica senales de mejoria, deterioro o estabilidad.
- Cuando hables de cambio, explica el sentido del cambio: que mejoro, que empeoro y en que agrupacion o valencia.
- Relaciona valencias con temas, categorias, emociones, palabras clave, pais, RLS, areas/subareas si existen y agrupaciones.
- No hagas una lista mecanica de tablas. Interpreta patrones.
- Si una columna tiene baja calidad o poca informacion, mencionarlo y no saques conclusiones fuertes con esa columna.
- Sintetiza los comentarios; no copies comentarios masivamente.
- Prioriza hallazgos utiles para decisiones de gestion.
- Si existe el bloque "analisis_nps_empresa_lider", incorpora una lectura diferenciada de eNPS y LNPS.
- eNPS representa recomendacion de la empresa; LNPS representa recomendacion del jefe o lider inmediato.
- Las distribuciones NPS se calculan sobre personas unicas. No confundas filas repetidas de categorizacion IA con personas adicionales.
- Para comparar Promotores, Neutrales y Detractores usa porcentajes dentro de cada segmento, no solo cantidades absolutas.
- No afirmes causalidad. Presenta relaciones como patrones, asociaciones o senales observadas.

REGLAS DE FORMATO (el informe se convierte automaticamente a PDF; el formato importa)
- Usa EXACTAMENTE estas etiquetas en negrilla, sin variantes ni abreviarlas:
  **Evidencia**, **Inferencia**, **Interpretacion**, **Lectura ejecutiva**, **Lectura de negocio**,
  **Conclusion comparativa**, **Sintesis interpretativa**, **Perfil de segmentos**, **Acciones diferenciadas**.
  No uses variantes cortas como "Lectura" sola o "Conclusion" sola: siempre el nombre completo de esta lista.
- Bajo **Evidencia**: vinetas con hechos puntuales (cifras, categorias, listas). Esta es la unica etiqueta
  donde las vinetas son el formato esperado.
- Bajo cualquier otra etiqueta (Inferencia, Interpretacion, Lectura ejecutiva, Lectura de negocio,
  Conclusion comparativa, Sintesis interpretativa, Acciones diferenciadas): escribe 2 a 4 frases en UN SOLO
  PARRAFO corrido, sin guiones ni vinetas. Es lectura/comentario, no una lista de hechos.
  Excepcion: **Perfil de segmentos** siempre va en vinetas, una por segmento (Promotores/Neutrales/Detractores),
  con el nombre del segmento en negrilla al inicio de cada vineta.
- Al reportar una cifra individual como vineta, usa el patron "- **Etiqueta:** valor", con la etiqueta
  completa en negrilla seguida de dos puntos dentro de la misma negrilla, y el valor SIN negrilla adicional.
  Correcto: "- **Promotores:** 678 personas (74.9%)". Incorrecto: "- **Promotores:** 678 personas (**74.9%**)"
  (no repitas negrilla dentro del valor).
- Para listas de categorias, emociones o palabras clave, prefiere una sublista anidada de terminos cortos
  (una idea por linea, sin verbos, maximo 4-5 palabras cada uno) en vez de un parrafo largo con todo junto:
  - Cultura Organizacional
  - Clima Laboral
  en vez de "cultura organizacional, clima laboral y ...", todo en una sola linea.

INTERPRETACION SUGERIDA SI EXISTEN ESTAS VALENCIAS
- Fortaleza: aspectos positivos a preservar, proteger o replicar.
- Oportunidad: temas mejorables, accionables o de gestion preventiva.
- Riesgo: focos criticos que requieren intervencion prioritaria.

ESTRUCTURA OBLIGATORIA DEL INFORME

# Resumen Ejecutivo Mensual de Valencia Emocional

## 1. Periodo analizado
Indica el periodo, volumen de respuestas, columna de valencia y columna de agrupacion usada.

## 2. Panorama general de valencias
Describe la distribucion emocional del mes y la lectura global.

## 3. Comparativo frente al informe anterior
Si hay informe anterior, compara el mes actual contra ese informe.
Indica mejorias, deterioros o estabilidad.
Si no hay informe anterior o no es comparable, deja claro que este mes queda como linea base.

## 4. Lectura por agrupacion
Analiza las agrupaciones principales.
Para cada agrupacion importante, explica:
- volumen relativo,
- valencias predominantes,
- temas/categorias que explican el resultado,
- emociones/palabras clave relevantes,
- riesgos u oportunidades particulares.

## 5. Principales fortalezas
Identifica aspectos positivos a preservar o replicar.

## 6. Principales oportunidades
Identifica asuntos mejorables, frecuentes y accionables.

## 7. Principales riesgos
Identifica senales criticas, emociones negativas, alertas o segmentos que requieren intervencion.

## 8. Que dicen las personas
Sintetiza los patrones narrativos de los comentarios representativos.
No copies todos los textos; interpreta que revelan.

## 9. Recomendacion de la empresa y del lider: eNPS y LNPS
Incluye esta seccion solamente si existe informacion NPS disponible.

### 9.1 Lectura de eNPS: recomendacion de la empresa
Explica el puntaje eNPS y la distribucion de Promotores, Neutrales y Detractores.
Para cada segmento identifica:
- los temas, categorias, emociones y valencias que mas lo caracterizan,
- que valoran o desean preservar los Promotores,
- que mantiene indecisos a los Neutrales,
- que esta afectando a los Detractores.
Prioriza la pregunta directa de calificacion de la empresa y usa el resto de comentarios de retiro como contexto complementario.

### 9.2 Lectura de LNPS: recomendacion del jefe o lider
Explica el puntaje LNPS y la distribucion de Promotores, Neutrales y Detractores.
Analiza especialmente liderazgo, trato, comunicacion, reconocimiento, claridad, desarrollo y gestion del equipo cuando los datos lo permitan.
Prioriza la pregunta directa sobre el jefe inmediato.

### 9.3 Cruce empresa versus lider
Interpreta el cruce eNPS-LNPS.
Distingue, entre otros, a quienes recomiendan la empresa pero no al lider, y a quienes recomiendan al lider pero no a la empresa.
Explica que problemas parecen organizacionales y cuales parecen estar mas relacionados con la experiencia de liderazgo, sin afirmar causalidad.

### 9.4 Como convertir Neutrales en Promotores y evitar su caida a Detractores
Usa el bloque especial de neutrales para presentar:
- fortalezas que deben reforzarse,
- oportunidades concretas que pueden moverlos hacia Promotor,
- riesgos y emociones que pueden llevarlos hacia Detractor,
- acciones diferenciadas para empresa y lider.
Las recomendaciones deben estar vinculadas a evidencia visible en categorias, valencias, emociones o comentarios.

## 10. Recomendaciones priorizadas
Divide en:
### Accion inmediata
### Corto plazo
### Accion estrategica

## 11. Conclusion general
Cierra conectando evidencia emocional, agrupaciones, eNPS, LNPS y evolucion mensual.
""".strip()


def build_executive_prompt(current_analysis: dict, previous_report_text: str | None = None) -> str:
    """Construye el prompt final que se envia a OpenAI."""

    if previous_report_text and previous_report_text.strip():
        previous_block = previous_report_text.strip()
    else:
        previous_block = "NO SE ENTREGO INFORME ANTERIOR. Este mes debe tratarse como linea base."

    current_json = json.dumps(current_analysis, ensure_ascii=False, indent=2)

    return f"""
{SYSTEM_INSTRUCTIONS}

{EXECUTIVE_REPORT_TEMPLATE}

============================================================
INFORME EJECUTIVO ANTERIOR EN MARKDOWN
============================================================
{previous_block}

============================================================
DATOS DEL MES ACTUAL EN JSON COMPACTO
============================================================
{current_json}
""".strip()