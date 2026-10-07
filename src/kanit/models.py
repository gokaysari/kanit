from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

EXPECTATIONS = ("reachable", "blocked")


class ProposalError(ValueError):
    """Öneri, doğrulamaya gönderilemeyecek kadar bozuk."""


@dataclass(frozen=True)
class FlowCheck:
    """Bir akış kümesi hakkında beklenti: tamamı ulaşmalı ya da tamamı engellenmeli."""

    name: str
    start: str
    dst: str
    expect: str
    src: str | None = None
    protocol: str | None = None
    dst_ports: str | None = None

    @staticmethod
    def from_dict(d: dict[str, Any]) -> "FlowCheck":
        if not isinstance(d, dict):
            raise ProposalError(f"Akış kontrolü bir nesne olmalı, gelen: {d!r:.200}")
        missing = [k for k in ("name", "start", "dst", "expect") if not d.get(k)]
        if missing:
            raise ProposalError(f"Akış kontrolünde eksik alan: {', '.join(missing)}")
        if d["expect"] not in EXPECTATIONS:
            raise ProposalError(f"expect '{d['expect']}' olamaz; {EXPECTATIONS} olmalı")
        return FlowCheck(
            name=str(d["name"]),
            start=str(d["start"]),
            dst=str(d["dst"]),
            expect=str(d["expect"]),
            src=d.get("src") or None,
            protocol=(str(d["protocol"]).upper() if d.get("protocol") else None),
            dst_ports=(str(d["dst_ports"]) if d.get("dst_ports") else None),
        )

    def describe(self) -> str:
        proto = self.protocol or "IP"
        port = f"/{self.dst_ports}" if self.dst_ports else ""
        return f"{self.src or 'herhangi'} -> {self.dst} {proto}{port}"


@dataclass(frozen=True)
class Edit:
    """Tek bir yapılandırma dosyasında birebir metin değişimi."""

    file: str
    old: str
    new: str

    @staticmethod
    def from_dict(d: Any) -> "Edit":
        fields = ("file", "old", "new")
        if not isinstance(d, dict) or not all(isinstance(d.get(k), str) for k in fields):
            raise ProposalError(
                f"Düzenleme şemaya uymuyor; file, old ve new metin olmalı, gelen: {d!r:.200}"
            )
        return Edit(d["file"], d["old"], d["new"])


@dataclass(frozen=True)
class Proposal:
    summary: str
    edits: tuple[Edit, ...]
    intent_checks: tuple[FlowCheck, ...]

    @staticmethod
    def from_dict(d: dict[str, Any]) -> "Proposal":
        if not isinstance(d, dict):
            raise ProposalError(f"Öneri bir nesne olmalı, gelen: {d!r:.200}")
        missing = [k for k in ("summary", "edits", "intent_checks") if k not in d]
        if missing:
            raise ProposalError(f"Öneri şemaya uymuyor; eksik alan: {', '.join(missing)}")
        for key in ("edits", "intent_checks"):
            if not isinstance(d[key], list):
                raise ProposalError(f"Öneri şemaya uymuyor; '{key}' bir liste olmalı")
        edits = tuple(Edit.from_dict(e) for e in d["edits"])
        checks = tuple(FlowCheck.from_dict(c) for c in d["intent_checks"])
        summary = str(d["summary"])
        if not edits:
            raise ProposalError("Öneri hiç değişiklik içermiyor")
        if not checks:
            raise ProposalError("Öneri hiç niyet kontrolü içermiyor; doğrulanacak bir şey yok")
        return Proposal(summary, edits, checks)


@dataclass
class Usage:
    """Model çağrılarının token tüketimi; maliyeti görünür kılmak için toplanır."""

    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0

    def add(self, api_usage: Any) -> None:
        """API yanıtındaki usage nesnesini ekler (eksik alanlar 0 sayılır)."""
        self.calls += 1
        for name in (
            "input_tokens",
            "output_tokens",
            "cache_read_input_tokens",
            "cache_creation_input_tokens",
        ):
            setattr(self, name, getattr(self, name) + (getattr(api_usage, name, 0) or 0))

    def __sub__(self, other: "Usage") -> "Usage":
        return Usage(
            *(getattr(self, f) - getattr(other, f) for f in self.__dataclass_fields__)
        )

    def __add__(self, other: "Usage") -> "Usage":
        return Usage(
            *(getattr(self, f) + getattr(other, f) for f in self.__dataclass_fields__)
        )

    def copy(self) -> "Usage":
        return self + Usage()

    def describe(self) -> str:
        def n(x: int) -> str:
            return f"{x:,}".replace(",", ".")

        cache = ""
        if self.cache_read_input_tokens or self.cache_creation_input_tokens:
            cache = (
                f" (önbellekten okunan {n(self.cache_read_input_tokens)},"
                f" önbelleğe yazılan {n(self.cache_creation_input_tokens)})"
            )
        return (
            f"{self.calls} çağrı, {n(self.input_tokens)} giriş + "
            f"{n(self.output_tokens)} çıkış token{cache}"
        )


@dataclass
class CheckResult:
    check: FlowCheck
    kind: str  # "invariant" | "intent"
    passed: bool
    counterexample: str | None = None
    # Değişmez önceden de ihlal ediliyordu VE aday ihlali genişletmiyor (Batfish ile
    # kanıtlandı). Yalnızca bu durumda ihlal kabulü engellemez; bkz.
    # BatfishVerifier._classify_preexisting.
    preexisting: bool = False


@dataclass
class Verdict:
    checks: list[CheckResult] = field(default_factory=list)
    new_parse_issues: list[str] = field(default_factory=list)
    new_undefined_refs: list[str] = field(default_factory=list)
    changed_flows: list[str] = field(default_factory=list)
    error: str | None = None  # öneri uygulanamadı / şemaya uymuyor

    @property
    def failures(self) -> list[CheckResult]:
        return [c for c in self.checks if not c.passed and not c.preexisting]

    @property
    def accepted(self) -> bool:
        return (
            self.error is None
            and not self.failures
            and not self.new_parse_issues
            and not self.new_undefined_refs
        )

    def feedback(self) -> str:
        """Reddedilen öneri için modele geri verilecek metin."""
        if self.error:
            return f"Öneri uygulanamadı: {self.error}"
        lines: list[str] = []
        for issue in self.new_parse_issues:
            lines.append(f"YENİ AYRIŞTIRMA SORUNU: {issue}")
        for ref in self.new_undefined_refs:
            lines.append(f"YENİ TANIMSIZ REFERANS: {ref}")
        for c in self.failures:
            label = "DEĞİŞMEZ İHLALİ" if c.kind == "invariant" else "NİYET SAĞLANMADI"
            want = "ulaşmalıydı" if c.check.expect == "reachable" else "engellenmeliydi"
            lines.append(
                f"{label}: '{c.check.name}' ({c.check.describe()}) {want}. "
                f"Karşı örnek akış: {c.counterexample}"
            )
        if self.changed_flows:
            lines.append("Değişiklikten etkilenen örnek akışlar:")
            lines.extend(f"  - {f}" for f in self.changed_flows)
        return "\n".join(lines)
