// Örnek ağdaki erişim listesi ve Batfish'in CI koşusunda ürettiği gerçek karşı örnek.
export const ACL_BEFORE = [
  "ip access-list extended SERVERS-OUT",
  " permit tcp 10.10.10.0 0.0.0.255 host 10.20.20.10 eq 443",
  " permit tcp 10.10.10.0 0.0.0.255 host 10.20.20.20 eq 22",
];
export const ACL_AFTER = [" deny ip any any"];

export const BROAD_LINE = "+permit ip 10.10.10.0 0.0.0.255 host 10.20.20.30";
export const NARROW_LINE = "+permit tcp 10.10.10.0 0.0.0.255 host 10.20.20.30 eq 5432";
export const COUNTEREXAMPLE =
  "10.10.10.0:49152 → 10.20.20.30:22 TCP (SYN) => DELIVERED_TO_SUBNET";
