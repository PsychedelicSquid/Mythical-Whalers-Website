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
from builder import wiki


def has_exact_name(folder, name):
    """Windows would open Tavern.png for tavern.png. GitHub Pages would not."""
    return os.path.isdir(folder) and name in os.listdir(folder)


def picture_size(path):
    with Image.open(path) as picture:
        return picture.size


class BodyHelpers:
    """The functions a page's HTML can call, bound to the page being rendered.

    Every picture needs alt text. Pass "" for a picture that only decorates.
    """

    def __init__(self, page, problems):
        self.page = page
        self.problems = problems

    def tag(self, source, path, alt, max_width, kind):
        width, height = picture_size(path)
        if kind == "pixel":
            # --w is the picture's real width; the stylesheet enlarges it by
            # whole numbers up to --max.
            html = '<img class="pixel" style="--w:%d; --max:%dpx"' % (width, max_width)
        else:
            html = '<img class="photo"'
        html += ' src="%s" alt="%s" width="%d" height="%d">' % (escape(source), escape(alt), width, height)
        return Markup(html)

    def need_alt(self, name, alt):
        if alt is None:
            self.problems.append("%s: picture '%s' has no alt text" % (self.page["source"], name))
            return ""
        return alt

    def image(self, name, alt=None, max_width=640, kind="pixel"):
        """A picture from the page's own folder.

        kind "pixel" is pixel art, shown at whole-number sizes up to max_width.
        kind "photo" is anything else: a screenshot of another program, a photo.
        """
        alt = self.need_alt(name, alt)
        folder = self.page["folder"]
        if not has_exact_name(folder, name):
            self.problems.append("%s: no picture named exactly '%s' in its folder" % (self.page["source"], name))
            return Markup("")
        return self.tag(name, os.path.join(folder, name), alt, max_width, kind)

    def art(self, path, alt=None, max_width=640):
        """A site-wide picture under /images/: game art, or a hand-made one in static/."""
        alt = self.need_alt(path, alt)
        relative = path.replace("/", os.sep)
        for root in [config.GAME_OUT_IMAGES, os.path.join(config.STATIC, "images")]:
            full = os.path.join(root, relative)
            if has_exact_name(os.path.dirname(full), os.path.basename(full)):
                return self.tag("/images/" + path, full, alt, max_width, "pixel")
        self.problems.append("%s: no picture at images/%s" % (self.page["source"], path))
        return Markup("")

    def player(self, still, animation, alt=None):
        """A still frame with a Play button that fetches the animation when pressed."""
        alt = self.need_alt(still, alt)
        folder = self.page["folder"]
        for name in [still, animation]:
            if not has_exact_name(folder, name):
                self.problems.append("%s: no file named exactly '%s' in its folder" % (self.page["source"], name))
                return Markup("")
        width, height = picture_size(os.path.join(folder, still))
        html = '<figure class="player">'
        html += '<img class="photo" src="%s" alt="%s" width="%d" height="%d">' % (escape(still), escape(alt), width, height)
        html += '<button class="btn" type="button" data-play="%s" aria-pressed="false">Play</button>' % escape(animation)
        html += '</figure>'
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


def add_tree(outputs, root, prefix, problems):
    """Every file under root goes to docs/ unchanged, under prefix."""
    for folder, folder_names, file_names in os.walk(root):
        folder_names.sort()
        file_names.sort()
        for name in file_names:
            source = os.path.join(folder, name)
            relative = os.path.relpath(source, root).replace(os.sep, "/")
            add_output(outputs, prefix + relative, read_bytes(source), problems)


def add_static_files(outputs, problems):
    """static/ is hand-made; game/ was copied out of the game by the extract.

    A name present in both is reported, so a hand-drawn piece can never
    silently replace a cut one or the other way round.
    """
    add_tree(outputs, config.STATIC, "", problems)
    add_tree(outputs, config.GAME_OUT_IMAGES, "images/", problems)
    add_tree(outputs, config.GAME_OUT_FONTS, "fonts/", problems)


def section_of(address):
    """'/devlog/art/' -> 'devlog'. The home page is 'home'."""
    parts = address.strip("/").split("/")
    if parts[0] == "":
        return "home"
    return parts[0]


def card_of(page, problems):
    """The picture a post shows in lists: its address and real size, or None."""
    name = page["card"]
    if name == "":
        return None
    if not has_exact_name(page["folder"], name):
        problems.append("%s: card picture '%s' is not in its folder" % (page["source"], name))
        return None
    width, height = picture_size(os.path.join(page["folder"], name))
    return {"url": page["url"] + name, "width": width, "height": height}


def page_view(page, problems):
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
        "card": card_of(page, problems),
        # Set for devlog posts by link_posts.
        "older": None,
        "newer": None,
    }


def link_posts(pages, views):
    """Devlog posts are the pages with a date. Returns their views, newest first."""
    dated = []
    for page in pages:
        if page["date"]:
            dated.append((page["date"], page["url"]))
    dated.sort()
    dated.reverse()

    posts = []
    for date, address in dated:
        posts.append(views[address])
    for position in range(len(posts)):
        if position > 0:
            posts[position]["newer"] = posts[position - 1]
        if position + 1 < len(posts):
            posts[position]["older"] = posts[position + 1]
    return posts


def short_hash(data):
    return hashlib.sha1(data).hexdigest()[:8]


def site_context(outputs):
    # Only fonts the extract was allowed to copy get an @font-face rule.
    fonts = []
    for font in config.FONTS:
        if "fonts/" + font["file"] in outputs:
            fonts.append({"family": font["family"], "url": "/fonts/" + font["file"]})

    card_image = ""
    if "images/site/card.png" in outputs:
        card_image = "/images/site/card.png"

    return {
        "name": config.SITE_NAME,
        "tagline": config.TAGLINE,
        "studio": config.STUDIO,
        "url": config.SITE_URL,
        "steam_url": config.STEAM_URL,
        "nav": config.NAV,
        "fonts": fonts,
        "card_image": card_image,
        "stylesheet": "/" + config.STYLESHEET,
        # These change whenever the file does, so browsers fetch the new one.
        "stylesheet_version": short_hash(outputs.get(config.STYLESHEET, b"")),
        "script_version": short_hash(outputs.get("js/site.js", b"")),
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

    views = {}
    for page in pages:
        views[page["url"]] = page_view(page, problems)
    posts = link_posts(pages, views)

    # The Wiki is built first so the other pages can link to its categories.
    try:
        wiki_addresses, site["wiki"] = wiki.build(environment, site, outputs, problems)
    except jinja2.TemplateError as error:
        problems.append("the Wiki: %s: %s" % (type(error).__name__, error))
        return
    if not wiki_addresses:
        # No game data has been extracted: leave the Wiki out of the navigation.
        without_wiki = []
        for item in site["nav"]:
            if item["section"] != "wiki":
                without_wiki.append(item)
        site["nav"] = without_wiki

    sitemap_addresses = list(wiki_addresses)
    for page in pages:
        view = views[page["url"]]
        helpers = BodyHelpers(page, problems)
        try:
            body_template = environment.from_string(page["body"])
            body = body_template.render(site=site, page=view, posts=posts, image=helpers.image,
                                        art=helpers.art, player=helpers.player)
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
