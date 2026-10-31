# For You: ASCII Letter & Rose Animation

A love-letter animation drawn entirely with text characters:

1. A cream paper envelope (shaded flap and folds, FOR YOU in ink, red wax-seal heart) fades in
2. It waits. Your mouse or finger is a small purple flame.
3. Move it onto the beating wax-seal heart and **touch / click the heart** to open the letter
4. The wax seal catches fire and the paper burns away from it: the paper browns, then a thin glowing edge spreads raggedly, leaving charred curls, with flickering flames, embers, smoke and ash
5. It crumbles away and a red rose (traced from your photo) grows up from a bud and opens into full bloom
6. The leaves and stem fade in, then blue light rays fan out

## Two ways to run it

### Option A: Python (`letter.py`, the version from the video)
- **Windows:** double-click `run.bat`
- **Any OS:** `python letter.py` (or `python3 letter.py`)
- Needs Python 3.8+ from https://www.python.org/downloads/. On Windows, tick **"Add Python to PATH"** when installing.
- It uses only the standard library (tkinter). On Linux you may need `sudo apt install python3-tk`.
- If it crashes, the error is saved to `letter_error.txt`.

### Option B: Browser (`index.html`)
Double-click `index.html`. It opens in Chrome, Edge, Firefox or Safari, works on phones too, and needs no installs.

## Controls
- **Touch / click the heart** to open the letter (clicking anywhere else does nothing). `Space` / `Enter` also opens it.
- Click again at the end to replay
- `R`: replay
- `Esc`: quit (Python)

## Customise
At the top of `letter.py` (or the `<script>` in `index.html`):
- `ENVELOPE_TEXT`: letters on the envelope. Supported letters: F O R Y U L V E I and space.
- `T_*`: timeline of each stage, in seconds
- `BURN_SPEED`: how fast the paper burns
- `PROMPT`: the "touch the heart to open" text
- `TITLE`: window title
