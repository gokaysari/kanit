# Yol haritası

Durum (Ekim 2026): döngü, kayıtlı önerilerle gerçek Batfish'e karşı uçtan uca çalışıyor ve CI'da test ediliyor. Claude'lu canlı yol hiç çalıştırılmadı. Kapsam: Cisco IOS, erişim listesi değişiklikleri, iki cihazlı örnek ağ.

Sıra önceliktir. Her maddede "bitti" ölçütü yazılı; ölçüt sağlanmadan madde kapanmaz.

## 1. Claude'lu canlı yolu çalıştır

Şu an yalnızca sahte istemciyle test ediliyor (`tests/test_unit.py`).

- `make plan` ile gerçek API'ye karşı çalıştır; çıkan hataları düzelt.
- Token kullanımını ve tur sayısını rapora ve çıktıya yaz (maliyet görünür olsun).
- API hatalarını ele al: anahtar yok, oran sınırı, aracın çağrılmaması, şemaya uymayan girdi.
- Bitti: örnek istek gerçek Claude ile kabul ediliyor; hata durumları anlaşılır mesajla bitiyor.

## 2. Niyet kontrollerini değişiklikten bağımsız üret

En önemli tasarım açığı: niyet kontrollerini de değişikliği yazan çağrı yazıyor. Model kendi değişikliğine uyan zayıf bir kontrol yazarsa doğrulama anlamsızlaşır.

- Kontrolleri ayrı bir Claude çağrısıyla, yalnızca istek ve ağ topolojisinden (değişikliği görmeden) türet.
- İstek, verilmesi gerekeni olduğu kadar verilmemesi gerekeni de içermeli: "5432 aç" için 5432 dışındaki portların kapalı kaldığı da kontrol edilmeli.
- Kontroller raporda değişiklikten önce gösterilsin.
- Bitti: `01-fazla-genis.json` önerisi, `policy.json`'daki SSH değişmezi silinse bile reddediliyor.

## 3. Yan etkileri kabul kuralına bağla

`differentialReachability` çıktısı şu an yalnızca raporda listeleniyor; kabulü etkilemiyor.

- Davranışı değişen akışları niyet kontrolleriyle eşleştir; hiçbir kontrolle açıklanamayan değişiklik reddetme sebebi olsun (ya da açık insan onayı istesin).
- Bitti: niyetin dışında bir akışı açan ya da kapatan değişiklik, ilgili değişmez tanımlı olmasa da kabul edilmiyor.

## 4. Değerlendirme seti

Başvuru ve pilot görüşmeleri için sayı gerekiyor.

- 20-30 istekten oluşan bir set: beklenen sonuç (kabul/ret) ve gerekçesiyle.
- Ölçümler: ilk turda kabul oranı, ortalama tur, yanlış kabul sayısı (sıfır olmalı), istek başına token.
- Bitti: tek komutla koşan ve tablo üreten bir değerlendirme; sonuç README'de.

## 5. Daha gerçekçi ağ ve değişiklik türleri

- Batfish'in örnek ağlarından çok cihazlı bir snapshot ekle.
- Erişim listesi dışında en az bir tür: statik rota ya da BGP politika değişikliği.
- İkinci üretici (Juniper) için en az bir uçtan uca test.
- Bitti: her yeni tür için bir kabul ve bir ret senaryosu CI'da.

## 6. Pull request botu (kapandı, Ekim 2026)

Ürünün asıl biçimi: yapılandırma reposundaki her PR'a otomatik etki raporu.

- PR'daki değişikliği aday snapshot olarak al, raporu PR yorumu olarak yaz, ihlalde kontrolü kırmızı yap.
- İstekten değişiklik üreten akış ayrı bir komut ya da etiketle tetiklensin.
- Bitti: örnek bir yapılandırma reposunda açılan PR'a rapor yorumu düşüyor.
- Kanıt (denetçi onaylı): deneme PR #1'de ihlalli commit'te `etki-raporu` kırmızı ve gerçek Batfish karşı örnekli rapor yorumu düştü; dar kuralla aynı yorum güncellendi ve kontrol yeşile döndü. Bileşenler: `kanit check` (model çağrısız doğrulama; değişmezler hedef daldan, değişmez silen ya da gevşeten PR reddedilir, sembolik bağlantı ve `..` içeren yollar reddedilir), `.github/actions/kanit-check`, `kanit-pr.yml`, `/kanit plan` yorum komutu (`kanit-plan.yml`, canlı Claude'la henüz koşmadı; madde 1'e bağlı).
- Açık kararlar (Gökay): değişmez silmek için istisna yolu (etiket / CODEOWNERS / ayrı PR türü); fork PR'larına yorum; plan akışı commit atsın mı; dış repolarda eylemi SHA'ya sabitleme yönergesi; Marketplace.
- Not: bu repoda deneme PR'ları `examples/acme`'yi değiştirince testlerin fikstürü bozulur; deneme için ayrı bir örnek ağ gerekir (madde 5).

## 7. Sağlamlık

- Batfish'e ulaşılamadığında anlaşılır hata (şu an ham istisna).
- Mevcut snapshot her turda yeniden yükleniyor; bir kez yükle.
- Yapılandırma içine gömülü talimatlara karşı test (ör. `description` satırında "ignore previous instructions").
- `ruff` ve tip denetimi CI'a eklensin.
- Makine tarafından okunabilir çıktı (`--json`).

## 8. Site ve yayın (karar Gökay'da)

- Ürün adı, alan adı, e-posta: `site/site.config.ts` içinde hâlâ yer tutucu. "Demo isteyin" düğmesi geçersiz adrese gidiyor.
- Yayın yeri (Vercel vb.), lisans dosyası, kısa demo videosu.
- Bitti: site alan adında yayında, iletişim adresi çalışıyor.
- Yapıldı (Ekim 2026, denetçi onaylı): paylaşım görseli (TR/EN, gerçek Batfish kaydından), demo kaydı için yer tutucu (`site.config.ts` → `demoVideo`), iki dilli 404 sayfası (Next `experimental.globalNotFound`), erişilebilirlik düzeltmeleri (axe 0 ihlal, 1280/390/320 px). Madde açık: kalanların hepsi yukarıdaki kararlara bağlı.

## Bilinen küçük eksikler

- `--apply` git ile bütünleşik değil.
- `examples/acme` ağında uç cihazlar modellenmiyor; başarı `DELIVERED_TO_SUBNET` olarak görünüyor.
- `.github/annotate.py`, iş günlüğüne erişilemeyen ortamlar için eklendi; günlükler okunabiliyorsa kaldırılabilir.
