from __future__ import annotations

import json
import shutil
from pathlib import Path

from .models import FlowCheck, Proposal, ProposalError

CONFIG_DIR = "configs"
POLICY_FILE = "policy.json"


class UnsupportedLayout(ValueError):
    """Snapshot, Batfish'e giden dosya kümesini birebir bilemeyeceğimiz bir düzende."""


def read_configs(snapshot: Path) -> dict[str, str]:
    """`configs/` altında Batfish'in yükleyeceği dosyaların hepsi: {dosya adı: metin}.

    Garanti: dönen anahtar kümesi, Batfish'in aynı `configs/` klasöründen yüklediği dosya
    kümesine birebir eşittir. Bu yüzden `kanit check`'in "değişti mi" kararı, rapordaki
    fark ve Batfish'e giden dosyalar aynı kümedir; okunmayan bir dosya modeli sessizce
    değiştiremez.

    Dayandığı Batfish davranışı (belgelenmemiş, tests/test_snapshot_batfish.py ile sabit):
    Batfish `configs/` altındaki her dosyayı uzantısına bakmadan yükler (tanımadığını
    UNKNOWN, boş dosyayı EMPTY olarak), adı nokta ile başlayan dosya ve klasörleri atlar,
    alt klasörleri ÖZYİNELEMELİ yükler.

    Kapalı yön: gizli olmayan bir alt klasör görülürse `UnsupportedLayout` (doğrulama
    çalışmadı, çıkış 2): alt klasörlü düzen desteklenmez, çünkü desteklemek Batfish'in
    özyineleme kurallarını (gizli klasörler, derinlik, yinelenen hostname) birebir
    taklit etmeyi gerektirir. Sembolik bağlantı ya da düzenli dosya olmayan giriş
    okunmadan ValueError verir. Gizli girişler okunmaz; Batfish de yüklemez.

    Garanti etmez: Batfish imajı bu kuralları değiştirirse eşitlik bozulur; o durumda ilk
    kalan test tests/test_snapshot_batfish.py olur.
    """
    cfg = snapshot / CONFIG_DIR
    if not cfg.is_dir():
        raise FileNotFoundError(f"{cfg} bulunamadı; snapshot '{CONFIG_DIR}/' klasörü içermeli")
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
