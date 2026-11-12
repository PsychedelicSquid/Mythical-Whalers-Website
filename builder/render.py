"""Turns pages into the files under docs/.

Nothing is written until every page has rendered and every check has passed,
so a failed build leaves docs/ exactly as it was.
"""

import hashlib
import os

import jinja2
from markupsafe import Markup, escape
from PIL import Image

from builder import config


class BodyHelpers:
    """The functions a page's HTML can call, bound to the page being rendered."""

    def __init__(self, page, problems):
        self.page = page
        self.problems = problems

    def image(self, name, alt=None, css_class=""):
        """An <img> for a picture in the page's own folder, with its real size.

        alt is required. Pass "" for a picture that only decorates.
        """
        folder = self.page["folder"]
        path = os.path.join(folder, name)
        if alt is None:
            self.problems.append("%s: image('%s') has no alt text" % (self.page["source"], name))
            alt = ""
        if name not in os.listdir(folder):
            # Windows would open Tavern.png for tavern.png. GitHub Pages would not.
            self.problems.append("%s: no picture named exactly '%s' in its folder" % (self.page["source"], name))
            return Markup("")

        with Image.open(path) as picture:
            width, height = picture.size

        html = "<img"
        if css_class:
            html += ' class="%s"' % escape(css_class)
        html += ' src="%s" alt="%s" width="%d" height="%d">' % (escape(name), escape(alt), width, height)
        return Markup(html)


def make_environment():
    return jinja2.Environment(
        loader=jinja2.FileSystemLoader(config.TEMPLATES),
        autoescape=True,
        undefined=jinja2.StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )


def read_bytes(path):
    with open(path, "rb") as handle:
        return handle.read()


def add_output(outputs, relative, data, problems):
    if relative in outputs:
        problems.append("two sources both produce docs/%s" % relative)
        return
    outputs[relative] = data


def add_static_files(outputs, problems):
    """Everything under static/ is copied to docs/ unchanged."""
    for folder, folder_names, file_names in os.walk(config.STATIC):
        folder_names.sort()
        file_names.sort()
        for name in file_names:
            source = os.path.join(folder, name)
            relative = os.path.relpath(source, config.STATIC).replace(os.sep, "/")
            add_output(outputs, relative, read_bytes(source), problems)


def section_of(address):
    """'/devlog/art/' -> 'devlog'. The home page is 'home'."""
    parts = address.strip("/").split("/")
    if parts[0] == "":
        return "home"
    return parts[0]


def page_view(page):
    """What a template is given about a page."""
    title = page["title"]
    if page["url"] == "/":
        full_title = config.SITE_NAME
    else:
        full_title = "%s - %s" % (title, config.SITE_NAME)
    return {
        "title": title,
        "full_title": full_title,
        "description": page["description"],
        "url": page["url"],
        "section": section_of(page["url"]),
        "date": page["date"],
        "date_text": page["date_text"],
        "summary": page["summary"],
    }


def newest_first(pages):
    """Devlog posts are the pages with a date."""
    dated = []
    for page in pages:
        if page["date"]:
            dated.append((page["date"], page["url"], page))
    dated.sort()
    dated.reverse()
    posts = []
    for date, address, page in dated:
        posts.append(page_view(page))
    return posts


def site_context(outputs):
    stylesheet = outputs.get(config.STYLESHEET, b"")
    return {
        "name": config.SITE_NAME,
        "studio": config.STUDIO,
        "url": config.SITE_URL,
        "steam_url": config.STEAM_URL,
        "stylesheet": "/" + config.STYLESHEET,
        # Changes whenever the stylesheet does, so browsers fetch the new one.
        "stylesheet_version": hashlib.sha1(stylesheet).hexdigest()[:8],
    }


def build_sitemap(addresses):
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for address in addresses:
        lines.append("  <url><loc>%s%s</loc></url>" % (config.SITE_URL, escape(address)))
    lines.append("</urlset>")
    return "\n".join(lines) + "\n"


def render_all(pages, outputs, problems):
    """Fill outputs with {path under docs/: bytes} for the whole site."""
    add_static_files(outputs, problems)

    environment = make_environment()
    site = site_context(outputs)
    posts = newest_first(pages)
    sitemap_addresses = []

    for page in pages:
        view = page_view(page)
        helpers = BodyHelpers(page, problems)
        try:
            body_template = environment.from_string(page["body"])
            body = body_template.render(site=site, page=view, posts=posts, image=helpers.image)
            layout = environment.get_template(page["template"])
            html = layout.render(site=site, page=view, posts=posts, body=Markup(body))
        except jinja2.TemplateError as error:
            problems.append("%s: %s: %s" % (page["source"], type(error).__name__, error))
            continue

        add_output(outputs, page["out"], html.encode("utf-8"), problems)
        for source, relative in page["assets"]:
            add_output(outputs, relative, read_bytes(source), problems)

        if page["out"] != "404.html":
            sitemap_addresses.append(page["url"])

        # A page that moved leaves a forwarding page at its old address.
        if page["old_url"]:
            old = page["old_url"]
            if not (old.startswith("/") and old.endswith("/")):
                problems.append("%s: old_url must start and end with /" % page["source"])
                continue
            stub = environment.get_template("redirect.html")
            stub_html = stub.render(site=site, page=view)
            add_output(outputs, old[1:] + "index.html", stub_html.encode("utf-8"), problems)

    sitemap_addresses.sort()
    add_output(outputs, "sitemap.xml", build_sitemap(sitemap_addresses).encode("utf-8"), problems)
    robots_lines = ["User-agent: *", "Allow: /", "Sitemap: %s/sitemap.xml" % config.SITE_URL]
    robots = "\n".join(robots_lines) + "\n"
    add_output(outputs, "robots.txt", robots.encode("utf-8"), problems)


def write_outputs(outputs):
    """Make docs/ hold exactly the built files. Returns (written, removed)."""
    removed = 0
    # First remove what the build no longer produces. Names are compared exactly,
    # so a file whose name changed only in letter case is removed here and
    # written again below under its new name.
    for folder, folder_names, file_names in os.walk(config.DOCS):
        for name in file_names:
            full = os.path.join(folder, name)
            relative = os.path.relpath(full, config.DOCS).replace(os.sep, "/")
            if relative not in outputs:
                os.remove(full)
                removed += 1

    written = 0
    relatives = list(outputs.keys())
    relatives.sort()
    for relative in relatives:
        full = os.path.join(config.DOCS, relative.replace("/", os.sep))
        data = outputs[relative]
        if os.path.isfile(full) and read_bytes(full) == data:
            continue
        folder = os.path.dirname(full)
        if not os.path.isdir(folder):
            os.makedirs(folder)
        with open(full, "wb") as handle:
            handle.write(data)
        written += 1

    # Remove folders the build emptied, deepest first.
    for folder, folder_names, file_names in os.walk(config.DOCS, topdown=False):
        if folder != config.DOCS and len(os.listdir(folder)) == 0:
            os.rmdir(folder)

    return written, removed
