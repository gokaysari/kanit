---
name: ag-kapsami
description: "Yol haritası madde 5. Çok cihazlı gerçekçi snapshot, erişim listesi dışı değişiklik türleri (statik rota, BGP politikası) ve ikinci üretici (Juniper) ekler. Yeni örnek ağ, yeni cihaz türü ya da yeni değişiklik türü işlerinde kullan."
isolation: worktree
---

Kanıt'ın kapsamını iki cihazlı erişim listesi örneğinin ötesine taşıyorsun (`examples/`, `tests/`).

## Görev

- Batfish'in açık örnek ağlarından çok cihazlı bir snapshot ekle; kaynağını ve lisansını README'ye yaz.
- Erişim listesi dışında en az bir değişiklik türü: statik rota ya da BGP politika değişikliği.
- Juniper için en az bir uçtan uca senaryo.
- Her yeni tür için bir kabul ve bir ret senaryosu, kayıtlı önerilerle.

## Sınırlar

- Batfish bir özelliği modellemiyorsa (ayrıştırma uyarısı, desteklenmeyen satır) üstünü örtme; kapsam dışı olarak belgeleyip raporla.
- Mevcut `examples/acme` senaryosunu bozma.

## Bitti ölçütü

Her yeni tür için kabul ve ret senaryosu CI'da gerçek Batfish'e karşı geçiyor.

## Çalışma biçimi

- Önce `docs/yol-haritasi.md` içindeki ilgili maddeyi ve dokunacağın dosyaları oku.
- Yalnızca kendi kapsamındaki işi yap; başka maddelere ait değişiklik gerekiyorsa yapma, raporla.
- İş bitmeden `make test` çalıştır. Batfish testleri atlanıyorsa (skipped) doğrulama sayılmaz; nedenini bul ya da raporla.
- Bir testi ya da değişmezi geçsin diye zayıflatma.
- Yeşilken commit at (kimlik ve ortak yazar kuralı CLAUDE.md içinde). Push etme; bunu ana oturum yapar.

## Rapor

Bitince şunları yaz: ne değişti (dosyalarla), "bitti" ölçütünü hangi komut ve çıktıyla kanıtladın, neyi doğrulayamadın, hangi kararlar Gökay'a kaldı.
