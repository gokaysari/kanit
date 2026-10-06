---
name: yan-etki-kapisi
description: "Yol haritası madde 3. differentialReachability çıktısını kabul kuralına bağlar; niyetle açıklanamayan davranış değişikliğini reddettirir. Yan etki, blast radius, changed_flows konularında kullan. Madde 2 bittikten sonra çalıştır."
---

Şu an davranışı değişen akışlar yalnızca raporda listeleniyor; kabul kararını etkilemiyor. Bunu değiştiriyorsun (`verifier.py`, `models.py`, `report.py`).

## Görev

- Davranışı değişen akışları niyet kontrolleriyle eşleştir. Hiçbir kontrolün kapsamadığı değişiklik "açıklanamayan yan etki" sayılsın ve öneriyi reddettirsin.
- Batfish'in fark sorgusu örnek akış döndürür, tüm kümeyi değil. Eşleştirmeyi örneklere güvenerek yapma; niyet kapsamının dışındaki başlık uzayı için ayrı sorgu kur ve yaklaşımın neyi garanti ettiğini, neyi etmediğini koda ve rapora yaz.
- Ret gerekçesi modele geri verilen metne de girsin.

## Bitti ölçütü

Niyetin dışında bir akışı açan ya da kapatan öneri, ilgili değişmez tanımlı olmasa da gerçek Batfish'te reddediliyor; dar ve doğru öneri hâlâ kabul ediliyor. İkisi de entegrasyon testinde.

## Çalışma biçimi

- Önce `docs/yol-haritasi.md` içindeki ilgili maddeyi ve dokunacağın dosyaları oku.
- Yalnızca kendi kapsamındaki işi yap; başka maddelere ait değişiklik gerekiyorsa yapma, raporla.
- İş bitmeden `make test` çalıştır. Batfish testleri atlanıyorsa (skipped) doğrulama sayılmaz; nedenini bul ya da raporla.
- Bir testi ya da değişmezi geçsin diye zayıflatma.
- Yeşilken commit at (kimlik ve ortak yazar kuralı CLAUDE.md içinde). Push etme; bunu ana oturum yapar.

## Rapor

Bitince şunları yaz: ne değişti (dosyalarla), "bitti" ölçütünü hangi komut ve çıktıyla kanıtladın, neyi doğrulayamadın, hangi kararlar Gökay'a kaldı.
