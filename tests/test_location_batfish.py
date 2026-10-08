"""Başlangıç konumu kümesi değişen adaylar, gerçek Batfish'e karşı (hatalar E2, Y1).

E2: edge'e ACL'siz yeni arayüz ekleyen aday KABUL alıyor, etki listesi boş kalıyordu
(differentialReachability yalnızca iki snapshot'ta da etkin konumları tarar; örnek
politikadaki internet değişmezi yalnızca Gi0/0'dan başlıyordu).

Y1: başlangıç konumu adayda hiçbir etkin konuma çözülmeyince Batfish tablo yerine metin
cevap döndürüyor ve `.frame()` AttributeError veriyordu: `kanit check` 2 dönüyor, `kanit
plan` traceback ile çöküyordu.

Senaryolar examples/acme kopyasında kurulur; repodaki örnek değiştirilmez.
"""

import json
import os
import shutil
import uuid
from pathlib import Path

import pytest

from kanit import cli, loop, report
from kanit.proposer import ScriptedProposer
from kanit.snapshot import POLICY_FILE, read_invariants
from kanit.verifier import BatfishVerifier, _NoSources, _table

ACME = Path(__file__).parent.parent / "examples" / "acme"
HOST = os.environ.get("BATFISH_HOST")
USERS = "@enter(core[GigabitEthernet0/1])"
INTERNET = "Internet sunucu ağına hiçbir şekilde erişemez"
HTTPS = "Kullanıcılar web sunucusuna HTTPS ile erişir"
SSH = "Kullanıcılar veritabanı sunucusuna SSH yapamaz"
GI2_EDGE = ("!\nip access-list",
            "!\ninterface GigabitEthernet0/2\n ip address 198.51.100.2 255.255.255.252\n"
            " {state}\n!\nip access-list")
USERS_UP = " description USERS\n ip address 10.10.10.1 255.255.255.0\n no shutdown\n"
USERS_DOWN = USERS_UP.replace("no shutdown", "shutdown")
PREEXISTING_TEXT = "önceden de ihlal ediliyordu; bu değişiklik ihlali genişletmiyor"

pytestmark = [
    pytest.mark.batfish,
    pytest.mark.skipif(not HOST, reason="BATFISH_HOST tanımlı değil"),
]


def edit(path: Path, old: str, new: str) -> None:
    text = path.read_text()
    assert text.count(old) == 1, old
    path.write_text(text.replace(old, new))


def copy(src: Path, dest: Path, invariants: list[dict] | None = None) -> Path:
    shutil.copytree(src, dest)
    if invariants is not None:
        policy = json.dumps({"invariants": invariants}, ensure_ascii=False, indent=2)
        (dest / POLICY_FILE).write_text(policy)
    return dest


def acme_invariant(name: str) -> dict:
    return next(i for i in json.loads((ACME / POLICY_FILE).read_text())["invariants"]
                if i["name"] == name)


def check(base: Path, cand: Path, out: Path) -> tuple[int, str]:
    rc = cli.main(["check", "--base", str(base), "--candidate", str(cand), "--out", str(out),
                   "--batfish-host", HOST])
    md = out.read_text()
    print(md)
    return rc, md


def row(md: str, name: str) -> str:
    return next(line for line in md.splitlines() if line.startswith(f"| {name}"))


def verify(base: Path, cand: Path, intents=()):
    verdict = BatfishVerifier(HOST).verify(base, cand, read_invariants(base), list(intents))
    for c in verdict.checks:
        print(c.check.name, c.passed, c.preexisting, c.counterexample)
    print("\n".join(verdict.changed_flows))
    return verdict, {c.check.name: c for c in verdict.checks}


# --- Batfish'in boş başlangıç kümesi cevabı ------------------------------------------


def test_empty_start_answers_are_recognised(tmp_path):
    """Dayanılan Batfish davranışı: boş akış kümesi tablo değil, bilinen metin döner."""
    from pybatfish.client.session import Session
    from pybatfish.datamodel.flow import HeaderConstraints, PathConstraints

    cand = copy(ACME, tmp_path / "cand")
    edit(cand / "configs" / "edge.cfg", GI2_EDGE[0], GI2_EDGE[1].format(state="no shutdown"))
    bf = Session(host=HOST)
    network = f"kanit-test-{uuid.uuid4().hex[:8]}"
    bf.set_network(network)
    try:
        bf.init_snapshot(str(cand), name="s", overwrite=True)
        for start, src in (("@enter(yok[Gi0/0])", "10.0.0.0/8"),
                           ("@enter(edge[GigabitEthernet0/2])", None)):
            answer = bf.q.reachability(
                pathConstraints=PathConstraints(startLocation=start),
                headers=HeaderConstraints(srcIps=src, dstIps="10.20.20.0/24"),
            ).answer(snapshot="s")
            with pytest.raises(_NoSources):
                _table(answer)
    finally:
        bf.delete_network(network)


# --- E2: yeni konumdan açılan akış ---------------------------------------------------


def test_example_policy_internet_invariant_covers_all_external_edge_interfaces(tmp_path):
    """Örnek politikada değişmezin kapsamı adıyla uyumlu: edge'in iç arayüzü (Gi0/1,
    TO-CORE) dışındaki her arayüzü. Mevcut ağda yalnızca Gi0/0'a çözülür."""
    from pybatfish.client.session import Session

    start = acme_invariant(INTERNET)["start"]
    cand = copy(ACME, tmp_path / "cand")
    edit(cand / "configs" / "edge.cfg", GI2_EDGE[0], GI2_EDGE[1].format(state="no shutdown"))
    bf = Session(host=HOST)
    network = f"kanit-test-{uuid.uuid4().hex[:8]}"
    bf.set_network(network)
    try:
        bf.init_snapshot(str(ACME), name="base", overwrite=True)
        bf.init_snapshot(str(cand), name="cand", overwrite=True)
        resolved = {
            snap: sorted(str(x) for x in bf.q.resolveLocationSpecifier(locations=start)
                         .answer(snapshot=snap).frame()["Location"])
            for snap in ("base", "cand")
        }
    finally:
        bf.delete_network(network)
    link = "InterfaceLinkLocation{{nodeName=edge, interfaceName=GigabitEthernet0/{}}}"
    assert resolved["base"] == [link.format(0)]
    assert resolved["cand"] == [link.format(0), link.format(2)]


def test_new_internet_interface_without_acl_is_rejected(tmp_path):
    """Uçtan uca testçinin senaryosu. Eski kod: KABUL, 'kanıtlandı', etki listesi yok."""
    cand = copy(ACME, tmp_path / "pr")
    edit(cand / "configs" / "edge.cfg", GI2_EDGE[0], GI2_EDGE[1].format(state="no shutdown"))
    rc, md = check(ACME, cand, tmp_path / "r.md")
    assert rc == 1
    assert "Kanıt etki raporu: REDDEDİLDİ" in md
    r = row(md, INTERNET)
    assert "**ihlal**" in r and "interface=GigabitEthernet0/2" in r and "->10.20.20." in r
    assert "Davranışı değişen örnek akışlar" in md
    assert "start=edge interface=GigabitEthernet0/2" in md and "(konum yok) ->" in md


def test_new_interface_flows_are_listed_even_when_no_invariant_covers_it(tmp_path):
    """Yan etki kapısı (madde 3) yokken asgari şart: etki GÖRÜNÜR. Politika eski dar
    kapsamlı (yalnızca Gi0/0) değişmezle; aday değişmezleri bozmadığı için kabul edilir,
    ama yeni konumdan sunucu ağına ulaşan akış etki listesinde."""
    narrow = dict(acme_invariant(INTERNET), start="@enter(edge[GigabitEthernet0/0])")
    base = copy(ACME, tmp_path / "base", [narrow])
    cand = copy(base, tmp_path / "pr")
    edit(cand / "configs" / "edge.cfg", GI2_EDGE[0], GI2_EDGE[1].format(state="no shutdown"))
    verdict, _ = verify(base, cand)
    assert verdict.accepted
    new_flows = [f for f in verdict.changed_flows
                 if "start=edge interface=GigabitEthernet0/2" in f and "(konum yok) ->" in f]
    assert new_flows, verdict.changed_flows

    rc, md = check(base, cand, tmp_path / "r.md")
    assert rc == 0
    assert "start=edge interface=GigabitEthernet0/2" in md and "(konum yok) ->" in md


def test_reactivated_interface_flows_are_listed(tmp_path):
    """Konum iki tarafta da var ama mevcutta kapalı: fark sorgusu onu taramaz."""
    narrow = dict(acme_invariant(INTERNET), start="@enter(edge[GigabitEthernet0/0])")
    base = copy(ACME, tmp_path / "base", [narrow])
    edit(base / "configs" / "edge.cfg", GI2_EDGE[0], GI2_EDGE[1].format(state="shutdown"))
    cand = copy(base, tmp_path / "pr")
    edit(cand / "configs" / "edge.cfg", "198.51.100.2 255.255.255.252\n shutdown\n",
         "198.51.100.2 255.255.255.252\n no shutdown\n")
    verdict, _ = verify(base, cand)
    assert any("interface=GigabitEthernet0/2" in f and "(konum yok) ->" in f
               for f in verdict.changed_flows), verdict.changed_flows
    # Örnek politikanın genişletilmiş değişmeziyle aynı aday reddedilir.
    wide = copy(base, tmp_path / "base-wide", [acme_invariant(INTERNET)])
    cand_wide = copy(cand, tmp_path / "pr-wide", [acme_invariant(INTERNET)])
    verdict, checks = verify(wide, cand_wide)
    assert not verdict.accepted
    assert "GigabitEthernet0/2" in checks[INTERNET].counterexample


# --- Y1: başlangıç konumu adayda çözülmüyor ---------------------------------------------


def test_shutting_single_start_interface_loses_access(tmp_path):
    """Eski kod: AttributeError, çıkış 2. Doğrusu: ret (1), 'erişim kayboldu'."""
    cand = copy(ACME, tmp_path / "pr")
    edit(cand / "configs" / "core.cfg", USERS_UP, USERS_DOWN)
    rc, md = check(ACME, cand, tmp_path / "r.md")
    assert rc == 1
    assert "Kanıt etki raporu: REDDEDİLDİ" in md
    r = row(md, HTTPS)
    assert "**ihlal**" in r and "erişim kayboldu" in r and "GigabitEthernet0/1" in r
    # blocked değişmezinde konumun yok olması ihlal değildir.
    assert row(md, SSH).endswith("| kanıtlandı |")
    assert "-> (konum yok)" in md


def test_blocked_invariant_whose_location_vanishes_is_not_violated(tmp_path):
    base = copy(ACME, tmp_path / "base", [acme_invariant(SSH)])
    cand = copy(base, tmp_path / "pr")
    edit(cand / "configs" / "core.cfg", USERS_UP, USERS_DOWN)
    rc, md = check(base, cand, tmp_path / "r.md")
    assert rc == 0
    assert row(md, SSH).endswith("| kanıtlandı |")


def test_blocked_invariant_location_renamed_and_opened_is_rejected(tmp_path):
    """Kapalı yön: hostname değişince eski konum kaybolur, aynı arayüz yeni adla gelir.
    Yeni ad SSH'ı açıyorsa kaybolan konum 'ihlal değil' diye geçirilemez."""
    base = copy(ACME, tmp_path / "base", [acme_invariant(SSH)])
    cand = copy(base, tmp_path / "pr")
    core = cand / "configs" / "core.cfg"
    edit(core, "hostname core\n", "hostname core1\n")
    edit(core, " deny ip any any\n", " permit ip any any\n")
    rc, md = check(base, cand, tmp_path / "r.md")
    assert rc == 1
    r = row(md, SSH)
    assert "**ihlal**" in r and "start=core1" in r and "yeni adla" in r


def test_blocked_invariant_location_renamed_but_still_blocked_is_accepted(tmp_path):
    base = copy(ACME, tmp_path / "base", [acme_invariant(SSH)])
    cand = copy(base, tmp_path / "pr")
    edit(cand / "configs" / "core.cfg", "hostname core\n", "hostname core1\n")
    rc, md = check(base, cand, tmp_path / "r.md")
    assert rc == 0, md
    assert "start=core1" in md and "(konum yok) ->" in md


def test_deleting_edge_config_is_verified_not_crashed(tmp_path):
    """Eski kod: AttributeError, çıkış 2. Internet değişmezinin konumu kayboldu (ihlal
    değil); HTTPS core üzerinden sürüyor. Kaybolan akışlar etki listesinde."""
    cand = copy(ACME, tmp_path / "pr")
    (cand / "configs" / "edge.cfg").unlink()
    rc, md = check(ACME, cand, tmp_path / "r.md")
    assert rc == 0
    assert "3 değişmez, 3 kanıtlandı, 0 ihlal" in md
    assert "start=edge" in md and "-> (konum yok)" in md


def test_invariant_start_resolving_nowhere_fails_closed(tmp_path):
    """Mevcutta da çözülmeyen konum: değişmez sınanamaz; kanıtlandı sayılmaz."""
    typo = dict(acme_invariant(SSH), name="yazım hatalı", start="@enter(kore[GigabitEthernet0/1])")
    base = copy(ACME, tmp_path / "base", [typo])
    cand = copy(base, tmp_path / "pr")
    edit(cand / "configs" / "core.cfg", " deny ip any any\n",
         " permit tcp any any eq 80\n deny ip any any\n")
    rc, md = check(base, cand, tmp_path / "r.md")
    assert rc == 1
    r = row(md, "yazım hatalı")
    assert "**ihlal**" in r and "iki snapshot'ta da hiçbir arayüze çözülmüyor" in r


def test_reachable_invariant_already_without_active_start_is_preexisting(tmp_path):
    """Mevcutta da kapalı başlangıç konumu: erişim önceden de yoktu; ilgisiz değişiklik
    ihlali genişletmez."""
    base = copy(ACME, tmp_path / "base", [acme_invariant(HTTPS)])
    edit(base / "configs" / "core.cfg", USERS_UP, USERS_DOWN)
    cand = copy(base, tmp_path / "pr")
    edit(cand / "configs" / "core.cfg", " deny ip any any\n",
         " permit tcp 10.10.10.0 0.0.0.255 host 10.20.20.10 eq 80\n deny ip any any\n")
    rc, md = check(base, cand, tmp_path / "r.md")
    assert rc == 0
    assert PREEXISTING_TEXT in row(md, HTTPS)


# --- Y1, plan (loop) yolu -------------------------------------------------------------


def scripted(tmp_path: Path, name: str, edits: list[tuple[str, str, str]], checks: list[dict]):
    path = tmp_path / f"{name}.json"
    path.write_text(json.dumps({
        "summary": name,
        "edits": [{"file": f, "old": o, "new": n} for f, o, n in edits],
        "intent_checks": checks,
    }, ensure_ascii=False))
    return path


DB_RULE = ("core.cfg", " deny ip any any\n",
           " permit tcp 10.10.10.0 0.0.0.255 host 10.20.20.30 eq 5432\n deny ip any any\n")


def db_check(start: str = USERS) -> dict:
    return {"name": "db 5432", "start": start, "src": "10.10.10.0/24", "dst": "10.20.20.30",
            "protocol": "TCP", "dst_ports": "5432", "expect": "reachable"}


def run_loop(tmp_path, *proposals):
    result = loop.run("db aç", ACME, ScriptedProposer(list(proposals)), BatfishVerifier(HOST))
    print(report.render(result))
    return result


def test_intent_with_unresolvable_start_is_rejected_and_loop_continues(tmp_path):
    """Eski kod: AttributeError, döngü çöküyor (traceback, rapor yok)."""
    bad = scripted(tmp_path, "yanlis-start", [DB_RULE], [db_check("@enter(core[Gi9/9])")])
    good = ACME / "scripted" / "02-dogru.json"
    result = run_loop(tmp_path, bad, good)
    assert result.error is None
    first, second = result.rounds
    assert not first.verdict.accepted and second.verdict.accepted
    (failure,) = first.verdict.failures
    assert failure.kind == "intent"
    assert "hiçbir arayüze çözülmüyor" in failure.counterexample
    assert "NİYET SAĞLANMADI: 'db 5432'" in first.verdict.feedback()


def test_proposal_shutting_start_interface_is_rejected_and_loop_continues(tmp_path):
    down = scripted(tmp_path, "kapat", [DB_RULE, ("core.cfg", USERS_UP, USERS_DOWN)],
                    [db_check()])
    result = run_loop(tmp_path, down, ACME / "scripted" / "02-dogru.json")
    first, second = result.rounds
    assert not first.verdict.accepted and second.verdict.accepted
    failures = {c.check.name: c for c in first.verdict.failures}
    assert "erişim kayboldu" in failures[HTTPS].counterexample
    assert "erişim kayboldu" in failures["db 5432"].counterexample


def test_plan_exit_codes_with_unresolvable_intent(tmp_path):
    bad = scripted(tmp_path, "yanlis-start", [DB_RULE], [db_check("@enter(core[Gi9/9])")])
    out = tmp_path / "r.md"
    rc = cli.main(["plan", "db aç", "--snapshot", str(ACME), "--scripted", str(bad),
                   "--max-rounds", "1", "--out", str(out), "--batfish-host", HOST])
    assert rc == 1
    assert "Kanıt raporu: REDDEDİLDİ" in out.read_text()


# --- Boş kaynak uzayı hiçbir zaman "kanıtlandı" değildir (denetçi KRİTİK) ---------------
# Batfish `src` verilmezse kaynağı konumdan çıkarır; /30 bağlantılarda ve internet ucunda
# (edge Gi0/0) bu uzay boştur ve sorgu "All sources have empty source IpSpaces" döner.
# 2ae7eb7 bunu "akış yok" sayıp blocked değişmezi kanıtlanmış ilan ediyordu (yanlış
# kabul); e403bfc ise 2 veriyordu.


def test_srcless_blocked_on_transit_link_is_tested_with_any_source(tmp_path):
    """Denetçi senaryosu A."""
    transit = {"name": "core'un edge bağlantısından sunuculara hiçbir akış yok",
               "start": "@enter(core[GigabitEthernet0/0])", "dst": "10.20.20.0/24",
               "expect": "blocked"}
    base = copy(ACME, tmp_path / "base", [transit])
    cand = copy(base, tmp_path / "pr")
    edit(cand / "configs" / "core.cfg", " deny ip any any\n",
         " permit ip any 10.20.20.0 0.0.0.255\n deny ip any any\n")
    rc, md = check(base, cand, tmp_path / "r.md")
    assert rc == 1
    assert "**ihlal**" in row(md, transit["name"])


def test_srcless_internet_invariant_catches_removed_deny(tmp_path):
    """Denetçi senaryosu A3: src'siz internet değişmezi; INTERNET-IN'deki 10/8 reddi
    siliniyor."""
    internet = dict(acme_invariant(INTERNET), start="@enter(edge[GigabitEthernet0/0])")
    del internet["src"]
    base = copy(ACME, tmp_path / "base", [internet])
    # Mevcut ağ değişmezi her kaynakla sağlıyor; yoksa test anlamsız olur.
    unchanged, checks = verify(base, base)
    assert unchanged.accepted and checks[INTERNET].passed
    cand = copy(base, tmp_path / "pr")
    edit(cand / "configs" / "edge.cfg", " deny ip any 10.0.0.0 0.255.255.255\n", "")
    rc, md = check(base, cand, tmp_path / "r.md")
    assert rc == 1
    r = row(md, INTERNET)
    assert "**ihlal**" in r and "->10.20.20." in r


def test_srcless_blocked_on_new_30_location_is_rejected(tmp_path):
    """Yeni konum yolu (_violation_at): src'siz değişmezin start'ı yeni /30 arayüzünü de
    kapsıyor; Batfish'in çıkardığı kaynak uzayı orada boş."""
    internet = dict(acme_invariant(INTERNET))
    del internet["src"]
    base = copy(ACME, tmp_path / "base", [internet])
    cand = copy(base, tmp_path / "pr")
    edit(cand / "configs" / "edge.cfg", GI2_EDGE[0], GI2_EDGE[1].format(state="no shutdown"))
    rc, md = check(base, cand, tmp_path / "r.md")
    assert rc == 1
    r = row(md, INTERNET)
    assert "**ihlal**" in r and "GigabitEthernet0/2" in r


def test_srcless_reachable_on_empty_source_location_is_untestable(tmp_path):
    """reachable yönü: kaynak uzayı boş konumdan erişim sınanamaz; kanıtlandı sayılmaz."""
    reach = {"name": "internet ucundan web sunucusuna erişim", "dst": "10.20.20.10",
             "start": "@enter(edge[GigabitEthernet0/0])", "protocol": "TCP",
             "dst_ports": "443", "expect": "reachable"}
    base = copy(ACME, tmp_path / "base", [reach])
    cand = copy(base, tmp_path / "pr")
    edit(cand / "configs" / "core.cfg", " deny ip any any\n",
         " permit tcp any host 10.20.20.10 eq 443\n deny ip any any\n")
    rc, md = check(base, cand, tmp_path / "r.md")
    assert rc == 1
    r = row(md, reach["name"])
    assert "**ihlal**" in r and "sınanamadı" in r


def test_srcless_reachable_intent_on_new_30_location_is_rejected(tmp_path):
    from kanit.models import FlowCheck

    intent = FlowCheck.from_dict(
        {"name": "yeni uçtan web", "start": "@enter(edge[GigabitEthernet0/2])",
         "dst": "10.20.20.10", "protocol": "TCP", "dst_ports": "443", "expect": "reachable"})
    cand = copy(ACME, tmp_path / "pr")
    edit(cand / "configs" / "edge.cfg", GI2_EDGE[0], GI2_EDGE[1].format(state="no shutdown"))
    verdict, checks = verify(ACME, cand, [intent])
    c = checks[intent.name]
    assert not verdict.accepted
    assert not c.passed and "sınanamadı" in c.counterexample
