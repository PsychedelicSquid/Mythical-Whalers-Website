"""Copies art out of the game repository into game/.

Run by `python build.py --extract`. It only reads the game repository. A file
leaves the game for one reason: a row in config names it. No folder is ever
copied whole, so drafts and cut content stay behind.
"""

import ast
import io
import os
import shutil

from PIL import Image

from builder import config


def find_source(relative, problems):
    """The real path of a game picture, or None.

    Windows opens Sword.png when asked for sword.png. The folder is listed and
    compared exactly so a wrong-case name is reported instead of hidden.
    """
    for folder in config.FORBIDDEN_FOLDERS:
        if folder in relative.replace("\\", "/").split("/"):
            problems.append("refused to copy %s: '%s' folders are never published" % (relative, folder))
            return None

    path = config.GAME_IMAGES
    for part in relative.replace("\\", "/").split("/"):
        if not os.path.isdir(path):
            problems.append("game picture not found: %s" % relative)
            return None
        names = os.listdir(path)
        if part in names:
            path = os.path.join(path, part)
            continue
        match = None
        for name in names:
            if name.lower() == part.lower():
                match = name
        if match is None:
            problems.append("game picture not found: %s" % relative)
            return None
        print("  note: %s is spelled %s on disk" % (relative, match))
        path = os.path.join(path, match)
    return path


def open_picture(relative, cache, problems):
    if relative in cache:
        return cache[relative]
    path = find_source(relative, problems)
    if path is None:
        return None
    with Image.open(path) as picture:
        loaded = picture.convert("RGBA")
    cache[relative] = loaded
    return loaded


def cut_piece(piece, cache, problems):
    """Assemble a frame piece from the ranges in its config row."""
    source = open_picture(piece["source"], cache, problems)
    if source is None:
        return None
    if "columns" not in piece:
        result = source.copy()
    else:
        # Work out each column as (picture, first, last).
        columns = []
        for column in piece["columns"]:
            if len(column) == 3:
                other = open_picture(column[0], cache, problems)
                if other is None:
                    return None
                columns.append((other, column[1], column[2]))
            else:
                columns.append((source, column[0], column[1]))

        width = 0
        for picture, first, last in columns:
            width += last - first + 1
        height = 0
        for first, last in piece["rows"]:
            height += last - first + 1

        result = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        y = 0
        for top, bottom in piece["rows"]:
            x = 0
            for picture, first, last in columns:
                box = (first, top, last + 1, bottom + 1)
                if box[2] > picture.width or box[3] > picture.height:
                    problems.append("%s: range %s is outside its source picture" % (piece["name"], str(box)))
                    return None
                result.paste(picture.crop(box), (x, y))
                x += last - first + 1
            y += bottom - top + 1

    if "enlarge" in piece:
        factor = piece["enlarge"]
        result = result.resize((result.width * factor, result.height * factor), Image.NEAREST)
    return result


def read_colour_shifts(name, problems):
    """Read HOVER_SHIFTS or SELECTED_SHIFTS from the game's tools.py as a dict."""
    path = os.path.join(config.GAME_SOURCE, "tools.py")
    with open(path, encoding="utf-8-sig") as handle:
        tree = ast.parse(handle.read())
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name) and target.id == name:
                table = {}
                for old, new in ast.literal_eval(node.value):
                    table[tuple(old)] = tuple(new)
                return table
    problems.append("tools.py no longer defines %s" % name)
    return {}


def recolour(picture, table):
    """Repaint the rim: every opaque pixel whose colour is in the table."""
    result = picture.copy()
    pixels = result.load()
    for y in range(result.height):
        for x in range(result.width):
            red, green, blue, alpha = pixels[x, y]
            if alpha == 255 and (red, green, blue) in table:
                new = table[(red, green, blue)]
                pixels[x, y] = (new[0], new[1], new[2], 255)
    return result


def native_size(picture):
    """Undo a whole-number enlargement, if the picture is one.

    Tries the largest factors first and keeps the first whose shrink-and-enlarge
    round trip gives back the identical picture, so nothing is lost.
    """
    for factor in [8, 6, 5, 4, 3, 2]:
        if picture.width % factor != 0 or picture.height % factor != 0:
            continue
        small = picture.resize((picture.width // factor, picture.height // factor), Image.NEAREST)
        again = small.resize(picture.size, Image.NEAREST)
        if same_pixels(again, picture):
            return small
    return picture


def same_pixels(first, second):
    """True when two pictures of the same mode hold the same pixels.

    The raw bytes are compared. ImageChops.difference().getbbox() looks only at
    the alpha channel of an RGBA picture, so it calls any two opaque pictures
    identical.
    """
    if first.size != second.size or first.mode != second.mode:
        return False
    return first.tobytes() == second.tobytes()


def encode_png(picture, transparency=None):
    buffer = io.BytesIO()
    if transparency is None:
        picture.save(buffer, format="PNG", optimize=True)
    else:
        picture.save(buffer, format="PNG", optimize=True, transparency=transparency)
    return buffer.getvalue()


def palette_png(picture):
    """The picture as a palette PNG, or None if it has more than 256 colours.

    Pixel art uses few colours, and a palette file stores one byte a pixel
    instead of four. The palette is built from the picture's own colours, so
    nothing is lost.
    """
    colours = picture.getcolors(256)
    if colours is None:
        return None

    index_of = {}
    palette = []
    alphas = []
    for count, colour in colours:
        index_of[colour] = len(index_of)
        palette.append(colour[0])
        palette.append(colour[1])
        palette.append(colour[2])
        alphas.append(colour[3])

    raw = picture.tobytes()
    indexes = bytearray(len(raw) // 4)
    position = 0
    for offset in range(0, len(raw), 4):
        colour = (raw[offset], raw[offset + 1], raw[offset + 2], raw[offset + 3])
        indexes[position] = index_of[colour]
        position += 1

    result = Image.frombytes("P", picture.size, bytes(indexes))
    result.putpalette(palette)
    return encode_png(result, bytes(alphas))


def smallest_png(picture):
    """PNG bytes for an RGBA picture: the palette form when that is smaller."""
    plain = encode_png(picture)
    palette = palette_png(picture)
    if palette is not None and len(palette) < len(plain):
        with Image.open(io.BytesIO(palette)) as check:
            if same_pixels(check.convert("RGBA"), picture):
                return palette
    return plain


def write_picture(picture, relative, written):
    """Write under game/images unless the file there already shows the same pixels."""
    full = os.path.join(config.GAME_OUT_IMAGES, relative.replace("/", os.sep))
    written[relative] = True
    if os.path.isfile(full):
        with Image.open(full) as existing:
            if same_pixels(existing.convert("RGBA"), picture.convert("RGBA")):
                return False
    folder = os.path.dirname(full)
    if not os.path.isdir(folder):
        os.makedirs(folder)
    with open(full, "wb") as handle:
        handle.write(smallest_png(picture.convert("RGBA")))
    return True


def remove_stale(folder, keep):
    """Delete files under folder that this run did not produce."""
    removed = 0
    for current, folder_names, file_names in os.walk(folder):
        for name in file_names:
            full = os.path.join(current, name)
            relative = os.path.relpath(full, folder).replace(os.sep, "/")
            if relative not in keep:
                os.remove(full)
                removed += 1
    for current, folder_names, file_names in os.walk(folder, topdown=False):
        if current != folder and len(os.listdir(current)) == 0:
            os.rmdir(current)
    return removed


def extract_fonts(problems):
    kept = {}
    for font in config.FONTS:
        if not font["publish"]:
            continue
        source = os.path.join(config.GAME_IMAGES, font["file"])
        if not os.path.isfile(source):
            problems.append("game font not found: %s" % font["file"])
            continue
        if not os.path.isdir(config.GAME_OUT_FONTS):
            os.makedirs(config.GAME_OUT_FONTS)
        target = os.path.join(config.GAME_OUT_FONTS, font["file"])
        kept[font["file"]] = True
        if os.path.isfile(target):
            with open(source, "rb") as first:
                with open(target, "rb") as second:
                    if first.read() == second.read():
                        continue
        shutil.copyfile(source, target)
    if os.path.isdir(config.GAME_OUT_FONTS):
        remove_stale(config.GAME_OUT_FONTS, kept)


def extract(problems):
    """Cut the frame pieces and copy the site's art. Returns (changed, removed)."""
    if not os.path.isdir(config.GAME_IMAGES):
        problems.append("the game repository was not found at %s" % config.GAME_REPO)
        return 0, 0

    cache = {}
    pictures = {}   # path under game/images -> picture

    hover = read_colour_shifts("HOVER_SHIFTS", problems)
    selected = read_colour_shifts("SELECTED_SHIFTS", problems)

    for piece in config.GUI_PIECES:
        picture = cut_piece(piece, cache, problems)
        if picture is None:
            continue
        pictures["gui/" + piece["name"]] = picture
        if piece["name"] in config.GUI_VARIANTS:
            stem = piece["name"][:-len(".png")]
            pictures["gui/" + stem + "-hover.png"] = recolour(picture, hover)
            pictures["gui/" + stem + "-selected.png"] = recolour(picture, selected)

    for row in config.SITE_ART:
        picture = open_picture(row["source"], cache, problems)
        if picture is None:
            continue
        if "crop" in row:
            picture = picture.crop(row["crop"])
        if row.get("native"):
            picture = native_size(picture)
        if row["to"] in pictures:
            problems.append("two config rows both write images/%s" % row["to"])
            continue
        pictures[row["to"]] = picture

    if problems:
        return 0, 0

    changed = 0
    written = {}
    names = list(pictures.keys())
    names.sort()
    for name in names:
        if name != name.lower() or " " in name:
            problems.append("images/%s: file names must be lowercase with no spaces" % name)
            continue
        if write_picture(pictures[name], name, written):
            changed += 1
    removed = 0
    if os.path.isdir(config.GAME_OUT_IMAGES):
        removed = remove_stale(config.GAME_OUT_IMAGES, written)

    extract_fonts(problems)
    return changed, removed
