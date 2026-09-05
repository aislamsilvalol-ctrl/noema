# Token economy: V2 (resend the transcript) vs V3 (stored turns + memory)

Offline replay of one lesson, prompt tokens per turn, estimated as chars ÷ 4 on the
real system block, a realistic learner line and a realistic reply. No model was called.

System block: 2138 tokens (identical in both; cacheable). Reply: 369 tokens. Learner line: 17 tokens.
V3 transcript budget 3500, compaction after 24 turns or 4500 tokens, keeping 6.

| Exchange | V2 prompt | V3 prompt | V3 turns sent | Summaries | Reduction | V2 cumulative | V3 cumulative |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 2,155 | 2,305 | 1 | 0 | -7% | 2,155 | 2,305 |
| 5 | 3,699 | 3,849 | 9 | 0 | -4% | 14,635 | 15,385 |
| 10 | 5,629 | 5,779 | 19 | 0 | -3% | 38,920 | 40,420 |
| 20 | 9,489 | 5,855 | 19 | 1 | 38% | 116,440 | 90,712 |
| 50 | 21,069 | 3,925 | 9 | 5 | 81% | 580,600 | 237,798 |
| 100 | 40,369 | 5,855 | 19 | 10 | 86% | 2,126,200 | 486,158 |

What the table does not show: V3 spends extra economy-tier calls per lesson (goal,
curriculum, routing on ambiguous messages, one compaction per window, cards, a
checkpoint paper). Those are recorded per feature in `ai_usage` and shown on the
admin dashboard; they are bounded per lesson, while the V2 transcript grew per turn.
