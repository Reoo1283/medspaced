# Faz 4 — Üretim, Öğrenme Zekâsı ve Ürün Genişletme

Faz 4 üç aşamada ilerler. Her aşama, önceki aşamanın kabul kriterleri sağlanmadan başlamaz.

## 4A — Üretim Sertleştirme

Amaç: MedSpaced'i tek kullanıcılı geliştirme ortamından güvenilir, gözlemlenebilir ve yedeklenebilir bir üretim servisine taşımak.

- [x] İstek kimliği (`X-Request-ID`), güvenlik başlıkları ve `/ready` veritabanı kontrolü.
- [x] Üretim ortamında zayıf `MEDSPACED_SECRET_KEY` değerini reddetme.
- [x] CI: backend test + derleme, frontend type-check + production build.
- [x] İstek kimliği taşıyan yapılandırılabilir JSON loglar.
- [x] Bellek içi hız sınırlama: auth uçları ve genel API.
- [x] Prometheus metin formatında temel HTTP metrikleri (`/metrics`).
- [x] OpenTelemetry izleme ve Sentry uyumlu hata toplama.
- [x] Redis tabanlı dağıtık hız sınırlama ve güvenilir proxy başlığı desteği.
- [x] Docker imajında Alembic migration çalıştırma ve geri alma prosedürü.
- [x] PostgreSQL yedekleme/geri yükleme tatbikatı ve saklama politikası.
- [x] Uzun içerik işlerini Celery/Redis kuyruğuna taşıma; yeniden deneme ve idempotency.
- [x] Taranmış PDF'ler için OCR (Tesseract veya PaddleOCR) ve kalite kontrolü.
- [x] Playwright E2E: kayıt → içerik → onay → tekrar → sınav akışı.
- [x] Yük testi ve kapasite bütçesi (p95 hedefleri, DB bağlantı havuzu).

Kabul kapısı: CI yeşil, E2E kritik akışları kapsıyor, yedekten geri dönüş tatbikatı başarılı, üretim sırları zorunlu.

> 4A yerel doğrulama notu: 60 pytest, 5 Playwright E2E, SQLite ve embedded PostgreSQL yedek/geri yükleme ile migration tatbikatı geçti. Docker ve gerçek Redis/Celery çalışma zamanı bu ortamda (Docker yok) doğrulanamadı; CI ilk çalıştırmasında `docker compose up --build` ayrıca kontrol edilmelidir.

## 4B — Öğrenme Zekâsı

Amaç: IRT ve FSRS kalibrasyonunu daha güvenilir, açıklanabilir ve ölçülebilir hale getirmek.

- [ ] 3PL ve çok boyutlu IRT; yetenek boyutları arasında korelasyon.
- [ ] SM-2 kartlarını geriye dönük FSRS durumuna taşıma aracı ve doğrulama raporu.
- [ ] FSRS optimizer için minimum veri eşiği, model sürümü ve geri alma mekanizması.
- [ ] İçerik zorluk kalibrasyonu: reviewer onayı ile IRT zorluğu arasındaki sapma raporu.
- [ ] Ustalık eşiği ve günlük kart limiti için kullanıcı bazlı politika.
- [ ] Öğrenme çıktısı metrikleri: retention, lapse, sınav hazırlığı ve kalibrasyon eğrisi.

Kabul kapısı: Model değişiklikleri A/B veya geri alınabilir özellik bayrağıyla açılabilir; her model sürümü için açıklama ve metrik raporu vardır.

## 4C — Ürün Genişletme

Amaç: Öğrenci erişimini ve günlük kullanımı artırmak.

- [ ] PWA: çevrimdışı tekrar kuyruğu, kurulum ve temel bildirimler.
- [ ] Zamanlanmış çalışma hatırlatmaları ve bildirim tercihleri.
- [ ] Gelişmiş lig/sosyal özellikler ve gizlilik kontrolleri.
- [ ] Öğrenci ve reviewer için raporlama panoları; dışa aktarma.
- [ ] Erişilebilirlik (WCAG 2.1 AA) ve mobil öncelikli düzen denetimi.
- [ ] Çok dilli içerik ve terminoloji sözlüğü.

Kabul kapısı: Erişilebilirlik denetimi, gizlilik etkisi değerlendirmesi ve mobil performans bütçesi sağlanır.

## Sıralama

1. 4A gözlemlenebilirlik, güvenlik ve CI.
2. 4A dayanıklılık: migration, yedekleme, kuyruk, OCR.
3. 4B model kalibrasyonu ve veri geçişi.
4. 4C PWA, bildirimler ve raporlama.
