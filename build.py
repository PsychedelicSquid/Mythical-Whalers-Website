"""Builds the website into docs/.

    python build.py             words, layouts or styles changed
    python build.py --extract   the game changed: re-read it first

Reads content/, templates/, static/ and game/, checks the result, and only then
rewrites docs/. If anything is wrong it prints every problem and changes nothing.

--extract first copies art out of the game repository into game/. It only reads
the game repository. Look at `git diff game/` before committing: that diff is
everything a game update would change on the site.
"""

import sys

from builder import assets
from builder import check
from builder import extract
from builder import pages
from builder import render


def report(problems):
    print("The build found %d problem(s) and wrote nothing:" % len(problems))
    for problem in problems:
        print("  - " + problem)


def main():
    problems = []

    if "--extract" in sys.argv[1:]:
        lines = extract.extract(problems)
        if problems:
            report(problems)
            return 1
        for line in lines:
            print("  " + line)
        changed, removed = assets.extract(problems)
        if problems:
            report(problems)
            return 1
        print("Extracted game art into game/ (%d changed, %d removed)." % (changed, removed))

    all_pages = pages.load_pages(problems)
    if problems:
        report(problems)
        return 1

    outputs = {}
    render.render_all(all_pages, outputs, problems)
    if problems:
        report(problems)
        return 1

    forward_paths = {}
    for page in all_pages:
        if page["old_url"]:
            forward_paths[page["old_url"][1:] + "index.html"] = True
    check.check_outputs(outputs, forward_paths, problems)
    if problems:
        report(problems)
        return 1

    written, removed = render.write_outputs(outputs)
    print("Built %d pages, %d files in docs/ (%d written, %d removed)."
          % (len(all_pages), len(outputs), written, removed))

    for message in check.tracked_case_mismatches(outputs):
        print("WARNING: " + message)
    return 0


sys.exit(main())
