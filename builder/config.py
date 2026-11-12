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

MONTHS = ["January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December"]
