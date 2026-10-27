# JARVIS — Yetenekler

Bu dosya JARVIS'in neler yapabildiğini kategoriler halinde listeler.
Kurulum adımları ve kurallar için [README.md](README.md) dosyasına bak.

JARVIS komutları **doğal dille** anlar; kalıp ezberlemen gerekmez. Aşağıdaki
örnekler birer kalıptır, birebir aynı cümleyi yazmak zorunda değilsin.

---

## 1. Uygulama ve oyun açma

- Bilgisayarda kurulu uygulama/oyunları ismen açar.
- İsmin bir kısmını veya küçük yazım hatalarını tolere eder.
- Bilmediği bir uygulamayı `.exe` yolu vererek **kalıcı olarak öğrenir**.
- Masaüstü ve Başlat Menüsü kısayollarını tarayarak uygulama indeksi oluşturur
  ve yeni kurulan programlar için indeksi yeniler.
- Birden fazla eşleşme varsa tahmin etmez, **butonlarla sorar**.

Örnek kalıplar:
- “Notepad aç”
- “Hesap makinesini başlat”
- “Steam'i aç”
- “Şu yoldaki programı aç: C:\...\program.exe” (yol verilirse öğrenir)

---

## 2. Dosya yönetimi

- Masaüstü, Belgeler, İndirilenler ve Resimler klasörlerinde dosya adına göre
  arama yapar (Türkçe/İngilizce klasör adlarını tanır).
- Tek sonuç bulursa dosyayı Telegram'a/panelden gönderir; çok sonuç varsa
  hangisini istediğini sorar.
- Word (`.docx`) belgesi oluşturur: başlık + paragraflar.

Örnek kalıplar:
- “Masaüstünde fatura ara”
- “İndirilenlerde pdf bul”
- “X konusunda kısa bir belge oluştur”

Sınırlar:
- Sistem klasörlerine kendi başına girmez; yalnızca kullanıcı klasörlerini
  tarar (istenirse belirli bir klasör verilebilir).
- Silme/taşıma işlemi yapmaz.

---

## 3. Web ve arama

- API anahtarı gerektirmeyen internet araması yapar ve sonuçları özetler.
- Bilinen arama sitelerinde (arama motorları, video platformları) arama
  sonuçlarını doğrudan açar.
- Diğer sitelerde arama kutusunu bulup arama metnini yazar.
- Kayıtlı bir kanalın (RSS üzerinden) en son içeriğini açar; yeni kanal
  kaydedebilir.

Örnek kalıplar:
- “X hakkında internette ara”
- “YouTube'da Y ara”
- “Google'da hava durumunu ara”
- “Şu kanalın son videosunu aç”

Sınırlar:
- Giriş/2FA/captcha gerektiren sayfalarda otomatik oturum açmaz.
- Sonuçların doğruluğu kaynağa bağlıdır; kritik bilgileri teyit et.

---

## 4. Mesajlaşma (WhatsApp Web)

- WhatsApp Web'i açar, kişiyi arama kutusunda arar ve **ismi eşleşen doğru
  sohbete** tıklar; en üstteki sohbete körü körüne tıklamaz.
- Eşleşme belirsizse tıklamaz, alternatifleri söyler.
- Mesajı Türkçe karakterler bozulmadan gönderir.

Örnek kalıp:
- “WhatsApp'ta <kişi> kişisine <mesaj> yaz”

Sınırlar:
- İlk kullanımda WhatsApp Web'e bir kez **QR ile giriş** yapılmış olmalıdır.
- Otomasyon sırasında bilgisayarı kullanma; yanlış yere tıklama riski vardır.
- Toplu/grup mesajı gönderme ve medya ekleme yoktur.

---

## 5. Ekran okuma (OCR) ve tıklama

- Ekran görüntüsü alır ve üzerindeki yazıları metne çevirir.
- Yazının ekrandaki konumunu (koordinatını) bulur.
- Bulunan yazıya/butona fareyle tek veya çift tıklar.
- OCR çalışmadığında, verilen koordinata doğrudan tıklayabilir.
- Ekran dışı koordinatı reddeder; bulunamayan hedefe tıklamaz.

Örnek kalıplar:
- “Ekranda ne yazıyor?”
- “'Gönder' yazısına tıkla”
- “Şu noktaya tıkla: 800, 400”
- “Ekran görüntüsü al”

Sınırlar:
- OCR için **Tesseract v4+** gerekir (bkz. README 2.10).
- Çok küçük/çok düşük kontrastlı yazılarda doğruluk düşebilir.
- Tıklama, fare imlecini hareket ettirir; otomasyon sırasında fareyi kullanma.

---

## 6. Medya ve ses

- Oynat/duraklat, sonraki/önceki parça, sessize al (uygulamadan bağımsız).
- Sistem ses seviyesini 0–100 arasında ayarlar.
- Sessize alınmışsa sesi açar ve **gerçek seviyeyi doğrular**; tutmazsa hata
  bildirir (yanlış “ayarlandı” demez).

Örnek kalıplar:
- “Müziği duraklat”
- “Sonraki şarkı”
- “Sesi 30 yap”
- “Sesi kapat”

Sınırlar:
- Yönetici izni gerekmez.
- Windows ana ses cihazını kontrol eder; uygulama bazlı ses karıştırıcısını
  değil.

---

## 7. Sistem ve belge

- Terminal komutu çalıştırır ve çıktısını döner.
- Tehlikeli görünen komutları (silme, format, kapatma vb.) **onay almadan**
  çalıştırmaz.
- Ekran görüntüsü dosyası üretir.
- Word belgesi oluşturur.

Örnek kalıplar:
- “Saat kaç?”
- “C diskinde ne kadar yer var?”
- “Bu klasördeki dosyaları listele”

Sınırlar:
- Komut çıktısı uzun olursa kısaltılır.
- Uzun süren komutlar zaman aşımına uğrayabilir.
- Ses/medya işleri için terminal komutu kullanılmaz; ilgili yetenekler tercih
  edilir.

---

## 8. Hafıza, onay ve dayanıklılık

- Son mesajları kısa süreli hatırlar (kanal başına ayrı: Telegram / panel).
- Onay ve seçimler butonlarla sunulur; süresi dolan istekler geçersiz olur.
- Birden fazla Gemini anahtarı tanımlıysa, biri limitlenince otomatik diğerine
  geçer ve **sohbet bağlamını kaybetmez**.
- Bir araç hata verse bile servis çökmez; hata mesajı döner.
- Arka plan servisi beklenmedik şekilde kapanırsa kendini yeniden başlatır.

Örnek kalıplar:
- “Sesi 20 yap” (limit hatası olsa bile bağlam korunur)
- “Evet” / “Hayır” (onay butonlarına yazıyla da cevap verilebilir)

---

## 9. Masaüstü paneli ve dashboard

- Yerel panelde sohbet, mikrofonla komut, onay butonları, dosya bağlantıları.
- Canlı log, onay geçmişi, durum göstergeleri.
- Uygulama ve kanal listesini yönetme.
- Tek tuşla düzgün kapatma.

Sınırlar:
- Panel yalnızca bu bilgisayardan (`127.0.0.1`) erişilebilir.
- Uzaktan erişim için tasarlanmamıştır; dışarıya açılmamalıdır.

---

## 10. Genel sınırlar

- **Windows 10/11** gerektirir; Linux/macOS desteklenmez.
- Yönetici izni gerektiren sistem değişikliklerini yapmaz.
- Şifre/2FA/captcha çözmez; hesaplara otomatik giriş yapmaz.
- İnternet ve geçerli API anahtarı olmadan dil/akıl yürütme yetenekleri çalışmaz
  (yerel uygulama açma gibi bazı işlemler yine de yapılabilir).
- Yaptığı işlemler senin kullanıcı yetkilerinle sınırlıdır.
- Otomasyon (fare/klavye) sırasında bilgisayarı başka biri kullanmamalıdır.
