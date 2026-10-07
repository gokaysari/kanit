// Ad, alan adı ve iletişim bilgileri yalnızca burada tanımlıdır.
// Ürün ve şirket adı NetLemma'dır; değiştirmek için bu dosya yeterli.
export const site = {
  name: "NetLemma",
  url: "https://netlemma.com",
  email: "gokay@netlemma.com",
  // Kaynak kod reposu private; herkese açılırsa adresi buraya yaz, bağlantılar kendiliğinden görünür.
  repo: null as string | null,
  batfish: "https://github.com/batfish/batfish",
  // Kısa demo kaydının adresi (ör. "/demo.mp4"). Kayıt yokken null kalır; sitede dürüst bir yer tutucu görünür.
  demoVideo: null as string | null,
} as const;
