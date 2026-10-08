// Ad, alan adı ve iletişim bilgileri yalnızca burada tanımlıdır.
// Ürün ve şirket adı NetLemma'dır; değiştirmek için bu dosya yeterli.
export const site = {
  name: "NetLemma",
  url: "https://netlemma.com",
  email: "gokay@netlemma.com",
  // Kaynak kod reposu private; herkese açılırsa adresi buraya yaz, bağlantılar kendiliğinden görünür.
  repo: null as string | null,
  batfish: "https://github.com/batfish/batfish",
  // Kısa demo kaydı (gerçek `make demo` çıktısı). null olursa sitede dürüst bir yer tutucu görünür.
  // Dosyalar site/public/ altında: video, kapak görseli ve dile göre altyazı.
  demoVideo: "/demo.webm" as string | null,
  // H.264 MP4 sürümü (iOS Safari için). Eklenirse <source> listesinde WebM'den önce gelir.
  demoVideoMp4: null as string | null,
  demoPoster: "/demo-poster.png",
  demoCaptions: { tr: "/demo.tr.vtt", en: "/demo.en.vtt" },
} as const;
