# JARVIS otomatik baslangic kaldirma (Gorev Zamanlayici).
# Calistirma (JARVIS klasorunde, PowerShell):
#   powershell -ExecutionPolicy Bypass -File scripts\otomatik_baslangici_kaldir.ps1
# "JARVIS" gorevini Zamanlayici'dan siler; bir daha otomatik baslamaz.
# (Su an calisan JARVIS process'ini durdurmaz; durdurmak icin Telegram'dan
# /kapat gonder veya dashboard'daki Durdur butonuna bas.)

$ErrorActionPreference = "Stop"
$TaskName = "JARVIS"

schtasks /delete /tn $TaskName /f
if ($?) {
    Write-Host "TAMAM: $TaskName gorevi kaldirildi, otomatik baslama kapandi." -ForegroundColor Green
} else {
    Write-Host "Bilgi: $TaskName adinda bir gorev bulunamadi (zaten kaldirilmis olabilir)." -ForegroundColor Yellow
}
