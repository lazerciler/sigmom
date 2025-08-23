# SIGMOM — Release Notes

## v1.0.1 — 2025-08-23

### 🎯 Öne Çıkanlar
- **Görünürlük Kuralları (Panel)**
  - **Misafir:** “Açık/Kapanan işlemler” ve KPI/Equity blokları ilk render’dan itibaren **gizli**.
  - **Girişli:** “Açık/Kapanan işlemler” **görünür**.
  - **Referans Doğrulanmış:** KPI’lar + Equity **görünür**. (Server-side koşullandırma + koşullu script yükleme ile FOUC bitti.)
- **Tarih Gösterimi (Borsa tarafı)**
  - “Kapanan işlemler” ve “Açık pozisyonlar”da PnL yerine **Tarih (UTC)**.
  - **ISO** ve **epoch (10/13 hane)** girişleri otomatik algılanır.
- **Scrollbar / UI Polisajı**
  - “Açık/Kapanan işlemler” listelerinde **ince kaydırma** (dikey/yatay).
  - `panel_extras.css` yorum hatası düzeltildi; yatay scrollbar **height** eklendi.
- **Equity / KPI**
  - Equity KPI ve grafiği yalnız **referanslı** kullanıcıda.
  - Başlangıç bakiyesi backend’den çekiliyor; gereksiz periyodik “dans” yok (**olay-tetikli** yenileme).
- **Boş durum senaryosu**
  - İlk kurulumda sinyal yoksa: “Henüz sinyal yok” etiketi + **ön tanımlı sembol** ile grafik boş kalmaz.

### 🧩 Kod & DB
- **DB Guard (Alembic)**
  - `20250821_enforce_positive_open_trade_insert.py`:
    - `strategy_open_trades` BEFORE INSERT tetikleyicisi:
      - `entry_price > 0`, `position_size > 0`, `leverage > 0`.
- **Trade Güvenliği**
  - `crud/trade.py`: kapanış fiyatı seçimi (close_price) **0’a düşmeyecek** güvenli seçim; PnL hesapları testlerle doğrulandı.
- **Testler**
  - `tests/test_trade_helpers.py` eklendi (yardımcı fonksiyonlar).
- **Araçlar / Stil**
  - `pre-commit` (ruff, black, EOF fixer) aktif; uyarılar temizlendi.
  - `zip_logger_backup.py` yol/sonsatır düzeni; `schema/` yapısı **db/json/skeletons** altına ayrıldı; guard patch’ler eklendi.

### 🔧 Yükseltme Adımları
1. **Migrasyon:** `alembic upgrade head`
2. **Statik sürüm etiketleri:** `panel.js`, `panel_equity.js`, `panel_extras.css` için `?v=` değerlerini güncelle.
3. **Tarayıcı:** Hard refresh (Ctrl+F5).

### 📌 Notlar
- Görünürlük akışı: **Misafir** (gizli) → **Girişli** (işlem tabloları) → **Referanslı** (KPI + Equity).
- Borsa tarihleri **her zaman UTC** (ISO/epoch destekli).
- Breaking changes: **Yok**.

## v1.0.0 — 2025-08-20 🎉 (TODAY'S DATE)

### 🚀 BÜYÜK TEMİZLİK VE STABİLİZASYON

**ÖNEMLİ:** Önceki tüm "stable" olmayan tag'ler silindi.

### ✅ Temizlenen Eski Tag'ler:
- v0.1.0-stable (stable değildi) ❌
- v0.2.0 ❌
- v0.2.1 ❌
- v0.2.2 ❌
- v0.3.0 ❌

### 🎯 Bu Release'de Neler Var?
- **Black Code Formatting** tüm kod tabanına uygulandı
- **Public klasörü** ve dosya yapısı iyileştirmeleri
- **`.gitignore`** merge conflict'leri temizlendi
- **Profesyonel tag yönetimi** başlatıldı

### 📊 Teknik Detaylar:
- 3+ dosya Black ile formatlandı
- Kod okunabilirliği önemli ölçüde arttı
- GitHub repo artık lokalle tam senkronize

### ⚠️ Kıran Değişiklikler:
- Eski tag'ler tamamen temizlendi
- Kod formatting standartları değişti

---

## [ESKİ RELEASE NOTLARI (ARŞİV) - AŞAĞIDA DEVAM EDİYOR...]

## v0.3.0 — 2025-08-17

### Öne Çıkanlar
- **Referans akışı (frontend)**
  - Panelde referans kodu modali artık `/referral/verify` endpoint’ine **JSON `{code}`** ile POST ediyor.
  - Hatalı format için **istemci tarafı regex** kontrolü eklendi (`AB12-CDEF-3456`).
  - Hata/başarı mesajlarında **light/dark** uyumlu, yüksek kontrastlı uyarı şeritleri.
  - “[object Object]” yerine okunabilir hata metni (liste/obje dönüşlerinde akıllı mesaj çıkarımı).

- **Erişim rolleri (UI metinleri)**
  - Terminoloji netleştirildi: **Misafir → Standart Üye → Asil Üye**.
  - Header rozetindeki (role-chip) ve “Durum > Erişim” satırındaki metinler güncellendi.

- **Equity (balance) erişim kapısı**
  - Equity/Chart bölümünün görünürlüğü **yalnızca** `EQUITY_ALLOWED` bayrağına bağlandı (heuristic/fazladan istek yok).

- **Kapasite temizliği**
  - `capacity_full` ve ilişkili tüm UI/şablon artıkları **kaldırıldı**.
  - `app/services/capacity.py` **silindi**.

- **Diğer UI/akış düzeltmeleri**
  - Sabit “USDT” etiketleri KPI başlıklarından kaldırıldı (değerler backend’den geliyor).
  - Yanlış endpoint’lere istek atan eski kodlar düzeltildi (özellikle referans doğrulama).
  - JS sürüm parametresi ile **cache busting** iyileştirildi.

### Teknik Notlar / Değişiklikler
- **Silinen dosya:** `app/services/capacity.py`
- **Güncellenen dosyalar (özet):**
  - `app/templates/panel.html` — rol/erişim metinleri, referans durumu; Tailwind safelist bloğu.
  - `app/static/js/panel.js` — referans modali wiring, format doğrulama, mesaj kontrastı.
  - `app/static/js/panel_equity.js` — `EQUITY_ALLOWED` temelli kapı.
  - `app/routers/panel.py` — `capacity_full` context’ten çıkarıldı.

### Kıran Değişiklikler
- Şablonlarda/JS’te **`capacity_full` ya da `capacityFull`** artık yok. Kullanan özel kodlarınız varsa güncelleyin.
- Referans doğrulama endpoint’i olarak **`POST /referral/verify` (JSON `{code}`)** kullanılmalı (çerezlerle `credentials: "include"`).

### Yükseltme Adımları
1. Pull → restart (uvicorn/servis).
2. Tarayıcıda **hard refresh** (veya `panel.js?v=` numarasını artırın).
3. “Referans Kodu Gir” modalında:
   - Yanlış formatta anında uyarı,
   - Geçerli kodda “Başarılı. Yenileniyor…” → sayfa yenilenir → “Asil Üye”.

> Not: “Sıraya Gir (waitlist)” özelliği bu sürüme **dahil değil**; ayrı bir sürümde eklenecek.


# v0.2.2 — LF Normalization & PyCharm Working Tree Sync
**Yayın Tarihi:** 15 Ağustos 2025

## 🚀 Öne Çıkanlar
- **Satır Sonu Standartlaştırma:**
  `.gitattributes` eklendi ve tüm kod tabanı **LF** satır sonuna normalize edildi.
  Bu, platformlar arası uyumu artırır ve gereksiz diff değişikliklerini engeller.
- **Yeni Router’lar:**
  - `app/routers/market.py` — Market verisi için API endpoint’leri
  - `app/routers/panel_data.py` — Panel arayüzüne veri sağlayan API endpoint’leri
- **Binance Futures Modülleri Güncellemeleri:**
  - `settings.py`, `utils.py`, `order_handler.py`, `positions.py`, `sync.py`, `account.py` üzerinde iyileştirmeler
- **Panel Arayüzü Geliştirmeleri:**
  - `app/static/css/panel.css` ve `app/static/js/panel.js` güncellendi
  - `app/templates/panel.html` üzerinde arayüz düzenlemeleri
- **Yeni Şema Dosyaları:**
  - `schema/acceptable_json_examples.txt`
  - `schema/sigmom_pro_v1_20250813_dump.sql`
- **Temizlik:**
  - `hash_log.txt` ve gereksiz eski dosyalar kaldırıldı
  - `crud/trade.py` düzenlendi, eski versiyon `trade-old.py` olarak arşivlendi

## 📊 Değişiklik Özeti
- **30 dosya değişti**
- **+1452 satır** eklendi, **-575 satır** silindi
- CRLF → LF dönüşümü tamamlandı


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
