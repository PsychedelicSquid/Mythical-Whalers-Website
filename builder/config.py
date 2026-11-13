"""Settings for the website build. Anything a person might want to change is here."""

import os

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Hand-written sources
CONTENT_PAGES = os.path.join(REPO, "content", "pages")
TEMPLATES = os.path.join(REPO, "templates")
STATIC = os.path.join(REPO, "static")

# Build output, served by GitHub Pages. Never edited by hand.
DOCS = os.path.join(REPO, "docs")

SITE_NAME = "Mythical Whalers"
STUDIO = "Kleen Fleet"
STEAM_URL = "https://store.steampowered.com/app/2787860/"

# http until GitHub Pages holds a certificate for the domain. Then change this
# to https and rebuild: every canonical address and the sitemap follow it.
SITE_URL = "http://www.mythicalwhalers.com"

# The stylesheet every page links.
STYLESHEET = "css/site.css"

# The navigation bar. "section" is the first part of an address; the item whose
# section matches the page being shown is drawn as selected.
NAV = [
    {"label": "Home", "url": "/", "section": "home"},
    {"label": "Wiki", "url": "/wiki/", "section": "wiki"},
    {"label": "Devlog", "url": "/devlog/", "section": "devlog"},
    {"label": "Team", "url": "/team/", "section": "team"},
]

# ---------------------------------------------------------------------------
# The Wiki. One row per category. Set "enabled" to False to take a category
# off the site: its pages are not built and links to its entries become plain
# text. The Wiki follows the in-game Bestiary's tabs; its Mobs tab is split by
# "group" into five.
#   source   the file in game/data the entries come from
#   group    for mobs: crewmate, whale, boss, captain or creature
#   tab      for items: the Bestiary tab
# ---------------------------------------------------------------------------
WIKI_CATEGORIES = [
    {"key": "crewmates", "title": "Crewmates", "source": "mobs", "group": "crewmate", "enabled": True,
     "intro": "The races you can hire. Each has its own stats, traits and starting gear."},
    {"key": "whales", "title": "Whales", "source": "mobs", "group": "whale", "enabled": True,
     "intro": "The whales of the Shrouded Seas."},
    {"key": "bosses", "title": "Bosses", "source": "mobs", "group": "boss", "enabled": True,
     "intro": "The largest things you can fight."},
    {"key": "captains", "title": "Captains", "source": "mobs", "group": "captain", "enabled": True,
     "intro": "The captains who lead other crews."},
    {"key": "creatures", "title": "Creatures", "source": "mobs", "group": "creature", "enabled": True,
     "intro": "Everything else that fights."},
    {"key": "weapons", "title": "Weapons", "source": "items", "tab": "Weapons", "enabled": True,
     "intro": "A weapon gives the crewmate holding it an ability and stat bonuses."},
    {"key": "armor", "title": "Armor", "source": "items", "tab": "Armor", "enabled": True,
     "intro": "Worn on the head, chest or feet."},
    {"key": "consumables", "title": "Consumables", "source": "items", "tab": "Consumables", "enabled": True,
     "intro": "Elixirs, tonics, mushrooms and potions."},
    {"key": "cargo", "title": "Cargo", "source": "items", "tab": "Cargo", "enabled": True,
     "intro": "What you carry, eat, sell and brew."},
    {"key": "ship-upgrades", "title": "Ship upgrades", "source": "items", "tab": "Upgrades", "enabled": True,
     "intro": "Fittings for your ship."},
    {"key": "traits", "title": "Traits", "source": "traits", "enabled": True,
     "intro": "What makes one crewmate different from another."},
    {"key": "abilities", "title": "Abilities", "source": "abilities", "enabled": True,
     "intro": "What a crewmate or creature can do on its turn."},
    {"key": "status-effects", "title": "Status effects", "source": "effects", "enabled": True,
     "intro": "What an ability can leave on its target."},
    {"key": "factions", "title": "Factions", "source": "factions", "enabled": True,
     "intro": "The powers of the Shrouded Seas."},
    {"key": "locations", "title": "Locations", "source": "locations", "enabled": True,
     "intro": "Where a crew trades, hires and brews."},
]

# How the Wiki's front page groups the categories.
WIKI_GROUPS = [
    {"title": "Bestiary", "keys": ["crewmates", "whales", "bosses", "captains", "creatures"]},
    {"title": "Gear", "keys": ["weapons", "armor", "consumables", "cargo", "ship-upgrades"]},
    {"title": "Crew and combat", "keys": ["traits", "abilities", "status-effects"]},
    {"title": "The world", "keys": ["factions", "locations"]},
]

# The entry whose picture stands for each category on its tile. A category
# not listed here, or whose entry is gone, shows its first entry.
WIKI_TILE_PICTURES = {
    "crewmates": "mobs.Salorian",
    "whales": "mobs.Narwhal",
    "bosses": "mobs.Kraken",
    "captains": "mobs.PirateCaptain",
    "creatures": "mobs.Spider",
    "weapons": "items.Cutlass",
    "armor": "items.SalorianArmor",
    "consumables": "items.ElixirHealth",
    "cargo": "items.ZypherBlubber",
    "ship-upgrades": "items.Spyglass",
    "traits": "traits.Hearty",
    "abilities": "abilities.FireBreath",
    "status-effects": "effects.Burning",
    "factions": "factions.Selkie",
    "locations": "locations.WhalingPort",
}

# The order a race's level-up traits are listed in (traits.TIER_WEIGHTS).
TRAIT_TIERS = ["common", "uncommon", "rare", "legendary", "never"]

# Names the Wiki writes differently from the game. The game names a mob after
# its class, so GlideFin is "Glide Fin" in the Bestiary; it is written Glidefin.
# Renaming the class in the game makes its row here unnecessary.
WIKI_NAMES = {
    "mobs.GlideFin": "Glidefin",
}


# ---------------------------------------------------------------------------
# The game repository. Read by `python build.py --extract`, never written to.
# ---------------------------------------------------------------------------
GAME_REPO = os.path.join(os.path.dirname(REPO), "Mythical-Whalers")
GAME_SOURCE = os.path.join(GAME_REPO, "mythical_whalers")
GAME_IMAGES = os.path.join(GAME_SOURCE, "data", "images")

# What the extract writes. Committed, so `git diff game/` shows what a game
# update would change on the site before any of it is public.
GAME = os.path.join(REPO, "game")
GAME_DATA = os.path.join(GAME, "data")
GAME_OUT_IMAGES = os.path.join(GAME, "images")
GAME_OUT_FONTS = os.path.join(GAME, "fonts")

# A source path holding any of these folder names is refused: drafts, cut
# content, and a third-party effects pack that is not ours to publish.
FORBIDDEN_FOLDERS = ["unused", "mockups", "legacy", "Effects"]

# Fonts from the game. Only a font with publish True is copied to the site.
# df_font.ttf carries no licence text and none was found published, so it stays
# off until the developer confirms it may be put on a public website. The
# stylesheet asks for it first and falls back to m5x7, so turning it on is this
# one change. m5x7 is published by Daniel Linssen as CC0.
#
# "family" is the name the stylesheet uses, not the font's own name. A font
# installed on a visitor's computer must never stand in for one the site did
# not send, or the site would look different on the developer's machine.
FONTS = [
    {"family": "MW Body", "file": "m5x7.ttf", "publish": True},
    {"family": "MW Title", "file": "df_font.ttf", "publish": False},
]

# ---------------------------------------------------------------------------
# Frame pieces cut from the game's GUI art into images/gui.
#
# The game has no stretchable frames: its windows are 640x360 pictures with the
# panel painted in. Each piece below keeps the corners and one pixel of each
# edge, so CSS border-image can stretch it to any size.
#
# "columns" and "rows" are inclusive pixel ranges in the source picture. A
# column written (file, first, last) is cut from that other file instead.
# A piece with neither is the whole source picture.
# ---------------------------------------------------------------------------
POPUP = "gui/popup.png"
LEFT_CORNER = (173, 199)       # 27 px: the left knots and rim
MIDDLE = (300, 300)            # 1 px of plain edge
RIGHT_CORNER = (440, 466)      # 27 px: the right knots and rim
RIGHT_CORNER_X = (428, 466)    # 39 px: as above plus the close-button cell

GUI_PIECES = [
    {"name": "panel.png", "source": POPUP,
     "columns": [LEFT_CORNER, MIDDLE, RIGHT_CORNER], "rows": [(39, 65), (150, 150), (295, 321)]},
    {"name": "window-head.png", "source": POPUP,
     "columns": [LEFT_CORNER, MIDDLE, RIGHT_CORNER], "rows": [(39, 65), (68, 68), (71, 76)]},
    {"name": "window-head-x.png", "source": POPUP,
     "columns": [LEFT_CORNER, MIDDLE, RIGHT_CORNER_X], "rows": [(39, 65), (68, 68), (71, 76)]},
    {"name": "window-mid.png", "source": POPUP,
     "columns": [LEFT_CORNER, MIDDLE, RIGHT_CORNER], "rows": [(150, 150), (222, 227)]},
    {"name": "window-foot.png", "source": POPUP,
     "columns": [LEFT_CORNER, MIDDLE, RIGHT_CORNER], "rows": [(150, 150), (295, 321)]},
    {"name": "frame.png", "source": "gui/main_menu/frame.png",
     "columns": [(0, 39), (320, 320), (600, 639)], "rows": [(0, 33), (180, 180), (326, 359)]},
    {"name": "tooltip.png", "source": "gui/tooltip.png",
     "columns": [(0, 7), (65, 65), (122, 129)], "rows": [(0, 7), (32, 32), (56, 63)]},
    {"name": "btn.png", "source": "buttons/button_left.png",
     "columns": [(0, 7), (200, 200), ("buttons/button_right.png", 0, 7)], "rows": [(0, 24)]},
    {"name": "trait.png", "source": "gui/trait_frame.png",
     "columns": [(0, 37), (80, 80), (122, 129)], "rows": [(0, 7), (22, 22), (36, 43)]},
    {"name": "slot.png", "source": "gui/frame.png"},
    {"name": "portrait.png", "source": "gui/crewmate_frame.png"},
    {"name": "banner.png", "source": "gui/faction_frame.png"},
    {"name": "close.png", "source": "buttons/close.png"},
    {"name": "close-hover.png", "source": "buttons/close_highlight.png"},
    {"name": "cursor.png", "source": "gui/cursor_1.png", "enlarge": 2},
    {"name": "sea-tile.png", "source": "tiles/water_1.png", "columns": [(0, 23)], "rows": [(0, 23)]},
]

# These pieces also get a -hover and a -selected version, made the way the game
# makes them: the rim browns are repainted with tools.HOVER_SHIFTS and
# tools.SELECTED_SHIFTS, which the extract reads from the game's tools.py.
GUI_VARIANTS = ["btn.png", "slot.png", "portrait.png"]

# ---------------------------------------------------------------------------
# Other art the site's own pages show. "to" is the path under images/.
#   crop    (left, top, right, bottom), right and bottom not included
# ---------------------------------------------------------------------------
SITE_ART = [
    {"to": "menu/sea.png", "source": "gui/main_menu/sea.png"},
    {"to": "menu/castle.png", "source": "gui/main_menu/castle.png"},
    {"to": "menu/cloud-1.png", "source": "gui/main_menu/cloud_1.png"},
    {"to": "menu/cloud-2.png", "source": "gui/main_menu/cloud_2.png"},
    {"to": "menu/cloud-3.png", "source": "gui/main_menu/cloud_3.png"},
    {"to": "menu/cloud-4.png", "source": "gui/main_menu/cloud_4.png"},
    {"to": "menu/logo.png", "source": "gui/main_menu/logo.png", "crop": (39, 21, 245, 101)},
    # The picture link previews show (Steam's main capsule).
    {"to": "site/card.png", "source": "steam art/store/Main Capsule.png"},
    # The browser tab's icon (the game's icon on Steam).
    {"to": "site/icon.png", "source": "steam art/app_icon.png"},
]

MONTHS = ["January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December"]
