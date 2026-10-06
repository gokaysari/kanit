from __future__ import annotations

import json
import shutil
from pathlib import Path

from .models import FlowCheck, Proposal, ProposalError

CONFIG_DIR = "configs"
POLICY_FILE = "policy.json"


def read_configs(snapshot: Path) -> dict[str, str]:
    cfg = snapshot / CONFIG_DIR
    if not cfg.is_dir():
        raise FileNotFoundError(f"{cfg} bulunamadı; snapshot '{CONFIG_DIR}/' klasörü içermeli")
    return {p.name: p.read_text() for p in sorted(cfg.iterdir()) if p.is_file()}


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
        (cfg / name).write_text(text)
    return dest
