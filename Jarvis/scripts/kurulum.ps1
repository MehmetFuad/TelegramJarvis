# JARVIS kurulum (Windows) — tek komutla hazir ortam.
# Calistirma:
#   powershell -ExecutionPolicy Bypass -File scripts\kurulum.ps1
#
# Yaptiklari:
#   1. Python surumunu kontrol eder (3.10+ onerilir; 3.11/3.12 en uyumlu).
#   2. .venv sanal ortami olusturur (projeye izole, sisteme dokunmaz).
#   3. requirements.txt bagimliliklarini kurar.
#   4. .env yoksa .env.example'dan kopyalar (anahtarlari sen doldurursun).
#   5. Sonraki adimlari yazar.
# Yonetici izni GEREKMEZ.

$ErrorActionPreference = "Stop"
$ProjectDir = Split-Path -Parent $PSScriptRoot

function Find-Python {
    $cmd = Get-Command "python.exe" -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    try {
        $py = (& py -3 -c "import sys; print(sys.executable)" 2>$null | Select-Object -First 1)
        if ($py) { return $py.Trim() }
    } catch {}
    return $null
}

$Python = Find-Python
if (-not $Python) {
    Write-Host "HATA: Python bulunamadi." -ForegroundColor Red
    Write-Host "Kur: https://www.python.org/downloads/ (3.11 veya 3.12; 'Add to PATH' isaretle)" -ForegroundColor Red
    exit 1
}

$Version = (& $Python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')").Trim()
Write-Host "Python bulundu: $Version ($Python)"
$Parts = $Version.Split(".")
$Major = [int]$Parts[0]; $Minor = [int]$Parts[1]
if ($Major -lt 3 -or ($Major -eq 3 -and $Minor -lt 10)) {
    Write-Host "HATA: En az Python 3.10 gerekli (bulunan: $Version)." -ForegroundColor Red
    exit 1
}
if ($Major -eq 3 -and $Minor -ge 13) {
    Write-Host "UYARI: Python $Version ile bazi paketler (pywin32/pycaw/pywebview) sorun cikarabilir." -ForegroundColor Yellow
    Write-Host "       Sorun yasarsan Python 3.11/3.12 ile tekrar dene." -ForegroundColor Yellow
}

$VenvDir = Join-Path $ProjectDir ".venv"
if (-not (Test-Path -LiteralPath $VenvDir)) {
    Write-Host "Sanal ortam olusturuluyor: $VenvDir"
    & $Python -m venv $VenvDir
}
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
if (-not (Test-Path -LiteralPath $VenvPython)) {
    Write-Host "HATA: Sanal ortam olusturulamadi." -ForegroundColor Red
    exit 1
}

Write-Host "Bagimliliklar kuruluyor (birkac dakika surebilir)..."
& $VenvPython -m pip install --upgrade pip | Out-Host
& $VenvPython -m pip install -r (Join-Path $ProjectDir "requirements.txt")
if ($LASTEXITCODE -ne 0) {
    Write-Host "HATA: Bagimliliklar kurulamadi (cikis kodu: $LASTEXITCODE)." -ForegroundColor Red
    exit 1
}

$EnvFile = Join-Path $ProjectDir ".env"
$EnvExample = Join-Path $ProjectDir ".env.example"
if (-not (Test-Path -LiteralPath $EnvFile) -and (Test-Path -LiteralPath $EnvExample)) {
    Copy-Item -LiteralPath $EnvExample -Destination $EnvFile
    Write-Host "Olusturuldu: .env  (anahtarlari doldurmayi unutma!)" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "=== JARVIS kurulumu tamam ===" -ForegroundColor Green
Write-Host "1) .env dosyasini ac, su alanlari doldur:"
Write-Host "   TELEGRAM_BOT_TOKEN, ALLOWED_TELEGRAM_USER_ID, GEMINI_API_KEY_1"
Write-Host "2) Baslat:  .\.venv\Scripts\python.exe run.py"
Write-Host "3) Masaustu uygulamasi:  .\.venv\Scripts\python.exe app.py"
Write-Host ""
Write-Host "Not: OCR (ekran okuma) icin Tesseract v4+ gerekir."
Write-Host "     Kur: https://github.com/UB-Mannheim/tesseract/wiki"
Write-Host "     (PATH'e eklemek zorunlu degil; JARVIS otomatik bulur,"
Write-Host "      Turkce dil dosyasini ilk kullanimda indirir.)"
