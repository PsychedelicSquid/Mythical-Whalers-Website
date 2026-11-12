"""Checks the built site before anything is written to docs/.

Every problem is collected and reported together, the way
mobs.validate_trait_tiers does in the game. A build with problems writes nothing.
"""

import os
import subprocess
from html.parser import HTMLParser
from urllib.parse import unquote

from builder import config

# Addresses the check does not follow.
OUTSIDE_PREFIXES = ["http://", "https://", "mailto:", "tel:", "data:", "#"]


class PageScan(HTMLParser):
    """Collects what the checks need from one HTML file."""

    def __init__(self):
        HTMLParser.__init__(self, convert_charrefs=True)
        self.titles = 0
        self.h1s = 0
        self.has_description = False
        self.is_forward = False
        self.links = []      # (attribute name, value)
        self.images = []     # dict of attributes

    def handle_starttag(self, tag, attrs):
        attributes = {}
        for name, value in attrs:
            attributes[name] = value

        if tag == "title":
            self.titles += 1
        if tag == "h1":
            self.h1s += 1
        if tag == "meta":
            if attributes.get("name") == "description" and attributes.get("content"):
                self.has_description = True
            if attributes.get("http-equiv") == "refresh":
                self.is_forward = True
        if tag == "img":
            self.images.append(attributes)
        if "href" in attributes and attributes["href"] is not None:
            self.links.append(("href", attributes["href"]))
        if "src" in attributes and attributes["src"] is not None:
            self.links.append(("src", attributes["src"]))


def is_outside(address):
    for prefix in OUTSIDE_PREFIXES:
        if address.startswith(prefix):
            return True
    return False


def target_of(address, page_path):
    """The docs/ path an address on a page points at."""
    address = address.split("#")[0].split("?")[0]
    address = unquote(address)
    if address.startswith("/"):
        target = address[1:]
    else:
        folder = ""
        if "/" in page_path:
            folder = page_path.rsplit("/", 1)[0] + "/"
        target = folder + address
    if target == "" or target.endswith("/"):
        target += "index.html"
    return target


def check_page(path, data, outputs, lowercase_paths, problems):
    scan = PageScan()
    scan.feed(data.decode("utf-8"))

    if scan.titles != 1:
        problems.append("docs/%s: has %d <title> tags, needs exactly 1" % (path, scan.titles))

    if not scan.is_forward:
        if scan.h1s != 1:
            problems.append("docs/%s: has %d <h1> headings, needs exactly 1" % (path, scan.h1s))
        if not scan.has_description:
            problems.append("docs/%s: has no description" % path)

    for attributes in scan.images:
        source = attributes.get("src", "")
        if "alt" not in attributes or attributes["alt"] is None:
            problems.append("docs/%s: picture %s has no alt text" % (path, source))
        if not attributes.get("width") or not attributes.get("height"):
            problems.append("docs/%s: picture %s has no width and height" % (path, source))

    for kind, address in scan.links:
        if address == "" or is_outside(address):
            continue
        target = target_of(address, path)
        if target in outputs:
            continue
        if target.lower() in lowercase_paths:
            problems.append("docs/%s: %s=\"%s\" differs only in letter case from docs/%s"
                            % (path, kind, address, lowercase_paths[target.lower()]))
        else:
            problems.append("docs/%s: %s=\"%s\" points at nothing" % (path, kind, address))


def check_outputs(outputs, forward_paths, problems):
    """forward_paths are the old addresses kept as forwarding pages; they may have spaces."""
    lowercase_paths = {}
    for path in outputs:
        lowered = path.lower()
        if lowered in lowercase_paths:
            problems.append("docs/%s and docs/%s differ only in letter case" % (path, lowercase_paths[lowered]))
        lowercase_paths[lowered] = path

    paths = list(outputs.keys())
    paths.sort()
    for path in paths:
        if path not in forward_paths and path != "CNAME":
            if path != path.lower() or " " in path:
                problems.append("docs/%s: file names must be lowercase with no spaces" % path)
        if path.endswith(".html"):
            check_page(path, outputs[path], outputs, lowercase_paths, problems)


def tracked_case_mismatches(outputs):
    """Files git tracks under docs/ whose letter case differs from the built file.

    Windows hides this; GitHub Pages serves the name git has. Returns a list of
    messages, empty when git is not available.
    """
    try:
        result = subprocess.run(["git", "-c", "core.quotepath=off", "ls-files", "docs"],
                                cwd=config.REPO, capture_output=True, text=True, encoding="utf-8")
    except OSError:
        return []
    if result.returncode != 0:
        return []

    built = {}
    for path in outputs:
        built[("docs/" + path).lower()] = "docs/" + path

    messages = []
    for tracked in result.stdout.split("\n"):
        tracked = tracked.strip()
        if tracked == "":
            continue
        wanted = built.get(tracked.lower())
        if wanted is not None and wanted != tracked:
            messages.append("git tracks %s but the site needs %s: run  git mv \"%s\" \"%s\""
                            % (tracked, wanted, tracked, wanted))
    return messages
