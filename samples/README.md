# Sample product photos

Drop real Aurati product shots here to test the pipeline against something
other than synthetic images. The directory is git-ignored except for this file
— nothing you put here is committed or pushed.

Naming is free-form, but `<code>_<angle>.jpg` (e.g. `E425_front.jpg`) lets the
test helpers pick them up automatically.

## What makes a useful test image

Background removal is easy on a solid pendant against seamless white, and that
is not where it fails. The matte quality that matters is:

- **fine chains** — thin, low-contrast strands are the first thing to break up
- **prong and claw settings** — small gaps the matte tends to fill in
- **polished metal** — reflects the background, which pulls the edge with it
- **busy or low-contrast backgrounds** — where the model actually has to work

One piece exhibiting two or three of those is worth more than ten clean
studio shots.
