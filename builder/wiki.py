"""Builds the Wiki's pages from game/data.

Each entry page shows what the in-game Bestiary shows for that entry (see
Bestiary.populate_mob, populate_item, populate_faction and populate_trait in
the game's gui.py), then the links the Bestiary cannot show: what drops an
item, what it brews into, which abilities apply a status effect.

All the deciding is done here. The templates only lay out what they are given.
"""

import json
import os

from PIL import Image

from builder import assets
from builder import config


def read_data(name):
    path = os.path.join(config.GAME_DATA, name)
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def slug_of(name):
    """'Dead Man's Lamp' -> 'dead-mans-lamp'."""
    result = ""
    for character in name.lower():
        if character.isalnum():
            result += character
        elif character in " -_/":
            if result and result[-1] != "-":
                result += "-"
    return result.strip("-")


def picture(game_path, sizes, problems):
    """A copied game picture: its address and real size. None if there is no path."""
    if not game_path:
        return None
    relative = assets.image_destination(game_path)
    if relative not in sizes:
        full = os.path.join(config.GAME_OUT_IMAGES, relative.replace("/", os.sep))
        if not os.path.isfile(full):
            problems.append("the Wiki needs images/%s, which the extract did not copy" % relative)
            sizes[relative] = None
        else:
            with Image.open(full) as opened:
                sizes[relative] = opened.size
    if sizes[relative] is None:
        return None
    return {"url": "/images/" + relative, "width": sizes[relative][0], "height": sizes[relative][1]}


def sign(value):
    """+3, -1: the way the game writes a bonus."""
    if value >= 0:
        return "+" + str(value)
    return str(value)


def title_words(key):
    return key.replace("_", " ").title()


# ---------------------------------------------------------------------------
# Entries
# ---------------------------------------------------------------------------

def category_for(source, record):
    for category in config.WIKI_CATEGORIES:
        if category["source"] != source:
            continue
        if source == "mobs" and category["group"] != record["group"]:
            continue
        if source == "items" and category["tab"] != record["tab"]:
            continue
        return category
    return None


def make_entries(data, sizes, problems):
    """One entry per record in game/data, keyed by its id.

    An entry whose category is switched off has no page, and its address is
    "": a link to it is shown as plain text.
    """
    entries = {}
    used_addresses = {}
    kinds = {"mobs": "mob", "items": "item", "traits": "trait", "abilities": "ability",
             "effects": "effect", "factions": "faction"}

    for identifier in config.WIKI_NAMES:
        if identifier.split(".")[0] not in data or identifier not in data[identifier.split(".")[0]]:
            problems.append("WIKI_NAMES in builder/config.py names %s, which game/data does not hold" % identifier)

    for source in ["mobs", "items", "traits", "abilities", "effects", "factions"]:
        records = data[source]
        identifiers = list(records.keys())
        identifiers.sort()
        for identifier in identifiers:
            record = records[identifier]
            category = category_for(source, record)
            if category is None:
                problems.append("%s fits no row of WIKI_CATEGORIES in builder/config.py" % identifier)
                continue
            name = config.WIKI_NAMES.get(identifier, record["name"])
            address = ""
            if category["enabled"]:
                address = "/wiki/%s/%s/" % (category["key"], slug_of(name))
                if address in used_addresses:
                    problems.append("%s and %s would both be at %s" % (identifier, used_addresses[address], address))
                    continue
                used_addresses[address] = identifier

            entry = {
                "id": identifier,
                "kind": kinds[source],
                "category": category,
                "name": name,
                "url": address,
                "record": record,
                "description": record.get("description", ""),
                "style": "slot",
                "icon": picture(record.get("image", ""), sizes, problems),
                "frame": 0,
                "zoom": 1,
                "card_zoom": 1,
                "summary": "",
            }

            if source == "mobs" and record["group"] == "crewmate":
                entry["style"] = "portrait"
            elif source == "mobs":
                entry["style"] = "sprite"
                if entry["icon"] is not None:
                    # A strip is four frames side by side. The Bestiary fits a
                    # frame into a 102-pixel box by a whole number
                    # (Bestiary.entry_frames); cards use a 48-pixel box.
                    frame = entry["icon"]["width"] // 4
                    entry["frame"] = frame
                    entry["zoom"] = max(1, min(102 // frame, 102 // entry["icon"]["height"]))
                    entry["card_zoom"] = max(1, 48 // frame)
            elif source == "effects":
                entry["style"] = "small"
            elif source == "factions":
                entry["style"] = "banner"
            entries[identifier] = entry
    return entries


def link(entries, reference, note=""):
    """What a template needs to show a link to another entry.

    Every reference in game/data names a record (extract.check_references
    sees to that), so the entry is always there.
    """
    entry = entries[reference]
    return {"name": entry["name"], "url": entry["url"], "icon": entry["icon"], "style": entry["style"],
            "frame": entry["frame"], "card_zoom": entry["card_zoom"], "note": note}


def links(entries, references, notes=None):
    """Links for a list of references. A reference listed twice becomes one link noted x2.

    notes, when given, holds the note for each reference that has one.
    """
    counts = {}
    order = []
    for reference in references:
        if reference not in counts:
            counts[reference] = 0
            order.append(reference)
        counts[reference] += 1
    result = []
    for reference in order:
        parts = []
        if notes is not None and reference in notes:
            parts.append(notes[reference])
        if counts[reference] > 1:
            parts.append("x%d" % counts[reference])
        result.append(link(entries, reference, ", ".join(parts)))
    return result


def change_note(changes, entries):
    """What an item or mob changes about its ability, as the note beside the link: 'Damage 4, Range 6, 2 stamina'.

    The Bestiary shows an ability as its owner uses it; the ability's own page
    shows it unchanged.
    """
    parts = []
    for key in changes.get("base_stats", {}):
        parts.append("%s %s" % (title_words(key), changes["base_stats"][key]))
    if "stamina_cost" in changes:
        parts.append("%s stamina" % changes["stamina_cost"])
    if "mana_cost" in changes:
        parts.append("%s mana" % changes["mana_cost"])
    for key in ["type", "damage_type"]:
        if key in changes:
            parts.append("%s %s" % (title_words(key), changes[key]))
    if "status_effects" in changes:
        names = []
        for reference in changes["status_effects"]:
            names.append(entries[reference]["name"])
        parts.append("applies " + ", ".join(names))
    return ", ".join(parts)


def by_name(items):
    """Sort links or entries by their name."""
    keyed = []
    for position in range(len(items)):
        keyed.append((items[position]["name"].lower(), position))
    keyed.sort()
    result = []
    for name, position in keyed:
        result.append(items[position])
    return result


def stat_picture(icon, sizes, problems):
    return picture("gui/stats/%s.png" % icon, sizes, problems)


def stat_names(data):
    """icon name -> the stat's name, from tooltips.py."""
    names = {}
    for group in data["stats"]:
        for stat in data["stats"][group]:
            names[stat["icon"]] = stat["name"]
    return names


def mob_stat_rows(record, data, sizes, problems):
    rows = []
    for stat in data["stats"]["crew"]:
        # The Health icon is named hp; the number it shows is max_hp.
        key = stat["icon"]
        if key == "hp":
            key = "max_hp"
        if key in record["stats"]:
            rows.append({"icon": stat_picture(stat["icon"], sizes, problems), "label": stat["name"],
                         "value": str(record["stats"][key])})
    return rows


def bonus_rows(modifiers, icon_table, data, sizes, problems, hidden):
    """Rows for an item's BONUSES or a trait's MODIFIERS."""
    names = stat_names(data)
    rows = []
    keys = list(modifiers.keys())
    for key in keys:
        if key in hidden:
            continue
        value = modifiers[key]
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            continue
        if key in icon_table:
            icon = icon_table[key]
            rows.append({"icon": stat_picture(icon, sizes, problems),
                         "label": names.get(icon, title_words(key)), "value": sign(value)})
        else:
            rows.append({"icon": None, "label": title_words(key), "value": sign(value)})
    return rows


def describe_mob(entry, entries, data, sizes, problems):
    record = entry["record"]
    page = {"facts": [], "stat_title": "STATS", "stat_rows": mob_stat_rows(record, data, sizes, problems),
            "groups": [], "tiers": [], "portraits": []}

    # IMMUNE, with the icons the Bestiary gives five of them
    effect_of_key = {}
    for identifier in entries:
        if entries[identifier]["kind"] == "effect" and entries[identifier]["record"]["key"]:
            effect_of_key[entries[identifier]["record"]["key"]] = identifier
    immune = []
    for immunity in record["immunities"]:
        icon_file = data["meta"].get("immunity_icons", {}).get(immunity, "")
        icon = None
        if icon_file:
            icon = picture("abilities/buffs/" + icon_file, sizes, problems)
        address = ""
        if immunity in effect_of_key:
            address = entries[effect_of_key[immunity]]["url"]
        immune.append({"name": title_words(immunity), "url": address, "icon": icon, "style": "small",
                       "frame": 0, "card_zoom": 1, "note": ""})

    if record["group"] == "crewmate":
        for portrait in record["portraits"]:
            found = picture(portrait, sizes, problems)
            if found is not None:
                page["portraits"].append(found)

        for identifier in data["factions"]:
            if entry["id"] in data["factions"][identifier]["members"]:
                page["facts"].append({"label": "FACTION", "text": "", "links": [link(entries, identifier)]})
        if record["hire_cost"]:
            page["facts"].append({"label": "HIRE COST", "text": "%d Gold" % record["hire_cost"], "links": []})
        if record["names"]:
            page["facts"].append({"label": "NAMES", "text": ", ".join(record["names"]), "links": []})

        starts = []
        for innate in record["innate_traits"]:
            note = ""
            if innate["level"] != 1:
                note = "level %d" % innate["level"]
            starts.append(link(entries, innate["trait"], note))
        page["groups"].append({"title": "STARTS WITH", "items": starts, "empty": "none"})

        rows = []
        for tier in config.TRAIT_TIERS:
            if tier in record["trait_tiers"] and record["trait_tiers"][tier]:
                rows.append({"label": tier.capitalize(), "items": links(entries, record["trait_tiers"][tier])})
        if rows:
            page["tiers"].append({"title": "TRAITS OFFERED AT LEVEL-UP", "rows": rows})

    # An ability the mob has changed is noted with what differs (the Dragon's Fire Breath: Radius 4).
    notes = {}
    for reference in record["ability_changes"]:
        notes[reference] = change_note(record["ability_changes"][reference], entries)
    page["groups"].append({"title": "ABILITIES", "items": links(entries, record["abilities"], notes),
                           "empty": "none"})
    page["groups"].append({"title": "IMMUNE", "items": immune, "empty": "none"})
    page["groups"].append({"title": "DROPS", "items": links(entries, record["drops"]), "empty": "none"})
    return page


def describe_item(entry, entries, data, sizes, problems):
    record = entry["record"]
    # A mana bonus is hidden in the game's item tooltips and in the Bestiary.
    rows = bonus_rows(record["modifiers"], data["meta"].get("item_icons", {}), data, sizes, problems, ["max_mana"])
    page = {"facts": [], "stat_title": "BONUSES", "stat_rows": rows, "groups": [], "tiers": [],
            "portraits": []}

    if record["slot"]:
        text = record["slot"].capitalize()
        if record["arms"]:
            text += ", " + record["arms"].replace("_", "-").capitalize()
        page["facts"].append({"label": "SLOT", "text": text, "links": []})
    if record["cost"] > 0:
        page["facts"].append({"label": "VALUE", "text": "%d %s" % (record["cost"], record["resource"].capitalize()),
                              "links": []})
    else:
        page["facts"].append({"label": "VALUE", "text": "none", "links": []})

    if record["ability"]:
        # The ability as this item changes it (the Musket's damage, range and stamina).
        note = change_note(record["ability_changes"], entries)
        page["groups"].append({"title": "ABILITY", "items": [link(entries, record["ability"], note)], "empty": ""})
    if record["grants_trait"]:
        page["groups"].append({"title": "TRAIT", "items": [link(entries, record["grants_trait"])], "empty": ""})
    if record["cures"]:
        page["groups"].append({"title": "CURES", "items": [link(entries, record["cures"])], "empty": ""})
    if record["brews_into"]:
        # An elixir vendor's cauldron turns one of these and some gems into the brew.
        gems = data["meta"]["brew_cost"]
        note = "with %d gems" % gems
        if gems == 1:
            note = "with 1 gem"
        page["groups"].append({"title": "BREWS INTO", "items": [link(entries, record["brews_into"], note)],
                               "empty": ""})

    brewed_from = []
    dropped_by = []
    for identifier in entries:
        other = entries[identifier]
        if other["kind"] == "item" and other["record"]["brews_into"] == entry["id"]:
            brewed_from.append(link(entries, identifier))
        if other["kind"] == "mob" and entry["id"] in other["record"]["drops"]:
            dropped_by.append(link(entries, identifier))
    if brewed_from:
        page["groups"].append({"title": "BREWED FROM", "items": by_name(brewed_from), "empty": ""})
    if dropped_by:
        page["groups"].append({"title": "DROPPED BY", "items": by_name(dropped_by), "empty": ""})
    return page


def describe_trait(entry, entries, data, sizes, problems):
    record = entry["record"]
    rows = bonus_rows(record["modifiers"], data["meta"].get("trait_icons", {}), data, sizes, problems, [])
    page = {"facts": [], "stat_title": "MODIFIERS PER LEVEL", "stat_rows": rows, "groups": [], "tiers": [],
            "portraits": []}
    page["facts"].append({"label": "MAX LEVEL", "text": str(record["max_level"]), "links": []})
    if record["offered_at_level_up"]:
        page["facts"].append({"label": "OFFERED AT LEVEL-UP", "text": "Yes", "links": []})
    else:
        page["facts"].append({"label": "OFFERED AT LEVEL-UP", "text": "No", "links": []})

    innate_to = []
    by_tier = {}
    granted_by = []
    cured_by = []
    for identifier in entries:
        other = entries[identifier]
        if other["kind"] == "mob" and other["record"]["group"] == "crewmate":
            for innate in other["record"]["innate_traits"]:
                if innate["trait"] == entry["id"]:
                    innate_to.append(link(entries, identifier))
            for tier in other["record"]["trait_tiers"]:
                if entry["id"] in other["record"]["trait_tiers"][tier]:
                    if tier not in by_tier:
                        by_tier[tier] = []
                    by_tier[tier].append(link(entries, identifier))
        if other["kind"] == "item":
            if other["record"]["grants_trait"] == entry["id"]:
                granted_by.append(link(entries, identifier))
            if other["record"]["cures"] == entry["id"]:
                cured_by.append(link(entries, identifier))

    if innate_to:
        page["groups"].append({"title": "INNATE TO", "items": by_name(innate_to), "empty": ""})
    if granted_by:
        page["groups"].append({"title": "GRANTED BY", "items": by_name(granted_by), "empty": ""})
    if cured_by:
        page["groups"].append({"title": "CURED BY", "items": by_name(cured_by), "empty": ""})

    tier_rows = []
    for tier in config.TRAIT_TIERS:
        if tier in by_tier:
            tier_rows.append({"label": tier.capitalize(), "items": by_name(by_tier[tier])})
    if tier_rows:
        page["tiers"].append({"title": "HOW OFTEN EACH RACE IS OFFERED IT", "rows": tier_rows})
    return page


def describe_ability(entry, entries, data, sizes, problems):
    record = entry["record"]
    rows = []
    for key in record["base_stats"]:
        value = record["base_stats"][key]
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            rows.append({"icon": None, "label": title_words(key), "value": str(value)})
    page = {"facts": [], "stat_title": "BASE", "stat_rows": rows, "groups": [], "tiers": [],
            "portraits": []}
    if record["type"]:
        page["facts"].append({"label": "TYPE", "text": record["type"].capitalize(), "links": []})
    if record["damage_type"]:
        page["facts"].append({"label": "DAMAGE TYPE", "text": record["damage_type"].capitalize(), "links": []})
    costs = []
    if record["stamina_cost"]:
        costs.append("%s stamina" % record["stamina_cost"])
    if record["mana_cost"]:
        costs.append("%s mana" % record["mana_cost"])
    if costs:
        page["facts"].append({"label": "COST", "text": ", ".join(costs), "links": []})

    if record["status_effects"]:
        page["groups"].append({"title": "APPLIES", "items": links(entries, record["status_effects"]), "empty": ""})
    granted_by = []
    used_by = []
    for identifier in entries:
        other = entries[identifier]
        if other["kind"] == "item" and other["record"]["ability"] == entry["id"]:
            granted_by.append(link(entries, identifier))
        if other["kind"] == "mob" and entry["id"] in other["record"]["abilities"]:
            used_by.append(link(entries, identifier))
    if granted_by:
        page["groups"].append({"title": "GRANTED BY", "items": by_name(granted_by), "empty": ""})
    if used_by:
        page["groups"].append({"title": "USED BY", "items": by_name(used_by), "empty": ""})
    return page


def describe_effect(entry, entries, data, sizes, problems):
    record = entry["record"]
    page = {"facts": [], "stat_title": "", "stat_rows": [], "groups": [], "tiers": [], "portraits": []}
    if record["duration"]:
        turns = "turns"
        if record["duration"] == 1:
            turns = "turn"
        page["facts"].append({"label": "LASTS", "text": "%d %s" % (record["duration"], turns), "links": []})

    applied_by = []
    immune = []
    for identifier in entries:
        other = entries[identifier]
        if other["kind"] == "ability" and entry["id"] in other["record"]["status_effects"]:
            applied_by.append(link(entries, identifier))
        if other["kind"] == "mob":
            # A mob whose own version of an ability applies it (the Sea Serpent's Melee poisons).
            for changed in other["record"]["ability_changes"]:
                if entry["id"] in other["record"]["ability_changes"][changed].get("status_effects", []):
                    applied_by.append(link(entries, identifier, "with " + entries[changed]["name"]))
            if record["key"] and record["key"] in other["record"]["immunities"]:
                immune.append(link(entries, identifier))
    if applied_by:
        page["groups"].append({"title": "APPLIED BY", "items": by_name(applied_by), "empty": ""})
    if immune:
        page["groups"].append({"title": "IMMUNE", "items": by_name(immune), "empty": ""})
    return page


def describe_faction(entry, entries, data, sizes, problems):
    record = entry["record"]
    page = {"facts": [], "stat_title": "", "stat_rows": [], "groups": [], "tiers": [], "portraits": []}
    for label, key in [("ALLY", "ally"), ("ENEMY", "enemy")]:
        if record[key]:
            found = None
            for identifier in entries:
                if entries[identifier]["kind"] == "faction" and entries[identifier]["name"] == record[key]:
                    found = link(entries, identifier)
            if found is None:
                page["facts"].append({"label": label, "text": record[key], "links": []})
            else:
                page["facts"].append({"label": label, "text": "", "links": [found]})
    if record["heralds"]:
        page["facts"].append({"label": "HERALDS", "text": ", ".join(record["heralds"]), "links": []})
    if record["sites"]:
        page["facts"].append({"label": "SITES", "text": ", ".join(record["sites"]), "links": []})
    if record["members"]:
        # In the game's order: it is the order a faction's races unlock in.
        page["groups"].append({"title": "MEMBERS", "items": links(entries, record["members"]), "empty": ""})
    return page


DESCRIBERS = {
    "mob": describe_mob,
    "item": describe_item,
    "trait": describe_trait,
    "ability": describe_ability,
    "effect": describe_effect,
    "faction": describe_faction,
}


def card_summary(entry, data):
    """The one line a category page shows under an entry's name."""
    record = entry["record"]
    if entry["kind"] == "mob":
        if record["group"] == "crewmate" and record["hire_cost"]:
            return "Hire: %d Gold" % record["hire_cost"]
        if "max_hp" in record["stats"]:
            return "Health %s" % record["stats"]["max_hp"]
        return ""
    if entry["kind"] == "item":
        names = stat_names(data)
        icon_table = data["meta"].get("item_icons", {})
        parts = []
        for key in record["modifiers"]:
            if key == "max_mana":
                continue
            value = record["modifiers"][key]
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                parts.append("%s %s" % (names.get(icon_table.get(key, ""), title_words(key)), sign(value)))
        if parts:
            return ", ".join(parts)
        return record["description"]
    if entry["kind"] == "faction":
        return ""
    return record.get("description", "")


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

def view(title, description, address):
    """The page facts every layout expects (see render.page_view)."""
    return {"title": title, "full_title": "%s - %s" % (title, config.SITE_NAME), "description": description,
            "url": address, "section": "wiki", "date": "", "date_text": "", "summary": "", "pitch": "",
            "card": None, "older": None, "newer": None}


def guide_pages(pages, views, problems):
    """The how-to-play pages' views, in the order config.WIKI_GUIDES lists them.

    They are the hand-written pages under content/pages/wiki/guide/.
    """
    found = {}
    for page in pages:
        if page["url"].startswith(config.WIKI_GUIDE_ADDRESS) and page["url"].endswith("/"):
            found[page["url"][len(config.WIKI_GUIDE_ADDRESS):-1]] = page

    ordered = []
    for name in config.WIKI_GUIDES:
        if name not in found:
            problems.append("WIKI_GUIDES in builder/config.py lists '%s', but there is no page at %s%s/"
                            % (name, config.WIKI_GUIDE_ADDRESS, name))
            continue
        if found[name]["game_version"] == "":
            problems.append("%s: a how-to-play page needs 'game_version' in its header" % found[name]["source"])
        ordered.append(views[found[name]["url"]])
    for name in found:
        if name not in config.WIKI_GUIDES:
            problems.append("%s is not listed in WIKI_GUIDES in builder/config.py" % found[name]["source"])
    return ordered


def stale_guides(pages):
    """A line for each how-to-play page written for another version of the game than game/data holds."""
    lines = []
    meta = read_data("meta.json")
    if meta is None:
        return lines
    for page in pages:
        if page["url"].startswith(config.WIKI_GUIDE_ADDRESS) and page["game_version"] != meta["version"]:
            lines.append("%s was written for game version %s, and game/data is now %s. Read it against the game again."
                         % (page["source"], page["game_version"], meta["version"]))
    return lines


def build(environment, site, guides, outputs, problems):
    """Add every Wiki page to outputs. Returns the addresses for the sitemap."""
    data = {}
    for name in ["mobs", "items", "traits", "abilities", "effects", "factions", "stats", "meta"]:
        loaded = read_data(name + ".json")
        if loaded is None:
            # No extract has been run. The site builds without a Wiki.
            return [], {"total": 0, "categories": [], "featured": []}
        data[name] = loaded

    sizes = {}
    entries = make_entries(data, sizes, problems)
    if problems:
        return [], {"total": 0, "categories": [], "featured": []}

    addresses = []
    search = []
    in_category = {}
    total = 0
    for identifier in entries:
        entry = entries[identifier]
        if entry["url"] == "":
            continue
        total += 1
        entry["summary"] = card_summary(entry, data)
        key = entry["category"]["key"]
        if key not in in_category:
            in_category[key] = []
        in_category[key].append(entry)

    version = data["meta"].get("version", "")
    entry_layout = environment.get_template("wiki_entry.html")
    category_layout = environment.get_template("wiki_category.html")
    home_layout = environment.get_template("wiki_home.html")

    categories = []
    for category in config.WIKI_CATEGORIES:
        if not category["enabled"] or category["key"] not in in_category:
            continue
        members = by_name(in_category[category["key"]])
        sample = entries.get(config.WIKI_TILE_PICTURES.get(category["key"], ""))
        if sample is None or sample["category"] != category:
            sample = members[0]
        shown = {"key": category["key"], "title": category["title"],
                 "url": "/wiki/%s/" % category["key"], "entries": members, "sample": sample}
        categories.append(shown)

        page = view(category["title"], "%s in Mythical Whalers. %s" % (category["title"], category["intro"]),
                    shown["url"])
        html = category_layout.render(site=site, page=page, category=shown, version=version)
        outputs["wiki/%s/index.html" % category["key"]] = html.encode("utf-8")
        addresses.append(shown["url"])

        for entry in members:
            details = DESCRIBERS[entry["kind"]](entry, entries, data, sizes, problems)
            if entry["description"]:
                description = "%s: %s" % (entry["name"], entry["description"])
            else:
                description = "%s, one of the %s in Mythical Whalers." % (entry["name"], category["title"].lower())
            page = view(entry["name"], description, entry["url"])
            html = entry_layout.render(site=site, page=page, entry=entry, details=details, category=shown,
                                       version=version)
            outputs[entry["url"][1:] + "index.html"] = html.encode("utf-8")
            addresses.append(entry["url"])
            search.append({"n": entry["name"], "c": category["title"], "u": entry["url"]})

    groups = []
    for group in config.WIKI_GROUPS:
        members = []
        for category in categories:
            if category["key"] in group["keys"]:
                members.append(category)
        if members:
            groups.append({"title": group["title"], "categories": members})

    page = view("Wiki", "The Mythical Whalers Wiki: crewmates, creatures, gear, traits and factions.", "/wiki/")
    html = home_layout.render(site=site, page=page, groups=groups, guides=guides, version=version)
    outputs["wiki/index.html"] = html.encode("utf-8")
    addresses.append("/wiki/")
    for guide in guides:
        search.append({"n": guide["title"], "c": "How to play", "u": guide["url"]})

    outputs["wiki/search.json"] = (json.dumps(search, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")

    # What other pages may show of the Wiki: the home page lists a few categories.
    featured = []
    for key in config.HOME_WIKI_CATEGORIES:
        for category in categories:
            if category["key"] == key:
                featured.append(category)
    return addresses, {"total": total, "categories": categories, "featured": featured}
