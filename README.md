# SIGMOM-Signal-Alert-Interface

SIGMOM, sinyal ve alarm arayüzü oluşturmaya yönelik bir Python projesidir.
Proje, çeşitli sinyal ve uyarı işlemlerinin yönetilmesi ve izlenmesi amacıyla tasarlanmıştır.

## Özellikler

- Sinyal ve uyarıların işlenmesi
- Python ile modüler kodlama
- Kolay entegrasyon ve özelleştirme

## Kurulum

Projeyi klonlayın:
```bash
git clone https://github.com/lazerciler/sigmom.git

pip install -r requirements.txt
```

## Yapılandırma

Oturum verilerini güvenle imzalamak için güçlü bir gizli anahtar gereklidir.
`.env` dosyanıza veya ortamınıza aşağıdaki değişkeni ekleyin:

```bash
SESSION_SECRET=<uzun-rastgele-dizge>
```

Bu değer boş bırakılırsa uygulama çalışmayı reddeder.

## Kullanım

Ana Python dosyasını çalıştırarak sinyal ve uyarı arayüzünü başlatabilirsiniz.
Daha fazla bilgi için kod ve dosya yapısını inceleyin.
