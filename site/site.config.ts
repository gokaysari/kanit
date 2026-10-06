// Ad, alan adı ve iletişim bilgileri yalnızca burada tanımlıdır.
// "Kanıt" geçici addır; değiştirmek için bu dosya yeterli.
export const site = {
  name: "Kanıt",
  url: "https://ORNEK-ALAN-ADI.com", // TODO: alan adı alınınca değiştir
  email: "merhaba@ORNEK-ALAN-ADI.com", // TODO: alan adı alınınca değiştir
  repo: "https://github.com/gokaysari/kanit",
  batfish: "https://github.com/batfish/batfish",
  // Kısa demo kaydının adresi (ör. "/demo.mp4"). Kayıt yokken null kalır; sitede dürüst bir yer tutucu görünür.
  demoVideo: null as string | null,
} as const;
