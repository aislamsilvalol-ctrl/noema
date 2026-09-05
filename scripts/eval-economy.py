#!/usr/bin/env python3
"""Measure what a turn costs, V2 vs V3, on real assembled prompts — offline.

    apps/api/.venv/bin/python scripts/eval-economy.py evals/economy/v3-vs-v2

Replays one scripted lesson of N exchanges through both context builders and
counts the tokens each would send per turn, with the same estimate the
codebase uses everywhere (chars ÷ 4, `noema/professor/budget.py`):

- V2: the system block plus the *whole transcript*, resent every turn — what
  `_dispatch_stream` did.
- V3: the same system block, the stored turns fitted to the transcript
  budget, and the summaries the compactor writes when the window grows —
  what `ProfessorEngine.prepare` sends.

No model is called (a fixed reply of realistic length stands in; the
compactor's summary is a fixed record of realistic size), so the numbers are
the shape of the prompt, not a provider's bill. Writes `<out>.md` and
`<out>.json`. Real usage is in the admin dashboard once lessons have run.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api"))
os.environ.setdefault("NOEMA_DEFAULT_PROVIDER", "mock")

from noema.core.config import get_settings
from noema.professor.budget import estimate, fit_transcript
from noema.professor.memory import should_compact
from noema.prompts import load
from noema.services.teaching_policy import persona, principles

#: Realistic sizes, from evals/teaching/*.json: Mino's V3 replies run 1 100 to
#: 2 150 chars; a learner's line 30 to 120. The summary is the size the
#: compactor's record takes once rendered (`memory._render_summary`).
LEARNER_LINE = "Não entendi direito essa parte do recalque, dá um exemplo do dia a dia?"
MINO_REPLY = ("Pensa numa lembrança que você evita. " * 40).strip()  # ≈1 500 chars
SUMMARY_BLOCK = (
    "Earlier in this lesson (turns 1-18):\n- covered: inconsciente, lapso, recalque\n"
    "- shown understood: lapso\n- still uncertain: recalque\n"
    "- misconceptions seen: tudo que esqueci está no inconsciente\n"
    "- what landed: o lapso de língua; a analogia do porteiro\n"
    "- last taught: recalque\n- agreed next step: resistência"
)
DIRECTIVE = (
    "<TURN_DIRECTIVE>\n"
    + load("move.teach").body
    + "\n</TURN_DIRECTIVE>\n<COURSE>\nCourse: 4 modules, 12 lessons, 2 done.\nCurrent lesson: Recalque — concepts: recalque, resistência\n</COURSE>\n<KNOWLEDGE_STATE>\n- inconsciente: learning · 3\n- lapso: mastered · 4\n- recalque: uncertain · 2\n</KNOWLEDGE_STATE>"
)


@dataclass
class Turn:
    content: str

    @property
    def token_estimate(self) -> int:
        return estimate(self.content)


def main(out: str) -> int:
    settings = get_settings()
    system = f"{persona().body}\n\n{load('tutor.explain').body}\n\n{principles().body}"
    system_tokens = estimate(system)
    checkpoints = (1, 5, 10, 20, 50, 100)
    rows: list[dict[str, int | float]] = []

    transcript: list[Turn] = []
    v2_total = 0
    v3_total = 0
    summaries = 0
    active: list[Turn] = []
    for exchange in range(1, max(checkpoints) + 1):
        transcript.append(Turn(LEARNER_LINE))
        active.append(Turn(LEARNER_LINE))

        v2 = system_tokens + sum(t.token_estimate for t in transcript)
        kept, _ = fit_transcript(active, settings.noema_professor_transcript_budget)
        memory = estimate(SUMMARY_BLOCK) if summaries else 0
        v3 = (
            system_tokens
            + sum(t.token_estimate for t in kept)
            + memory
            + estimate(DIRECTIVE)
        )
        v2_total += v2
        v3_total += v3
        if exchange in checkpoints:
            rows.append(
                {
                    "exchange": exchange,
                    "v2_prompt_tokens": v2,
                    "v3_prompt_tokens": v3,
                    "v3_transcript_turns": len(kept),
                    "summaries": summaries,
                    "reduction": round(1 - v3 / v2, 3),
                    "v2_cumulative": v2_total,
                    "v3_cumulative": v3_total,
                }
            )

        transcript.append(Turn(MINO_REPLY))
        active.append(Turn(MINO_REPLY))
        if should_compact(
            active,
            after_tokens=settings.noema_professor_compact_after_tokens,
            after_turns=settings.noema_professor_compact_after_turns,
            keep=settings.noema_professor_keep_turns,
        ):
            active = active[-settings.noema_professor_keep_turns :]
            summaries += 1

    path = Path(out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.with_suffix(".json").write_text(
        json.dumps(
            {
                "system_tokens": system_tokens,
                "learner_line_tokens": estimate(LEARNER_LINE),
                "reply_tokens": estimate(MINO_REPLY),
                "transcript_budget": settings.noema_professor_transcript_budget,
                "compact_after_turns": settings.noema_professor_compact_after_turns,
                "compact_after_tokens": settings.noema_professor_compact_after_tokens,
                "keep_turns": settings.noema_professor_keep_turns,
                "rows": rows,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    lines = [
        "# Token economy: V2 (resend the transcript) vs V3 (stored turns + memory)",
        "",
        "Offline replay of one lesson, prompt tokens per turn, estimated as chars ÷ 4 on the",
        "real system block, a realistic learner line and a realistic reply. No model was called.",
        "",
        f"System block: {system_tokens} tokens (identical in both; cacheable). "
        f"Reply: {estimate(MINO_REPLY)} tokens. Learner line: {estimate(LEARNER_LINE)} tokens.",
        f"V3 transcript budget {settings.noema_professor_transcript_budget}, compaction after "
        f"{settings.noema_professor_compact_after_turns} turns or "
        f"{settings.noema_professor_compact_after_tokens} tokens, keeping "
        f"{settings.noema_professor_keep_turns}.",
        "",
        "| Exchange | V2 prompt | V3 prompt | V3 turns sent | Summaries | Reduction | V2 cumulative | V3 cumulative |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in rows:
        lines.append(
            f"| {r['exchange']} | {r['v2_prompt_tokens']:,} | {r['v3_prompt_tokens']:,} | "
            f"{r['v3_transcript_turns']} | {r['summaries']} | {r['reduction']:.0%} | "
            f"{r['v2_cumulative']:,} | {r['v3_cumulative']:,} |"
        )
    lines += [
        "",
        "What the table does not show: V3 spends extra economy-tier calls per lesson (goal,",
        "curriculum, routing on ambiguous messages, one compaction per window, cards, a",
        "checkpoint paper). Those are recorded per feature in `ai_usage` and shown on the",
        "admin dashboard; they are bounded per lesson, while the V2 transcript grew per turn.",
    ]
    path.with_suffix(".md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "evals/economy/v3-vs-v2"))
