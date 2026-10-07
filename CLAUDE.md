# NetLemma (kod adı: kanit)

Claude ağ değişikliğini yazar, Batfish canlıya çıkmadan doğrular. Amaç: çalışan bir prototipi pilot müşteriye gösterilebilir hâle getirmek ve Claude for Startups başvurusuna zemin hazırlamak. Ürün ve şirket adı NetLemma'dır (netlemma.com); komut satırı aracı, Python paketi ve repo şimdilik `kanit` adını taşır.

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
- `src/kanit/proposer.py`: `ClaudeProposer` (Anthropic SDK; `propose_change` aracı `tool_choice: auto` + `strict`, çünkü varsayılan model zorunlu araç seçimini 400 ile reddeder) ve `ScriptedProposer`.
- `src/kanit/verifier.py`: `BatfishVerifier`; mevcut ve aday snapshot'ı yükler, kontrolleri çalıştırır. Önceden var olan ihlal yalnızca genişlemediği kanıtlanırsa kabulü engellemez (`_classify_preexisting`).
- `src/kanit/loop.py`: öner, doğrula, karşı örnekle düzelt döngüsü.
- `src/kanit/snapshot.py`: düzenlemeleri uygular; `old` metni dosyada tam bir kez geçmek zorunda.
- `src/kanit/review.py`: `kanit check`, model çağrısı olmadan PR doğrulaması; `.github/actions/kanit-check` ve `kanit-pr.yml` bunu PR yorumu olarak yazar.
- Çıkış kodu sözleşmesi: 0 kabul, 1 ret, 2 doğrulama çalışmadı.
- `examples/acme/`: örnek ağ, `policy.json` (değişmezler), `scripted/` (kayıtlı öneriler).
- `site/`: Next.js App Router tanıtım sitesi, vinext ile Cloudflare Workers'a (OpenAI Sites) derlenir; çalışma anında dosya sistemi yoktur. Metinler `content/`, kimlik bilgileri `site.config.ts`. Yayını Gökay Sites üzerinden yapar.

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
- `main` korumalı: force-push ve silme yasak, `test` ve `site` kontrolleri zorunlu. Değişiklikler main'e PR üzerinden, CI yeşilken girer. CI (`.github/workflows/ci.yml`) Batfish testlerini ve site derlemesini koşar; kırmızıyken yeni iş ekleme.

## Ajanlar ve iş akışları

Ana oturum orkestratördür: işi ilgili ajana verir, kendisi yapmaz (Gökay aksini söylemedikçe). Ajanlar yol haritası maddelerine değil iş akışlarına göre tanımlıdır; her biri işini uçtan uca yürütür (hazırlık, yeniden üretme, uygulama, gerçek Batfish/derleme ile kanıt, öz denetim, commit, rapor) ve push etmez.

| İş akışı | Ajan | Yazdığı yer | Yol haritası |
|---|---|---|---|
| Doğrulama çekirdeği | `dogrulama-muhendisi` | `verifier.py`, `models.py`, `loop.py`, `snapshot.py`, `examples/` | 2 (doğrulama), 3, 5, 7 (çekirdek) |
| Claude ile değişiklik üretme | `model-muhendisi` | `proposer.py`, canlı testler | 1, 2 (model tarafı) |
| Platform ve teslim | `platform-muhendisi` | `cli.py`, `report.py`, `review.py`, `.github/`, `Makefile`, `pyproject.toml` | 6, 7 (platform) |
| Değerlendirme | `degerlendirme` | `evals/`, `make eval` | 4 |
| Site ve demo | `site` | `site/` | 8 |
| Ürün | `urun-uzmani` | yalnızca `docs/urun/` | kabul kriterleri, pilot, demo senaryosu |
| İş | `is-analisti` | yalnızca `docs/is/` | başvuru, pazar, riskler |
| Denetim | `denetci` | hiçbir dosya (salt okunur) | her iş birleşmeden önce |

Teslim akışı (her iş için):

1. Ana oturum işi ve bitti ölçütünü yazıp ajana verir. Yazan ajanların hepsi ayrı worktree'de, `origin/main`'den başlar.
2. Ajan uçtan uca çalışır, commit atar, raporlar.
3. `denetci` bağımsız denetler. "Ölçüt sağlanmadı" ise bulgular aynı ajana döner; bu, denetçi onaylayana kadar tekrarlanır.
4. Ana oturum dalı push eder, PR açar, CI yeşilse birleştirir, main CI'ını kontrol eder, `docs/yol-haritasi.md`'yi günceller.

Kurallar:

- Çekirdek dosyalara (`models.py`, `verifier.py`, `loop.py`) aynı anda yalnızca bir iş dokunur. Diğer akışlar paralel koşabilir.
- Worktree'lerde önce `make setup`; testler `COMPOSE_PROJECT_NAME=kanit make test` ile koşulur (mevcut Batfish kapsayıcısını kullanır, port çakışmaz).
- Ücretli API çağrıları (canlı test, değerlendirme) ana oturumun onayıyla yapılır. API anahtarı yalnızca macOS Anahtar Zinciri'nden (`kanit-anthropic`) komut anında okunur; dosyaya yazılmaz.
- Denetlenmemiş araştırma `arastirma/*` dallarında durur (`dogrulama`, `platform`, `urun`, `is`); kullanılmadan önce `denetci` kaynaklarını sınar.
- Bir madde, `denetci` "ölçüt sağlandı" demeden kapatılmaz ve main'e girmez.
