---
name: niyet-kontrolleri
description: "Yol haritası madde 2. Niyet kontrollerini değişikliği yazan çağrıdan bağımsız üretir. Doğrulamanın döngüselliği, intent_checks, zayıf ya da eksik kontrol konularında kullan."
---

Kanıt'ın en önemli tasarım açığını kapatıyorsun: niyet kontrollerini şu an değişikliği yazan çağrı yazıyor, yani model kendi değişikliğine uyan zayıf bir kontrol yazabilir.

## Görev

- Kontrolleri ayrı bir adımda, yalnızca istekten ve ağdan (aday değişikliği görmeden) türet. Değişikliği yazan çağrı kontrolleri değiştiremesin.
- Kontroller isteğin verdiğini olduğu kadar vermediğini de kapsasın: "5432 aç" için 5432 dışındaki portların kapalı kaldığı da sınanmalı.
- Raporda kontroller değişiklikten önce gösterilsin.
- `ScriptedProposer` ve mevcut testler yeni akışla çalışmaya devam etsin; kayıtlı öneri biçimi değişiyorsa `examples/acme/scripted/` dosyalarını güncelle.

## Bitti ölçütü

`examples/acme/policy.json` içinden SSH değişmezi çıkarıldığında bile `01-fazla-genis.json` önerisi gerçek Batfish'te reddediliyor. Bunu kalıcı bir entegrasyon testiyle göster (policy dosyasını bozmadan, testte geçici kopyayla).

## Çalışma biçimi

- Önce `docs/yol-haritasi.md` içindeki ilgili maddeyi ve dokunacağın dosyaları oku.
- Yalnızca kendi kapsamındaki işi yap; başka maddelere ait değişiklik gerekiyorsa yapma, raporla.
- İş bitmeden `make test` çalıştır. Batfish testleri atlanıyorsa (skipped) doğrulama sayılmaz; nedenini bul ya da raporla.
- Bir testi ya da değişmezi geçsin diye zayıflatma.
- Yeşilken commit at (kimlik ve ortak yazar kuralı CLAUDE.md içinde). Push etme; bunu ana oturum yapar.

## Rapor

Bitince şunları yaz: ne değişti (dosyalarla), "bitti" ölçütünü hangi komut ve çıktıyla kanıtladın, neyi doğrulayamadın, hangi kararlar Gökay'a kaldı.
