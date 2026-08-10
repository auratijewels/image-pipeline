# Next steps

Status as of Milestone 3. Four commits exist locally; none are pushed.

**Your manual tasks live in [YOUR_TASKS.md](YOUR_TASKS.md)** — this file is the
engineering plan.

| Milestone | State |
|---|---|
| 1 — Scaffold, provider interface, registries, run scripts | Done (`1864054`) |
| 2 — Product model, dimensions form, five-angle upload | Done (`19bdb14`) |
| 3 — Background removal + cut-out preview | Done (`d6c0e97`), pending real-photo validation |
| 4 — Scale pipeline end to end for one product | Next — needs a design decision, see below |
| 5 — All 7 image asset types generating | Not started |
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

## Milestone 4 — the scale pipeline

The reason the product exists. Everything before this is plumbing.

### Decide first: the ruler is wrong as specified

`config/anatomy.py` currently calibrates on **earlobe height (19 mm)**, per §4
step C of the brief. Two problems, both found while probing MediaPipe 1.0:

1. **MediaPipe has no earlobe landmark.** Neither `FaceLandmarker` (478 points)
   nor the removed FaceMesh exposes one. The face oval's outermost points sit at
   the tragion, not the lobe. Any earlobe measurement would be inferred from
   surrounding geometry — i.e. guessed.
2. **Earlobe height varies ~15% across adults.** The §10 acceptance criterion is
   **±8%**. Calibrating on a span whose own population variance is nearly double
   the tolerance cannot meet that criterion, however good the detector is.

**Proposed fix — separate the ruler from the anchor.** These are two different
jobs and the brief conflates them:

- **Calibration span** — something detected reliably with low population
  variance, used *only* to derive pixels-per-mm.
- **Mount anchor** — where the product is placed. Can be approximate; being a
  few pixels off is a composition issue, not a scale error.

Candidate calibration spans:

| Mount | Span | mm | Variance | Landmarks |
|---|---|---|---|---|
| Ear, neck | Interpupillary distance | ~62 | ~4% | Very reliable |
| Ear, neck | Bizygomatic (face) width | ~128 | ~5% | Reliable |
| Finger, wrist | Palm width, index-to-pinky MCP | ~78 | ~5% | Reliable |

Interpupillary distance is the strongest option for face-mounted pieces: it is
the most reliably detected span on the face and has the lowest variance of any
candidate. A 4% ruler leaves real headroom under an 8% budget; a 15% ruler
leaves none.

This keeps the §4 architecture exactly as specified — measure, derive px/mm,
scale the real cut-out — and changes only *which* span is measured. Worth
confirming before I write it, since it deviates from the brief's wording.

### Then build

- `pipeline/landmarks.py` — `FaceLandmarker` and `HandLandmarker` via the Tasks
  API. Returns the calibration span in pixels *and* the mount anchor.
- `pipeline/scale.py` — px/mm from the span against the ruler; reject
  detections outside `tolerance_pct` rather than silently scaling off a bad
  landmark. A wrong-but-confident measurement is worse than a refusal.
- `pipeline/composite.py` — resize the cut-out to `primary_mm × px_per_mm`,
  rotate to the body part's axis, composite at the anchor, contact shadow,
  colour-match to the scene.
- Validation: measure the composited product back and assert it lands within
  `SCALE_ACCEPTANCE_PCT`. This is the §10 acceptance criterion and should fail
  loudly in CI, not be eyeballed.

### Setup step not in the brief

**MediaPipe 1.0.0 removed the legacy `mp.solutions` API entirely and ships no
bundled model files** (`has legacy solutions: False`, zero `.tflite`/`.task`
assets in the package). Only the Tasks API remains, and each landmarker needs
its `.task` bundle fetched separately:

- `face_landmarker.task` — ~3.8 MB
- `hand_landmarker.task` — ~7.5 MB

Small, but they need downloading, caching under `models/weights/` (already
git-ignored), and a first-run message so it does not look like a hang the way
the 970 MB BiRefNet download did. Bundle this into `run.ps1` setup rather than
leaving it to first use.

### Sequencing

Build the composite against a **fixed, checked-in scene image** before Gemini
enters the loop. Scale error and generation variance are each tractable alone
and miserable together — with both moving you cannot tell whether the landmark
detector misread the ear or the model simply drew a different one.

---

## Milestones 5–8, in brief

- **5** — Wire the 7 asset types through the orchestrator. DIRECT types go
  straight from cut-out to Gemini; COMPOSITE types run steps B–E. Live progress
  over SSE. This is where spend starts, so the cap in `core/costs.py` gets its
  first real exercise.
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
