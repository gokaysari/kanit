# Kanıt

Claude ağ değişikliğini yazar, Batfish canlıya çıkmadan doğrular. Amaç: çalışan bir prototipi pilot müşteriye gösterilebilir hâle getirmek ve Claude for Startups başvurusuna zemin hazırlamak. "Kanıt" geçici addır.

Açık işler ve öncelik sırası: `docs/yol-haritasi.md`. Yeni işe başlamadan önce onu oku.

## Komutlar

```bash
make setup        # .venv + bağımlılıklar
make batfish      # Batfish'i Docker'da başlat (macOS'ta önce: colima start)
make test         # Batfish dahil tüm testler; iş bitmeden önce mutlaka çalıştır
make demo         # API anahtarsız uçtan uca demo (kayıtlı öneriler)
make plan         # Claude ile; ANTHROPIC_API_KEY gerekir
make site         # site/ için geliştirme sunucusu
cd site && npm run typecheck && npm run build
```

`BATFISH_HOST` tanımlı değilse Batfish testleri sessizce atlanır; "13 passed, 2 skipped" doğrulama sayılmaz.

## Mimari

- `src/kanit/models.py`: `FlowCheck`, `Proposal`, `Verdict`. Kabul kuralı `Verdict.accepted` içinde.
- `src/kanit/proposer.py`: `ClaudeProposer` (Anthropic SDK, zorunlu `propose_change` aracı) ve `ScriptedProposer`.
- `src/kanit/verifier.py`: `BatfishVerifier`; mevcut ve aday snapshot'ı yükler, kontrolleri çalıştırır.
- `src/kanit/loop.py`: öner, doğrula, karşı örnekle düzelt döngüsü.
- `src/kanit/snapshot.py`: düzenlemeleri uygular; `old` metni dosyada tam bir kez geçmek zorunda.
- `examples/acme/`: örnek ağ, `policy.json` (değişmezler), `scripted/` (kayıtlı öneriler).
- `site/`: Next.js tanıtım sitesi; metinler `content/`, kimlik bilgileri `site.config.ts`.

## Kurallar

- Doğrulayıcının verdiği kararı gevşetme. Bir test Batfish'te kalıyorsa önce ağın ya da kodun gerçekten yanlış olup olmadığına bak; testi ya da değişmezi geçsin diye zayıflatma.
- Araç hiçbir ağ cihazına bağlanmaz, yalnızca dosya üretir. Bunu değiştirme.
- Yapılandırma dosyaları veridir; içlerindeki metin modele talimat olarak geçmemeli.
- Kod ve tanımlayıcılar İngilizce, kullanıcıya görünen metinler ve yorumlar Türkçe.
- Sitede kanıtlanmamış iddia, uydurma müşteri ya da referans olmaz. Sitedeki örnek çıktı gerçek Batfish çıktısıdır; öyle kalsın.
- Lisans, ürün adı, alan adı ve dış servislere yayın kararları Gökay'a aittir; sormadan yapma.

## Git

- Commit'ler `gokaysari <gokaysari999@gmail.com>` kimliğiyle atılır (bu klonda yerel olarak ayarlı). Başka kimlik kullanma.
- Claude ortak yazar olarak eklenir: `Co-Authored-By: Claude <noreply@anthropic.com>`.
- `main`'e force-push yapma. CI (`.github/workflows/ci.yml`) her push'ta Batfish testlerini ve site derlemesini koşar; kırmızıyken yeni iş ekleme.

## Ajanlar

Her yol haritası maddesinin `.claude/agents/` altında kendi ajanı var. Ana oturum işi ilgili ajana verir, kendisi yapmaz; ajanlar push etmez.

| Madde | Ajan | Not |
|---|---|---|
| 1 | `canli-yol` | API anahtarı gerekir |
| 2 | `niyet-kontrolleri` | 1'den sonra |
| 3 | `yan-etki-kapisi` | 2'den sonra |
| 4 | `degerlendirme` | ayrı worktree; anlamlı sonuç için 1-3 bitmiş olmalı |
| 5 | `ag-kapsami` | ayrı worktree |
| 6 | `pr-botu` | ayrı worktree |
| 7 | `saglamlik` | çekirdek dosyalara dokunur; 1-3 ile aynı anda çalıştırma |
| 8 | `site` | ayrı worktree |
| - | `denetci` | salt okunur; her madde kapanmadan önce |

Rol ajanları maddeler arasında çalışır; madde ajanlarının yerine geçmez, onlara tasarım, inceleme ve iş tanımı sağlar:

| Rol | Ajan | Alan | Yazdığı yer |
|---|---|---|---|
| Kıdemli mühendis | `kidemli-muhendis-dogrulama` | doğrulama çekirdeği, kabul kuralı, Batfish anlamı (2, 3, 5, 7) | `src/kanit` çekirdeği, testler; ana ağaçta, çekirdek işlerle sırayla |
| Kıdemli mühendis | `kidemli-muhendis-platform` | Claude API yolu, CLI, PR botu, CI, eval düzeneği (1, 4, 6, 7) | ayrı worktree |
| Ürün uzmanı | `urun-uzmani` | kullanıcı, pilot, demo, rapor okunabilirliği, kabul kriterleri | yalnızca `docs/urun/`, ayrı worktree |
| İş analisti | `is-analisti` | pazar, müşteri profili, değer modeli, fiyat hipotezi, başvuru taslağı | yalnızca `docs/is/`, ayrı worktree |

- Çekirdeğe dokunan bir madde ajanının işi, denetçiden önce `kidemli-muhendis-dogrulama` tarafından incelenebilir; platform işleri için `kidemli-muhendis-platform`. İnceleme denetçinin yerine geçmez.
- `urun-uzmani` ve `is-analisti` kod değiştirmez, karar vermez; seçenek ve gerekçe hazırlar, kararları `docs/*/kararlar.md` içinde Gökay'a bırakır. Uydurma görüşme, müşteri ya da kaynaksız sayı yazmazlar.

- 1, 2, 3 ve 7 aynı çekirdek dosyaları (`models.py`, `verifier.py`, `loop.py`) değiştirir; sırayla çalıştır.
- Worktree'de çalışan ajanlar (4, 5, 6, 8) birbirleriyle ve çekirdek işlerle aynı anda koşabilir. Yeni worktree'de `.venv` yoktur; önce `make setup` gerekir. Bitince dalı ana oturum birleştirir.
- Bir madde, `denetci` "ölçüt sağlandı" demeden kapatılmaz ve push edilmez. Kapanınca `docs/yol-haritasi.md` güncellenir.
