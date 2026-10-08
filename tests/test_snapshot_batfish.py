"""Batfish'e giden dosya kümesi ile read_configs'in okuduğu küme (hata E1).

Eskiden read_configs yalnızca configs/ altındaki üst düzey dosyaları okuyordu; Batfish
ise alt klasörleri de yükler. configs/ek/core2.cfg ekleyen aday `kanit check`'te
"KABUL / Yapılandırma değişmedi" ve çıkış 0 alıyordu, oysa Batfish'te model değişiyordu.
Şimdi alt klasörlü düzen desteklenmez: çıkış 2 ("doğrulama çalışmadı").

Bu dosya ayrıca read_configs'in dayandığı belgelenmemiş Batfish yükleme kurallarını
sabitler; Batfish imajı değişirse ilk kalan testler bunlardır.
"""

import json
import os
import shutil
import uuid
from pathlib import Path

import pytest

from kanit import cli
from kanit.snapshot import UnsupportedLayout, read_configs, write_candidate

ACME = Path(__file__).parent.parent / "examples" / "acme"
HOST = os.environ.get("BATFISH_HOST")

pytestmark = [
    pytest.mark.batfish,
    pytest.mark.skipif(not HOST, reason="BATFISH_HOST tanımlı değil"),
]


def core_copy(hostname: str = "core") -> str:
    """Örnek ağdaki core'un sunucu ACL'si 'permit ip any any' olan kopyası."""
    text = (ACME / "configs" / "core.cfg").read_text()
    assert text.count(" deny ip any any\n") == 1
    return text.replace("hostname core", f"hostname {hostname}").replace(
        " deny ip any any\n", " permit ip any any\n"
    )


def batfish_files(snapshot: Path) -> set[str]:
    """Batfish'in snapshot'tan yüklediği dosyalar (fileParseStatus)."""
    from pybatfish.client.session import Session

    bf = Session(host=HOST)
    network = f"kanit-test-{uuid.uuid4().hex[:8]}"
    bf.set_network(network)
    try:
        bf.init_snapshot(str(snapshot), name="s", overwrite=True)
        df = bf.q.fileParseStatus().answer(snapshot="s").frame()
        return {str(name) for name in df["File_Name"]}
    finally:
        bf.delete_network(network)


def test_read_configs_equals_what_batfish_loads(tmp_path):
    """Gizli dosya ve klasörler, uzantısı tanınmayan ve boş dosya: read_configs'in
    okuduğu küme Batfish'in yüklediği kümeyle birebir aynı."""
    snap = tmp_path / "snap"
    shutil.copytree(ACME, snap)
    cfg = snap / "configs"
    (cfg / ".gizli.cfg").write_text(core_copy("gizli"))
    (cfg / ".git").mkdir()
    (cfg / ".git" / "x.cfg").write_text(core_copy("gitx"))
    (cfg / "notlar.txt").write_text("yapılandırma değil\n")
    (cfg / "bos.cfg").write_text("")
    (cfg / "core.cfg~").write_text(core_copy("yedek"))
    # Kökte izinli girişler (check_layout): içlerine yapılandırma konsa da Batfish
    # yüklemez. (scripted/ ve policy.json zaten acme kopyasında var.)
    (snap / "scripted" / "x.cfg").write_text(core_copy("scripted"))
    (snap / "README.md").write_text(core_copy("readme"))
    (snap / "LICENSE").write_text(core_copy("license"))
    (snap / ".gizli").mkdir()
    (snap / ".gizli" / "x.cfg").write_text(core_copy("kokgizli"))

    read = {f"configs/{name}" for name in read_configs(snap)}
    loaded = batfish_files(snap)
    print(sorted(read), sorted(loaded))
    assert read == loaded
    assert "configs/.gizli.cfg" not in loaded and "configs/notlar.txt" in loaded
    # Doğrulayıcıya giden kopya (write_candidate) da aynı kümeyi taşır.
    copy = write_candidate(read_configs(snap), tmp_path / "copy")
    assert batfish_files(copy) == loaded


def test_batfish_loads_subdirectories_so_read_configs_refuses_them(tmp_path):
    """Neden reddediyoruz: Batfish alt klasördeki dosyayı (her derinlikte) yükler."""
    snap = tmp_path / "snap"
    shutil.copytree(ACME, snap)
    (snap / "configs" / "ek" / "derin").mkdir(parents=True)
    (snap / "configs" / "ek" / "core2.cfg").write_text(core_copy("core2"))
    (snap / "configs" / "ek" / "derin" / "d.cfg").write_text(core_copy("derin"))
    loaded = batfish_files(snap)
    assert {"configs/ek/core2.cfg", "configs/ek/derin/d.cfg"} <= loaded
    with pytest.raises(UnsupportedLayout):
        read_configs(snap)


def test_batfish_loads_root_runtime_data_so_layout_is_refused(tmp_path):
    """Neden kökü de denetliyoruz: batfish/runtime_data.json yapılandırma dosyası değildir
    ama arayüzü kapatır (lineUp=false); kanit bu klasörü Batfish'e götürmez."""
    from pybatfish.client.session import Session

    snap = tmp_path / "snap"
    shutil.copytree(ACME, snap)
    (snap / "batfish").mkdir()
    (snap / "batfish" / "runtime_data.json").write_text(json.dumps(
        {"runtimeData": {"core": {"interfaces": {"GigabitEthernet0/1": {"lineUp": False}}}}}))
    bf = Session(host=HOST)
    network = f"kanit-test-{uuid.uuid4().hex[:8]}"
    bf.set_network(network)
    try:
        bf.init_snapshot(str(snap), name="s", overwrite=True)
        df = bf.q.interfaceProperties(nodes="core", properties="Active").answer().frame()
        active = {str(r["Interface"].interface): bool(r["Active"]) for _, r in df.iterrows()}
    finally:
        bf.delete_network(network)
    assert active["GigabitEthernet0/1"] is False
    with pytest.raises(UnsupportedLayout, match="batfish"):
        read_configs(snap)


@pytest.mark.parametrize("entry", ["batfish/runtime_data.json", "hosts/h1.json"])
def test_candidate_changing_other_batfish_inputs_is_never_accepted(tmp_path, entry):
    """Eski kod: 'YAPILANDIRMA DEĞİŞMEDİ', çıkış 0."""
    cand = tmp_path / "pr"
    shutil.copytree(ACME, cand)
    path = cand / entry
    path.parent.mkdir()
    path.write_text(json.dumps(
        {"runtimeData": {"core": {"interfaces": {"GigabitEthernet0/1": {"lineUp": False}}}}}))
    rc, md = check(ACME, cand, tmp_path / "r.md")
    assert rc == 2
    assert "Kanıt etki raporu: DOĞRULAMA ÇALIŞMADI" in md
    assert "snapshot kökünde desteklenmeyen giriş" in md and entry.split("/")[0] in md


def check(base: Path, cand: Path, out: Path) -> tuple[int, str]:
    rc = cli.main(["check", "--base", str(base), "--candidate", str(cand), "--out", str(out),
                   "--batfish-host", HOST])
    md = out.read_text()
    print(md)
    return rc, md


@pytest.mark.parametrize("hostname", ["core", "core2"])
def test_candidate_adding_file_in_subdirectory_is_never_accepted(tmp_path, hostname):
    """Uçtan uca testçinin senaryosu (hostname core: Batfish düğümleri yeniden adlandırır)
    ve kısıtlanmamış yeni cihaz (core2). Eski kod: KABUL, çıkış 0."""
    cand = tmp_path / "pr"
    shutil.copytree(ACME, cand)
    (cand / "configs" / "ek").mkdir()
    (cand / "configs" / "ek" / "core2.cfg").write_text(core_copy(hostname))
    rc, md = check(ACME, cand, tmp_path / "r.md")
    assert rc == 2
    assert "Kanıt etki raporu: DOĞRULAMA ÇALIŞMADI" in md
    assert "desteklenmeyen düzende" in md and "alt klasör desteklenmiyor" in md
    assert "KABUL" not in md


def test_change_inside_existing_subdirectory_is_never_accepted(tmp_path):
    """Hedef dalda da alt klasör var ve PR onun içindeki dosyayı değiştiriyor."""
    base = tmp_path / "base"
    shutil.copytree(ACME, base)
    (base / "configs" / "ek").mkdir()
    (base / "configs" / "ek" / "core2.cfg").write_text(core_copy("core2").replace(
        " permit ip any any\n", " deny ip any any\n"))
    cand = tmp_path / "pr"
    shutil.copytree(base, cand)
    (cand / "configs" / "ek" / "core2.cfg").write_text(core_copy("core2"))
    rc, md = check(base, cand, tmp_path / "r.md")
    assert rc == 2
    assert "alt klasör desteklenmiyor" in md
