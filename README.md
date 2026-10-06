# Kanıt (geçici ad)

Claude ağ değişikliğini yazar, [Batfish](https://github.com/batfish/batfish) canlıya çıkmadan önce doğrular. Yalnızca doğrulamadan geçen değişiklik kabul edilir.

```
niyet (düz dil) ──► Claude: değişiklik + niyet kontrolleri
                          │
                          ▼
              Batfish: değişmezler, niyet, ayrıştırma, fark
                          │
            ret + karşı örnek ──► Claude düzeltir (en çok N tur)
                          │
                       kabul ──► rapor (kanit-rapor.md)
```

## Durum

Erken prototip. Kapsam: Cisco IOS, erişim listesi değişiklikleri, örnek iki cihazlı ağ.

- Birim testleri (döngü, düzenleme güvenliği, Claude mesaj akışı) geçiyor.
- Gerçek Batfish'e karşı uçtan uca test her push'ta GitHub Actions'ta koşuyor (`.github/workflows/ci.yml`).
- Claude'lu canlı yol bir API anahtarıyla henüz denenmedi.

## Çalıştırma

```bash
docker compose up -d                 # Batfish
pip install -e ".[dev]"

# API anahtarı olmadan, kayıtlı iki öneriyle (önce ret, sonra kabul):
kanit plan "Kullanıcı ağından veritabanı sunucusuna (10.20.20.30) tcp/5432 aç" \
  --snapshot examples/acme \
  --scripted examples/acme/scripted/01-fazla-genis.json examples/acme/scripted/02-dogru.json

# Claude ile:
export ANTHROPIC_API_KEY=...
kanit plan "Kullanıcı ağından veritabanı sunucusuna (10.20.20.30) tcp/5432 aç" \
  --snapshot examples/acme
```

Çıkış kodu kabulde 0, rette 1. `--apply` kabul edilen değişikliği snapshot'a yazar; model `--model` ya da `KANIT_MODEL` ile seçilir.

Testler: `pytest` (Batfish'li testler için `BATFISH_HOST=localhost pytest`).

## Snapshot düzeni

```
examples/acme/
  configs/       cihaz yapılandırmaları (Batfish'in beklediği düzen)
  policy.json    değişmezler: her değişiklikten sonra geçerli kalması gereken akış kuralları
  scripted/      demo ve testler için kayıtlı öneriler
```

Bir akış kontrolü, bir akış kümesinin tamamının ulaşmasını (`reachable`) ya da tamamının engellenmesini (`blocked`) ister. Batfish kümede beklentiyi bozan tek bir akış bulursa onu karşı örnek olarak döndürür.

## Bilinen sınırlar

- Niyet kontrollerini de Claude yazar. Değişmezler bağımsızdır, ama niyet kontrolleri raporda insan tarafından okunmalıdır.
- Koruma `policy.json` içindeki değişmezler kadar güçlüdür.
- Batfish'in modellemediği cihaz ve özellikler kapsam dışıdır.
- Araç hiçbir cihaza bağlanmaz; yalnızca dosya üretir.

## Site

`site/index.html` tek dosyalık tanıtım sayfasıdır (TR/EN). Ad, e-posta ve repo adresi yer tutucudur: dosyada `Kanıt`, `ORNEK-ALAN-ADI` ve `KULLANICI/REPO` aratıp değiştirin.
