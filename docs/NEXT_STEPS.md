# Next steps

Status as of Milestone 2. Two commits exist locally; neither is pushed.

| Milestone | State |
|---|---|
| 1 — Scaffold, provider interface, registries, run scripts | Done (`1864054`) |
| 2 — Product model, dimensions form, five-angle upload | Done (`19bdb14`) |
| 3 — Background removal + cut-out preview | Next |
| 4 — Scale pipeline end to end for one product | Not started |
| 5 — All 7 image asset types generating | Not started |
| 6 — Format matrix export + ZIP download | Not started |
| 7 — Consistency controls, cost logging, dry-run, error handling | Partly built |
| 8 — Polish, docs, final push | Not started |

---

## Blocked on you

These are ordered by when they start costing time.

### 1. GitHub token cannot write (blocking the push)

The active `gh` token is a fine-grained PAT that resolves to the `auratijewels`
account but has no write grant on this repo. Confirmed directly:

```
{"message":"Resource not accessible by personal access token","status":"403"}
```

Fix either way:

- At <https://github.com/settings/personal-access-tokens>, edit the token, add
  `auratijewels/image-pipeline` under *Repository access*, set *Repository
  permissions → Contents* to **Read and write**. No re-auth needed afterwards.
- Or mint an OAuth token instead: `gh auth login --hostname github.com --web`.

Then:

```powershell
git push --force -u origin main
```

The force is deliberate — the remote holds one unrelated "Initial commit"
containing a stub README that our README supersedes.

Note the repo is currently **public**. §8 of the brief said private; you chose
to leave it public. Flagged once here so the decision is on the record, not to
reopen it.

### 2. Real product photos (needed for Milestone 3)

Background removal quality is the input to everything downstream, and synthetic
test images prove nothing about how BiRefNet handles a fine chain against a
busy background. Two or three real shots of any sample code (J292, E425, R383)
would let Milestone 3 be validated rather than assumed.

### 3. `GOOGLE_API_KEY` (needed for Milestone 5)

Not blocking 3 or 4 — both run entirely on local models. Add it to `.env`
before asset generation starts.

### 4. The Aurati_Gemini_Prompt_Kit (needed for Milestone 5)

`config/prompts.py` currently holds placeholders written from the brand rules
in §7. The keys and `{name}/{desc}/{dimensions}/{category}` placeholders are the
stable contract; only the `template` strings get replaced.

### 5. Unresolved: 7 asset types or 9?

§1 and the §2 heading say "9 asset types" and §7 says "the 9-prompt set", but
§2 lists **7**. The registry has 7, on the assumption the other 2 were the video
assets cut in §11. If the kit arrives with 9 image prompts, two entries get
added to `core/assets.py`.

---

## Milestone 3 — background removal + cut-out preview

The first stage that touches real photographs.

**Build**

- `pipeline/cutout.py` — wrap `rembg` with the `birefnet-general` session.
  Load the session once at process start; it is expensive to construct and
  re-creating it per call would dominate runtime.
- Alpha post-processing: despeckle, close pinholes inside stones, and erode
  the matte by a pixel to kill the light halo that background removal leaves
  on polished metal.
- Cache cut-outs to `data/cutouts/<product_id>/<angle>.png`, keyed on the
  source file's hash so re-running is free but a re-upload invalidates.
- `GET /api/products/{id}/cutouts/{angle}` plus a `POST .../cutouts` trigger.
- UI: cut-out preview beside each uploaded angle, on a checkerboard so the
  alpha channel is actually visible, with a re-run control.

**Watch for**

- First call downloads model weights. birefnet-general is **~970 MB**, several
  minutes on a normal connection, and rembg reports progress only to stderr —
  from the API's side the call simply blocks. Surface it in the step log or it
  reads as a hang. An interrupted download leaves a `tmp*` file in
  `%USERPROFILE%\.u2net\` and does not resume; delete it and re-run.
- `rembg` is synchronous and slow enough to block the event loop. Run it in a
  worker thread, not inline in the request handler.
- Fine chains and prong settings are where mattes fail. That is the quality
  bar, not the solid pendant body.

**Done when** a real Aurati photo produces a transparent PNG with clean edges
on a chain, cached, previewed in the UI, and covered by a test that asserts
the output actually carries a non-trivial alpha channel.

---

## Milestone 4 — the scale pipeline

The reason the product exists. Everything before this is plumbing.

- `pipeline/landmarks.py` — MediaPipe Face Landmarker (earlobe, neck) and Hand
  Landmarker (finger, wrist). Return the anchor point *and* the measured span
  in pixels.
- `pipeline/scale.py` — pixels-per-mm from the measured span against the ruler
  in `config/anatomy.py`; reject detections whose aspect falls outside the
  ruler's `tolerance_pct` rather than silently scaling off a bad landmark.
- `pipeline/composite.py` — resize the cut-out to `primary_mm × px_per_mm`,
  rotate to the body part's axis, composite at the anchor, add a contact
  shadow and colour-match to the scene.
- Validation: measure the composited product back against the landmark and
  assert it lands within the ±8% in `SCALE_ACCEPTANCE_PCT`. This is the §10
  acceptance criterion and should fail loudly in CI, not be eyeballed.

**Sequencing note.** Build the composite against a *fixed* checked-in scene
image first, so the scale maths is verified deterministically before Gemini is
in the loop. Debugging measurement error and generation variance at the same
time is much harder than doing them in order.

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
- **FastAPI 0.141 nests included routes** under an `_IncludedRouter` object
  rather than flattening them into `app.routes`. Introspecting `app.routes`
  will wrongly suggest routers never registered — test over HTTP instead.
  `test_meta_endpoints_are_reachable` guards this.
- **ffmpeg is not installed.** Irrelevant for v1; needed if video ships in v2.
