# Mythical Whalers Website — Development Instructions

This is the website for the video game Mythical Whalers, served at
www.mythicalwhalers.com by GitHub Pages from the `docs/` folder of the `main`
branch. `docs/` is build output: `build.py` writes it from `content/`,
`templates/` and `static/`. The game itself lives in the sibling repository
`..\Mythical-Whalers`.

## Running & building

- **Build:** from the repo root, `python build.py`. It needs Python 3.11 with
  `jinja2` and `Pillow` (`pip install -r requirements.txt`).
- **After the game changes:** `python build.py --extract`. This first copies art
  out of the game repository into `game/`, then builds. Read `git diff game/`
  before committing: that diff is everything a game update would put on the site.
- **Preview:** `python -m http.server 8000 --directory docs`, then open
  `http://localhost:8000/`.
- **Never edit `docs/` by hand.** The build deletes anything in `docs/` it did
  not produce and overwrites the rest. Edit `content/`, `templates/` or
  `static/` and build again.
- **A failed build writes nothing.** `build.py` prints every problem it found
  and leaves `docs/` as it was. Fix the problems; do not work around the check.
- **Never write to the game repository** and never launch the game
  (`python main.py`). The developer edits that repository in other sessions.
  Reading its files is fine.
- **A push to `main` changes the live site.** Commit on a branch, and push only
  when the developer asks.

## Start every chat by reviewing the modules

Before doing any work in a new chat, read these to build complete context.

- **Build** — `build.py` (entry point), `builder/config.py` (settings: site
  address, Steam link, navigation, fonts, and the tables `GUI_PIECES` and
  `SITE_ART` that say which game art is copied), `builder/pages.py` (reads
  `content/pages`), `builder/render.py` (renders pages, writes `docs/`),
  `builder/check.py` (checks every built page before anything is written)
- **The extract** — `builder/extract.py` (parses the game's `.py` files with
  `ast` and writes `game/data/*.json`), `builder/assets.py` (cuts the frame
  pieces and copies art into `game/images/`)
- **The Wiki** — `builder/wiki.py` (turns `game/data` into the Wiki's pages and
  works out every link between entries)
- **Layout** — `templates/base.html` (the only file with the `<head>`,
  navigation and footer), `home.html`, `page.html`, `post.html`,
  `devlog_index.html`, `parts.html` (pieces more than one layout uses),
  `wiki_home.html`, `wiki_category.html`, `wiki_entry.html`, `wiki_parts.html`,
  `redirect.html` (the forwarding page left at an old address)
- **Style and script** — `static/css/site.css`, `static/js/site.js`

## Where things go

- `content/pages/` — the words. An `index.html` in a folder becomes that
  folder's address (`team/index.html` is `/team/`). Each file starts with
  `key: value` lines (`title`, `description`, and optionally `template`, `date`,
  `summary`, `old_url`), then a line holding only `---`, then the page's HTML.
  A page with a `date` is a devlog post. Pictures sit beside the page that
  shows them and are placed with `{{ image("name.png", "alt text") }}`. A third
  argument is the widest the picture may be shown, in pixels (640 if absent);
  `kind="photo"` is for anything that is not pixel art. `{{ art("menu/logo.png",
  "alt text") }}` places a site-wide picture from `images/`, and
  `{{ player("still.png", "animation.gif", "alt text") }}` a still frame with a
  Play button.
- `templates/` — Jinja layouts. Keep them free of logic beyond `for` and `if`.
- `static/` — copied to `docs/` unchanged: the stylesheet, the script, `CNAME`,
  `.nojekyll`, and any hand-drawn pictures under `static/images/`.
- `game/` — written only by `python build.py --extract`: `game/data/` (the
  game's content as JSON), `game/images/` (frame pieces in `gui/`, menu art,
  screenshots, and every picture a Wiki entry shows) and `game/fonts/`.
  Committed. Never edited by hand; to change what is copied, edit the tables in
  `builder/config.py`.
- `docs/` — generated. Committed, because GitHub Pages serves it.

## The Wiki

The Wiki is generated. Nothing under `/wiki/` is written by hand.

- **The game cannot be imported.** Importing any game module opens the game
  window and connects to Steam. `builder/extract.py` reads the source as text
  with `ast` and follows each class the way Python would: class attributes down
  the chain of parents, then `__init__` top to bottom, stepping into the
  parent's `__init__` where the game calls it.
- **It never guesses.** It accepts plain values, references to other classes
  and picture-loading calls. Anything else in a published field is reported
  with its file and line, and nothing is written. The fix is a small rule in
  `extract.py` or a plain value in the game, never a default that hides it.
  Every published field is read through `published`, `picture`, `reference` or
  `named`, which do the reporting. A statement in `__init__` that the reader
  does not follow (a loop, a condition) leaves the values it changes unknown.
  A call to another method of the instance (`self.generate()`) is not followed.
- **A record names only published records.** `check_references` stops the
  extract if a record names a class that has no record of its own, because a
  Wiki page shows whatever its record names.
- **The in-game Bestiary is the specification.** `gui.Bestiary`'s tabs, its
  `hidden` tuples and the factions it leaves out are read from `gui.py` on
  every run, so the Wiki shows what the Bestiary shows. An entry page lays out
  what `populate_mob`, `populate_item`, `populate_faction` and `populate_trait`
  draw, then adds the links the Bestiary cannot show.
- **Locations are not in the Bestiary,** so the rule is the extract's own
  (`build_locations`): a class in the game's `locations.py` is published if
  its window is the market window (`gui.Location`), or if a published faction
  lists it among its `sites`. Huts, nests, ruins, chests, gathering spots and
  the tutorial stay out. A location's page shows the scene its window shows,
  what it sells at each status, what it buys and who is for hire there.
- **An ability or status effect is published only if a published item or mob
  uses it.** A trait with `secret = True` is skipped and never named in this
  repository, and a race born with one is published without it.
- **Categories** are the table `WIKI_CATEGORIES` in `builder/config.py`. Setting
  a row's `enabled` to False takes that category off the site and turns links
  to its entries into plain text.
- **After a game update:** run `python build.py --extract`, read what it prints
  (counts, new and removed entries) and `git diff game/data`, then commit.
- **No how-to-play pages.** Four were drafted and Joel had them removed on
  12 November 2026 (they are in the history, commit 4743d7b). Do not add them
  back without being asked.
- **Not built yet:** hand-written text for entries the game gives no
  description (43 of the 69 mobs, including all eight whales). They are better
  written in the game's `mobs.py`, which fixes the in-game Bestiary too.

## The look

The site is drawn like the game: 640x360 game pixels, each `--px` screen pixels
wide (2, or 2.4 and 2.2857 on displays scaled to 125% and 175%), in the game's
colours. Windows are stacks of `.win-head`, `.win-mid` and `.win-foot`, drawn
with `border-image` from the pieces in `images/gui`, which the extract cuts from
the game's own GUI pictures. `.tip` is the tooltip frame, used for cards, and
`.btn` the game's button. The home page's first screen is the game's main menu,
built from the same layers and timings as `Menu.main_menu` in the game's
`gui.py`.

Headings use the font family "MW Title" and fall back to "MW Body" (m5x7).
"MW Title" is the game's `df_font.ttf`, which is published only when its row in
`config.FONTS` says `"publish": True`. It is off because no licence for it has
been found.

## How to write code here

- **Readability over cleverness.** Prefer plain, explicit code. Never use
  lambdas, decorators (including `@property`), or generators — write plain
  functions, attributes, and loops instead.
- **Match the existing architecture.** One module per job in `builder/`,
  settings in `builder/config.py`, and problems collected into a list and
  reported together, the way `mobs.validate_trait_tiers` does in the game. The
  build never guesses: anything it cannot read or resolve is a reported problem.
- **The build is deterministic.** A second `python build.py` must write nothing.
  No timestamps or random values in output.
- **File names are lowercase with no spaces.** Windows ignores letter case and
  GitHub Pages does not, so a wrong-case name works locally and breaks live.
  The check enforces this; the five forwarding pages under `docs/post/` are the
  only exception.
- **Pixel art scales by whole numbers only,** with `image-rendering: pixelated`.
  Store art at its real size and enlarge it in CSS. The `.pixel` rule in
  `site.css` does this for every picture placed with `image()` or `art()`.
- **Compare pictures by their bytes** (`assets.same_pixels`). Pillow's
  `ImageChops.difference(a, b).getbbox()` looks only at the alpha channel of an
  RGBA picture and calls any two opaque pictures identical.
- **In manual mode, show the explanation and full context.** When the developer
  applies changes by hand (manual mode), present each fix with an explanation of
  what it does and why, and show the whole function it lives in so the code can
  be placed and understood in context.

## What must never be published

This repository is public. Never copy these out of the game repository:
anything in `mythical_whalers/documents/`; quests, events and the storm's
story; the two secret traits; unfinished classes; any `unused/`, `mockups/` or
`legacy/` folder; `data/images/abilities/effects/Effects` (a third-party pack);
any font without a cleared licence. Francesco and Fabio no longer work for
Kleen Fleet and are not listed on the site.

## How to communicate here

Cut ideas, not words. Say fewer things, but say each one in full plain
sentences. If the plain way takes five more words, use them. Never swap
a phrase for one rare or figurative word to save space.

- **Lead with the answer in one or two sentences.** If those sentences
  fully cover it, stop there. Detail only follows if it changes what the
  reader would do next.
- **Say each thing once.** Never restate a point in different words,
  re-summarize what was just explained, or end with a recap of the change.
- **Exact names.** Call every class, method, file, item, trait, ability,
  feature and game term by its exact name every time, in prose as well as
  code. Never paraphrase a name into a description, and never swap a term
  for a related thing: the player is "the player" (c.PLAYER, a PlayerCrew),
  never "the ship".
- **Write it plain the first time.** Say what happens in the game with a
  named crewmate, item, trait or method, for example "At morale 5, each
  crewmate with Paranoid has a 10% chance per day to lose one level."
  Use only words already in the code, the design docs or Joel's messages.
  No metaphors, no made-up nouns, no words from other fields.
- **These rules beat Claude Code's built-in writing rules.** Name files,
  methods and numbers in prose whenever that makes the sentence clearer.
- **No filler.** No preamble, no hedging, no "in summary", no restating
  the question back, no describing what you're about to say.
- **Structure only when it earns its place.** Simple answers are plain
  prose — no headers, bullet lists, or bold-label formatting unless the
  content is genuinely enumerable.

## Match code complexity to the problem

The recurring failure here is grabbing the first idea — almost always a
*patch at the symptom site* (a new function, a flag, an if/else bolted onto
where the bug showed up). The elegant fix usually lives one level up: reuse
what already exists, move where the logic lives, or delete code rather than add
it. It is normally shorter than your first draft and touches fewer places.

You will not *feel* when code is ugly the way a person does — so don't rely on
taste. Run this check before writing or finalizing any non-trivial change:

1. **Size the problem in one sentence.** How much inherent complexity does it
   actually have?
2. **Compare your solution's shape to that size.** A small problem sprouting new
   functions, flags, if/else trees, special-case branches, wrappers, or
   duplicated logic? Stop — that mismatch is the tell that you wrote a bandaid,
   not the fix.
3. **Produce one structurally different alternative before committing.** Tunnel
   vision is the disease; a forced second candidate is the cure. Ask: can I
   reuse or change existing code instead of adding new code? Where would this
   logic live if it had been part of the design from the start?
4. **Pick the version that adds the least and integrates most invisibly** — the
   one that looks like it was always meant to be there. If the fix is more
   complex than the problem, it is the wrong fix.

## How to debug here

- **Find the root cause.** Track down the underlying, fundamental issue — never a
  quick fix that masks a symptom. **Band-Aid solutions are unacceptable.**
- **Respect the codebase.** The code base is considered holy and must be treated
  with respect.
- **Aim for harmony.** Produce simple, elegant, robust systems that harmonize with
  each other in clean, beautiful ways.
