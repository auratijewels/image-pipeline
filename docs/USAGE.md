# Aurati Studio — walkthrough

A written version of the demo. Follow it top to bottom the first time.

---

## 0. One-time setup

1. Install Python 3.12 (side-by-side, your default Python is untouched):

   ```powershell
   winget install --id Python.Python.3.12 --exact --scope user
   ```

2. Get a Google AI Studio key at <https://aistudio.google.com/apikey>.

3. From the repo root:

   ```powershell
   .\run.ps1
   ```

   The first run takes several minutes — it downloads ~700 MB of ML wheels. It will
   create a `.env` for you and tell you to fill it in.

4. Open `.env`, paste your key into `GOOGLE_API_KEY=`, save.

5. Re-run `.\run.ps1`. Open <http://localhost:5173>.

**Before you spend anything**, try dry-run mode. It exercises the entire pipeline —
progress log, compositing, format export, ZIP packaging — using placeholder images and
zero API calls:

```powershell
.\run.ps1 -DryRun
```

---

## 1. Create a product

Products dashboard → **New product**.

| Field | Example | Why it matters |
|---|---|---|
| Product code | `E425` | Used in output filenames |
| Name | Cascade Drop Earrings | Injected into every prompt |
| Category | Earrings | Selects the anatomical ruler used for scale |
| Description | Waterproof gold-tone, freshwater pearl | Injected into every prompt |
| **Dimensions (mm)** | drop `36`, width `12` | **Mandatory.** This is the number the whole scale pipeline is built around |

Get the dimensions right. Everything downstream is measured against them — an error
here propagates into every on-model shot.

---

## 2. Upload angles

Five labelled drop slots: **front**, **back**, **left**, **right**, **extra**.

- **Front is required.** The others are optional but strongly recommended — the pipeline
  picks the most flattering angle per asset type (front for the white hero, side for
  on-ear shots), and with only one angle every output uses the same view.
- Shoot on a plain contrasting background if you can. Background removal is good, but
  a busy background costs you edge quality on chains and prongs.
- The **extra** slot is a good place for a scale or detail shot.

---

## 3. Check the cut-outs

Save the product, then hit **Remove backgrounds** in the Cut-outs panel.

Each uploaded angle becomes a transparent PNG, shown on a checkerboard so you can
actually see the alpha channel — on a flat background a bad matte looks identical to a
good one.

**Judge them on the hard parts, not the easy ones.** A solid pendant against seamless
white always cuts out cleanly and tells you nothing. What to look at:

- **chains** — thin strands are the first thing to break into dashes
- **prong and claw settings** — small gaps the matte tends to fill in solid
- **polished metal edges** — reflections pull the boundary outward into a halo

Each tile reports what percentage of the frame survived. That number is a sanity check,
not a quality score: very low means the matte collapsed, very high means it kept the
background. Anything flagged **check source** hit one of those extremes.

Cut-outs are cached, so re-opening a product is instant. Re-uploading an angle
invalidates its cut-out automatically. **Re-run all** forces a rebuild if you have
changed `REMBG_MODEL`.

---

## 4. Generate

Click **Generate**. The processing view streams a live step log:

```
  cut-out            removing background from 4 angles (BiRefNet)
  scale calibration  earlobe ruler: 19 mm  ->  4.71 px/mm
  scene generation   3 scenes, seed 20260101
  compositing        placing 36 mm drop at 170 px
  realism pass       contact shadow + relight, SSIM 0.97 (pass)
  formatting         7 assets x 7 formats = 49 exports
```

You also see running spend against the ₹100 cap and a **Cancel** button. If a call
would push you past the cap, generation stops and warns rather than continuing.

---

## 5. Review results

Results are grouped by the seven asset types. Each shows every format variant with an
individual download, plus **Download All (ZIP)**.

Two controls matter:

- **Regenerate this one** — re-rolls a single asset without redoing the rest.
- **Size ± / Rotate** (on-model shots only) — the sliders default to the computed
  value. You should rarely need them; they exist for the shot where landmark detection
  picked an awkward anchor.

**Check the scale first.** On-model shots display the derived pixels-per-mm and the
measured size. If a 36 mm earring reports 36 mm ±8%, the pipeline did its job.

---

## 6. Campaign consistency

Settings → **Campaign style**.

The seed and style string are applied to every product in the catalogue. Leave them
alone once you start a campaign — changing the seed mid-catalogue means your first ten
products and your next ten won't look like the same shoot.

---

## 7. Prompt library

Settings → **Prompts**. All seven templates are editable, with `{name}`, `{desc}`,
`{dimensions}` and `{category}` auto-filled per product.

One rule: every product-preserving template must keep its opening line —

> Keep the uploaded piece 100% identical to the reference — exact shape, proportions,
> stones, links and gold finish. Do not redesign.

Overrides persist to `data/prompt_overrides.json`. Delete that file to return to
defaults.

---

## Troubleshooting

**"Python 3.12 was not found"** — run the winget command in step 0.1. `run.ps1`
deliberately refuses to build the venv on 3.13/3.14 because MediaPipe and onnxruntime
have no wheels there; it would fail deeper in with a much worse error.

**Provider shows `dryrun` when you expected `gemini`** — `GOOGLE_API_KEY` is empty or
invalid. The app falls back rather than crashing so the UI stays usable. Check `.env`.

**First cut-out seems to hang** — it is downloading the BiRefNet model, ~970 MB.
Progress appears in the backend console, not the UI. If it was interrupted, clear the
partial file and re-run; the download does not resume:

```powershell
Remove-Item "$env:USERPROFILE\.u2net\tmp*" -Force
```

**Cut-out has ragged edges on a chain** — confirm `REMBG_MODEL=birefnet-general`
(`u2netp` is much rougher), and re-shoot against a plain contrasting background.

**Product looks the wrong size on the model** — check the dimensions you entered first;
that's the cause nine times out of ten. If they're right, the landmark detector picked
a poor anchor: use the size slider, or regenerate to get a different scene.

**Budget cap hit early** — each regeneration costs another call. Raise the cap in
Settings, or work in `-DryRun` while you're iterating on prompts.
