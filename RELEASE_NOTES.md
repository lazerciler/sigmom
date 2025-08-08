# SIGMOM — Release Notes

## v0.1.0-stable — 2025-08-08

### Öne Çıkanlar
- **No-delete close flow**: Açık pozisyonlar kapanırken `strategy_open_trades` silinmiyor; `status='closed'` ile işaretleniyor.
- **Güvenilir kapanış kaydı**: `strategy_trades` satırı oluşturulup `open_trade_public_id` ile ilişkilendiriliyor.
- **Doğrulama döngüsü (verifier)**: Pending → Open → Closed akışı stabilize edildi.
- **Logger temizlikleri**: Aşırı gürültü yapan debug/warn satırlarının seviyesi ayarlandı; format/sessizleştirme planı hazır.

### Davranış Değişiklikleri
- Kapanışta FK çakışmalarına yol açan “önce sil, sonra trade ekle” sırası terk edildi.
- `reduceOnly` kapanış emirlerinde zorlanıyor (Binance futures testnet).

### Veritabanı/Migrasyon
- Alembic HEAD uygulanmış durumda.
- Son oluşturulan snapshot: `0d7470062267_snapshot_before_fk_rework`.

### Konfig (özet)
- `DATABASE_URL` (MySQL/Aurora)
- `BINANCE_FUTURES_BASE_URL` (testnet)
- `API_KEY`, `API_SECRET`

### Bilinen Notlar
- Testnette `leverage=None` hatası → close sinyallerinde leverage çağrısı engellendi.
- PowerShell’de `git` pager “q” takılması yaşanırsa: `git config --global core.pager ""`.

### Sonraki Sprint (Plan)
- **FK rework**: `strategy_trades.open_trade_id (BIGINT, FK -> strategy_open_trades.id)` ekle, backfill, kodu `open_trade_id`’ye geçir, `NOT NULL` yap.
- **Logger profili**: Prod için döner dosya + JSON opsiyonu.

---

## Yükseltme Rehberi
1. Depoyu çekin: `git pull --tags`
2. Venv/Requirements: `pip install -r requirements.txt`
3. Migrasyon: `alembic upgrade head`
4. Çevre değişkenlerini/.env’i güncelleyin (aşağıdaki checklist).
5. Servisi başlatın: `uvicorn app.main:app --host 0.0.0.0 --port 8000`
