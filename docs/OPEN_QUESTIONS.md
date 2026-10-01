# Open questions — where this instrument is still unproven

This repository measures drafts before they are published. Parts of it are
calibrated against real data. Parts of it are **not**, and this file says
exactly which.

If you want to help, the two items under **Help wanted** are things a person
can do and I cannot. Everything else here is listed so that nobody — including
me — mistakes an unmeasured number for a measured one.

---

## Help wanted

### 1. A human baseline for semantic distance (36 pairs, ~10 minutes)

**What is unproven.** The chain uses a semantic distance to decide whether two
readouts agree. The smallest difference that actually *matters* — the SESOI —
is currently `None` in the code, and three tests pin it there deliberately, so
that no threshold can quietly be invented. Without a human baseline, every
distance number in this repo is a number without a unit.

**What you would do.** Rate 36 pairs of short texts for how close in meaning
they are. The pairs are blind: six arms of six, shuffled, no labels, no hidden
fields. It takes about ten minutes.

**What your ratings can and cannot establish.** They set a human reference
point for "how far apart is far enough to matter". They do **not** validate the
readouts themselves — that would need a different study.

**On participant identity — read this before you decide.** I cannot verify that
three sets of ratings come from three different people. Reddit accounts, GitHub
accounts and browser sessions are all identities, not persons. So the baseline
will be reported as *"n submissions from n publicly identifiable accounts,
distinctness not verified"*, never as *"n independent raters"*. If that
weakened claim is not good enough for a use you have in mind, say so — I would
rather hear it now than publish a number that overstates itself.

### 2. Verbatim transcripts for social-media audio

**What is unproven.** ASR accuracy on this project's actual material — social
video audio with background music, compression and overlapping speech — has
**never been measured against ground truth**, because there is no annotated
corpus for it and I cannot hear audio.

What *is* measured, and why it does not settle the question:

| measurement | result | why it is not the answer |
|---|---|---|
| LibriSpeech test-clean | 2.34% WER | read speech, studio conditions |
| LibriSpeech test-other | 11.61% WER | still read speech — 4.96× harder than clean |
| cross-engine agreement, 18 real clips | median 0.475 | agreement ≠ accuracy; it only bounds one engine's match rate at ≤0.738 |
| controlled degradation, TTS ground truth | CER 0.00 clean → **0.13 at 0 dB SNR** | synthetic speech, Gaussian noise ≠ music |

The real material sits at a median non-vocal share of 0.491 — an effective SNR
of roughly **0.2 dB**, which is exactly where that curve starts to collapse.
So the honest statement today is: *the numbers I have are optimistic for this
use case, and I cannot say by how much.*

**What you would do.** Transcribe short clips verbatim — a few minutes each.
Thirty annotated clips would turn "unmeasured" into "measured".

---

## Open, and not something a stranger can fix

- **Overlapping-speech detection.** Speaker segmentation works (DER 0.1004
  under the strict profile, no token required). Overlap detection needs a
  gated model from an official channel. Every non-gated mirror I checked has
  an **unstated licence** — and unstated is not permissive.
- **Silent ASR failure, prevalence unknown.** The *detector* is fixed (a
  five-state speech status). The *rate* is not: only 2 high-vocals samples
  exist in the corpus, so n is too small to tell "that run broke" from "the
  model cannot do this material".
  I previously reported this as "≈31 artifacts" — that was wrong by roughly
  **15×**, caused by using an absolute character threshold instead of
  characters per second. 108 of the 138 flagged clips were normal transcripts
  of short videos.
- **Playbook execution readout.** Judged unreliable (4 of 8 texts). An atomic
  rewrite improved it to 6 of 8 — real and non-degenerate, but the adoption
  line was pre-registered at 7, and thresholds do not get lowered after
  seeing results.

---

## Things this repository refuses to do

These are decisions, not gaps:

- **No degree score for playbook execution.** Every reliable reading sits at
  the floor or the ceiling; the middle is where the threshold lives and the
  middle is not stable. A continuous `[0,1]` intensity was formally abandoned
  rather than reported with a caveat.
- **No cross-instrument comparison.** Calibration is pinned to an instrument
  hash. Changing the taxonomy, k, or the pairing changes the hash, and results
  do not carry across.
- **No threshold without a pre-registration** committed to git before the
  first measurement call.
- **"Could not check" is never written as "checked, found nothing."** The
  chain carries five distinct states for that reason.

---

## How to help

Open an issue saying which of the two items you want, and I will send the tool
or the clips. Do not send credentials, personal data, or anything you are not
free to share.

Corrections to anything on this page are more welcome than participation.
Six times in this project an "interesting result" turned out to be a broken
instrument, and every one of those was caught by checking the instrument
rather than believing the number.
