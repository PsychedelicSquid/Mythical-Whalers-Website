"""Reads the hand-written pages under content/pages.

A page file starts with a header of "key: value" lines, then a line holding
only ---, then the page's HTML. An index.html becomes its folder's address
(team/index.html is /team/). Any other .html file keeps its own name
(404.html is /404.html). Every other file in a page's folder is a picture
that travels with the page.

Header keys:
    title        the page's name, shown in the browser tab         (required)
    description  one sentence for search engines and link previews (required)
    template     the file in templates/ that lays the page out; page.html if absent
    date         YYYY-MM-DD; a page with a date is a devlog post
    summary      one line shown beside the post in lists
    old_url      the address this page used to have; a forwarding page is written there
"""

import os

from builder import config

REQUIRED_KEYS = ["title", "description"]
KNOWN_KEYS = ["title", "description", "template", "date", "summary", "old_url"]


def read_page_file(path, problems):
    """Split a page file into its header (a dict) and its HTML body."""
    with open(path, encoding="utf-8") as handle:
        text = handle.read()

    lines = text.split("\n")
    meta = {}
    body_start = None
    for number, line in enumerate(lines):
        stripped = line.strip()
        if stripped == "---":
            body_start = number + 1
            break
        if stripped == "":
            continue
        if ":" not in stripped:
            problems.append("%s line %d: expected 'key: value' or ---" % (path, number + 1))
            continue
        key, value = stripped.split(":", 1)
        key = key.strip()
        if key not in KNOWN_KEYS:
            problems.append("%s line %d: unknown header key '%s'" % (path, number + 1, key))
            continue
        meta[key] = value.strip()

    if body_start is None:
        problems.append("%s: no --- line between the header and the HTML" % path)
        return meta, ""

    for key in REQUIRED_KEYS:
        if key not in meta or meta[key] == "":
            problems.append("%s: header has no '%s'" % (path, key))

    body = "\n".join(lines[body_start:])
    return meta, body


def address_for(relative_path):
    """content/pages path -> (address, output path). Both use forward slashes."""
    relative_path = relative_path.replace(os.sep, "/")
    if relative_path == "index.html":
        return "/", "index.html"
    if relative_path.endswith("/index.html"):
        folder = relative_path[:-len("index.html")]
        return "/" + folder, relative_path
    return "/" + relative_path, relative_path


def format_date(text, path, problems):
    """'2022-10-02' -> '2 October 2022'."""
    parts = text.split("-")
    if len(parts) != 3 or not (parts[0].isdigit() and parts[1].isdigit() and parts[2].isdigit()):
        problems.append("%s: date '%s' is not YYYY-MM-DD" % (path, text))
        return text
    month = int(parts[1])
    if month < 1 or month > 12:
        problems.append("%s: date '%s' has no such month" % (path, text))
        return text
    return "%d %s %s" % (int(parts[2]), config.MONTHS[month - 1], parts[0])


def load_pages(problems):
    """Return one dict per page, in address order."""
    pages = []
    for folder, folder_names, file_names in os.walk(config.CONTENT_PAGES):
        folder_names.sort()
        file_names.sort()
        html_names = []
        other_names = []
        for name in file_names:
            if name.lower().endswith(".html"):
                html_names.append(name)
            else:
                other_names.append(name)

        for name in html_names:
            source = os.path.join(folder, name)
            relative = os.path.relpath(source, config.CONTENT_PAGES)
            address, output = address_for(relative)
            meta, body = read_page_file(source, problems)

            page = {
                "source": source,
                "folder": folder,
                "url": address,
                "out": output,
                "meta": meta,
                "body": body,
                "title": meta.get("title", ""),
                "description": meta.get("description", ""),
                "template": meta.get("template", "page.html"),
                "date": meta.get("date", ""),
                "date_text": "",
                "summary": meta.get("summary", ""),
                "old_url": meta.get("old_url", ""),
                "assets": [],
            }
            if page["date"]:
                page["date_text"] = format_date(page["date"], source, problems)

            # Pictures belong to the folder's index.html.
            if name == "index.html":
                out_folder = output[:-len("index.html")]
                for other in other_names:
                    page["assets"].append((os.path.join(folder, other), out_folder + other))
            pages.append(page)

    return pages
