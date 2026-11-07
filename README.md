# MedSpaced

Anestezi öğrencileri için aralıklı tekrar platformu.

## Özellikler

- **FSRS / SM-2** aralıklı tekrar algoritmaları
- **IRT (1PL/2PL/3PL/MIRT)** yetenek tahmini
- **SM-2 → FSRS** göç aracı (rollback + validation)
- **Kişiselleştirme** (hedef hatırlama, optimizer)
- **Yetenek ağacı** (önkoşullar, kilitler, mastery)
- **Rotasyon odaklı** tekrar
- **Sınav modu** (HMAC oturum, IRT/XP güncelleme)
- **İçerik işleme** (PDF/DOCX/PPTX/MD → chunk → LLM soru üretimi)
- **Uzman inceleme** kuyruğu
- **XP / Lig / Seri** gamifikasyon
- **Gözlemler** (OpenTelemetry, Sentry, Prometheus)
- **Rate limiting** (memory/Redis, trusted proxy)
- **Kuyruk** (inline/Celery, retry, idempotency)
- **Yedekleme/geri yükleme** (SQLite/PostgreSQL, retention prune)
- **E2E testler** (Playwright, 5 kritik akış)

## Hızlı başlangıç

```bash
make setup
make dev
```

## Yapı

```
backend/   # FastAPI + SQLAlchemy + Alembic
frontend/  # Next.js 15 App Router + React 19
```

## Ortam değişkenleri

`backend/.env.example` kopyalayın ve düzenleyin.

## Test

```bash
make test          # pytest (60 test)
make test-e2e      # Playwright (5 test)
make load-test     # yük testi (p95 < 500ms)
```

## Docker

```bash
docker compose up -d
```

## Lisans

MIT
