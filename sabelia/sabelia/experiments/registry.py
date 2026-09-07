"""Runs and models, recorded so that a result can be reproduced and compared.

No tracking server. A run is one JSON line in ``runs.jsonl`` with the model,
the dataset name and version, the config, the seed, the metrics, the wall
time, the hardware and the git commit. A registered model is a directory
with the weights (or parameters), the vocabulary, the config and a
``model.json`` carrying its status: ``experimental``, ``staging``,
``production`` or ``deprecated``. Promotion is a status change, never a
file rename, so rollback is setting the previous version back to
``production``.
"""

from __future__ import annotations

import json
import platform
import subprocess
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

STATUSES = ("experimental", "staging", "production", "deprecated")


def git_commit() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL, text=True
        ).strip()
    except Exception:
        return None


def environment_info() -> dict[str, Any]:
    info: dict[str, Any] = {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "machine": platform.machine(),
    }
    try:
        import torch  # noqa: PLC0415

        info["torch"] = torch.__version__
        info["device"] = (
            "cuda" if torch.cuda.is_available() else ("mps" if torch.backends.mps.is_available() else "cpu")
        )
    except Exception:
        info["torch"] = None
        info["device"] = "cpu"
    return info


@dataclass
class ExperimentRun:
    run_id: str
    model: str
    dataset: str
    dataset_version: str
    dataset_kind: str
    seed: int
    config: dict[str, Any]
    metrics: dict[str, Any]
    train_seconds: float
    environment: dict[str, Any] = field(default_factory=environment_info)
    git: str | None = field(default_factory=git_commit)
    created_at: float = field(default_factory=time.time)
    notes: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class Registry:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.runs_path = self.root / "runs.jsonl"
        self.models_dir = self.root / "models"
        self.models_dir.mkdir(exist_ok=True)

    # ── runs ──────────────────────────────────────────────────────────
    def record(self, run: ExperimentRun) -> None:
        with self.runs_path.open("a") as f:
            f.write(json.dumps(run.as_dict(), sort_keys=True) + "\n")

    def runs(self) -> list[dict[str, Any]]:
        if not self.runs_path.exists():
            return []
        return [json.loads(line) for line in self.runs_path.read_text().splitlines() if line.strip()]

    def compare(self, dataset: str | None = None, metric: str = "auc") -> list[dict[str, Any]]:
        rows = [r for r in self.runs() if dataset is None or r["dataset"].startswith(dataset)]
        rows.sort(key=lambda r: -(r["metrics"].get(metric) or 0))
        return rows

    # ── models ────────────────────────────────────────────────────────
    def register(
        self,
        name: str,
        version: str,
        *,
        payload: dict[str, Any],
        metrics: dict[str, Any],
        status: str = "experimental",
    ) -> Path:
        if status not in STATUSES:
            raise ValueError(f"status must be one of {STATUSES}")
        d = self.models_dir / name / version
        d.mkdir(parents=True, exist_ok=True)
        (d / "model.json").write_text(
            json.dumps(
                {
                    "name": name,
                    "version": version,
                    "status": status,
                    "metrics": metrics,
                    "created_at": time.time(),
                    "git": git_commit(),
                    "environment": environment_info(),
                    **{k: v for k, v in payload.items() if k != "weights"},
                },
                indent=2,
                sort_keys=True,
            )
        )
        return d

    def set_status(self, name: str, version: str, status: str) -> None:
        if status not in STATUSES:
            raise ValueError(f"status must be one of {STATUSES}")
        p = self.models_dir / name / version / "model.json"
        meta = json.loads(p.read_text())
        if status == "production":
            # one production version per model name
            for other in (self.models_dir / name).iterdir():
                op = other / "model.json"
                if op.exists() and other.name != version:
                    m = json.loads(op.read_text())
                    if m.get("status") == "production":
                        m["status"] = "deprecated"
                        op.write_text(json.dumps(m, indent=2, sort_keys=True))
        meta["status"] = status
        p.write_text(json.dumps(meta, indent=2, sort_keys=True))

    def production(self, name: str) -> Path | None:
        d = self.models_dir / name
        if not d.exists():
            return None
        for v in sorted(d.iterdir()):
            p = v / "model.json"
            if p.exists() and json.loads(p.read_text()).get("status") == "production":
                return v
        return None

    def versions(self, name: str) -> list[dict[str, Any]]:
        d = self.models_dir / name
        if not d.exists():
            return []
        out = []
        for v in sorted(d.iterdir()):
            p = v / "model.json"
            if p.exists():
                out.append(json.loads(p.read_text()))
        return out
