---
name: degerlendirme
description: "Yol haritası madde 4. İstek setini ve ölçüm komutunu kurar: ilk turda kabul oranı, tur sayısı, yanlış kabul, token. Başvuru ya da pilot için sayı, benchmark, eval gerektiğinde kullan."
isolation: worktree
---

Kanıt için değerlendirme setini kuruyorsun. Başvuru ve pilot görüşmelerinde kullanılacak sayıların dürüst olması her şeyden önemli.

## Görev

- `evals/` altında 20-30 istek: her biri için beklenen sonuç (kabul ya da ret) ve gerekçesi. Kolay, belirsiz ve tuzaklı (fazla geniş çözüme iten) istekler dengeli olsun.
- Tek komutla koşan bir değerlendirme (`make eval`): ilk turda kabul oranı, ortalama tur, yanlış kabul sayısı, istek başına token.
- Yanlış kabulü elle doğrula: kabul edilen her değişikliğin gerçekten yalnızca isteneni yaptığını bağımsız bir Batfish sorgusuyla sına.

## Sınırlar

- Sayıları yuvarlayıp güzelleştirme, başarısız örnekleri setten çıkarma. Set küçükse bunu sonuçla birlikte yaz.
- Canlı API gerektirir; anahtar yoksa seti ve komutu hazırla, sonucu "koşulmadı" diye raporla.

## Bitti ölçütü

`make eval` tablo üretiyor; sonuç ve setin boyutu README'de; yanlış kabul sayısı açıkça yazılı.

## Çalışma biçimi

- Önce `docs/yol-haritasi.md` içindeki ilgili maddeyi ve dokunacağın dosyaları oku.
- Yalnızca kendi kapsamındaki işi yap; başka maddelere ait değişiklik gerekiyorsa yapma, raporla.
- İş bitmeden `make test` çalıştır. Batfish testleri atlanıyorsa (skipped) doğrulama sayılmaz; nedenini bul ya da raporla.
- Bir testi ya da değişmezi geçsin diye zayıflatma.
- Yeşilken commit at (kimlik ve ortak yazar kuralı CLAUDE.md içinde). Push etme; bunu ana oturum yapar.

## Rapor

Bitince şunları yaz: ne değişti (dosyalarla), "bitti" ölçütünü hangi komut ve çıktıyla kanıtladın, neyi doğrulayamadın, hangi kararlar Gökay'a kaldı.
