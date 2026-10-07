import { BROAD_LINE, COUNTEREXAMPLE, NARROW_LINE } from "./record";
import type { Dictionary } from "./types";

// Kontrol adları examples/acme/policy.json ve kayıtlı önerilerdeki adlarla aynıdır.
const checks = {
  web: "Kullanıcılar web sunucusuna HTTPS ile erişir",
  db: "Kullanıcılar veritabanına tcp/5432 ile erişir",
  internet: "Internet sunucu ağına hiçbir şekilde erişemez",
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
  nav: { label: "Sayfa bölümleri", record: "Örnek kayıt", how: "Nasıl çalışır", demo: "Demo", limits: "Sınırlar" },
  labels: {
    eyebrow: "Doğrulanmış ağ değişiklikleri",
    process: "Süreç / 03 adım",
    fieldRepo: "Sahada çalıştır",
    fieldLive: "Gerçek make demo çıktısı",
    scope: "Kanıtın sınırı",
    chapter: "Bölüm",
    availability: "Pilot erişimi açık",
  },
  hero: {
    title: "Ağ değişikliğini canlıya çıkmadan kanıtlayın.",
    lede: "Ne istediğinizi düz dille yazın. Claude yapılandırma değişikliğini üretir, Batfish ağınızın modelinde doğrular. Önünüze yalnızca doğrulamadan geçen değişiklik gelir.",
    cta: "Demo isteyin",
    status: "Erken prototip. Şu an Cisco IOS erişim listeleri için çalışıyor.",
  },
  record: {
    label: "Örnek değişiklik kaydı",
    title: "Örnek değişiklik kaydı",
    provenance:
      "Gerçek Batfish çıktısı, kayıtlı önerilerle: iki öneri elle yazılıp kaydedildi (--scripted), bu kayıtta model çağrılmadı.",
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
          { label: checks.web, passed: true },
          { label: checks.internet, passed: true },
          { label: checks.ssh, passed: false, counterexample: COUNTEREXAMPLE },
          { label: checks.db, passed: true },
        ],
        stamp: "RET",
      },
      {
        tab: "Tur 2",
        verdict: "Kabul",
        accepted: true,
        addedLine: NARROW_LINE,
        checks: [
          { label: checks.web, passed: true },
          { label: checks.internet, passed: true },
          { label: checks.ssh, passed: true },
          { label: checks.db, passed: true },
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
        body: "Mevcut yapılandırmaları ve kurallarınızı okur; isteği karşılayan en dar değişikliği hedefleyen bir öneri ve isteğin karşılandığını sınayacak akış kontrolleri yazar.",
      },
      {
        title: "Batfish doğrular",
        body: "Değişiklik ağın modeline uygulanır. Her kontrol tek tek paketlerle değil, tüm akış kümesi üzerinde sınanır; bozulan bir şey varsa somut bir karşı örnek çıkar.",
      },
      {
        title: "Karşı örnek geri döner",
        body: "Reddedilen öneri, karşı örnekle birlikte Claude'a geri verilir ve düzeltmesi istenir; en çok üç tur. Hiçbir öneri geçemezse yapılandırmaya dokunulmaz.",
      },
    ],
  },
  demo: {
    title: "Kısa demo",
    placeholder: "Demo kaydı henüz hazır değil.",
    body: "Aynı akışı kendi makinenizde çalıştırabilirsiniz: fazla geniş öneri karşı örnekle reddedilir, dar olan kabul edilir. Docker ve Python yeterli, API anahtarı gerekmez.",
    commandLabel: "Komut",
    setupLink: "Kurulum adımları",
    requestBody: "Aynı akışı sizin için canlı da çalıştırabiliriz: fazla geniş öneri karşı örnekle reddedilir, dar olan kabul edilir.",
    requestLink: "Canlı gösterim isteyin",
    videoNote:
      "Kayıt, gerçek make demo çıktısıdır: Batfish gerçek, iki öneri ise kayıtlıdır (--scripted), model çağrılmaz. Bekleme ve doğrulama süreleri gerçek zamanlıdır.",
    videoFallback: "Video bu tarayıcıda açılamadı (WebM biçimi).",
    videoDownload: "Videoyu indirin",
  },
  proves: {
    title: "Neyi kanıtlar",
    items: [
      "Önerinin kendi akış kontrollerinin (niyet kontrolleri) sağlandığını; her kontrol, tanımladığı akış kümesinin tamamında sınanır.",
      "Tanımladığınız değişmez kuralların değişiklikten sonra da geçerli olduğunu.",
      "Değişikliğin yeni ayrıştırma hatası ya da tanımsız referans getirmediğini.",
      "Ayrıca davranışı değişen örnek akışları, öncesi ve sonrasıyla listeler.",
    ],
  },
  limits: {
    title: "Neyi kanıtlamaz",
    items: [
      "Niyet kontrollerini şu an değişikliği öneren model yazar; isteğin tamamını kapsadıkları ayrıca kanıtlanmaz.",
      "Yazmadığınız bir kuralı bilemez. Koruma, tanımladığınız değişmezler kadar güçlüdür.",
      "Batfish'in modellemediği cihaz ve özellikler kapsam dışıdır.",
      "Model yapılandırmadan kurulur; donanım arızası ya da yazılım hatası gibi çalışma anı sorunlarını görmez.",
      "Son onay insandadır. Araç değişikliği cihaza kendisi uygulamaz.",
    ],
  },
  closing: {
    title: "Kendi ağınızda deneyin",
    body: "Doğrulama Batfish'te, model çağrısı olmadan yapılır: yerelde kendi makinenizde, PR botunda CI'da (GitHub runner). Değişikliği Claude'a yazdırırsanız (kanit plan ya da PR'da /kanit plan) yapılandırmalarınız Anthropic API'sine gönderilir. Araç hiçbir cihaza bağlanmaz. İlk pilot kurumları arıyoruz.",
    cta: "Pilot için yazın",
    mailSubject: "iletişim",
  },
  footer: { builtOn: "Açık kaynak", and: "ve Claude üzerine kuruludur.", source: "Kaynak kod" },
  notFound: {
    title: "Sayfa bulunamadı",
    body: "Aradığınız adres bu sitede yok.",
    home: "Ana sayfaya dönün",
  },
};
