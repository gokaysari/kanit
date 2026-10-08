from __future__ import annotations

import json
import shutil
from pathlib import Path

from .models import FlowCheck, Proposal, ProposalError

CONFIG_DIR = "configs"
POLICY_FILE = "policy.json"


class UnsupportedLayout(ValueError):
    """Snapshot, Batfish'e giden dosya kümesini birebir bilemeyeceğimiz bir düzende."""


# Snapshot kökünde Batfish'in YÜKLEMEDİĞİ, kanit'in de izin verdiği girişler. Gerisi
# (hosts/, iptables/, batfish/ içindeki runtime_data.json ya da layer1_topology.json,
# aws_configs/, azure_configs/, sonic_configs/, checkpoint_management/, kökteki
# external_bgp_announcements.json, *_blacklist ... ve tanınmayan her şey) modeli
# değiştirebilir ama kanit Batfish'e yalnızca configs/ gönderir; bu yüzden desteklenmez.
ROOT_ALLOWED = frozenset({CONFIG_DIR, POLICY_FILE, "scripted"})
ROOT_HARMLESS_PREFIXES = ("readme", "license", "licence", "changelog")
ROOT_HARMLESS_SUFFIXES = (".md", ".rst")


def _root_entry_allowed(entry: Path) -> bool:
    name = entry.name
    if name.startswith(".") or name in ROOT_ALLOWED:
        return True
    lower = name.lower()
    return not entry.is_dir() and (
        lower.startswith(ROOT_HARMLESS_PREFIXES) or lower.endswith(ROOT_HARMLESS_SUFFIXES)
    )


def check_layout(snapshot: Path) -> None:
    """Snapshot kökünde yalnızca kanit'in Batfish'e götürdüğü (configs/) ya da Batfish'in
    yüklemediği bilinen girişler olmalı; değilse `UnsupportedLayout`.

    İzinli: `configs/`, `policy.json`, `scripted/` (kanit'in kayıtlı önerileri), adı nokta
    ile başlayan girişler (Batfish gizli girişleri atlar; .git gibi), README*/LICENSE*/
    CHANGELOG* ve .md/.rst dosyaları. Bunları Batfish'in yüklemediği
    tests/test_snapshot_batfish.py ile sabittir. Bilinmeyen her giriş kapalı yönde
    desteklenmez sayılır (yanlış "çalışmadı" üretebilir, yanlış kabul üretmez)."""
    extra = [p.name for p in sorted(snapshot.iterdir()) if not _root_entry_allowed(p)]
    if extra:
        raise UnsupportedLayout(
            f"{snapshot}: snapshot kökünde desteklenmeyen giriş: {', '.join(extra)}. kanit "
            f"Batfish'e yalnızca '{CONFIG_DIR}/' ve '{POLICY_FILE}' götürür; Batfish'in "
            "yükleyebileceği başka girişler (hosts/, batfish/, iptables/ ...) modeli "
            "değiştirebilir ve doğrulanamaz"
        )


def read_configs(snapshot: Path) -> dict[str, str]:
    """Snapshot'ta Batfish'in yükleyeceği yapılandırma dosyalarının hepsi: {ad: metin}.

    Garanti (kapsam: snapshot kökü ve `configs/`): okuma başarılıysa, Batfish'in bu
    snapshot klasöründen yükleyeceği dosya kümesi tam olarak `configs/<anahtar>`
    dosyalarıdır. İki parçası var: (1) kökte `check_layout`'un izin verdiği girişlerden
    başkası yoktur ve izinli girişlerin hiçbirini Batfish yüklemez (policy.json dahil);
    (2) `configs/` altında Batfish'in yükleyeceği her dosya okunur. Bu yüzden
    `kanit check`'in "değişti mi" kararı, rapordaki fark ve Batfish'e giden dosyalar aynı
    kümedir; okunmayan bir dosya modeli sessizce değiştiremez.

    Dayandığı Batfish davranışı (belgelenmemiş, tests/test_snapshot_batfish.py ile sabit):
    Batfish `configs/` altındaki her dosyayı uzantısına bakmadan yükler (tanımadığını
    UNKNOWN, boş dosyayı EMPTY olarak), adı nokta ile başlayan dosya ve klasörleri atlar,
    alt klasörleri ÖZYİNELEMELİ yükler. Kökteki `scripted/`, policy.json, README ve .md
    dosyalarını yüklemez; `batfish/runtime_data.json` gibi girişleri yükler.

    Kapalı yön: kökte izinsiz giriş ya da `configs/` altında gizli olmayan bir alt klasör
    görülürse `UnsupportedLayout` (doğrulama çalışmadı, çıkış 2). Alt klasör desteği
    Batfish'in özyineleme kurallarını (gizli klasörler, derinlik, yinelenen hostname)
    birebir taklit etmeyi gerektirirdi. Sembolik bağlantı ya da düzenli dosya olmayan giriş
    okunmadan ValueError verir. Gizli girişler okunmaz; Batfish de yüklemez.

    Garanti etmez: Batfish imajı bu kuralları değiştirirse eşitlik bozulur; o durumda ilk
    kalan test tests/test_snapshot_batfish.py olur.
    """
    cfg = snapshot / CONFIG_DIR
    if not cfg.is_dir():
        raise FileNotFoundError(f"{cfg} bulunamadı; snapshot '{CONFIG_DIR}/' klasörü içermeli")
    check_layout(snapshot)
    entries = [p for p in sorted(cfg.iterdir()) if not p.name.startswith(".")]
    for p in entries:
        if p.is_symlink():
            raise ValueError(f"{p} sembolik bağlantı; okunmadı")
        if p.is_dir():
            raise UnsupportedLayout(
                f"{p}: '{CONFIG_DIR}/' altında alt klasör desteklenmiyor (Batfish alt "
                "klasörleri de yükler; doğrulanan dosya kümesi bilinemez). Yapılandırma "
                f"dosyalarını doğrudan '{CONFIG_DIR}/' altına koyun"
            )
        if not p.is_file():
            raise ValueError(f"{p} düzenli bir dosya değil; okunmadı")
    return {p.name: p.read_text() for p in entries}


def read_invariants(snapshot: Path) -> list[FlowCheck]:
    path = snapshot / POLICY_FILE
    if not path.exists():
        return []
    return [FlowCheck.from_dict(d) for d in json.loads(path.read_text()).get("invariants", [])]


def apply_edits(configs: dict[str, str], proposal: Proposal) -> dict[str, str]:
    """Düzenlemeleri uygular. Her 'old' metni dosyada tam olarak bir kez geçmelidir."""
    out = dict(configs)
    for e in proposal.edits:
        if e.file not in out:
            raise ProposalError(
                f"'{e.file}' diye bir yapılandırma dosyası yok (mevcut: {', '.join(out)})"
            )
        count = out[e.file].count(e.old)
        if not e.old or count != 1:
            raise ProposalError(
                f"'{e.file}' içinde 'old' metni {count} kez geçiyor; tam olarak 1 kez geçmeli"
            )
        out[e.file] = out[e.file].replace(e.old, e.new)
    return out


def write_candidate(configs: dict[str, str], dest: Path) -> Path:
    """Batfish'in beklediği düzende (configs/) aday snapshot'ı yazar."""
    cfg = dest / CONFIG_DIR
    if cfg.exists():
        shutil.rmtree(cfg)
    cfg.mkdir(parents=True)
    for name, text in configs.items():
        if Path(name).name != name or name.startswith("."):
            raise ValueError(f"'{name}' düz bir yapılandırma dosyası adı değil")
        (cfg / name).write_text(text)
    return dest
