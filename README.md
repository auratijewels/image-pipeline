# Aurati Studio

An AI product-photography pipeline for **Aurati Jewels**. Upload up to five angles of a
piece, enter its real-world dimensions in millimetres, click Generate — get back a
complete, brand-consistent set of e-commerce and social images in every format Shopify
and the social platforms ask for.

The hard problem this exists to solve: **when jewellery is placed on a human model, it
must appear at its true real-world size.** Text-to-image try-on drifts — a 36 mm earring
comes back looking like a 70 mm chandelier. Aurati Studio eliminates that drift by
design rather than by prompting. See [How the scale pipeline works](#how-the-scale-pipeline-works).

> **v1 is images only.** Video (Veo 3) is deferred to v2. The provider interface and
> asset registry are already generic enough to take a video module without refactoring.

---

## Quick start

```powershell
.\run.ps1
```

First run creates the Python 3.12 venv, installs dependencies (~700 MB of ML wheels),
installs frontend packages, copies `.env.example` to `.env`, and starts both servers.
Subsequent runs skip straight to launch.

| Command | What it does |
|---|---|
| `.\run.ps1` | Setup if needed, then launch backend + frontend |
| `.\run.ps1 -Setup` | Force a clean dependency reinstall |
| `.\run.ps1 -DryRun` | Launch with placeholder images and **zero API spend** |
| `.\run.ps1 -BackendOnly` | API only — docs at `http://127.0.0.1:8000/docs` |
| `run.bat` | Same thing, double-clickable |

Then open **http://localhost:5173**.

---

## Requirements

| | Version | Notes |
|---|---|---|
| Windows | 10 / 11 | Only supported OS for v1 |
| Python | **3.12** | Hard requirement — see below |
| Node.js | 20+ | For the Vite frontend |
| ffmpeg | — | Not needed in v1; required for v2 video |

### Why Python 3.12 specifically

`mediapipe` (landmark detection) and `onnxruntime` (which `rembg` runs on) publish no
wheels for Python 3.13 or 3.14. Both are load-bearing for the scale pipeline, so the
venv is pinned to 3.12 regardless of what `python` resolves to on your PATH:

```powershell
winget install --id Python.Python.3.12 --exact --scope user
```

It installs side-by-side. Your default `python` is untouched — `run.ps1` finds 3.12
through the `py` launcher.

### ffmpeg (v2 only)

Not required for v1. When the video module lands:

```powershell
winget install --id Gyan.FFmpeg
```

---

## Configuration

Copy `.env.example` to `.env` and fill in. `.env` is git-ignored; nothing secret is
ever committed.

| Key | Default | Purpose |
|---|---|---|
| `GOOGLE_API_KEY` | — | **Required.** Get one at [aistudio.google.com/apikey](https://aistudio.google.com/apikey) |
| `GEMINI_IMAGE_MODEL` | `gemini-2.5-flash-image` | Image generation / editing model |
| `IMAGE_PROVIDER` | `gemini` | `gemini` (live) or `dryrun` (free placeholders) |
| `BUDGET_CAP_INR_PER_PRODUCT` | `100` | Hard stop before exceeding; editable in Settings |
| `USD_TO_INR` | `88.0` | Conversion used for the cap |
| `REMBG_MODEL` | `birefnet-general` | Cut-out model; `u2netp` is faster, rougher |
| `BACKEND_PORT` / `FRONTEND_PORT` | `8000` / `5173` | |

If `GOOGLE_API_KEY` is missing, the app **falls back to dry-run** rather than crashing —
you can still explore the UI and the export pipeline.

---

## Architecture

```
                    ┌───────────────────────────────┐
   Browser ────────▶│  React + Vite + Tailwind      │
   localhost:5173   │  upload · progress · gallery  │
                    └──────────────┬────────────────┘
                                   │  /api  (proxied)
                    ┌──────────────▼────────────────┐
                    │  FastAPI  (127.0.0.1:8000)    │
                    │                               │
                    │  api/       routes            │
                    │  core/      assets · formats  │
                    │             costs             │
                    │  pipeline/  cutout · landmarks│
                    │             scale · composite │
                    │  providers/ ImageProvider ABC │
                    │  config/    settings· anatomy │
                    │             prompts           │
                    └───┬───────────────────────┬───┘
                        │                       │
              ┌─────────▼─────────┐   ┌─────────▼──────────┐
              │  Local, free      │   │  Google AI Studio  │
              │  rembg (BiRefNet) │   │  Gemini 2.5 Flash  │
              │  MediaPipe        │   │  Image             │
              │  Pillow / OpenCV  │   │                    │
              └───────────────────┘   └────────────────────┘
```

Everything that touches an AI vendor goes through the `ImageProvider` interface
(`backend/app/providers/base.py`) — two methods, `generate` and `edit`. Swapping in
fal.ai, or adding Veo 3 for v2, means writing one class and registering it.

---

## How the scale pipeline works

The generative model never places the product on the person. It only ever paints the
*scene*. The real product is composited in afterwards at a size derived from
measurement, not from prompting.

```
  A. CUT OUT            rembg / BiRefNet on each uploaded angle
     ───────────▶       clean transparent PNGs, best angle picked per asset type

  B. SCENE ONLY         Gemini generates the model + lighting with NO jewellery
     ───────────▶       seeded from the campaign seed so every product matches

  C. MEASURE            MediaPipe Face/Hand Landmarker finds the mount region
     ───────────▶       earlobe height spans N pixels
                        earlobe height is 19 mm  (config/anatomy.py)
                        ⇒ pixels_per_mm = N / 19

  D. SCALE + PLACE      product resized to  product_mm × pixels_per_mm
     ───────────▶       rotated to the body part's angle, composited at the anchor
                        the size is now measured, not guessed

  E. HARMONIZE          contact shadow, colour-match to scene lighting,
     ───────────▶       optional low-denoise relight pass
                        SSIM check on the product region — if it drifted, discard
                        and retry with lower denoise

  F. NUDGE              size ± and rotate sliders in the UI, defaulted to the
     ───────────▶       computed value, for the rare shot that needs a human eye
```

The anatomical constants in `backend/app/config/anatomy.py` are the reference rulers.
Their accuracy directly bounds the accuracy of every on-model shot, so they are kept in
one file, documented, and overridable per shot.

**Acceptance target:** a 36 mm earring composited onto a generated ear measures 36 mm
against the calibrated earlobe landmark, within ±8%.

---

## Cost and the budget guardrail

Every API call is logged to `data/costs.jsonl` with model, operation, and estimated
cost. Gemini 2.5 Flash Image bills images as output tokens — 1290 tokens per image at
$30/1M ≈ **$0.039 (~₹3.4) per image**. Seven asset types plus retries lands well inside
the default ₹100/product cap.

The cap is checked *before* each call, not after, and the ledger is file-backed so a
crash mid-generation can't silently reset the running total.

---

## Project layout

```
backend/
  app/
    api/          FastAPI routers
    config/       settings · anatomy constants · prompt library
    core/         asset-type registry · format matrix · cost ledger
    providers/    ImageProvider interface · Gemini · dry-run · registry
    main.py
  requirements.txt
frontend/
  src/            React app
docs/
  USAGE.md        walkthrough
run.ps1 / run.bat
```

---

## Documentation

- [docs/USAGE.md](docs/USAGE.md) — step-by-step walkthrough
