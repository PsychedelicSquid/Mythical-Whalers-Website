# Mythical Whalers website

The website for the game Mythical Whalers, at www.mythicalwhalers.com.

GitHub Pages serves the `docs/` folder of the `main` branch. `docs/` is build
output. Do not edit it by hand.

## Build

Needs Python 3.11 with `jinja2` and `Pillow`:

    pip install -r requirements.txt
    python build.py

`build.py` reads `content/`, `templates/`, `static/` and `game/`, checks the
result, and only then rewrites `docs/`. If it finds a problem (a broken link, a
picture with no alt text, a file name that is not lowercase) it prints every
problem and writes nothing.

After the game changes, run this instead:

    python build.py --extract

It first reads the game repository, which it expects beside this one at
`..\Mythical-Whalers`, and writes what the site needs into `game/`: the game's
content as JSON in `game/data/` and its art in `game/images/`. It only reads
the game repository and never runs it. Read `git diff game/` before committing:
that diff is everything the update would change on the site.

## The Wiki

Every page under `/wiki/` is generated from `game/data/`. It shows what the
in-game Bestiary shows: creatures, crewmate races, weapons, armor, consumables,
cargo, ship upgrades, factions and traits, plus the abilities and status
effects they use. To take a category off the site, set its `enabled` to False
in `WIKI_CATEGORIES` in `builder/config.py`.

## Preview

    python -m http.server 8000 --directory docs

Then open http://localhost:8000/.

## Layout

    build.py       the one command
    builder/       the build code
    templates/     page layouts; base.html holds the <head> and page shell
    content/pages/ the pages: words, and the pictures that belong to them
    static/        copied to docs/ unchanged: stylesheet, script, CNAME
    game/          data, art and fonts read from the game by --extract
    docs/          generated; served by GitHub Pages

## Adding a devlog post

Create `content/pages/devlog/<name>/index.html`:

    title: The title
    description: One sentence for search engines and link previews.
    summary: One line shown beside the post in lists.
    template: post.html
    date: 2026-01-31
    ---
    <h1>The title</h1>
    <p>The post.</p>
    {{ image("picture.png", "What the picture shows.") }}

Put `picture.png` in the same folder, run `python build.py`, and commit.

## Licence

The website's code is under the MIT licence. Game art, text and data are
copyright Kleen Fleet and are not. See `LICENSE`.
