# JARVIS masaustu kisayolu olusturma (Windows).
# Calistirma (JARVIS klasorunde, PowerShell):
#   powershell -ExecutionPolicy Bypass -File scripts\masaustu_kisayolu_olustur.ps1
# Masaustune "JARVIS" kisayolu koyar; cift tiklayinca Python (pythonw.exe)
# penceresiz olarak app.py'yi calistirir ve masaustu uygulamasi acilir.
#
# Python secimi (sirayla): .venv\Scripts\pythonw.exe -> PATH'teki pythonw.exe
# -> py launcher -> python.exe. Boylece her bilgisayarda farkli Python
# surumu/konumu olsa da calisir.

$ErrorActionPreference = "Stop"
$ProjectDir = Split-Path -Parent $PSScriptRoot
$AppFile = Join-Path $ProjectDir "app.py"
if (-not (Test-Path -LiteralPath $AppFile)) {
    Write-Host "HATA: $AppFile bulunamadi." -ForegroundColor Red
    exit 1
}

function Find-Python {
    param([string]$Name)
    $venv = Join-Path $ProjectDir ".venv\Scripts\$Name.exe"
    if (Test-Path -LiteralPath $venv) { return $venv }
    $cmd = Get-Command "$Name.exe" -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    try {
        $py = (& py -3 -c "import sys; print(sys.executable)" 2>$null | Select-Object -First 1)
        if ($py) {
            $candidate = Join-Path (Split-Path -Parent $py.Trim()) "$Name.exe"
            if (Test-Path -LiteralPath $candidate) { return $candidate }
        }
    } catch {}
    return $null
}

$PythonW = Find-Python "pythonw"
if (-not $PythonW) { $PythonW = Find-Python "python" }
if (-not $PythonW) {
    Write-Host "HATA: Python bulunamadi." -ForegroundColor Red
    Write-Host "Python 3.11/3.12 kur: https://www.python.org/downloads/ (PATH'e ekle)" -ForegroundColor Red
    Write-Host "Sonra once scripts\kurulum.ps1 calistir." -ForegroundColor Red
    exit 1
}

$IconFile = Join-Path $ProjectDir "assets\jarvis.ico"
$Desktop = [Environment]::GetFolderPath("Desktop")
$LinkPath = Join-Path $Desktop "JARVIS.lnk"

$Shell = New-Object -ComObject WScript.Shell
$Link = $Shell.CreateShortcut($LinkPath)
$Link.TargetPath = $PythonW
$Link.Arguments = "`"$AppFile`""
$Link.WorkingDirectory = $ProjectDir
$Link.Description = "JARVIS masaustu uygulamasi"
if (Test-Path -LiteralPath $IconFile) {
    $Link.IconLocation = $IconFile
} else {
    $Link.IconLocation = "$PythonW, 0"
}
$Link.Save()

Write-Host "TAMAM: Masaustune JARVIS kisayolu olustu: $LinkPath" -ForegroundColor Green
Write-Host "Cift tiklayinca uygulama acilir (backend kapaliysa kendisi baslatir)."
