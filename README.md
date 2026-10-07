# NetLemma

Ürün ve şirket adı NetLemma (netlemma.com). Komut satırı aracı ve Python paketi şimdilik `kanit` adını taşıyor.

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

Gerekenler: Python 3.10+, Docker (Batfish için), site için Node 22.

```bash
make setup     # Python ortamı
make demo      # API anahtarı olmadan: fazla geniş öneri reddedilir, dar olan kabul edilir
make test      # Batfish dahil tüm testler

export ANTHROPIC_API_KEY=...
make plan      # Claude ile; başka istek için: make plan INTENT="..."
```

Rapor `kanit-rapor.md` dosyasına yazılır. Çıkış kodları `kanit plan` ve `kanit check` için aynıdır:

| Kod | Anlamı |
|---|---|
| 0 | Kabul: son öneri doğrulamadan geçti. |
| 1 | Ret: hiçbir öneri doğrulamadan geçmedi (kayıtlı öneriler bittiğinde de son turun reddi geçerlidir). |
| 2 | Doğrulama çalışmadı ya da sonuç teslim edilemedi: Batfish'e ulaşılamadı, snapshot ya da kayıtlı öneri okunamadı, geçersiz argüman, API anahtarı yok, API hatası, beklenmeyen hata ya da rapor/snapshot yazılamadı. Tek satırlık bir mesaj ne yapılacağını söyler; karar verildiyse onu da söyler ("kabul edildi ama rapor yazılamadı"). Rapor (yazılabildiyse) "DOĞRULAMA ÇALIŞMADI" der. Bu bir ret değildir. Ayrıntılı hata için `KANIT_DEBUG=1`. |

Batfish'e önce kısa bir bağlantı ön kontrolü yapılır (varsayılan 5 sn, `KANIT_BATFISH_TIMEOUT` ile 600 sn'ye kadar); ulaşılamazsa uzun beklemeden 2 ile durur. `--batfish-host` ana makine adı ya da IPv4 olmalı (port 9996 sabit). `--apply` ya hep ya hiç yazar: bir dosya yazılamazsa snapshot olduğu gibi kalır. `make plan` API anahtarı yoksa Batfish'i başlatmadan durur. Docker Compose proje adı `kanit` olarak sabittir; repo hangi klasörde olursa olsun aynı Batfish kapsayıcısı kullanılır.

Doğrudan komut: `kanit plan "<istek>" --snapshot <klasör>`; `--apply` kabul edilen değişikliği snapshot'a yazar, model `--model` ya da `KANIT_MODEL` ile seçilir.

## Pull request botu

Model çağrısı olmadan yalnızca doğrulama: PR'daki snapshot aday, hedef daldaki mevcut.

```bash
kanit check --base <hedef dal snapshot> --candidate <PR snapshot>   # 0 kabul, 1 ret, 2 doğrulama çalışmadı (kanit plan ile aynı)
```

Değişmezler hedef daldaki `policy.json`'dan okunur; PR'ın eklediği yeni değişmezler de kontrol edilir. Hedef daldaki bir değişmezi silen ya da değiştiren PR, yapılandırması ne olursa olsun reddedilir (değişmez önce tek başına silinip sonra ihlal edilemesin). PR snapshot'ında sembolik bağlantı varsa hiçbir dosya okunmadan reddedilir; bağlantı snapshot dışındaki içeriği (ör. ortam değişkenlerini) rapora ya da modele taşıyabilirdi.

- `.github/actions/kanit-check/`: yeniden kullanılabilir eylem. Raporu PR yorumu olarak yazar (her push'ta aynı yorumu günceller), ihlalde kontrolü kırmızı yapar. Sır kullanmaz; fork PR'larında yorum yerine iş özetine yazar.
- `.github/workflows/kanit-pr.yml`: `examples/acme` için örnek iş akışı (`pull_request`, izinler `contents: read`, `pull-requests: write`). Başka bir yapılandırma reposunda `uses: gokaysari/kanit/.github/actions/kanit-check@<commit>` ile kullanılır; Batfish servis kapsayıcısı ve `fetch-depth: 2` gerekir; `snapshot` repo köküne göre göreli olmalı (mutlak ya da `..` içeren yol reddedilir, çünkü yolun bileşenlerinde sembolik bağlantı ancak böyle denetlenebilir). Dış repoda eylemi bir dala değil commit SHA'ya sabitleyin; bu repoda eylem ve araç PR'ın kendi kodundan kurulduğu için kontrol PR'ın kendisi tarafından değiştirilebilir.
- `.github/workflows/kanit-plan.yml`: istekten değişiklik üreten akış. PR'a `/kanit plan <istek>` yorumu yazılınca (yalnızca sahip, üye, iş birlikçi; fork PR'ında çalışmaz) Claude önerir, Batfish varsayılan daldaki değişmezlerle doğrular, rapor PR yorumuna düşer. `ANTHROPIC_API_KEY` repo sırrı gerekir; öneri dala yazılmaz.

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

`site/` altında Next.js App Router ve TypeScript ile yazılmış, vinext (Vite) ile derlenen tanıtım sitesi; Türkçe `/`, İngilizce `/en/`.

```bash
make site         # http://localhost:3000
make site-build   # üretim derlemesi: site/dist/
```

- Metinler `site/content/tr.ts` ve `site/content/en.ts` içinde.
- Ad, alan adı, e-posta ve repo adresi yalnızca `site/site.config.ts` içinde (alan adı: netlemma.com).
- Yayın Sites (Cloudflare Workers) üzerinden; yapılandırma `site/vite.config.ts` ve `site/.openai/hosting.json`.
