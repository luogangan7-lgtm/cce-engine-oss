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

Research code. The knot taxonomy's acceptance gates (G-K1/G-K2/G-K3) have not
been run; any conclusion drawn from stage-2 output should carry that caveat.
