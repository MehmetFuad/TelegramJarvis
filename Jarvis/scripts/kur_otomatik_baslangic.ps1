# JARVIS otomatik baslangic kurulumu (Windows Gorev Zamanlayici).
# Calistirma (JARVIS klasorunde, PowerShell):
#   powershell -ExecutionPolicy Bypass -File scripts\kur_otomatik_baslangic.ps1
# Ne yapar: "JARVIS" adinda, oturum acildiginda run.py'yi arka planda
# (konsol penceresi acmadan) baslatan bir gorev olusturur.
# Normal kullanici yetkisi yeterlidir (yonetici gerekmez).
# Once scripts\kurulum.ps1 ile .venv olusturmaniz onerilir.

$ErrorActionPreference = "Stop"
$TaskName = "JARVIS"
$ProjectDir = Split-Path -Parent $PSScriptRoot

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
    Write-Host "Python 3.11/3.12 kur, sonra scripts\kurulum.ps1 calistir." -ForegroundColor Red
    exit 1
}
if (-not (Test-Path -LiteralPath (Join-Path $ProjectDir "run.py"))) {
    Write-Host "HATA: $ProjectDir\run.py bulunamadi." -ForegroundColor Red
    exit 1
}

$Action = "`"$PythonW`" `"$ProjectDir\run.py`""
Write-Host "Gorev olusturuluyor: $TaskName"
Write-Host "  Program : $PythonW"
Write-Host "  Proje   : $ProjectDir"

schtasks /create /tn $TaskName /tr $Action /sc ONLOGON /rl LIMITED /f
if ($?) {
    Write-Host ""
    Write-Host "TAMAM: Bilgisayar acilip oturum actiginda JARVIS arka planda baslayacak." -ForegroundColor Green
    Write-Host "Test: gorevi hemen baslatmak icin:  schtasks /run /tn $TaskName"
    Write-Host "Kaldirma: powershell -ExecutionPolicy Bypass -File scripts\otomatik_baslangici_kaldir.ps1"
} else {
    Write-Host "HATA: gorev olusturulamadi." -ForegroundColor Red
    exit 1
}
