# JARVIS — Kisisel Yapay Zeka Asistani

Windows üzerinde çalışan, Telegram ve yerel masaüstü panelinden Türkçe komutla
bilgisayarını yöneten kişisel asistan. Gemini'nin function calling özelliğini
kullanır: sohbet etmez, gerçek işlem yapar (uygulama açar, dosya bulur, sesi
ayarlar, ekranı okur, mesaj gönderir...).

> **Neler yapabildiğinin tam ve güncel listesi:** [ABILITIES.md](ABILITIES.md)

---

## 1. Gereksinimler

| Gereksinim | Detay |
|---|---|
| **İşletim sistemi** | **Windows 10 veya 11** (zorunlu). Linux/macOS'ta çalışmaz; `pywin32`, `pycaw`, `win32com` Windows API'lerine bağlıdır. |
| **Python** | **3.11 veya 3.12** (önerilen). 3.10 desteklenir. **3.13 ve üzeri önerilmez**; `pywin32`, `pycaw`, `pywebview` gibi paketlerde derleme/uyum sorunları çıkabilir. |
| **İnternet** | Gemini API için gerekli. İlk OCR kullanımında Türkçe dil dosyası da indirilir. |
| **Disk** | ~500 MB (sanal ortam + paketler). Proje kendisi ~150 KB'dır. |
| **Mikrofon** | Opsiyonel (masaüstü panelinde sesli komut için). |
| **Tesseract OCR** | Opsiyonel (ekran okuma / OCR için). **v4 veya üzeri** gerekir; PATH'e eklemek zorunlu değildir. |
| **Yönetici izni** | **Gerekmez.** Kurulum ve çalışma normal kullanıcı yetkisiyle yapılır. |

> `__pycache__` klasörleri **kurulmaz**; Python ilk çalıştırmada kendisi
> oluşturur. Depoda görünmemeleri normaldir, eksiklik değildir.

---

## 2. Kurulum (adım adım)

### 2.1 Projeyi indir

İki yöntemden biri:

- **Git ile:** `git clone <repo-adresi>` (önerilir; güncellemesi kolaydır)
- **ZIP ile:** GitHub sayfasında **Code → Download ZIP** → sağ tık **Extract All**

Öneri: projeyi **kısa ve yerel** bir klasöre çıkar, örn.
`C:\Jarvis`. OneDrive/Google Drive gibi senkronize klasörlerde log ve SQLite
dosyaları kilitlenme sorunu çıkarabilir. Türkçe karakter/boşluk içeren yollar
sorun çıkarmaz ama en temizi `C:\Jarvis` gibi sade bir yoldur.

### 2.2 Python'u kur

1. [python.org/downloads](https://www.python.org/downloads/) adresinden
   **Python 3.11.x veya 3.12.x** (64-bit) indir.
2. Kurulumun ilk ekranında **“Add python.exe to PATH”** kutusunu **mutlaka**
   işaretle.
3. Kurulumdan sonra **yeni** bir PowerShell aç ve doğrula:

```powershell
python --version
```

`Python 3.11.x` veya `3.12.x` görmelisin. `python` bulunamıyorsa PATH'e
eklenmemiştir; kurulumu “Modify” ile tekrar çalıştırıp PATH seçeneğini aç.

> Bilgisayarda birden fazla Python varsa sorun değil; aşağıdaki kurulum script'i
> projeye özel `.venv` oluşturur ve o ortamı kullanır. Sisteme hiçbir şey
> bulaştırmaz.

### 2.3 Otomatik kurulum script'ini çalıştır

Proje klasöründe PowerShell aç (klasörde boş yere **Shift + sağ tık →
“Open PowerShell window here”**), sonra:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\kurulum.ps1
```

Bu script sırasıyla:

1. Python sürümünü kontrol eder (3.10+; 3.13+ ise uyarır),
2. `.venv` sanal ortamı oluşturur,
3. `requirements.txt` bağımlılıklarını kurar,
4. `.env` yoksa `.env.example`'dan kopyalar,
5. sonraki adımları ekrana yazar.

“Script çalıştırılamıyor / execution policy” hatası alırsan yukarıdaki
komuttaki `-ExecutionPolicy Bypass` kısmını atlamadığından emin ol. Kalıcı
çözüm (opsiyonel):

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

**Manuel kurulum (script'siz):**

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

### 2.4 Gemini API anahtarı al

1. [Google AI Studio → API Keys](https://aistudio.google.com/app/apikey)
   adresine Google hesabınla gir.
2. **“Create API key”** → uygun projeyi seç → anahtarı kopyala.
3. Ücretsiz kotada günlük/dakikalık limit olabilir. Limit dolarsa asistan
   “yogun” der; yedek anahtar tanımlarsan otomatik geçer.

**Tek anahtar yeterlidir.** `.env` içinde yalnızca `GEMINI_API_KEY_1`
doldurursan sistem çalışır ve hiçbir yedeğe geçmez.

**Çoklu anahtar (opsiyonel):** `GEMINI_API_KEY_2`, `GEMINI_API_KEY_3` de
doldurulabilir. Sıra her zaman şöyledir:

1. `GEMINI_API_KEY_1` denenir.
2. Kota/limit/hata olursa `GEMINI_API_KEY_2` denenir.
3. O da olmazsa `GEMINI_API_KEY_3` denenir.
4. Bir sonraki mesajda **tekrar `GEMINI_API_KEY_1` ile başlanır.**

Anahtar değişse bile **sohbet bağlamı korunur**; geçmiş sıfırlanmaz.

### 2.5 Telegram botu oluştur

1. Telegram'da [@BotFather](https://t.me/BotFather) ile sohbet başlat.
2. `/newbot` gönder. Sırayla:
   - **Bot adı** (görünen isim, örn. “My Jarvis”),
   - **kullanıcı adı** (benzersiz olmalı, `bot` ile bitmeli, örn. `my_jarvis_bot`).
3. BotFather sana şu formatta bir **token** verir:

```
1234567890:AAExampleTokenExampleTokenExample
```

Bu token **şifre gibidir**; kimseyle paylaşma, ekran görüntüsüne alma, koda
yazma. Sızarsa BotFather'da `/revoke` ile iptal edip yenisini al.

### 2.6 Kendi Telegram kullanıcı ID'ni öğren

Bot yalnızca **senin** hesabından gelen komutlara cevap verir. ID'ni öğrenmek
için [@userinfobot](https://t.me/userinfobot) ile sohbet başlat; sana
`Id: 123456789` gibi bir sayı verir. Bu sayıyı not al.

### 2.7 `.env` dosyasını doldur

Proje klasöründeki `.env` dosyasını Not Defteri ile aç (`.env` gizli dosya
olabilir; Not Defteri'nde “Tüm dosyalar” seç). Şu alanları doldur:

```.env
# --- Telegram ---
TELEGRAM_BOT_TOKEN=1234567890:AAExampleTokenExampleTokenExample
ALLOWED_TELEGRAM_USER_ID=123456789

# --- Gemini ---
GEMINI_API_KEY_1=AIzaOrAQ_Ile_Baslayan_Anahtarin
# Yedek kullanmayacaksan _2 ve _3'u bos birak:
GEMINI_API_KEY_2=
GEMINI_API_KEY_3=
GEMINI_MODEL=gemini-3.5-flash-lite

# --- Dashboard (varsayilanlar yeterli) ---
DASHBOARD_HOST=127.0.0.1
DASHBOARD_PORT=8000
```

Kurallar:

- Değerlerin etrafına **tırnak koyma**: `GEMINI_API_KEY_1="abc"` yerine
  `GEMINI_API_KEY_1=abc` yaz.
- `=` işaretinin iki yanında **boşluk bırakma**.
- Satır başına `#` yorum satırıdır; anahtarı yorum satırına yazma.
- Dosyayı **UTF-8** kaydet; adı **tam olarak `.env`** kalmalı (`.env.txt`
  olursa okunmaz).
- Dosyayı **silme/yeniden adlandırma**; JARVIS tüm ayarları buradan okur.

### 2.8 Çalıştır

**Arka plan servisi (Telegram botu + dashboard):**

```powershell
.\.venv\Scripts\python.exe run.py
```

Başarılı çıktı örneği:

```
Dashboard: http://127.0.0.1:8000 adresinden erisilebilir.
JARVIS Telegram botu baslatiliyor (polling)...
Bot calisiyor. Durdurmak icin Ctrl+C.
```

**Masaüstü uygulaması (ayrı terminal veya çift tık):**

```powershell
.\.venv\Scripts\python.exe app.py
```

Pencere açılır; backend kapalıysa kendisi başlatır. Pencereyi kapatmak botu
durdurmaz.

**Telegram'dan test:** bota `/start` ve ardından örn. `Notepad ac` yaz.

**Dashboard:** tarayıcıdan [http://127.0.0.1:8000](http://127.0.0.1:8000).
Durum, canlı log, onay geçmişi, komut paneli, uygulama/kanal yönetimi burada.

### 2.9 Masaüstü kısayolu ve otomatik başlangıç (opsiyonel)

```powershell
# Masaustune JARVIS kisayolu
powershell -ExecutionPolicy Bypass -File scripts\masaustu_kisayolu_olustur.ps1

# Bilgisayar acilinca arka planda otomatik baslat (Gorev Zamanlayici)
powershell -ExecutionPolicy Bypass -File scripts\kur_otomatik_baslangic.ps1

# Otomatik baslangici kaldir
powershell -ExecutionPolicy Bypass -File scripts\otomatik_baslangici_kaldir.ps1
```

Notlar:

- Otomatik başlangıç **oturum açınca** çalışır (bilgisayar açılışında değil).
- Proje klasörünü **taşırsan** kısayol ve otomatik başlangıç eski yolu
  gösterir; iki script'i yeniden çalıştır.
- Durdurmak için: Telegram'dan `/kapat`, dashboard'daki **Durdur** butonu ya da
  Görev Yöneticisi'nden Python sürecini kapat.

### 2.10 OCR (ekran okuma) — OPSİYONEL

Ekrandaki yazıları okuma ve yazıya tıklama için Tesseract gerekir:

1. [UB-Mannheim Tesseract](https://github.com/UB-Mannheim/tesseract/wiki)
   sayfasından **v5 (64-bit)** kurulumu indir.
2. Kurulumda ek dil seçiminde **Turkish** işaretle (zorunlu değil; JARVIS
   eksikse ilk kullanımda indirir).
3. PATH'e eklemek **zorunlu değildir**: JARVIS `C:\Program Files\Tesseract-OCR`
   gibi bilinen yerlerde v4+ arar ve PATH'teki eski sürümü yok sayar.
4. Kurulumdan sonra JARVIS'i yeniden başlat. İlk OCR çağrısı dil dosyası
   indirdiği için birkaç saniye yavaş olabilir.

Tesseract olmadan da her şey çalışır; yalnızca “ekranı oku / yazıya tıkla”
özellikleri anlaşılır bir hata mesajı verir.

---

## 3. Model değiştirme (`GEMINI_MODEL`)

Evet, model `.env` üzerinden değiştirilir:

```dotenv
GEMINI_MODEL=gemini-3.5-flash-lite
```

- Değişiklik **JARVIS yeniden başlatıldığında** geçerli olur (ayarlar açılışta
  okunur).
- **Önemli:** yazdığın ad **Google tarafından yayınlanmış ve anahtarının
  erişebildiği** bir model olmalı. Var olmayan bir ad (örn. henüz çıkmamış
  `gemini-3.6-...`) yazarsan çağrılar “model bulunamadı” hatası verir.
- Bu durumda sistem **tüm yedek anahtarları boşuna denemez**; hızlıca
  “GEMINI_MODEL kullanilamiyor” der ve `.env`'i düzeltmeni söyler.
- Güncel model adlarını Google AI Studio / Gemini API belgelerinden kontrol et.
- Varsayılan `gemini-3.5-flash-lite` olarak ayarlıdır; mevcut modelinle uyumlu
  değilse `.env`'den değiştir.

---

## 4. Yapılmaması gerekenler (kurallar)

Bunlar projeyi bozar, güvenliği düşürür veya veri kaybettirir:

**Gizlilik / güvenlik**

1. **`.env` dosyasını GitHub'a veya kimseye göndermeyin.** İçinde Telegram
   token'ı ve Gemini anahtarları vardır.
2. Anahtarları **koda, README'ye, ekran görüntüsüne** yazmayın.
3. Telegram token'ı sızarsa **hemen** BotFather `/revoke`; Gemini anahtarı
   sızarsa AI Studio'dan **silip yenisini** oluşturun.
4. `ALLOWED_TELEGRAM_USER_ID=0` bırakmayın; aksi halde bot kimseye cevap
   vermez. Başkasının ID'sini yazmayın (o kişi bilgisayarınızı yönetebilir).
5. `DASHBOARD_HOST`'u `0.0.0.0` yapmayın, portu router'dan dışarı açmayın.
   Dashboard kimlik doğrulaması olmadan **yalnızca bu bilgisayarda** çalışmak
   üzere tasarlandı.
6. Ekran görüntüleri ve `data/` klasörü kişisel veri içerebilir; paylaşmadan
   önce temizleyin.

**Çalıştırma**

7. **Aynı token ile iki JARVIS çalıştırmayın.** İkinci örnek `Conflict` hatası
   alır ve sessizce çekilir. Tek `run.py` yeterlidir.
8. `run.py` çalışırken `data/` altındaki dosyaları elle düzenlemeyin/silmeyin;
   log ve SQLite kilitlenebilir.
9. Projeyi **yönetici olarak çalıştırmayın**; gerek yoktur ve güvenlik riskini
   artırır.
10. JARVIS açıkken bilgisayarı uyutmayın/kilitlemeyin ve aynı anda fare+klavye
    otomasyonu (WhatsApp/tıklama) başlatmayın; otomasyon yanlış yere tıklayabilir.
11. Pencereyi kapattığınızda bot durmaz; durdurmak için `/kapat` veya
    dashboard “Durdur” kullanın.

**Kurulum / sistem**

12. **Python 3.13/3.14 ile zorlamayın.** Hata alırsanız 3.11/3.12 kurup
    `scripts\kurulum.ps1`'i tekrar çalıştırın.
13. Projeyi **Linux/macOS'ta** çalıştırmayı denemeyin; Windows'a özeldir.
14. `.env` dosyasını `.env.txt` olarak kaydetmeyin, adını değiştirmeyin.
15. Proje klasörünü OneDrive/Drive gibi senkronize klasöre koymayın; dosya
    kilitleri ve log tekrarları sorun çıkarır.
16. `GEMINI_MODEL` alanına doğrulanmamış/uydurma model adı yazmayın.
17. `Tesseract` **v3 veya daha eskisini** kullanmayın; OCR sessizce bozulur.
    v4+ kurun.
18. `data/` klasörünü elle oluşturmak zorunda değilsiniz; uygulama kendisi
    oluşturur. Silerseniz “öğrenilen uygulamalar, kanallar, geçmiş” sıfırlanır
    (anahtarlar `.env`'de olduğu için silinmez).

---

## 5. Sorun giderme

| Belirti | Neden / Çözüm |
|---|---|
| `TELEGRAM_BOT_TOKEN eksik/gecersiz` | `.env` doldurulmamış veya dosya adı `.env.txt`. Düzelt, yeniden başlat. |
| Bot cevap vermiyor | `ALLOWED_TELEGRAM_USER_ID` yanlış ya da `run.py` çalışmıyor. `/ping` dene. |
| `Conflict` / iki bot | Aynı token'la ikinci örnek çalışıyor. Diğerini kapat; tek `run.py`. |
| `Gemini API anahtarlari gecersiz` | Anahtar silinmiş/yanlış kopyalanmış. AI Studio'dan yenisini al. |
| `Gemini su an yogun (kota/limit)` | Ücretsiz kota doldu. Bekle veya `GEMINI_API_KEY_2/_3` ekle. |
| `GEMINI_MODEL kullanilamiyor` | Model adı yanlış/erişilemiyor. Geçerli model yaz, yeniden başlat. |
| `Tesseract ... bulunamadi` | Tesseract yok/eski. v4+ kur, JARVIS'i yeniden başlat. |
| Ses ayarlanmıyor | `pycaw`/`comtypes` kurulu olmalı; Windows'ta bir çıkış cihazı seçili olmalı. |
| Mikrofon çalışmıyor | Windows ayarlarından JARVIS/Python'a mikrofon izni ver. |
| `Dashboard` açılmıyor | Port 8000 dolu olabilir. `.env`'de `DASHBOARD_PORT=8001` yap. |
| Uygulama açılmıyor | İsim belirsizse butonla sorar; `.exe` yolunu vererek öğretebilirsin. |
| `pycache` yok, eksik mi? | Hayır. Python otomatik oluşturur; depoda olması gerekmez. |
| Türkçe karakter bozuk | Dosyaları UTF-8 kaydet; terminal kod sayfası sorunlarını `chcp 65001` ile çöz. |
| `Script ... cannot be loaded` | `-ExecutionPolicy Bypass` ekle veya `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`. |
| İlk çalıştırma çok yavaş | OCR dil dosyası indiriliyor olabilir; sonraki çağrılar hızlanır. |

Loglar: `data/jarvis.log`, `data/jarvis.db`, `data/app_crash.log`.
Dashboard'daki “Durdur” veya Telegram `/kapat` düzgün kapatır.

---

## 6. Sıfırlama, yedekleme ve güncelleme

**Ayarları sıfırlama (anahtarlar dahil):** `.env`'i `.env.example`'dan yeniden
kopyala.

**Sadece öğrenilenleri/geçmişi sıfırlama:** JARVIS'i durdur, **`data`**
klasörünü sil, yeniden başlat. Uygulama temiz bir `data/` oluşturur.

**Güncelleme:** `git pull` → bağımlılıklar değiştiyse
`.\.venv\Scripts\python.exe -m pip install -r requirements.txt` → yeniden
başlat.

**Yedek:** `.env` ve (istersen) `data/` klasörünü kopyala. `.env`'i asla
paylaşma.

---

## 7. Proje yapısı

```
Jarvis/
├─ run.py                  # Arka plan servisi (Telegram botu + dashboard)
├─ app.py                  # Masaüstü uygulaması (pywebview)
├─ config.py               # .env okuyan tek merkez
├─ core/
│  ├─ gemini_brain.py      # Gemini + tool döngüsü + anahtar failover
│  ├─ channel_flow.py      # Telegram/panel ortak konuşma akışı
│  ├─ session_state.py     # Kısa süreli hafıza + bekleyen onay/seçim
│  ├─ pending_flow.py      # Onay/seçim yardımcıları
│  ├─ logger.py            # Konsol + SQLite + dönen dosya log
│  └─ status.py            # Paylaşılan durum
├─ tools/                  # 17 yetenek (her biri TOOL_SCHEMA + fonksiyon)
├─ telegram_bot/           # Bot handler'ları + yetkilendirme
├─ dashboard/              # FastAPI + statik panel
├─ scripts/                # Kurulum, kısayol, otomatik başlangıç
├─ data/                   # Çalışma verisi (git'e girmez, otomatik oluşur)
├─ assets/                 # Simge
├─ requirements.txt
├─ .env.example
└─ ABILITIES.md            # Yapabildiklerinin listesi
```

Yeni yetenek eklemek için: `tools/` altına `TOOL_SCHEMA` + fonksiyon (dict
döndürmeli) yaz, `tools/__init__.py` içindeki `_REGISTRY` listesine ekle.
Onay gerekiyorsa `requires_confirmation`, seçim gerekiyorsa `ambiguous`
alanlarını döndür (ayrıntı kod içindeki docstring'lerde).

---

## 8. Güvenlik özeti

- Anahtarlar yalnızca `.env`'de; `.env` ve `data/` git'e girmez.
- Dashboard yalnızca `127.0.0.1` dinler; dışarıya açmayın.
- Telegram'da yalnızca senin ID'n komut verebilir.
- Tehlikeli terminal komutları onay ister.
- Tool'lar senin kullanıcı yetkilerinle çalışır; yönetici izni istemez.
- Fare/klavye otomasyonu senin oturumunda çalışır: çalışırken bilgisayarı
  başkasına bırakma.
