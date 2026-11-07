# MedSpaced — Anestezi Öğrencileri İçin Aralıklı Tekrarlı Öğrenme Platformu

> Bu doküman, projeyi devralacak yapay zeka/geliştirici için yazılmıştır. Usta-çırak mantığıyla ilerler: her bölümde önce **"neden"** sorusu cevaplanır, sonra **"nasıl"** anlatılır. Sırayı atlama — mimari kararların çoğu birbirine bağımlı, baştan sona okumadan kod yazmaya başlarsan ileride geri dönüp kırman gerekir.

---

## 0. Önce Şunu Anla: Bu Proje Neyin Kopyası Değil

Bu platform "Duolingo'nun tıp versiyonu" gibi tanıtılacak ama **doğrudan kopyası değil**. Fark şurada: Duolingo'da içerik (dil kuralları, kelime havuzu) sabit, önceden bilinen, hatasız bir evrendir. Burada içerik **kullanıcıların yüklediği ham ders notlarından üretilecek** ve yanlış üretilen bir soru, dilde "yanlış çeviri" gibi komik değil, tıpta **tehlikeli** bir sonuç doğurabilir.

Bu yüzden projenin can alıcı noktası skill tree ya da gamification değil — **içerik üretim ve doğrulama pipeline'ı**. Oraya en çok özeni sen vereceksin. Bunu unutma, ilerleyen bölümlerde tekrar vurgulayacağım.

---

## 1. Sistem Mimarisine Kuş Bakışı

```
┌─────────────────┐     ┌──────────────────────┐     ┌─────────────────┐
│  İçerik Yükleme  │────▶│  İşleme Pipeline'ı    │────▶│  İnceleme Kuyruğu │
│  (PDF/DOCX/PPTX) │     │  (extract→chunk→gen)  │     │  (uzman onayı)    │
└─────────────────┘     └──────────────────────┘     └────────┬────────┘
                                                                │ onaylanan içerik
                                                                ▼
┌─────────────────┐     ┌──────────────────────┐     ┌─────────────────┐
│   Kullanıcı UI   │◀───▶│   SRS Scheduler      │◀───▶│  İçerik Deposu    │
│ (web/mobile)     │     │   (FSRS algoritması)  │     │  (skill graph)    │
└─────────────────┘     └──────────────────────┘     └─────────────────┘
         │
         ▼
┌─────────────────┐
│  Gamification    │
│  (streak/XP/lig) │
└─────────────────┘
```

Beş ana servis var. Her biri bağımsız ölçeklenebilir olmalı (microservice ya da modüler monolit — ekip büyüklüğüne göre sen karar ver, ama sınırları **şimdiden** bu şekilde çiz ki ileride ayırmak acı vermesin).

---

## 2. İçerik İşleme Pipeline'ı — En Kritik Bölüm

### 2.1 Neden bu kadar önemli?

Çünkü bu pipeline'ın çıktısı yanlışsa, sistemin geri kalanı ne kadar iyi tasarlanırsa tasarlansın öğrenciye yanlış bilgi öğretir. Burada kısa yol arama.

### 2.2 Adım Adım Akış

**Adım 1 — Metin Çıkarma (Extraction)**
- PDF: `PyMuPDF (fitz)` veya `pdfplumber` kullan. Taranmış (scanned) sayfalar için OCR gerekir — `Tesseract` yeterli, ama tıbbi terimler için özel bir dil modeli/sözlük ekle, yoksa "rokuronyum" gibi kelimeleri yanlış okur.
- DOCX/PPTX: `python-docx`, `python-pptx` ile direkt yapılandırılmış metin çıkar (slayt başlıkları, madde işaretleri bilgisi değerlidir, kaybetme).

**Adım 2 — Chunking (Anlamlı Parçalara Bölme)**
- Düz karakter sayısına göre bölme (`chunk_size=500` gibi) **YANLIŞ**. Başlık/alt başlık hiyerarşisine göre böl (örn. "## İndüksiyon Ajanları" → bu başlık altındaki tüm içerik tek chunk).
- Her chunk şu metadata'yı taşımalı: `source_file`, `page_number`, `section_title`, `chunk_id`. Bu, öğrenciye sonradan "bu soru şu notun şu sayfasından geliyor" linkini vermeni sağlar — tıp eğitiminde kaynağa dönebilmek kritik bir güven unsuru.

**Adım 3 — Kavram Çıkarımı (Concept Extraction)**
- Her chunk'tan anahtar kavramları çıkar (ilaç isimleri, dozlar, prosedür adımları, kontrendikasyonlar).
- Bunun için bir LLM çağrısı kullanabilirsin ama **yapılandırılmış çıktı** (JSON schema) zorunlu kıl, serbest metin değil. Örnek şema:

```json
{
  "concepts": [
    {
      "term": "Propofol",
      "category": "indüksiyon_ajanı",
      "key_facts": [
        "İndüksiyon dozu: 1.5-2.5 mg/kg IV",
        "Kontrendikasyon: yumurta/soya alerjisi (formülasyona bağlı)"
      ],
      "source_chunk_id": "chunk_0042"
    }
  ]
}
```

**Adım 4 — Soru/Flashcard Üretimi**
- Her kavramdan birden fazla egzersiz tipi üret (bkz. Bölüm 5). Burada da **asla serbest metin çıktı alma** — her egzersiz tipi için sabit bir JSON şeması tanımla ve LLM'e onu doldurt.
- Üretirken `temperature` düşük tut (0.2-0.3 civarı) — yaratıcılık değil, doğruluk istiyorsun.
- Her üretilen soru, kaynağı olan `source_chunk_id`'yi taşımalı. Kaynaksız soru sisteme giremez — bunu şema seviyesinde zorunlu alan yap.

**Adım 5 — Uzman İnceleme Kuyruğu (Review Queue)**
- Bu adımı **asla atlama veya opsiyonel yapma**. Üretilen her soru şu durumlardan birine girer: `draft` → `under_review` → `approved` / `rejected`.
- Bir anestezi uzmanı/asistanı rol bazlı giriş yapıp onaylamadan hiçbir soru öğrenciye gösterilmez.
- Reddedilen sorular neden reddedildiği (free-text not) ile birlikte arşivlenir — bu veri ileride LLM prompt'unu iyileştirmek için altın değerinde.

### 2.3 Teknik Not

Bu pipeline'ı senkron değil, **asenkron kuyruk** (Celery + Redis, ya da RabbitMQ) üzerine kur. Bir öğretim üyesi 200 sayfalık bir ders notu yüklediğinde kullanıcıyı bekletme — "işleniyor, bittiğinde bildirim alacaksın" de ve arka planda işle.

---

## 3. Kavram Grafiği (Skill Graph)

### 3.1 Veri Modeli

Duolingo'nun skill tree'si aslında bir **DAG (yönlü asiklik graf)**. Düğümler (node) kavramları/dersleri, kenarlar (edge) önkoşul ilişkilerini temsil eder.

```sql
CREATE TABLE skill_nodes (
    id UUID PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    category VARCHAR(100),  -- 'farmakoloji', 'hava_yolu', 'monitorizasyon' vs.
    description TEXT,
    created_from_chunk_id UUID REFERENCES content_chunks(id)
);

CREATE TABLE skill_prerequisites (
    skill_id UUID REFERENCES skill_nodes(id),
    prerequisite_id UUID REFERENCES skill_nodes(id),
    PRIMARY KEY (skill_id, prerequisite_id)
);

CREATE TABLE user_skill_progress (
    user_id UUID REFERENCES users(id),
    skill_id UUID REFERENCES skill_nodes(id),
    mastery_score FLOAT DEFAULT 0,  -- 0-100
    last_practiced_at TIMESTAMP,
    PRIMARY KEY (user_id, skill_id)
);
```

### 3.2 Graf Nasıl Kurulur?

İçerik yükleme sırasında öğretim üyesinden (ya da başlangıçta elle) bir müfredat iskeleti alman gerekir — örneğin:

```
Temel Farmakoloji
  ├─ İndüksiyon Ajanları
  ├─ Kas Gevşeticiler
  └─ Analjezikler (Opioidler)
Hava Yolu Yönetimi
  ├─ Maske Ventilasyonu
  ├─ LMA Uygulaması
  └─ Entübasyon (± Zor Hava Yolu)
Monitörizasyon
  ...
```

LLM'in otomatik olarak chunk'lardan hiyerarşi çıkarmasına **güvenme** — ilk sürümde bunu yarı-otomatik yap: LLM bir taslak hiyerarşi önersin, uzman düzenleyip onaylasın. Tam otomasyon ancak sistem olgunlaştıkça (yeterli onaylı veri birikince) güvenli hale gelir.

### 3.3 İlerleme Kuralı

Bir node'a "kilitli değil" (unlocked) denebilmesi için tüm önkoşullarının `mastery_score >= eşik_değer` (örn. 70) olması gerekir. Duolingo'daki gibi "zayıf geçiş" (partial unlock, düşük XP ile) de bir opsiyon ama tıp eğitiminde ben bunu **önermem** — kritik bir konuyu yarım öğrenip sonrakine geçmek, dil öğrenmekten farklı olarak klinik risk taşır.

---

## 4. SRS (Spaced Repetition) Algoritması — FSRS

### 4.1 Neden FSRS, neden SM-2 değil?

SM-2 basit ve hızlı implemente edilir ama 1987'de tasarlandı, tek bir sabit formülle herkese aynı eğriyi uygular. **FSRS (Free Spaced Repetition Scheduler)**, her kullanıcı-kart çifti için üç parametre tutan modern, veriden öğrenen bir modeldir: `Difficulty (D)`, `Stability (S)`, `Retrievability (R)`. Anki projesinin resmi algoritmasıdır, açık kaynaktır, Python/Rust implementasyonları hazırdır (`py-fsrs` paketi).

### 4.2 Temel Formül Mantığı

```
R(t) = (1 + t / (9 × S))^(-1)
```

- `t`: son tekrardan geçen gün sayısı
- `S`: stability (kararlılık) — kart ne kadar "kalıcı" öğrenilmiş
- `R`: retrievability — şu an hatırlama olasılığı

Her cevapta (Again/Hard/Good/Easy — 4'lü değerlendirme, sadece doğru/yanlış değil) sistem `D` ve `S` değerlerini günceller, bir sonraki gösterim tarihini hesaplar.

### 4.3 Implementasyon Adımları

1. `py-fsrs` kütüphanesini kullan, sıfırdan yazma — algoritma matematiksel olarak hassas, kendi implementasyonun hata barındırır.
2. Her `user_card_state` kaydı şu alanları tutmalı: `difficulty`, `stability`, `retrievability`, `due_date`, `review_count`, `lapse_count`.
3. Günlük "bugün tekrar edilecekler" sorgusu: `WHERE due_date <= NOW() ORDER BY retrievability ASC` — en çok unutma riski taşıyanlar önce gelir.
4. Kullanıcı cevap verdikçe parametreleri FSRS kütüphanesinin `review()` fonksiyonuna geçir, dönen yeni state'i kaydet.

### 4.4 Soğuk Başlangıç Problemi (Cold Start)

Yeni bir kullanıcı ya da yeni bir kart için yeterli veri yoksa FSRS'in varsayılan global parametrelerini kullan (kütüphane bunu sağlar). Yeterli review verisi birikince (genelde >1000 review/kullanıcı), FSRS'in kendi parametre optimizasyon fonksiyonunu (`optimizer`) periyodik çalıştırarak kullanıcıya özel kalibrasyon yapabilirsin. Bunu v1'de yapma, v2 için not et.

---

## 5. Egzersiz Tipleri ve Üretimi

Her skill node altında şu egzersiz tiplerini destekle (hepsini aynı anda kurmak zorunda değilsin, öncelik sırası önerim):

1. **Çoktan seçmeli (MCQ)** — en kolay üretilir, en kolay otomatik doğrulanır. İlk sürümde buna odaklan.
2. **Cloze (boşluk doldurma)** — "Propofol indüksiyon dozu ____ mg/kg'dır." Kavram ezberini test eder.
3. **Vaka vinyeti (clinical vignette)** — "68 yaşında, ASA III, acil apendektomi planlanan hastada indüksiyon ajanı seçimini ve gerekçesini belirtin." Bunlar otomatik puanlanamaz, ya çoktan seçmeli vaka sorusu formatına indirge ya da (ileri aşama) rubric bazlı LLM değerlendirmesi ekle — ama bunu da bir uzmanın spot-check etmesi lazım.
4. **Eşleştirme** — ilaç-doz, komplikasyon-tedavi eşleştirmeleri.

Her egzersiz, sunum zamanında **procedural olarak** çeşitlendirilmeli (aynı kavramın farklı soru kalıpları arasında rotasyonu) — amaç ezber değil gerçek anlama.

---

## 6. Zorluk Kalibrasyonu (IRT)

Tıp sınavları (TUS, USMLE) zaten **Item Response Theory (IRT)** kullanır, tekerleği yeniden icat etme, aynı yaklaşımı benimse.

- Her soru bir `difficulty` ve `discrimination` parametresi taşır.
- Her kullanıcı bir `ability` (yetkinlik) skoru taşır.
- 3PL (3-parametre lojistik) modeli: `P(doğru) = c + (1-c) / (1 + e^(-a(θ-b)))`
  - `θ`: kullanıcı yetkinliği, `b`: soru zorluğu, `a`: ayırt edicilik, `c`: şans faktörü (MCQ'da şans ile doğru bilme payı)
- Kullanıcı cevapladıkça bu parametreler **Bayesian güncelleme** ile kalibre olur. `py-irt` veya `girth` gibi Python kütüphaneleri hazır implementasyon sağlar, sıfırdan yazma.

Bu sana bonus bir özellik de verir: "Bu öğrenci gerçek sınava ne kadar hazır" tahmini — çünkü aynı IRT modeli gerçek sınav formatına da uygulanabilir.

---

## 7. Gamification Katmanı

Duolingo'nun oyunlaştırma mantığı davranışsal psikolojiye dayanır, aynen uyarlanabilir:

- **Streak (seri)**: kesintisiz çalışma günü sayacı — kayıp korkusu (loss aversion) motive eder.
- **XP + Lig sistemi**: haftalık leaderboard, bronz→gümüş→altın ligleri.
- **Hearts/Can sistemi**: Tıp eğitiminde bunu **dikkatli** kullan — çok fazla cezalandırıcı olursa öğrenci stresi klinik öğrenmeyi olumsuz etkiler. Önerim: pratik modunda can sınırı olmasın, sadece "sınav simülasyonu" modunda olsun.
- **Rotasyon bazlı özelleştirme** (tıbba özgü ekleme): "Bu hafta kardiyak anestezi rotasyonundayım" dersen sistem o konudaki node'ları öne çeker, bildirimleri ona göre hedefler.

---

## 8. Veritabanı Şeması — Genel İskelet

```sql
-- İçerik tarafı
content_files (id, uploaded_by, filename, status, uploaded_at)
content_chunks (id, file_id, section_title, page_number, raw_text)
skill_nodes (id, title, category, description, source_chunk_id)
skill_prerequisites (skill_id, prerequisite_id)
exercises (id, skill_id, type, payload_json, status, source_chunk_id, created_by_ai, reviewed_by, reviewed_at)

-- Kullanıcı tarafı
users (id, email, role, created_at)  -- role: 'student' | 'reviewer' | 'admin'
user_skill_progress (user_id, skill_id, mastery_score, last_practiced_at)
user_card_state (user_id, exercise_id, difficulty, stability, retrievability, due_date, review_count, lapse_count)
review_logs (id, user_id, exercise_id, answer, is_correct, response_time_ms, reviewed_at)

-- Gamification
user_streaks (user_id, current_streak, longest_streak, last_active_date)
user_xp (user_id, total_xp, league_id, league_rank)
```

---

## 9. Teknoloji Yığını Önerisi

| Katman | Öneri | Neden |
|---|---|---|
| Backend API | Python + FastAPI | Async destekli, NLP/LLM entegrasyonu Python'da çok daha rahat |
| İçerik işleme worker | Python + Celery + Redis | Asenkron, ölçeklenebilir kuyruk |
| Veritabanı | PostgreSQL | İlişkisel veri (skill graph, progress) için en uygunu |
| Vektör arama | pgvector (Postgres eklentisi) | Notlardan semantik arama, "bu soru hangi sayfadan" linki için |
| SRS motoru | `py-fsrs` | Hazır, test edilmiş, doğru implementasyon |
| IRT motoru | `py-irt` / `girth` | Hazır, sıfırdan yazma |
| Frontend web | React / Next.js | — |
| Mobil | React Native veya Flutter | Tek kod tabanı, offline-first önemli |
| LLM entegrasyonu | Claude/GPT API, yapılandırılmış JSON çıktı zorunlu | Soru üretimi — her zaman human review'dan geçecek |

---

## 10. Geliştirme Yol Haritası (Öncelik Sırası)

**Faz 1 — Çekirdek (MVP)**
1. İçerik yükleme + extraction + chunking
2. Manuel/yarı-otomatik skill graph tanımlama arayüzü
3. MCQ üretimi + review queue
4. Basit SRS (önce SM-2 ile başlayabilirsin, hızlı prototipleme için — sonra FSRS'e geç)
5. Temel kullanıcı ilerleme takibi

**Faz 2 — Olgunlaşma**
1. FSRS'e geçiş
2. Cloze + eşleştirme egzersiz tipleri
3. IRT bazlı zorluk kalibrasyonu
4. Gamification (streak, XP, lig)

**Faz 3 — İleri Seviye**
1. Vaka vinyeti soruları + rubric bazlı LLM destekli değerlendirme
2. Kullanıcıya özel FSRS parametre optimizasyonu
3. Rotasyon bazlı içerik önceliklendirme
4. Sınav simülasyon modu

---

## 11. Asla Unutma — Üç Altın Kural

1. **Kaynaksız soru yok.** Her egzersiz, hangi ders notu chunk'ından geldiğini taşımalı.
2. **İncelemesiz yayın yok.** LLM'in ürettiği hiçbir tıbbi içerik, bir uzman onayı olmadan öğrenciye gösterilmemeli.
3. **Ezber değil, anlama hedefi.** Procedural soru üretimi (aynı kavramın farklı kalıplarda sorulması) bu yüzden opsiyonel değil, mimarinin bir parçası.

---

*Bu doküman projenin iskeletidir. Her bölümdeki kütüphane/algoritma seçimleri kesin zorunluluk değil, gerekçesiyle verilmiş önerilerdir — ekip ihtiyacına göre değiştirilebilir, ama değiştirirken buradaki "neden" kısmını yeniden değerlendir.*

---

## 12. Uygulama Durumu ve Çalıştırma

> Bu bölüm spesifikasyonun üzerine, teslim edilen çalışan sürümü anlatır. Bölüm 0–11 proje gereksinimleridir; bu bölüm ise mevcut kod tabanının nasıl çalıştırılacağını ve nelerin uygulandığını özetler.

### 12.1 Hazır Olanlar

- **Backend (FastAPI, modüler monolit):** kimlik doğrulama (JWT access/refresh, Argon2), rol tabanlı yetkilendirme (student/reviewer/admin), içerik yükleme + extraction (PDF/DOCX/PPTX/MD/TXT), taranmış PDF'ler için RapidOCR (Tesseract varsa yedek) OCR, başlık hiyerarşisine göre chunking, LLM ile kavram/soru üretimi (fake + OpenAI-uyumlu + Anthropic + Ollama/vLLM), inceleme kuyruğu ve durum makinesi (`draft → under_review → approved/rejected`), FSRS varsayılan (SM-2 opsiyonel) SRS, kullanıcıya özel hedef hatırlama kalibrasyonu, online IRT/2PL yetenek ve soru zorluğu kalibrasyonu, yetenek ağacı + önkoşul kilidi + mastery, XP/seri/haftalık lig promosyonu, rotasyon bazlı tekrar önceliklendirme, rubric bazlı vaka vinyeti değerlendirmesi (deterministik + opsiyonel LLM), durumsuz sınav simülasyonu, günlük tekrar kuyruğu ve istatistikler, arka plan işleri ve job takibi. Üretimde Redis tabanlı hız sınırlama, Celery/Redis kuyruğu (retry + idempotency), Sentry uyumlu hata toplama, OpenTelemetry izleme, PostgreSQL bağlantı havuzu ve yedekleme araçları vardır.
- **Frontend (Next.js 15 App Router, TypeScript):** panel, giriş/kayıt, tekrar ekranı (MCQ/cloze/eşleştirme/vaka vinyeti), yetenek ağacı, içerik yönetimi (yükleme/işleme/soru üretme + job poll), inceleme kuyruğu (onay/red), rotasyon ve FSRS kişiselleştirme kartları, sınav simülasyonu, yönetim (kullanıcı oluşturma) ve yetenek ağacı yönetimi (CRUD, hiyerarşi ve önkoşul düzenleme).
- **Testler:** 60 pytest testi (auth, chunking, OCR, SRS/IRT, grading/vignette, exam, rotation, personalization, pipeline, queue/idempotency, backup/restore, PostgreSQL migration, health/readiness, rate limit, telemetry, load-test yardımcıları) — `make test`. Ayrıca 5 Playwright E2E testi (kayıt → içerik → onay → tekrar → sınav) — `make e2e`.
- **Altyapı:** Alembic migration'ları, Dockerfile'lar, `docker-compose.yml` (Postgres + Redis + backend + Celery worker + frontend), seed script'i, otomatik migration entrypoint'i, yedekleme/geri yükleme ve saklama aracı.
- **Faz 3 durumu:** Vaka vinyeti + rubric değerlendirmesi, kullanıcıya özel FSRS hedef hatırlama kalibrasyonu, rotasyon bazlı önceliklendirme ve sınav simülasyonu tamamlandı.
- **Faz 4 durumu:** 4A üretim sertleştirme tamamlandı: gözlemlenebilirlik, dağıtık hız sınırlama, Docker migration, PostgreSQL yedekleme/geri yükleme tatbikatı, Celery/Redis kuyruğu, OCR, Playwright E2E ve yük testi. 4B/4C `docs/PHASE4_ROADMAP.md` dosyasında sırada.

### 12.2 Yerel Hızlı Başlangıç

Gereksinimler: Python ≥ 3.11, Node.js ≥ 20.

```bash
make setup        # .venv + backend bağımlılıkları + frontend npm install
cd backend && ../.venv/bin/alembic upgrade head   # veritabanı migration'ları
make seed         # demo kullanıcılar, yetenekler ve onaylı sorular
```

Tam FSRS parametre optimizasyonu (`fsrs.optimizer`) opsiyoneldir ve ek bağımlılık ister:

```bash
.venv/bin/pip install --index-url https://download.pytorch.org/whl/cpu torch==2.15.0+cpu
.venv/bin/pip install -r backend/requirements-optimizer.txt
```

Bu bağımlılıklar yoksa sistem sezgisel hedef hatırlama kalibrasyonuna geri döner.

İki terminalde:

```bash
make dev          # http://localhost:8000  (API + Swagger: /docs)
make frontend-dev # http://localhost:3000
```

Frontend varsayılan olarak `http://localhost:8000/api/v1` adresine bağlanır. Farklı bir API için `frontend/.env.local` içine `NEXT_PUBLIC_API_URL=...` yazın. Backend ayarları için `backend/.env.example` dosyasını `backend/.env` olarak kopyalayıp düzenleyin (`MEDSPACED_` öneki).

### 12.3 Demo Hesaplar

| Rol | E-posta | Parola |
|---|---|---|
| Admin | `admin@medspaced.local` | `Admin1234!` |
| Reviewer | `reviewer@medspaced.local` | `Reviewer1234!` |
| Student | `student@medspaced.local` | `Student1234!` |

Seed; `demo-anestezi-temelleri.md` dosyasını işler, 6 yetenek ve 8 onaylı soru oluşturur.

### 12.4 Test ve Derleme

```bash
make test         # backend pytest (60 test)
make lint         # python compileall
make build        # frontend üretim derlemesi
make e2e          # Playwright kritik akışlar (backend + frontend başlatır)
```

Kapasite duman testi (seed'li çalışan backend'e karşı):

```bash
cd backend
../.venv/bin/python -m scripts.load_test \
  --base-url http://127.0.0.1:8000 \
  --concurrency 10 --duration 10 --p95-ms 500
```

Yerel referans: 10 eşzamanlı istekte SQLite p95 ~263 ms, embedded PostgreSQL p95 ~273 ms; hata oranı %0.

### 12.5 Docker ile Çalıştırma

```bash
docker compose up --build
docker compose exec backend python -m scripts.seed
```

- Frontend: `http://localhost:3000`
- Backend: `http://localhost:8000`
- Postgres: `localhost:5432` (`medspaced/medspaced`)
- Redis: `localhost:6379`

Backend entrypoint'i `MEDSPACED_RUN_MIGRATIONS=true` iken `alembic upgrade head` çalıştırır; worker migration çalıştırmaz. Üretimde `MEDSPACED_SECRET_KEY` ve veritabanı parolasını mutlaka değiştirin.

### 12.6 Yedekleme ve İzleme

```bash
make backup BACKUP_DIR=backups/2026-11-07
make restore BACKUP=backups/2026-11-07
make prune-backups BACKUP_DIR=backups BACKUP_KEEP=14 PRUNE_ARGS=--apply
```

- Varsayılan saklama politikası: son 14 yedek; `prune-backups` varsayılan olarak kuru çalışır, silmek için `PRUNE_ARGS=--apply` gerekir.
- PostgreSQL yedeği `pg_dump`, geri yükleme `pg_restore` kullanır; `MEDSPACED_PG_BIN` ile araç dizini verilebilir. Docker imajında `postgresql-client` kuruludur.
- Sentry: `MEDSPACED_SENTRY_DSN`; OpenTelemetry: `MEDSPACED_OTEL_ENABLED=true` + `MEDSPACED_OTEL_EXPORTER_OTLP_ENDPOINT`. İkisi de kapalıyken no-op çalışır.
- `/ready` veritabanı hazırlığını, `/metrics` Prometheus metriklerini (isteğe bağlı `MEDSPACED_METRICS_TOKEN`) sunar.

### 12.7 Bilinçli Sınırlamalar / Sonraki Adımlar

- Docker ve gerçek Redis/Celery çalışma zamanı bu geliştirme ortamında doğrulanamadı; compose dosyası ve birim testleri hazırdır, ilk dağıtımda `docker compose up --build` ile doğrulanmalıdır.
- OCR varsayılan olarak RapidOCR ile çalışır; Tesseract yalnızca kuruluysa yedek yol olarak kullanılır. Taranmış PDF kalitesi görüntü çözünürlüğüne bağlıdır.
- IRT/ability alanları ve temel online 2PL kalibrasyonu mevcut; çok boyutlu yetenek modeli ve tam 3PL parametre tahmini 4B kapsamındadır.
- Mevcut SM-2 kart durumları otomatik FSRS'e dönüştürülmez; 4B'de geri alınabilir migration aracı eklenecektir. Yeni kartlar `MEDSPACED_SRS_ALGORITHM` ayarıyla seçilen algoritmayı kullanır.
- Kullanıcıya özel FSRS kalibrasyonu şimdilik sezgisel hedef hatırlama oranıyla çalışır; tam FSRS parametre optimizasyonu (`fsrs-optimizer`) opsiyonel bağımlılıkla çalışır, yeterli veri yoksa sezgisel yola döner.
- Vaka vinyeti değerlendirmesinde LLM puanlaması opsiyoneldir; LLM kapalıyken deterministik rubric anahtar kelimeleri kullanılır ve uzman spot-check'i önerilir.
- PWA/çevrimdışı kuyruk, çalışma hatırlatmaları, raporlama/dışa aktarma, WCAG denetimi ve i18n 4C kapsamındadır.
