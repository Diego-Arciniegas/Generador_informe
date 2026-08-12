# Análisis ejecutivo de Valencia / Equivalencia Emocional

Este proyecto lee un Excel de respuestas de salida/retiro, detecta automáticamente la columna de **Valencia emocional** o **Equivalencia emocional**, identifica los valores existentes —por ejemplo, Fortaleza, Oportunidad, Riesgo— y genera un resumen ejecutivo con la API de OpenAI.

## 1) Crear entorno

### Windows PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

### macOS / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

## 2) Guardar la API key

Abre el archivo `.env` y reemplaza:

```env
OPENAI_API_KEY=pega_tu_api_key_aqui
```

por tu clave real. No la pegues dentro del código ni la compartas.

## 3) Poner el Excel

Crea una carpeta `data` y guarda ahí tu archivo, por ejemplo:

```text
data/base_retiros_analisis_valencia.xlsx
```

## 4) Ejecutar el análisis

```bash
python src/analisis_valencia.py --input "data/base_retiros_analisis_valencia.xlsx"
```

También puedes cambiar el modelo:

```bash
python src/analisis_valencia.py --input "data/base_retiros_analisis_valencia.xlsx" --model "gpt-5.4-mini"
```

Para probar solo el análisis local sin llamar a la API:

```bash
python src/analisis_valencia.py --input "data/base_retiros_analisis_valencia.xlsx" --no-api
```

## 5) Salidas generadas

El script genera archivos en `outputs/`:

- `analysis_payload.json`: resumen estadístico que se envía al modelo.
- `tablas_resumen.xlsx`: tablas locales de distribución y cruces.
- `resumen_ejecutivo.md`: resumen ejecutivo generado por la API.

## Qué hace el script

1. Lee el Excel.
2. Detecta la columna de valencia/equivalencia emocional.
3. Detecta automáticamente las valencias existentes.
4. Limpia texto de preguntas, respuestas y columnas IA.
5. Evita inflar conclusiones por comentarios repetidos cuando hay varias categorías por respuesta.
6. Calcula distribuciones por valencia.
7. Cruza valencia con temas, categorías, país, RLS, área, subárea, emoción, palabras clave y alertas si existen.
8. Envía solo un resumen compacto a la API, no todo el Excel completo.
9. Genera un resumen ejecutivo accionable.

## Nota importante sobre duplicados

En muchas bases de encuestas una misma respuesta aparece repetida porque la IA asignó varias categorías. El script diferencia entre:

- **Registros del Excel**: cada fila del archivo.
- **Respuestas únicas**: combinación de ID, pregunta, respuesta y valencia.

El resumen ejecutivo usa ambas vistas para no sobreinterpretar respuestas duplicadas.

## 6) Informe técnico en PDF + página local

Además del `resumen_ejecutivo.md`, el proyecto genera un informe técnico en PDF (con gráficos)
y una página HTML local para verlo/descargarlo desde el navegador, sin depender de internet.

Entorno real usado por estos scripts (distinto al `.venv` genérico descrito arriba, por si ya
tenías uno roto o apuntando a otro Python):

```powershell
py -3 -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
```

Generar el informe del período más reciente en `outputs/`:

```powershell
.\.venv\Scripts\python.exe generar_informe_pdf.py
```

Esto crea, dentro de `outputs/AAAA-MM/`:

- `Informe_Valencia_Emocional_AAAA-MM.pdf`: informe técnico con gráficos (distribución de
  valencia, comparativo mensual, comparativo por agrupación, top categorías por valencia,
  eNPS/LNPS y cruce empresa-líder).
- `Informe_Valencia_Emocional_AAAA-MM.html`: página local con el mismo resumen, un botón de
  descarga y una vista previa embebida del PDF. Se abre con doble clic, sin servidor.
- `graficos/`: las imágenes usadas en el PDF, por si quieres reutilizarlas.

El script detecta automáticamente el período más reciente y el período anterior para el
comparativo; se pueden forzar con `--periodo 2026-07 --periodo-anterior 2026-06`.

## 7) Ejecución automática el día 1 de cada mes

`ejecutar_mensual.ps1` corre `analisis_valencia.py` y luego `generar_informe_pdf.py` en
secuencia, con log en `logs/`. Antes de que corra, actualiza el Excel de entrada
(`base_retiros_analisis_valencia.xlsx` y `NPS -EVA.xlsx`) con los datos del mes.

Ya quedó registrada una tarea programada de Windows:

```powershell
schtasks /query /tn "AnalisisValenciaEmocional_Mensual" /v /fo list
```

- Corre el día 1 de cada mes a las 07:00, solo si la sesión de Windows está iniciada
  (modo "Solo interactivo", sin guardar contraseña).
- Para correrla ahora mismo de prueba: `schtasks /run /tn "AnalisisValenciaEmocional_Mensual"`.
- Para eliminarla: `schtasks /delete /tn "AnalisisValenciaEmocional_Mensual" /f`.
- Para cambiar la hora o el día, edítala desde el Programador de tareas de Windows o con
  `schtasks /change`.
