# CCE — Content Communication Engine

Measurement chain for outbound community content: context readout, knot
classification, emotion policy, and publication gates.

## What this is

A pipeline that measures a draft before it is published, and measures the
community response after. It does not decide what to say. It records what a
draft is doing, and refuses to let unverified claims through the guard.

- `scripts/cce_full_run.py` — the profile-frozen chain (s0 → s4)
- `scripts/style_check.py` — style gate, calibrated against a human corpus
- `scripts/cce_outbound_guard.py` — compliance gate
- `config/knot_taxonomy.json` — the nine-knot motivational taxonomy (v1.3.1)
- `.github/workflows/cce-submit.yml` — the production entrypoint

## On the corpora

Every corpus in this repository is **de-identified**. Real usernames were
replaced with stable pseudonyms, author fields were stripped, and in-body
mentions were redacted. The identity mapping is not in this repository and
will not be published.

The people whose public comments informed this work did not sign up to be a
dataset. Pseudonymisation was verified to be lossless for every downstream
consumer before it was applied — the style gate reads identical values on the
de-identified corpus, and the subject distiller produces identical statistics.

## Status

Research code. The knot taxonomy's acceptance gates have been run, but G-K1
(inter-annotator agreement) has **no robust pass evidence** (未建立稳健通过证据):
two runs of the same gate protocol (v2) landed on opposite sides of the 0.25 JS
threshold (0.2422 / 0.2601), and the v3 re-test (4 runs, crossed bootstrap) is
UNRESOLVED for the four-model panel — see
`tests/data/gk1_fail_diagnosis_2026-10-03.json` and `tests/data/gk1_v3_result.json`.
G-K2 and G-K3 are not established either (`config/knot_taxonomy.json`, `status`).
Any conclusion drawn from stage-2 output should carry an "unverified" caveat.

**[OPEN_QUESTIONS.md](docs/OPEN_QUESTIONS.md) says exactly which parts are still
unproven** — including two things a person can help with and I cannot: a human
baseline for semantic distance (36 pairs, ~10 minutes), and verbatim
transcripts for social-media audio. Corrections to that page are more welcome
than participation.
