# Ejecuta el pipeline mensual completo: analisis_valencia.py -> generar_informe_pdf.py
# Pensado para correr sin supervision (Programador de tareas de Windows, dia 1 de cada mes).
# Actualiza el Excel de entrada (base_retiros_analisis_valencia.xlsx / "NPS -EVA.xlsx") ANTES
# de que corra esta tarea; el script usa el archivo que encuentre en ese momento.

$ErrorActionPreference = "Stop"
$ProjectDir = $PSScriptRoot
Set-Location $ProjectDir

$VenvPython = Join-Path $ProjectDir ".venv\Scripts\python.exe"
$LogDir = Join-Path $ProjectDir "logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$LogFile = Join-Path $LogDir ("ejecucion_{0}.log" -f (Get-Date -Format "yyyy-MM-dd_HHmmss"))

function Write-Log {
    param([string]$Message)
    $line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    Write-Output $line
    Add-Content -Path $LogFile -Value $line -Encoding utf8
}

if (-not (Test-Path $VenvPython)) {
    Write-Log "ERROR: no encuentro el entorno virtual en $VenvPython. Crea .venv con: py -3 -m venv .venv"
    exit 1
}

Write-Log "===== Inicio de ejecucion mensual ====="

Write-Log "Paso 1/2: analisis_valencia.py (analisis local + resumen ejecutivo con IA)"
& $VenvPython (Join-Path $ProjectDir "analisis_valencia.py") 2>&1 | ForEach-Object { Write-Log $_ }
if ($LASTEXITCODE -ne 0) {
    Write-Log "ERROR: analisis_valencia.py termino con codigo $LASTEXITCODE. Se detiene la ejecucion."
    exit 1
}

Write-Log "Paso 2/2: generar_informe_pdf.py (PDF + pagina HTML local)"
& $VenvPython (Join-Path $ProjectDir "generar_informe_pdf.py") 2>&1 | ForEach-Object { Write-Log $_ }
if ($LASTEXITCODE -ne 0) {
    Write-Log "ERROR: generar_informe_pdf.py termino con codigo $LASTEXITCODE."
    exit 1
}

Write-Log "===== Ejecucion mensual completada correctamente ====="
Write-Log "Revisa la carpeta outputs\ del periodo mas reciente para el PDF y la pagina HTML."
