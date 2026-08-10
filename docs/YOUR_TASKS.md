# Your manual tasks

Five things only you can do. Each has a verification step — run it, and you'll know
the task is actually done rather than assuming.

Total: about 20 minutes, most of it task 2.

| # | Task | Time | Blocks |
|---|---|---|---|
| 1 | Grant the GitHub token write access | 3 min | Pushing all 4 commits |
| 2 | Drop real product photos into `samples/` | 10 min | Validating Milestone 3 |
| 3 | Add `GOOGLE_API_KEY` to `.env` | 3 min | Milestone 5 |
| 4 | Hand over the prompt kit | 2 min | Milestone 5 |
| 5 | Answer: 7 asset types or 9? | 30 sec | Milestone 5 |

Tasks 1 and 2 are the ones worth doing now. Tasks 3–5 aren't needed until Milestone 5,
which is two milestones away.

---

## 1. Grant the GitHub token write access

**Why it's stuck:** your `gh` token is a fine-grained PAT
(`github_pat_11CH63PGI0…`). It authenticates correctly as `auratijewels` and can *read*
the repo — but reading a public repo needs no permission at all. It has no write grant,
so the push 403s.

### Steps

1. Go to <https://github.com/settings/personal-access-tokens>
2. Click the token in the list (the one whose name you gave it — it starts
   `github_pat_11CH63PGI0…`)
3. Under **Repository access**, choose **Only select repositories**, then add
   `auratijewels/image-pipeline`
4. Expand **Permissions → Repository permissions**
5. Find **Contents** and set it to **Read and write**
   *(Metadata → Read-only gets enabled automatically. That's expected.)*
6. Scroll down, click **Update token**

No re-authentication needed afterwards — it's the same token, with more rights.

### Verify

```bash
gh api repos/auratijewels/image-pipeline --jq .permissions
```

That already returned `push: true` before, so it proves nothing. Use this instead — it
actually attempts a write:

```bash
gh api -X PATCH repos/auratijewels/image-pipeline -f has_issues=true
```

A wall of JSON = working. `Resource not accessible by personal access token` = the
permission didn't save; redo step 5.

### Then tell me, and I'll push

Or push it yourself from the repo root:

```bash
git push --force -u origin main
```

The `--force` is deliberate and safe: the remote holds a single unrelated "Initial
commit" containing a stub `README.md` that ours replaces. Nothing else is up there.

### If the above doesn't work

Mint an OAuth token instead — one command, broader scope, no web UI fiddling:

```bash
gh auth login --hostname github.com --git-protocol https --web
```

Sign in as **auratijewels** when the browser opens.

---

## 2. Drop real product photos into `samples/`

**Why it matters:** the cut-out stage is validated only against a synthetic test image
right now. That image proves the *algorithm* handles thin strands — every chain link
survived. It proves nothing about how BiRefNet handles *your* lighting, *your*
backgrounds, and real metal reflections.

Everything downstream consumes these cut-outs. If the matte is wrong, every one of the
49 exported images is wrong.

### Steps

1. Put 2–5 photos in `G:\repos\image-pipeline\samples\`
2. Name them `CODE_angle.jpg` if convenient — e.g. `E425_front.jpg`, `J292_left.jpg`.
   Not required, just tidier.

The folder is git-ignored. Nothing you put there is committed or pushed, so it's fine
to use unedited originals.

### Which photos to pick

Choose for *difficulty*, not beauty. A solid pendant on seamless white always cuts out
cleanly and tells us nothing. Pick pieces with:

- **a fine chain** — thin, low-contrast strands break into dashes first
- **prong or claw settings** — small gaps the matte fills in solid
- **polished/mirror metal** — reflects the backdrop and drags the edge outward
- **a busy or low-contrast background** — where the model actually has to work

One awkward photo is worth more than ten clean studio shots. If you have a shot that
looked hard to edit by hand, that's the one.

### Verify

From `G:\repos\image-pipeline\backend`:

```bash
../venv/Scripts/python.exe -m pytest tests/test_cutout.py -k real_photos -v
```

There's a test that automatically picks up whatever is in `samples/` and runs the real
BiRefNet model over each file. It currently reports `SKIPPED` because the folder is
empty. Once photos are there it runs per-file and fails loudly on any matte that
collapsed or kept the background.

Weights are already downloaded and cached, so this takes seconds, not minutes.

---

## 3. Add `GOOGLE_API_KEY` to `.env`

Not needed until Milestone 5. Milestones 3 and 4 run entirely on local models.

### Steps

1. Get a key at <https://aistudio.google.com/apikey> → **Create API key**
2. If `.env` doesn't exist yet, create it from the template:

   ```powershell
   Copy-Item .env.example .env
   ```

3. Open `.env` and paste the key after `GOOGLE_API_KEY=` — no quotes, no spaces:

   ```
   GOOGLE_API_KEY=AIza...
   ```

4. Save. Restart the backend if it's running.

`.env` is git-ignored and will never be committed.

### Verify

```bash
curl -s http://127.0.0.1:8000/api/health
```

Look at `provider`. It should say `gemini`. If it still says `dryrun`, the key is empty
or invalid — the app deliberately falls back rather than crashing, so a bad key looks
like normal operation apart from this field.

### Budget note

The cap is **₹100 per product**, checked *before* each API call, not after. At roughly
₹3.4 per generated image, seven asset types plus retries sits well inside it. Change it
in `.env` via `BUDGET_CAP_INR_PER_PRODUCT` if you want more headroom.

---

## 4. Hand over the prompt kit

§7 of your brief says the `Aurati_Gemini_Prompt_Kit` spreadsheet content would be
pasted. `config/prompts.py` currently holds placeholders I wrote from the brand rules —
they work, but they aren't your copy.

### Steps

Either paste the prompts into chat, or save the spreadsheet content anywhere in the repo
and tell me the path.

### What I need per prompt

- which of the 7 asset types it belongs to
- the prompt text itself

The template **keys** and the `{name}` / `{desc}` / `{dimensions}` / `{category}`
placeholders are the stable contract with the rest of the pipeline. Only the prompt text
gets swapped, so the format you send it in doesn't matter much.

One constraint worth knowing: every product-preserving prompt must keep its opening
line — *"Keep the uploaded piece 100% identical to the reference…"*. A test enforces
this, so if your kit omits it, I'll prepend it rather than drop it.

---

## 5. Answer: 7 asset types or 9?

Thirty seconds, but it changes what Milestone 5 builds.

Your brief contradicts itself:

- §1 step 6 says *"all 9 asset types"*
- the §2 heading says *"THE 9 ASSET TYPES"* — but then lists **7**
- §7 says *"the 9-prompt set"*
- §11 cuts video from v1 entirely

I built **7**, assuming the missing 2 were the video assets you cut in §11.

**Just reply "7 is right" or tell me what the other 2 are.** If it's 9, they're two extra
entries in `core/assets.py` and two extra prompts — small, but better known now than
discovered halfway through Milestone 5.

---

## Not blocking, but worth a decision

**The repo is public.** §8 of the brief said private; you chose public when I flagged
it. Noted and not reopening it — just be aware that once pushed, the prompt library,
brand palette and pipeline architecture become publicly readable and indexable. If you
change your mind, it's one command:

```bash
gh repo edit auratijewels/image-pipeline --visibility private --accept-visibility-change-consequences
```
