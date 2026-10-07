import { BROAD_LINE, COUNTEREXAMPLE, NARROW_LINE } from "./record";
import type { Dictionary } from "./types";

const checks = {
  db: "Kullanıcılar veritabanına tcp/5432 ile erişir",
  internet: "Internet sunucu ağına erişemez",
  ssh: "Kullanıcılar veritabanı sunucusuna SSH yapamaz",
};

export const tr: Dictionary = {
  lang: "tr",
  otherLang: { label: "English", href: "/en/" },
  meta: {
    title: "NetLemma: doğrulanmış ağ değişiklikleri",
    description:
      "Claude ağ değişikliğini yazar, Batfish canlıya çıkmadan önce biçimsel olarak doğrular.",
  },
  og: {
    alt: "NetLemma: ağ değişikliğini canlıya çıkmadan kanıtlayın. Örnek kayıtta dar erişim listesi satırı Batfish doğrulamasından geçip kabul ediliyor.",
    label: "Örnek değişiklik kaydı, tur 2",
  },
  skipLink: "İçeriğe geç",
  nav: { label: "Sayfa bölümleri", how: "Nasıl çalışır", demo: "Demo", limits: "Sınırlar" },
  hero: {
    title: "Ağ değişikliğini canlıya çıkmadan kanıtlayın.",
    lede: "Ne istediğinizi düz dille yazın. Claude yapılandırma değişikliğini üretir, Batfish ağınızın modelinde doğrular. Önünüze yalnızca doğrulamadan geçen değişiklik gelir.",
    cta: "Demo isteyin",
    status: "Erken prototip. Şu an Cisco IOS erişim listeleri için çalışıyor.",
  },
  record: {
    label: "Örnek değişiklik kaydı",
    requestLabel: "Değişiklik isteği",
    request: "Kullanıcı ağından veritabanı sunucusuna (10.20.20.30) tcp/5432 aç.",
    proved: "kanıtlandı",
    violated: "ihlal",
    counterexample: "Karşı örnek",
    tablistLabel: "Doğrulama turları",
    diffLabel: "Erişim listesindeki değişiklik",
    rounds: [
      {
        tab: "Tur 1",
        verdict: "Ret",
        accepted: false,
        addedLine: BROAD_LINE,
        checks: [
          { label: checks.db, passed: true },
          { label: checks.internet, passed: true },
          { label: checks.ssh, passed: false, counterexample: COUNTEREXAMPLE },
        ],
        stamp: "RET",
      },
      {
        tab: "Tur 2",
        verdict: "Kabul",
        accepted: true,
        addedLine: NARROW_LINE,
        checks: [
          { label: checks.db, passed: true },
          { label: checks.internet, passed: true },
          { label: checks.ssh, passed: true },
        ],
        stamp: "KABUL",
      },
    ],
  },
  how: {
    title: "Nasıl çalışır",
    steps: [
      {
        title: "Claude değişikliği yazar",
        body: "Mevcut yapılandırmaları ve kurallarınızı okur, isteği karşılayan en dar değişikliği ve bunu kanıtlayacak akış kontrollerini üretir.",
      },
      {
        title: "Batfish doğrular",
        body: "Değişiklik ağın modeline uygulanır. Her kontrol tek tek paketlerle değil, tüm akış kümesi üzerinde sınanır; bozulan bir şey varsa somut bir karşı örnek çıkar.",
      },
      {
        title: "Karşı örnek geri döner",
        body: "Reddedilen öneri gerekçesiyle Claude'a geri verilir ve düzeltilir. Hiçbir öneri geçemezse yapılandırmaya dokunulmaz.",
      },
    ],
  },
  demo: {
    title: "Kısa demo",
    placeholder: "Demo kaydı henüz hazır değil.",
    body: "Kayıt eklenene kadar aynı akışı kendi makinenizde çalıştırabilirsiniz: fazla geniş öneri karşı örnekle reddedilir, dar olan kabul edilir. Docker ve Python yeterli, API anahtarı gerekmez.",
    commandLabel: "Komut",
    setupLink: "Kurulum adımları",
    requestBody: "Kayıt eklenene kadar aynı akışı sizin için canlı çalıştırabiliriz: fazla geniş öneri karşı örnekle reddedilir, dar olan kabul edilir.",
    requestLink: "Canlı gösterim isteyin",
  },
  proves: {
    title: "Neyi kanıtlar",
    items: [
      "İsteğin gerektirdiği akışların tamamının ulaştığını ya da engellendiğini.",
      "Tanımladığınız değişmez kuralların değişiklikten sonra da geçerli olduğunu.",
      "Değişikliğin yeni ayrıştırma hatası ya da tanımsız referans getirmediğini.",
      "Ayrıca davranışı değişen örnek akışları, öncesi ve sonrasıyla listeler.",
    ],
  },
  limits: {
    title: "Neyi kanıtlamaz",
    items: [
      "Yazmadığınız bir kuralı bilemez. Koruma, tanımladığınız değişmezler kadar güçlüdür.",
      "Batfish'in modellemediği cihaz ve özellikler kapsam dışıdır.",
      "Model yapılandırmadan kurulur; donanım arızası ya da yazılım hatası gibi çalışma anı sorunlarını görmez.",
      "Son onay insandadır. Araç değişikliği cihaza kendisi uygulamaz.",
    ],
  },
  closing: {
    title: "Kendi ağınızda deneyin",
    body: "Doğrulama kendi makinenizde çalışan Batfish üzerinde yapılır; araç hiçbir cihaza bağlanmaz. Değişikliği Claude'a yazdırırsanız yapılandırmalarınız Anthropic API'sine gönderilir. İlk pilot kurumları arıyoruz.",
    cta: "Pilot için yazın",
  },
  footer: { builtOn: "Açık kaynak", and: "ve Claude üzerine kuruludur.", source: "Kaynak kod" },
  notFound: {
    title: "Sayfa bulunamadı",
    body: "Aradığınız adres bu sitede yok.",
    home: "Ana sayfaya dönün",
  },
};
