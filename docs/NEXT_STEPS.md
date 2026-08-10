# Next steps

Status as of Milestone 4. Pushed to `auratijewels/image-pipeline`.

**Your manual tasks live in [YOUR_TASKS.md](YOUR_TASKS.md)** — this file is the
engineering plan.

| Milestone | State |
|---|---|
| 1 — Scaffold, provider interface, registries, run scripts | Done (`1864054`) |
| 2 — Product model, dimensions form, five-angle upload | Done (`19bdb14`) |
| 3 — Background removal + cut-out preview | Done (`d6c0e97`), pending real-photo validation |
| 4 — Scale pipeline end to end for one product | Done, pending a real generated scene |
| 5 — All 7 image asset types generating | Next — needs `GOOGLE_API_KEY` |
| 6 — Format matrix export + ZIP download | Not started |
| 7 — Consistency controls, cost logging, dry-run, error handling | Partly built |
| 8 — Polish, docs, final push | Not started |

---

## Blocked on you

Full instructions with verification steps: **[YOUR_TASKS.md](YOUR_TASKS.md)**.

| # | Task | Blocks |
|---|---|---|
| 1 | Grant the GitHub PAT *Contents: Read and write* | Pushing 4 commits |
| 2 | Put real product photos in `samples/` | Validating Milestone 3 |
| 3 | `GOOGLE_API_KEY` in `.env` | Milestone 5 |
| 4 | The Aurati_Gemini_Prompt_Kit | Milestone 5 |
| 5 | Confirm 7 asset types vs 9 | Milestone 5 |

Nothing on that list blocks Milestone 4 — it runs entirely on local models.

---

## Milestone 3 — done (`d6c0e97`)

Cut-out via rembg/BiRefNet, cached against the source hash, trimmed to the
product bounding box, previewed on a checkerboard in the UI.

Verified against a synthetic image with a fine chain and a claw setting: every
link survived individually and the hoop interior stayed transparent, so the
pinhole-closing step correctly distinguished a real gap from a defect.

**Still open:** validation against real photographs. `test_cutout.py` runs the
real model over anything in `samples/` and is skipped while that folder is
empty — see task 2.

---

## Milestone 4 — done

The reason the product exists. Built and verified deterministically:

- `config/anatomy.py` — calibration spans separated from mount anchors.
- `pipeline/mp_assets.py` — downloads and caches the `.task` bundles.
- `pipeline/landmarks.py` — face and hand readings that **reject rather than
  guess** when the two rulers disagree or a face is too small to calibrate from.
- `pipeline/scale.py` — pure millimetre arithmetic, no imagery.
- `pipeline/composite.py` — scale, rotate, place, contact shadow, relight, then
  measure the finished pixels back against the true size.

**Proof:** a 36 mm earring cut-out composited at a pinned 5 px/mm measures
exactly 180 px, +0.0% error. 110 tests pass, including the ±8% boundary at
7.99% (pass) and 8.3% (fail), and scale invariance across cut-out resolutions
from 60×200 to 300×1000.

**Still open:** the landmark layer is verified against synthetic landmark sets,
not a real generated scene — there was no face image to test against, and one
should not be committed to a public repo. `test_landmarks.py` runs the real
model over anything dropped in `samples/scenes/` and is skipped while that is
empty. The first Gemini-generated scene in Milestone 5 closes this.

### The design decision taken here

`config/anatomy.py` originally calibrated on **earlobe height (19 mm)**, per §4
step C of the brief. Two problems, both found while probing MediaPipe 1.0:

1. **MediaPipe has no earlobe landmark.** Neither `FaceLandmarker` (478 points)
   nor the removed FaceMesh exposes one. The face oval's outermost points sit at
   the tragion, not the lobe. Any earlobe measurement would be inferred from
   surrounding geometry — i.e. guessed.
2. **Earlobe height varies ~15% across adults.** The §10 acceptance criterion is
   **±8%**. Calibrating on a span whose own population variance is nearly double
   the tolerance cannot meet that criterion, however good the detector is.

**Fix, agreed 2026-08-10 — separate the ruler from the anchor.** These are two
different jobs and the brief conflates them:

- **Calibration span** — something detected reliably with low population
  variance, used *only* to derive pixels-per-mm.
- **Mount anchor** — where the product is placed. Can be approximate; being a
  few pixels off is a composition issue, not a scale error.

Spans in use:

| Detector | Role | Span | mm | Variance |
|---|---|---|---|---|
| Face | primary | Interpupillary distance | 62 | ~4% |
| Face | cross-check | Bizygomatic width | 128 | ~5% |
| Hand | primary | Palm width, index-to-pinky MCP | 78 | ~5% |

Interpupillary distance is the primary ruler for face-mounted pieces: the most
reliably detected span on the face, and at ~4% it leaves real headroom under an
8% budget where a 15% ruler leaves none. Face width is measured independently;
when the two disagree by more than 12% the detection is untrustworthy (head
turned too far, partial occlusion) and the shot is **rejected** rather than
silently mis-scaled.

The hand has no cross-check on purpose — every candidate second span shares the
same MCP landmarks, so agreement would be circular and prove nothing. This is
asserted in the tests so nobody "fixes" it later.

The brief's 19 mm earlobe figure survives as a *diagnostic*: the generated
model's ear region is inferred from the IPD-derived scale and warns when
anatomically implausible, catching a malformed generation without letting it
drive scale.

This keeps the §4 architecture exactly as specified — measure, derive px/mm,
scale the real cut-out — and changes only *which* span is measured.

### Setup step not in the brief

**MediaPipe 1.0.0 removed the legacy `mp.solutions` API entirely and ships no
bundled model files** (`has legacy solutions: False`, zero `.tflite`/`.task`
assets in the package). Only the Tasks API remains, and each landmarker needs
its `.task` bundle fetched separately:

- `face_landmarker.task` — ~3.8 MB
- `hand_landmarker.task` — ~7.5 MB

Handled by `pipeline/mp_assets.py`: downloads on first use, caches under
`models/weights/` (git-ignored), writes to a `.partial` file and swaps
atomically so an interrupted run cannot leave a truncated bundle that fails
opaquely inside MediaPipe. Measured sizes match the estimates — 3.76 MB and
7.82 MB.

**Outstanding:** move this into `run.ps1` setup so it happens alongside the
dependency install rather than on first use.

---

## Milestones 5–8, in brief

- **5** — Wire the 7 asset types through the orchestrator. DIRECT types go
  straight from cut-out to Gemini; COMPOSITE types run steps B–E. Live progress
  over SSE. This is where spend starts, so the cap in `core/costs.py` gets its
  first real exercise. The first generated scene also closes the outstanding
  landmark validation — save one into `samples/scenes/` when it appears.
- **6** — Smart-crop export across the 7-format matrix and ZIP packaging.
  Subject-aware cropping matters most for 1.91:1 Facebook, where a centre crop
  of a 4:5 portrait decapitates the model.
- **7** — Campaign seed and style controls, cost display, regenerate-one,
  and the size/rotate nudge sliders from §4F.
- **8** — Run all 12 sample codes end to end, finish docs, push.

---

## Already in place ahead of schedule

Some of Milestone 7 landed early because it was cheaper to build in than to
retrofit:

- Dry-run provider — full pipeline exercise at zero API cost (`-DryRun`).
- File-backed cost ledger with the cap checked *before* each call.
- Provider fallback to dry-run when `GOOGLE_API_KEY` is absent, so a missing
  key degrades instead of crashing.
- `Product.blockers` as a computed field, so every "not ready" state explains
  itself.

---

## Known environment quirks

- **Python is pinned to 3.12.** `mediapipe` and `onnxruntime` ship no wheels
  for 3.13/3.14. `run.ps1` resolves 3.12 through the `py` launcher and refuses
  to build the venv otherwise.
- **MediaPipe 1.0 dropped `mp.solutions`.** Every FaceMesh/Hands tutorial you
  will find online uses that API and will not run. Use `mediapipe.tasks.python
  .vision` instead, and download the `.task` bundles yourself — the package
  contains no model assets.
- **BiRefNet weights are ~970 MB**, cached in `%USERPROFILE%\.u2net\`. An
  interrupted download does not resume and leaves a `tmp*` file behind; delete
  it before retrying.
- **FastAPI 0.141 nests included routes** under an `_IncludedRouter` object
  rather than flattening them into `app.routes`. Introspecting `app.routes`
  will wrongly suggest routers never registered — test over HTTP instead.
  `test_meta_endpoints_are_reachable` guards this.
- **ffmpeg is not installed.** Irrelevant for v1; needed if video ships in v2.
