#!/usr/bin/env python3
"""Convert the pages of ks0man.com that were never migrated into block markup.

WHAT THIS IS FOR
----------------
The archive migration carried 242 dated documents across. It did not carry the
rest of the old site: the member roster, the Silent Keys memorials, the Field
Day galleries from 1997 onward, and three write-ups of public-service events the
Society worked. Eleven pages, and between them the only surviving account of
what the club did on the days it was not publishing a newsletter.

They were left out under the redaction policy, which is over: the Society
decided on 17 September 2026 to publish its own record in full. The roster stood
on ks0man.com for years with name, callsign and town in it; the obituaries were
published by the Society when each member died. This tool brings them across.

WHAT IT PRODUCES
----------------
content/mirror_pages.json -- slug, title, parent and Gutenberg block markup, in
the same shape as the `pages` array of content/seed.json.

References to media and to archive documents are left as tokens rather than
URLs, because neither is knowable here:

    {{media:silentkey-nadine-stueve.jpg}}   an uploaded file, by its shipped name
    {{pub:newsletter_01-24.pdf}}            an archive document, by its source file

tools/push_pages.py resolves them against a live site. A token that cannot be
resolved is reported rather than published, so a page never goes out with
"{{media:...}}" printed in it.

Run:  python3 tools/prepare_pages.py            (writes content/mirror_pages.json)
      python3 tools/prepare_pages.py --report   (prints what each page became)
"""

from __future__ import annotations

import argparse
import html as H
import json
import os
import re
import sys
import urllib.parse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIRROR = os.path.expanduser("~/ks0man-migration/mirror/ks0man.com")
# The webmaster's own working folder, supplied on 16 October 2026 as
# "MAARS Page.zip" and kept extracted beside the mirror. The mirror is what the
# site SERVED, so it wins where both hold a page; the folder supplies what was
# never served -- drafts, earlier rosters, the running log of announcements.
FOLDER = os.path.expanduser("~/ks0man-migration/webmaster-folder")
OUT = os.path.join(ROOT, "content", "mirror_pages.json")

# Furniture from a 1998 web page: rules, arrows, "back to top" hands, the
# Acrobat badge, the GeoCities counter. None of it is the record.
CHROME = {
    "spacebar.gif", "blueline_6px.gif", "maroon_line.gif", "top.gif", "home.gif",
    "goback.gif", "acrobat.gif", "email.gif", "e-mail.png", "lefthand.gif",
    "mac-blk.gif", "FDpulsarani.gif", "rcbackbg.gif", "gc_icon.gif",
    "newscollage.gif", "favicon.ico",
}
# Not furniture, though their names look like it: news40wpm.jpg is the cartoon
# the June 1998 issue ran under the treasurer's report, and newsart.jpg is the
# July 1998 issue's "Figure 1", which its own text points readers to.
CHROME_RE = re.compile(r"^(news[a-z0-9]*\.gif|maarslogo|newscollage|visit\.gif)", re.I)
CHROME_LC = {n.lower() for n in CHROME}


def is_chrome(name: str) -> bool:
    """Furniture, by name, in any case: the GeoCities page asked for "Email.gif"."""
    return bool(name) and (name.lower() in CHROME_LC or bool(CHROME_RE.match(name)))

# The pages, what they become, and what they are made of. A photo story the old
# site split across nine pages becomes one page here: nine clicks to see eight
# photographs is a 1997 constraint, not a decision worth migrating.
PAGES = [
    {"slug": "members", "title": "Members", "parent": None,
     "sources": ["members.html"], "kind": "roster",
     "lede": "The Society's roster as it stood on the old site: name, callsign "
             "and town, published by the club about the club.",
     "epilogue": [
         '<!-- wp:heading {"level":2} --><h2 class="wp-block-heading">Earlier lists</h2><!-- /wp:heading -->',
         '<!-- wp:list --><ul class="wp-block-list">'
         '<!-- wp:list-item --><li><a href="/members/roster-2014/">October 2014</a>, {names:roster-2014}</li><!-- /wp:list-item -->'
         '<!-- wp:list-item --><li><a href="/members/roster-2022/">March 2022</a>, {names:roster-2022}</li><!-- /wp:list-item -->'
         '<!-- wp:list-item --><li><a href="/members/roster-undated/">A later list, undated</a>, {names:roster-undated}</li><!-- /wp:list-item -->'
         '</ul><!-- /wp:list -->',
         '<!-- wp:paragraph --><p>Each list shows the names its page showed. The webmaster also '
         'kept some rows in the pages\' code without showing them, one at the member\'s own request, '
         'and they are not shown here either.</p><!-- /wp:paragraph -->',
         '<!-- wp:paragraph --><p>The member lists the Society kept for its own use, with addresses, '
         'telephone numbers and e-mail, are on <a href="/club-files/#membership">the club files page</a>.</p>'
         '<!-- /wp:paragraph -->',
     ]},
    {"slug": "silent-keys", "title": "Silent Keys", "parent": None,
     "sources": ["silentkey.html"], "kind": "memorial",
     "lede": "Members the Society has lost. Each notice is as the club published "
             "it at the time."},
    {"slug": "field-day-1997", "title": "Field Day 1997", "parent": "events",
     "sources": ["FD97.html", "FD97-1.html", "FD97-2.html", "FD97-3.html",
                 "FD97-4.html", "FD97-5.html", "FD97-6.html", "FD97-7.html",
                 "FD97-8.html", "FD97-9.html"], "kind": "gallery"},
    {"slug": "field-day-1998", "title": "Field Day 1998", "parent": "events",
     "sources": ["FD98.html"], "kind": "gallery"},
    {"slug": "field-day-2005", "title": "Field Day 2005", "parent": "events",
     "sources": ["FD05.html"], "kind": "gallery"},
    {"slug": "field-day-2015", "title": "Field Day 2015", "parent": "events",
     "sources": ["FD15.html"], "kind": "gallery"},
    {"slug": "field-day-2018", "title": "Field Day 2018", "parent": "events",
     "sources": ["FD18.html"], "kind": "gallery"},
    {"slug": "ride-for-red", "title": "Ride for Red", "parent": "events",
     "sources": ["photo_ride_for_red.html"], "kind": "article"},
    {"slug": "rms-queen-mary", "title": "RMS Queen Mary", "parent": "events",
     "sources": ["photo_RMS_Queen_Mary.html"], "kind": "article"},
    {"slug": "endurance-horse-race", "title": "International Endurance Horse Race",
     "parent": "events", "sources": ["horserace.html"], "kind": "article"},
    # From the webmaster's folder: pages that were never served, or were
    # served once and replaced.
    {"slug": "roster-2014", "title": "Members, October 2014", "parent": "members",
     "sources": ["members (archive from 10-2014).html"], "kind": "roster",
     "lede": "The roster as the webmaster archived it in October 2014."},
    {"slug": "roster-2022", "title": "Members, March 2022", "parent": "members",
     "sources": ["members original 3-2022.html"], "kind": "roster",
     "lede": "The roster as it stood in March 2022, before the page was restyled. "
             "The restyled copy the webmaster kept lists the same names."},
    {"slug": "roster-undated", "title": "Members, an undated later list",
     "parent": "members", "sources": ["members CODE ARCHIVE.html"], "kind": "roster",
     "lede": "A later roster the webmaster kept as a code archive, with no date on "
             "it. Callsigns in it that are missing from the March 2022 list place "
             "it after that."},
    {"slug": "announcements", "title": "Announcements from the old home page",
     "parent": "history",
     "sources": ["CONTENTS - INDEX PAGE.html", "CONTENTS - MONTHLY MEETING - TOP OF PAGE.html",
                 "CONTENTS - MONTHLY MEETING.html", "text repair.html"],
     "kind": "article",
     "lede": "The webmaster kept every announcement written for the old home page "
             "in one running file, filed alphabetically by event, and pasted from it "
             "as each event came round. This is that file, as it was kept."},
    {"slug": "home-page-2015", "title": "The home page, January 2015", "parent": "history",
     "sources": ["index  (archive - old meeting site).html"], "kind": "article", "retired": True,
     "lede": "The old site's front page as the webmaster archived it, when the "
             "next meeting was Friday, January 9."},
    {"slug": "home-page-geocities", "title": "The home page in the GeoCities years",
     "parent": "history", "sources": ["oldindex.html"], "kind": "article",
     "lede": "The Society's first front page, from when the site was hosted on GeoCities."},
    {"slug": "repeater-notes-from-farren", "title": "Repeater notes from Farren",
     "parent": "history", "sources": ["REPEATER NOTES FROM FARREN.html"], "kind": "article"},
    # The old site's own pages, as they last stood. The new site rewrote each of
    # these from the study rather than carrying it, so without these the text
    # of ks0man.com's home, links, repeater, storm-spotter and events pages was
    # on no page anywhere -- 10,800 words, most of them the old home page.
    {"slug": "old-home-page", "title": "The old home page, as it last stood",
     "parent": "history", "sources": ["index.html"], "kind": "article", "retired": True,
     "lede": "ks0man.com's front page in full, as it stood when this site replaced it."},
    {"slug": "old-events-page", "title": "Past events and photos, as the old site listed them",
     "parent": "history", "sources": ["events.html"], "kind": "article"},
    {"slug": "old-links-page", "title": "The old links page", "parent": "history",
     "sources": ["links-maars.html"], "kind": "article",
     "lede": "Every link the old site kept, as it kept them. Many point at sites that "
             "have moved or gone; they are left as they were."},
    {"slug": "old-repeater-page", "title": "The repeater page, as the old site had it",
     "parent": "history", "sources": ["repeater.html"], "kind": "article"},
    {"slug": "old-storm-spotters-page", "title": "Severe weather spotters, as the old site had it",
     "parent": "history", "sources": ["warn.html"], "kind": "article", "retired": True},
    {"slug": "old-newsletters-index", "title": "The old newsletters index", "parent": "history",
     "sources": ["newsletters.html"], "kind": "article", "retired": True,
     "lede": "The old site's list of newsletters and minutes. Each link now opens the "
             "issue's record in the archive."},
    {"slug": "home-page-autumn-2023", "title": "The home page, autumn 2023", "parent": "history",
     "sources": ["index (has coding defects).html"], "kind": "article", "retired": True,
     "lede": "A copy of the front page the webmaster kept in the folder as \u201cindex (has "
             "coding defects)\u201d. Its newest item is dated 21 October 2023 and its officers "
             "are the 2022\u201323 slate, so this is the home page shortly before the November "
             "2023 election. It shows four items the last version of the page no longer did: "
             "the August 2021 repeater outage, the club T-shirts, the 2022\u201323 officers "
             "and the breakfast of 18 November."},
    {"slug": "breakfast", "title": "Saturday breakfast", "parent": "events",
     "sources": ["CONTENTS - BREAKFAST.html"], "kind": "article",
     "lede": "Breakfast with a side of ham: the Saturday mornings, where and when, "
             "as the webmaster announced them."},
    {"slug": "exams", "title": "License exams", "parent": None,
     "sources": ["exams.html"], "kind": "article",
     "lede": "The old site's exam page, from 2002, and the November 2023 test session "
             "flyer.",
     "epilogue": [
         '<!-- wp:paragraph --><p>The most recent session the Society advertised: '
         '<a href="{{media:maars-vec-test-session-november-2023.pdf}}">the November 2023 '
         'test session flyer</a> (PDF).</p><!-- /wp:paragraph -->',
     ]},
    {"slug": "downloads", "title": "Downloads", "parent": None,
     "sources": ["downloads.html"], "kind": "article",
     "lede": "The Kansas repeater lists the old site offered for loading into a "
             "radio, with the webmaster's instructions for saving them."},
]

# A link to a name that was never on the site, whose document the folder has
# under another name. The announcements file's "Hamfest Mailer" pointed at
# Salina_Hamfest_2015.pdf, which ks0man.com never held; the webmaster's folder
# has the mailer for that hamfest as Salina_mailer_2015.pdf. The gaps page says
# so, so the substitution is on the record.
LINK_ALIASES = {"Salina_Hamfest_2015.pdf": "Salina_mailer_2015.pdf"}

# Old page -> where it lives now. Used to rewrite links inside the converted
# pages, so a 1997 page that said "back to the newsletters" still works.
PAGE_LINKS = {
    "index.html": "/",
    "events.html": "/events/",
    "newsletters.html": "/archive/",
    "minutes.html": "/archive/type/minutes/",
    "repeater.html": "/on-the-air/",
    "warn.html": "/storm-spotting/",
    "links.html": "/links/",
    "links-maars.html": "/links/",
    "downloads.html": "/downloads/",
    "members.html": "/members/",
    "silentkey.html": "/silent-keys/",
    "horserace.html": "/events/endurance-horse-race/",
    "photo_ride_for_red.html": "/events/ride-for-red/",
    "photo_RMS_Queen_Mary.html": "/events/rms-queen-mary/",
    "FD97.html": "/events/field-day-1997/",
    "FD98.html": "/events/field-day-1998/",
    "FD05.html": "/events/field-day-2005/",
    "FD15.html": "/events/field-day-2015/",
    "FD18.html": "/events/field-day-2018/",
}
for _n in range(1, 10):
    PAGE_LINKS[f"FD97-{_n}.html"] = "/events/field-day-1997/"

DOC_RE = re.compile(r"\.(pdf|docx?|csv|zip|mp4|rtf|pptx?|xlsx?|txt|psd|indd|ttf|pm)$", re.I)
# The old site linked itself absolutely under both names it ever had.
OWN_HOST = re.compile(r"^https?://(www\.)?ks0man\.(com|org)(/|$)", re.I)
IMG_RE = re.compile(r"\.(jpe?g|png|gif)$", re.I)
NEWSLETTER_RE = re.compile(r"^newsletter_[\w.-]+\.(pdf|html?|docx?)$", re.I)


def read(path: str) -> str:
    raw = open(path, "rb").read()
    text = None
    for enc in ("utf-8", "cp1252", "latin-1"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        text = raw.decode("latin-1", "replace")
    # "W&OslashPBV": the 1998 pages wrote the slashed zero as an entity with no
    # semicolon, run straight into the next letters. The parser leaves that as
    # literal text, and escaping it printed "W&amp;OslashPBV" on the page.
    return re.sub(r"&([Oo]slash)(?!;)", r"&\1;", text)


def media_map() -> dict[str, str]:
    """Original name on ks0man.com -> the name the file ships under."""
    manifest = json.load(open(os.path.join(ROOT, "media", "manifest.json")))
    return {item["src"]: item["file"] for item in manifest}


def esc(text: str) -> str:
    return H.escape(text, quote=False)


def anchor_id(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "-", urllib.parse.unquote(name or "")).strip("-")


FULL_SIZE: dict[str, str] = {}   # original name -> shipped name of its full-size copy
DUPLICATES: dict[str, str] = {}  # original name -> the source it is a byte-for-byte copy of
INTENDED: dict[str, str] = {}    # relative path -> the absolute address the webmaster wrote


def intended_urls() -> dict[str, str]:
    """Links that lost their site's name on the way to ks0man.com.

    The links page as ks0man.com served it pointed at "files/file/Clubs/Tips
    and Tonics for Healthier Radio Clubs.pdf" -- the ARRL's path with the ARRL
    left off -- and four more like it, and the home page at the Morse Code
    Ninja white paper the same way. None of them ever opened. The webmaster's
    own copy of the links page has the full addresses. A relative path with a
    directory in it that matches one of those addresses' paths goes there.
    """
    if not INTENDED and os.path.isdir(FOLDER):
        for page in sorted(os.listdir(FOLDER)):
            if not page.lower().endswith((".html", ".htm")):
                continue
            for url in re.findall(r'href\s*=\s*"(https?://[^"]+)"', read(os.path.join(FOLDER, page)), re.I):
                if OWN_HOST.match(url):
                    continue
                path = urllib.parse.unquote(urllib.parse.urlparse(url).path).lstrip("/")
                if "/" in path:
                    INTENDED.setdefault(path, url)
    return INTENDED


def duplicate_map() -> dict[str, str]:
    if not DUPLICATES:
        manifest = json.load(open(os.path.join(ROOT, "media", "manifest.json")))
        DUPLICATES.update({i["src"]: i["duplicate_of"] for i in manifest if i.get("duplicate_of")})
    return DUPLICATES


def full_size_map() -> dict[str, str]:
    """Original name -> the "-original" file the webmaster's folder supplied.

    The migration shipped some photographs reduced to 1600px; the folder held
    the files as ks0man.com served them, and those shipped beside the reduced
    ones as "<name>-original.jpg". A link that promises the full picture goes
    to that file.
    """
    if not FULL_SIZE:
        manifest = json.load(open(os.path.join(ROOT, "media", "manifest.json")))
        for item in manifest:
            if item["src"].endswith(" (the webmaster's copy)"):
                FULL_SIZE[item["src"].replace(" (the webmaster's copy)", "")] = item["file"]
    return FULL_SIZE


def resolve_ref(href: str, media: dict[str, str], unresolved: list[str]) -> str | None:
    """Rewrite one href from the old site. None means 'drop the link'.

    Links go to the place the thing now lives: an archive record ({{pub:}}), a
    page, or a file ({{media:}}, or {{media-full:}} for a photograph, which
    resolves to the full-size upload rather than WordPress's scaled copy).
    """
    href = (href or "").strip()
    if href.startswith("#"):
        # The same cleaning as the anchor it points at ("#Our Repeater" names
        # <a name="Our Repeater">, which becomes id="Our-Repeater").
        return "#" + anchor_id(href[1:]) if len(href) > 1 else None
    if not href or href.startswith("javascript:"):
        return href or None
    if href.lower().startswith("mailto:"):
        return "mailto:" + href[7:].strip()          # "mailto: someone@…", a stray space
    if href.lower().startswith("www."):
        return "http://" + href                      # "www.k0ham.com", no scheme
    if "@" in href and "/" not in href and ":" not in href:
        return "mailto:" + href                      # a bare address, no mailto:
    if href.startswith("http"):
        if not OWN_HOST.match(href):
            return href                              # a genuine outbound link, kept
        href = urllib.parse.urlparse(href).path or "/"
    if href.split("?")[0].lower().endswith("login.php"):
        return None                                  # a wget artefact of a Facebook link
    if not href.startswith("/") and "/" in href.split("?")[0]:
        away = intended_urls().get(urllib.parse.unquote(href.split("#")[0].split("?")[0]).lstrip("./"))
        if away:
            return away                              # the address the webmaster wrote
    name = urllib.parse.unquote(os.path.basename(href.split("?")[0].split("#")[0]))
    name = LINK_ALIASES.get(name, name)
    if not name:
        return "/"
    if name.lower().startswith("index.htm"):
        return "/"
    if NEWSLETTER_RE.match(name):
        # "Jan. 2017" linked newsletter_01-17.pdf, a byte-for-byte copy of the
        # February minutes; the copy has no record, so the link opens the
        # record of the document it is.
        return "{{pub:" + duplicate_map().get(name, name) + "}}"
    if name in PAGE_LINKS:
        return PAGE_LINKS[name]
    if IMG_RE.search(name):
        full = full_size_map().get(name)
        if full:
            return "{{media-full:" + full + "}}"
        if name in media:
            return "{{media-full:" + media[name] + "}}"
        unresolved.append(name)
        return None
    if DOC_RE.search(name):
        if name in media:
            return "{{media:" + media[name] + "}}"
        unresolved.append(name)
        return None
    if re.search(r"\.html?$", name, re.I):
        unresolved.append(name)
        return None
    return href


def inline_image(img, media, unresolved) -> str:
    """An <img> inside running text: a picture in a list item, or the photo a
    link wraps. inline() used to skip every one of these, which is how the
    Glen Rubash Award photograph and the repeater rack left the old home page
    and an empty link sat above "(click photo to enlarge)"."""
    name = urllib.parse.unquote(os.path.basename(img.get("src", "") or ""))
    if not name or is_chrome(name) or "?" in name:
        return ""
    if name not in media:
        unresolved.append(name)
        return ""
    alt = esc(img.get("alt", "") or "")
    return f'<img src="{{{{media:{media[name]}}}}}" alt="{alt}"/>'


def inline(node, media, unresolved) -> str:
    """Inline content, keeping emphasis, links, pictures and jump targets."""
    from bs4 import Comment, NavigableString

    out = []
    for child in node.children:
        if isinstance(child, Comment):
            continue
        if isinstance(child, NavigableString):
            out.append(esc(str(child)))
            continue
        tag = child.name.lower()
        if tag in ("b", "strong"):
            out.append("<strong>" + inline(child, media, unresolved) + "</strong>")
        elif tag in ("i", "em"):
            out.append("<em>" + inline(child, media, unresolved) + "</em>")
        elif tag == "a" and child.get("href"):
            target = resolve_ref(child["href"], media, unresolved)
            text = inline(child, media, unresolved)
            if target and not re.sub(r"<[^>]+>", "", text).strip() and "<img" not in text:
                if target.startswith("mailto:"):
                    # A link whose only content was a 1997 e-mail icon: say
                    # where it goes, rather than leave an anchor nobody can see.
                    text = esc(target[7:])
                elif target.startswith(("/", "#")):
                    # <a href="index.html"><img src="home.gif"></a>: a home or
                    # back button whose picture was furniture. Printing its
                    # address put a bare "/" link on twenty-five pages.
                    target = None
                else:
                    token = re.fullmatch(r"\{\{(?:media|media-full|pub):([^}]+)\}\}", target)
                    text = esc(token.group(1) if token else target)
            out.append(f'<a href="{H.escape(target, quote=True)}">{text}</a>'
                       if target else text)
        elif tag == "a" and child.get("name"):
            # <a name="nets">: the target of the page's own table of contents.
            out.append(f'<a id="{anchor_id(child["name"])}"></a>' + inline(child, media, unresolved))
        elif tag == "img":
            out.append(inline_image(child, media, unresolved))
        elif tag == "br":
            out.append("<br>")
        elif tag in ("script", "style"):
            continue
        elif tag == "li":
            # A list inside a table cell, where a block list cannot go: each
            # item on its own line, never dropped.
            out.append(inline(child, media, unresolved).strip() + "<br>")
        else:
            out.append(inline(child, media, unresolved))
    return re.sub(r"[ \t]+", " ", "".join(out))


def list_items(node, media, unresolved) -> list[str]:
    """Every item of a list, including the ones the 1998 markup never closed.

    "<LI>one<LI>two<LI>three" parses as three items nested one inside the
    next, and rendering the first one swallowed the rest: the old links page
    came out as one bullet holding forty-two vendors. Text that sits in a list
    but outside any item (a <P> after the last <LI>) is an item of its own,
    because the old page showed it there.
    """
    items: list[str] = []
    pending = []

    def emit():
        if pending:
            from bs4 import BeautifulSoup
            holder = BeautifulSoup("<x></x>", "html.parser").x
            for part in pending:
                holder.append(part.__copy__() if hasattr(part, "__copy__") else part)
            html = inline(holder, media, unresolved).strip()
            if re.sub(r"<[^>]+>", "", html).strip() or "<img" in html:
                items.append(html)
            pending.clear()

    for child in list(node.children):
        name = getattr(child, "name", None)
        if name == "li":
            emit()
            own = [c for c in child.children if getattr(c, "name", None) not in ("li", "ul", "ol")]
            pending.extend(own)
            emit()
            nested = [c for c in child.children if getattr(c, "name", None) in ("li",)]
            for sub in nested:
                items.extend(list_items_from_li(sub, media, unresolved))
            for sub in [c for c in child.children if getattr(c, "name", None) in ("ul", "ol")]:
                items.extend(list_items(sub, media, unresolved))
        elif name in ("ul", "ol"):
            emit()
            items.extend(list_items(child, media, unresolved))
        else:
            pending.append(child)
    emit()
    return items


def list_items_from_li(li, media, unresolved) -> list[str]:
    from bs4 import BeautifulSoup
    wrapper = BeautifulSoup("<ul></ul>", "html.parser").ul
    wrapper.append(li.__copy__())
    return list_items(wrapper, media, unresolved)


def image_block(src: str, media, unresolved, caption: str = "", link: str | None = None) -> str | None:
    name = urllib.parse.unquote(os.path.basename(src or ""))
    if not name or is_chrome(name):
        return None
    if name not in media:
        unresolved.append(name)
        return None
    token = "{{media:" + media[name] + "}}"
    if link is None:
        # A photograph links to itself at full size, the way the old galleries
        # did; for the ones the folder supplied larger, that is the larger file.
        full = full_size_map().get(name)
        link = "{{media-full:" + (full or media[name]) + "}}"
    figcaption = (f'<figcaption class="wp-element-caption">{esc(caption)}</figcaption>'
                  if caption else "")
    img = f'<img src="{token}" alt="{esc(caption)}"/>'
    if link:
        img = f'<a href="{H.escape(link, quote=True)}">{img}</a>'
    return ('<!-- wp:image {"sizeSlug":"large","linkDestination":"media"} -->'
            f'<figure class="wp-block-image size-large">{img}'
            f"{figcaption}</figure><!-- /wp:image -->")


def para(text: str) -> str | None:
    if not re.sub(r"<[^>]+>", "", text).strip():
        return None
    return f"<!-- wp:paragraph --><p>{text.strip()}</p><!-- /wp:paragraph -->"


def heading(text: str, level: int = 2) -> str:
    return (f'<!-- wp:heading {{"level":{level}}} -->'
            f'<h{level} class="wp-block-heading">{esc(text)}</h{level}>'
            "<!-- /wp:heading -->")


def is_data_table(tbl) -> bool:
    """A table of DATA, as opposed to a 1998 page laid out with a table.

    The difference is the shape of the cells, not their number: the member
    roster is forty-four rows of three short cells, and a Field Day write-up is
    one cell with six hundred words in it. Counting rows alone turned the 2015
    write-up into a table and emitted its text twice -- 290% of the words of the
    page it came from.
    """
    rows = own_rows(tbl)
    if len(rows) < 3:
        return False
    widths, lengths = [], []
    for cells in rows:
        if not cells:
            continue
        widths.append(len(cells))
        lengths.extend(len(c.get_text(strip=True)) for c in cells)
    # Most rows, not every row: the roster is forty-one rows of three cells with
    # three single-cell rows around them -- a title, a note, a spacer. Requiring
    # every row to be wide threw the whole roster out.
    if not widths or sum(1 for w in widths if w >= 2) < 0.6 * len(widths):
        return False
    lengths.sort()
    median = lengths[len(lengths) // 2] if lengths else 0
    if median > 80:
        return False

    # A grid of photographs is tabular in shape and is not data. The 1998 Field
    # Day page is a four-by-three table of links to pictures with two words in
    # each cell, which passes every test above; published as a table it loses
    # every photograph on the page.
    cells = tbl.find_all(["td", "th"])
    pictorial = sum(
        1 for c in cells
        if c.find("img") or any(
            IMG_RE.search(urllib.parse.unquote(os.path.basename(
                (a.get("href") or "").split("?")[0])))
            for a in c.find_all("a"))
    )
    if cells and pictorial >= 0.4 * len(cells):
        return False

    return True


def own_rows(tbl) -> list[list]:
    """The rows that belong to THIS table, as lists of cells.

    Two things the 1998 markup does are handled here. A layout table with a
    table in a cell: find_all("tr") yielded the inner rows twice, and the old
    events page came out at 454% of its source. And a row with no opening
    <tr>: "</tr><td>Johnson, Jason</td><td>KBØEOD</td>..." -- the parser leaves
    those cells loose under the table, and keeping only <tr> children dropped
    Jason Johnson, the Society's Secretary, from all three rosters, though every
    browser showed him on the old site.
    """
    rows: list[list] = []
    loose: list = []

    def take(children):
        for child in children:
            name = getattr(child, "name", None)
            if name == "tr":
                if loose:
                    rows.append(list(loose))
                    loose.clear()
                rows.append([c for c in child.children if getattr(c, "name", None) in ("td", "th")])
            elif name in ("td", "th"):
                loose.append(child)
            elif name in ("tbody", "thead", "tfoot"):
                take(child.children)

    take(tbl.children)
    if loose:
        rows.append(list(loose))
    return [r for r in rows if r]


def table_block(tbl, media, unresolved) -> str | None:
    head, body = [], []
    rows = own_rows(tbl)
    for i, cells in enumerate(rows):
        rendered = [inline(c, media, unresolved) for c in cells]
        if not any(re.sub(r"<[^>]+>", "", c).strip() for c in rendered):
            continue
        is_header = (i == 0 and all(c.name == "th" for c in cells)) or (
            i == 0 and all(re.search(r"<strong>", c) for c in rendered))
        row = "<tr>" + "".join(
            f"<{'th' if is_header else 'td'}>{re.sub('</?strong>', '', c) if is_header else c}"
            f"</{'th' if is_header else 'td'}>" for c in rendered) + "</tr>"
        (head if is_header else body).append(row)
    if not body:
        return None
    return ('<!-- wp:table {"className":"maars-roster"} -->'
            '<figure class="wp-block-table maars-roster"><table>'
            + (f"<thead>{''.join(head)}</thead>" if head else "")
            + f"<tbody>{''.join(body)}</tbody></table></figure><!-- /wp:table -->")


def content_root(soup):
    """Where to start walking.

    The whole body. The first version of this took the biggest <td> instead, on
    the theory that a 1998 layout table has one content cell -- and lost the
    forty-four-row member roster (the biggest cell was the footnote under it)
    and every photograph on the Field Day pages (the picture and its caption sit
    in different cells). Walking everything and filtering the furniture by name
    keeps both, and these pages have no navigation worth excluding.
    """
    return soup.body or soup


BLOCKISH = ["ul", "ol", "li", "table", "p", "div", "center", "h1", "h2", "h3", "h4", "h5", "h6",
            "blockquote", "hr"]


def convert_page(paths: list[str], media, kind: str) -> tuple[list[str], list[str], dict]:
    """One page of the old site as a list of block strings."""
    from bs4 import BeautifulSoup, Comment, NavigableString

    blocks: list[str] = []
    unresolved: list[str] = []
    stats = {"images": 0, "tables": 0, "paragraphs": 0, "headings": 0,
             "words_in": 0, "words_out": 0}

    for path in paths:
        soup = BeautifulSoup(read(path), "html.parser")
        for bad in soup.find_all(["script", "style"]):
            bad.decompose()
        stats["words_in"] += len(soup.get_text(" ", strip=True).split())
        root = content_root(soup)

        buffer: list[str] = []

        def flush():
            if not buffer:
                return
            text = re.sub(r"(<br>\s*){2,}", "\n\n", "".join(buffer))
            for chunk in re.split(r"\n\n+", text):
                chunk = chunk.strip()
                # A run that is nothing but one bolded line is a heading.
                bare = re.sub(r"<[^>]+>", "", chunk).strip()
                if not bare:
                    # <A NAME="figure">&nbsp;</A>: no text, but it is where the
                    # issue's "see figure 1 below" lands. Keep the target.
                    for anchor in re.findall(r'<a id="[^"]+"></a>', chunk):
                        blocks.append(f"<!-- wp:html -->{anchor}<!-- /wp:html -->")
                    continue
                only_strong = re.fullmatch(r"\s*<strong>(.*?)</strong>\s*", chunk, re.S)
                # A bolded line is a heading -- unless it is a link. On the
                # GeoCities page "*Kansas Repeaters" and the committee e-mail
                # names were bold links, and as headings they lost the links.
                if only_strong and len(bare) < 90 and "<a " not in chunk:
                    blocks.append(heading(re.sub(r"<[^>]+>", "", only_strong.group(1)).strip(), 3))
                    stats["headings"] += 1
                    continue
                # "Nadine Stueve, KUHF, age 91, of Wamego, passed away on ..."
                # Each notice opens with the member's name and callsign in bold
                # and runs straight on into the obituary. Without this the whole
                # page is one undifferentiated column of 228 paragraphs with no
                # way to find anyone in it.
                opener = re.match(r"\s*<strong>(.{3,80}?)</strong>\s*(.*)", chunk, re.S)
                if kind == "memorial" and opener and re.search(
                        r"[A-Z][A-Za-z.'-]+\s*,\s*[A-Z0-9\u00d8/]{3,7}", opener.group(1)):
                    blocks.append(heading(re.sub(r"<[^>]+>", "", opener.group(1)).strip(), 3))
                    stats["headings"] += 1
                    rest = opener.group(2).strip().lstrip(",").strip()
                    if rest:
                        block = para(rest[0].upper() + rest[1:] if rest[:1].islower() else rest)
                        if block:
                            blocks.append(block)
                            stats["paragraphs"] += 1
                    continue
                block = para(chunk.replace("<br>", "<br>"))
                if block:
                    blocks.append(block)
                    stats["paragraphs"] += 1
            buffer.clear()

        def walk(node):
            for child in node.children:
                if isinstance(child, Comment):
                    continue
                if isinstance(child, NavigableString):
                    buffer.append(esc(str(child)))
                    continue
                tag = child.name.lower()
                if tag == "img":
                    flush()
                    block = image_block(child.get("src", ""), media, unresolved)
                    if block:
                        blocks.append(block)
                        stats["images"] += 1
                elif tag == "table":
                    # A gallery page can carry both: the 1998 page is one table
                    # holding the photographs AND the Field Day score. Take the
                    # pictures out of it first, then decide what is left.
                    if kind == "gallery":
                        for node in list(child.find_all(["img", "a"])):
                            # An <a> taken out takes its <img> with it, and the
                            # list still holds the child. A decomposed node has
                            # no attributes at all.
                            if node.parent is None or getattr(node, "attrs", None) is None:
                                continue
                            ref = node.get("src") if node.name == "img" else node.get("href")
                            if not ref:
                                continue
                            if not IMG_RE.search(urllib.parse.unquote(
                                    os.path.basename(ref.split("?")[0]))):
                                continue
                            caption = (node.get_text(" ", strip=True)
                                       if node.name == "a" else "")
                            block = image_block(ref, media, unresolved, caption)
                            if block:
                                flush()
                                blocks.append(block)
                                stats["images"] += 1
                            node.decompose()
                    if is_data_table(child):
                        flush()
                        block = table_block(child, media, unresolved)
                        if block:
                            blocks.append(block)
                            stats["tables"] += 1
                    else:
                        walk(child)
                elif tag in ("p", "div", "center", "tr", "td", "tbody", "blockquote"):
                    flush()
                    walk(child)
                    flush()
                elif re.fullmatch(r"h[1-6]", tag):
                    flush()
                    text = child.get_text(" ", strip=True)
                    if text:
                        blocks.append(heading(text, min(3, int(tag[1]) + 1)))
                        stats["headings"] += 1
                elif tag in ("ul", "ol"):
                    flush()
                    items = "".join(f"<li>{item}</li>" for item in list_items(child, media, unresolved))
                    if items:
                        tagname = "ol" if tag == "ol" else "ul"
                        ordered = ' {"ordered":true}' if tag == "ol" else ""
                        blocks.append(f"<!-- wp:list{ordered} --><{tagname} "
                                      f'class="wp-block-list">{items}</{tagname}>'
                                      "<!-- /wp:list -->")
                elif tag == "hr":
                    flush()
                elif (tag == "a" and kind == "gallery" and child.get("href")
                      and IMG_RE.search(urllib.parse.unquote(
                          os.path.basename(child["href"].split("?")[0])))):
                    # The old gallery pages linked to their photographs rather
                    # than showing them, because a 1997 page could not afford
                    # the bytes. The link text is the caption.
                    flush()
                    block = image_block(child["href"], media, unresolved,
                                        child.get_text(" ", strip=True))
                    if block:
                        blocks.append(block)
                        stats["images"] += 1
                elif (tag == "a" and child.get("href") and child.find("img")
                      and not child.get_text(strip=True)):
                    # <a href="repeater_1-2020_4032.jpg"><img src="..._600.jpg"></a>:
                    # a small picture that opens the big one. It stays a picture,
                    # linked to the big one at full size.
                    img = child.find("img")
                    name = urllib.parse.unquote(os.path.basename(img.get("src", "") or ""))
                    if is_chrome(name or "x") or name not in media:
                        buffer.append(inline_one(child, media, unresolved))
                    else:
                        flush()
                        target = resolve_ref(child["href"], media, unresolved)
                        block = image_block(img.get("src", ""), media, unresolved, "", target or "")
                        if block:
                            blocks.append(block)
                            stats["images"] += 1
                elif tag in ("b", "strong", "i", "em", "a", "font", "br", "span",
                             "sup", "sub", "small", "big", "u", "tt", "code"):
                    if child.find(BLOCKISH):
                        # <font size="+1"><ol>...</ol></font>: an inline wrapper
                        # around block content is a container, or the list in it
                        # is flattened into one line of text.
                        walk(child)
                    else:
                        buffer.append(inline_one(child, media, unresolved))
                else:
                    walk(child)

        def inline_one(child, media, unresolved):
            wrapper = BeautifulSoup("<x></x>", "html.parser").x
            wrapper.append(child.__copy__())
            return inline(wrapper, media, unresolved)

        walk(root)
        flush()

    plain = re.sub(r"<[^>]+>", " ", "\n".join(blocks))
    stats["words_out"] = len(plain.split())
    return blocks, unresolved, stats


# Navigation from a 1997 page, which is furniture: "next", "back to the
# index", the GeoCities advertisement. ONLY a line that is nothing else is
# dropped. The first version dropped any paragraph whose links all read "here"
# or "click here", and that took real sentences with it: "Online condolences may
# be left for the family by clicking here", the Taste of IWR course, the TARPN
# network, Myron Calhoun's lists of area amateurs.
NAV_TEXT = re.compile(r"^\s*(click|here|next|prev(ious)?|back|more|index|top|home)\b",
                      re.I)
ANCHOR = re.compile(r"<a\b[^>]*>(.*?)</a>", re.S)

JUNK = [
    re.compile(r"hosted by GeoCities", re.I),
    re.compile(r"free home page", re.I),
]


CLOSERS = re.compile(r"</(strong|em|a|p|span|font|b|i)>", re.I)
OPENERS = re.compile(r"<(strong|em|a|span|font|b|i)\b", re.I)


def balance(block: str) -> str:
    """Drop close tags with nothing open in front of them.

    The source is hand-written 1997 HTML with unbalanced <B> and <FONT> in it,
    and an orphaned </strong> inside a paragraph block is markup WordPress will
    happily store and the browser will happily ignore -- until the block editor
    flags the page as invalid and offers to "attempt recovery".
    """
    opened: list[str] = []
    out = []
    pos = 0
    for m in re.finditer(r"<(/?)(strong|em|a|span|font|b|i)\b[^>]*>", block, re.I):
        out.append(block[pos:m.start()])
        pos = m.end()
        tag = m.group(2).lower()
        if m.group(1):
            if tag in opened:
                opened.remove(tag)
                out.append(m.group(0))
            # else: an orphan, dropped
        else:
            opened.append(tag)
            out.append(m.group(0))
    out.append(block[pos:])
    # Anything still open at the end of the block is closed here, in reverse:
    # an unclosed <strong> runs the emphasis into the next block.
    for tag in reversed(opened):
        out.append(f"</{tag}>")
    return "".join(out)


def dedupe_headings(blocks: list[str]) -> list[str]:
    """One banner heading, not nine.

    Nine pages folded into one carry nine copies of the banner each of them
    wore -- "MAARS ARRL Field Day 1997 Photo Gallery", once above every
    photograph.
    """
    seen: set[str] = set()
    out = []
    for block in blocks:
        if block.startswith("<!-- wp:heading"):
            text = re.sub(r"[^a-z0-9]+", " ",
                          re.sub(r"<[^>]+>", " ", block).lower()).strip()
            if text in seen:
                continue
            seen.add(text)
        out.append(block)
    return out


def drop_navigation(blocks: list[str]) -> list[str]:
    kept = []
    for block in blocks:
        text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", re.sub(r"<!--.*?-->", "", block))).strip()
        text = text.replace("\xa0", " ")
        if any(j.search(text) for j in JUNK):
            continue
        if block.startswith("<!-- wp:paragraph"):
            anchors = ANCHOR.findall(block)
            nav = [a for a in anchors if NAV_TEXT.match(re.sub(r"<[^>]+>", "", a))]
            if nav:
                rest = text
                for a in nav:
                    rest = rest.replace(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", a)).strip(), " ", 1)
                rest = re.sub(r"\s+", " ", rest).strip()
                if len(rest.split()) == 0 and len(nav) == len(anchors):
                    continue              # nothing but "next" / "back to index"
                if re.match(r"^\s*click\b", text, re.I) and nav and len(rest.split()) <= 12:
                    # The 1997 gallery index: "click  Fred Stueve and Lenore
                    # Layman hang the banner". The word "click" was navigation;
                    # the caption is the record. Keep the caption.
                    block = ANCHOR.sub(lambda m: "" if NAV_TEXT.match(
                        re.sub(r"<[^>]+>", "", m.group(1))) else m.group(0), block, count=1)
                    block = re.sub(r"(<p[^>]*>)\s*(click\s*)?", r"\1", block, count=1, flags=re.I)
        kept.append(balance(block))
    return kept


def drop_repeated_title(blocks: list[str], title: str) -> list[str]:
    """A page whose first heading is its own title says it twice.

    The old pages carried their title in the body because they had no theme to
    put it in the header; this one does.
    """
    wanted = re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()
    out = []
    for i, block in enumerate(blocks):
        if i < 3 and block.startswith("<!-- wp:heading"):
            text = re.sub(r"<[^>]+>", " ", block)
            text = re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()
            if text == wanted:
                continue
        out.append(block)
    return out


# ---------------------------------------------------------------------------
# Text the webmaster took off a page by commenting it out instead of deleting it:
# retired announcements, an officer's row, the note about the missing minutes
# of February 2023. A browser never showed it, so it is not what the page said;
# it IS part of the record, and the Society asked for all of it. It goes at the
# foot of the page under its own heading, so nobody mistakes it for the page.
#
# Roster pages never get this: the rows hidden there are members taken off the
# public list, one of them at the member's own request.
# ---------------------------------------------------------------------------
MARKER = re.compile(r"^\s*((BEGINNING|END) OF\b|(END OF )?CONTENTS FOR\b|ENCLOSING TABLE"
                    r"|This is a blank space row)|x{4,}|text below generated by server", re.I)


def retired_fragments(path: str) -> list[str]:
    """The commented-out HTML of one page worth keeping, in page order."""
    out = []
    for m in re.finditer(r"<!--(.*?)-->", read(path), re.S):
        inner = m.group(1)
        words = H.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", inner))).strip()
        if MARKER.search(words):
            continue                      # layout markers and blank templates
        linked = re.search(r'<a\s[^>]*href\s*=\s*"(?!#|")', inner, re.I)
        pictured = any(
            not is_chrome(os.path.basename(src))
            for src in re.findall(r'<img[^>]*src\s*=\s*"([^"]+)"', inner, re.I))
        if len(words.split()) >= 3 or linked or pictured:
            out.append(inner)
    return out


def retired_blocks(path: str, media) -> list[str]:
    import tempfile

    fragments = retired_fragments(path)
    if not fragments:
        return []
    blocks = [heading("Taken off the page, but kept in its code", 2),
              '<!-- wp:paragraph --><p>The webmaster took these off the page by turning them into '
              "comments in its code, which a browser does not show, instead of deleting them. "
              "They are kept here as written, in the order they appear in the page.</p>"
              "<!-- /wp:paragraph -->"]
    with tempfile.TemporaryDirectory() as tmp:
        for i, fragment in enumerate(fragments):
            body = fragment
            if re.search(r"<t[rd]\b", body, re.I) and not re.search(r"<table\b", body, re.I):
                body = "<table>" + body + "</table>"
            path_i = os.path.join(tmp, f"retired-{i}.html")
            with open(path_i, "w") as fh:
                fh.write("<html><body>" + body + "</body></html>")
            converted, _, _ = convert_page([path_i], media, "article")
            converted = drop_navigation(converted)
            if not converted:
                continue
            if len(blocks) > 2:
                blocks.append('<!-- wp:separator --><hr class="wp-block-separator has-alpha-channel-opacity"/>'
                              "<!-- /wp:separator -->")
            blocks.extend(converted)
    return blocks if len(blocks) > 2 else []


NUMBER_WORDS = ("zero one two three four five six seven eight nine ten eleven twelve thirteen "
                "fourteen fifteen sixteen seventeen eighteen nineteen").split()
TENS_WORDS = "_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()


def number_words(n: int) -> str:
    if n < 20:
        return NUMBER_WORDS[n]
    if n < 100:
        tens, unit = divmod(n, 10)
        return TENS_WORDS[tens] + ("-" + NUMBER_WORDS[unit] if unit else "")
    return str(n)


def roster_names(blocks: str) -> int:
    """Rows of a roster table that are a member: three cells, a name in the first."""
    count = 0
    for row in re.findall(r"<tr>(.*?)</tr>", blocks, re.S):
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)
        if len(cells) == 3 and re.search(r"[A-Za-z]", re.sub(r"<[^>]+>", "", cells[0])):
            count += 1
    return count


# ---------------------------------------------------------------------------
# /club-files/ -- every file that is not an archive record, by topic.
#
# Generated from media/manifest.json rather than written by hand, because a hand
# list is the kind of thing that is complete on the day it is written: every
# manifest item carrying a `category` is placed here, and tests/test_static.py
# checks that nothing in the manifest is left unreachable.
# ---------------------------------------------------------------------------
CLUB_FILE_SECTIONS = [
    ("membership", "Membership",
     "Applications, dues and rates, and the member lists the Society kept for its own use, "
     "with addresses, telephone numbers and e-mail as the club recorded them."),
    ("meetings", "Meetings and meeting places",
     "Flyers, floor plans and the rooms the Society has met in."),
    ("breakfast", "Saturday breakfast",
     "The places the Saturday breakfast has met. The announcements are on "
     "<a href=\"/events/breakfast/\">the breakfast page</a>."),
    ("field-day", "Field Day",
     "Every Field Day photograph and file, year by year. The galleries on "
     "<a href=\"/events/\">the events page</a> show the same photographs with their captions."),
    ("winter-field-day", "Winter Field Day", ""),
    ("events", "Other events",
     "Fox hunts, Christmas parties, picnics, public-service events and hamfests."),
    ("storm-spotting", "Storm spotting",
     "The W.A.R.N. storm spotter documents and map, beside "
     "<a href=\"/storm-spotting/\">the storm spotting page</a>."),
    ("exams", "License exams",
     "The old site's exam page is kept as <a href=\"/exams/\">License exams</a>."),
    ("officers", "Officers, past", "Portraits from an earlier officers page."),
    ("silent-keys", "Silent Keys",
     "The portraits from the notices on <a href=\"/silent-keys/\">the Silent Keys page</a>, "
     "the larger copies the webmaster kept, and a memorial card."),
    ("photographs", "Photographs at full size",
     "Photographs the old site served at full camera size. The ones marked full size are the "
     "files exactly as ks0man.com served them; beside each are the smaller copies the "
     "pages show."),
    ("collections", "Antique radios and station logs",
     "A member's antique receivers and handwritten logs, as the webmaster kept them."),
    ("repeater", "The repeater and repeater lists",
     "Photographs of the repeater, and the Kansas repeater lists the old site offered as "
     "spreadsheets for loading into a radio."),
    ("reading", "Reading room",
     "Reference material the old site carried, including articles, charts, forms and a video "
     "by other authors, published here as they were there."),
    ("history", "History", ""),
    ("site", "The old website itself",
     "Logos, newsletter art, the small graphics the 1997 pages were built from, the "
     "webmaster's design files, and every web page of the old site in two zips: exactly as "
     "ks0man.com served them, and as the webmaster kept them in the folder."),
]

SHOWABLE = {".jpg", ".jpeg", ".png", ".gif", ".bmp"}
YEAR_FROM = [(re.compile(r"^fd(\d\d)", re.I), lambda m: ("19" if int(m.group(1)) > 50 else "20") + m.group(1)),
             (re.compile(r"(19\d\d|20[0-2]\d)"), lambda m: m.group(1))]


def human_label(src: str) -> str:
    base = src.replace(" (the webmaster's copy)", "")
    stem = os.path.splitext(base)[0] if "." in base else base
    stem = re.sub(r"[_]+", " ", stem)
    stem = re.sub(r"\s+", " ", stem).strip()
    if src.endswith(" (the webmaster's copy)"):
        stem += ", full size"
    return stem


def size_label(n: int) -> str:
    if n >= 1048576:
        return f"{n / 1048576:.1f} MB"
    return f"{max(1, round(n / 1024))} KB"


def kind_label(name: str) -> str:
    ext = os.path.splitext(name)[1].lower()
    return {
        ".pdf": "PDF", ".doc": "Word", ".docx": "Word", ".rtf": "RTF", ".txt": "text",
        ".xls": "Excel", ".xlsx": "Excel", ".csv": "CSV", ".pptx": "PowerPoint",
        ".mp4": "video", ".zip": "zip", ".psd": "Photoshop", ".indd": "InDesign",
        ".pm": "PageMaker", ".ttf": "font", ".ico": "icon", ".bmp": "bitmap",
    }.get(ext, ext.lstrip(".").upper())


def club_files_page(manifest: list) -> dict:
    blocks = ['<!-- wp:paragraph {"className":"maars-lede"} --><p class="maars-lede">'
              "Every file from the Society's old website, and from the folder the webmaster built "
              "it from, by what it is about, apart from the newsletters, minutes and reports. "
              'Those are in <a href="/archive/">the archive</a>, each on its own page with every '
              "format it was kept in. A photograph shown on another page is here as well.</p>"
              "<!-- /wp:paragraph -->"]

    by_cat: dict[str, list] = {}
    for item in manifest:
        if item.get("category"):
            by_cat.setdefault(item["category"], []).append(item)

    toc = []
    for key, title, _ in CLUB_FILE_SECTIONS:
        if by_cat.get(key):
            toc.append(f'<!-- wp:list-item --><li><a href="#{key}">{esc(title)}</a> '
                       f'({len(by_cat[key])})</li><!-- /wp:list-item -->')
    blocks.append('<!-- wp:list {"className":"maars-club-files__toc"} -->'
                  '<ul class="wp-block-list maars-club-files__toc">' + "".join(toc)
                  + "</ul><!-- /wp:list -->")

    def gallery(items: list) -> str:
        figures = []
        for item in items:
            token = "{{media:" + item["file"] + "}}"
            # The link opens the file as uploaded. For a photograph over 2560px
            # WordPress shows a "-scaled" copy; {{media-full:}} is the upload.
            full = "{{media-full:" + item["file"] + "}}"
            label = esc(human_label(item["src"]))
            figures.append('<!-- wp:image {"sizeSlug":"large","linkDestination":"media"} -->'
                           f'<figure class="wp-block-image size-large"><a href="{full}">'
                           f'<img src="{token}" alt="{label}"/></a>'
                           f'<figcaption class="wp-element-caption">{label}</figcaption></figure>'
                           "<!-- /wp:image -->")
        return ('<!-- wp:gallery {"columns":3,"linkTo":"media","className":"maars-club-files__gallery"} -->'
                '<figure class="wp-block-gallery has-nested-images columns-3 is-cropped '
                'maars-club-files__gallery">' + "".join(figures) + "</figure><!-- /wp:gallery -->")

    def listing(items: list) -> str:
        rows = []
        for item in items:
            token = "{{media:" + item["file"] + "}}"
            rows.append(f'<!-- wp:list-item --><li><a href="{token}">{esc(human_label(item["src"]))}</a> '
                        f'<span class="maars-club-files__meta">{kind_label(item["file"])}, '
                        f'{size_label(item["bytes"])}</span></li><!-- /wp:list-item -->')
        return ('<!-- wp:list {"className":"maars-club-files__list"} -->'
                '<ul class="wp-block-list maars-club-files__list">' + "".join(rows)
                + "</ul><!-- /wp:list -->")

    def videos(items: list) -> list:
        out = []
        for item in items:
            token = "{{media:" + item["file"] + "}}"
            out.append('<!-- wp:video --><figure class="wp-block-video">'
                       f'<video controls preload="metadata" src="{token}"></video>'
                       f'<figcaption class="wp-element-caption">{esc(human_label(item["src"]))}, '
                       f'{size_label(item["bytes"])}</figcaption></figure><!-- /wp:video -->')
        return out

    def section_blocks(items: list) -> list:
        items = sorted(items, key=lambda i: human_label(i["src"]).lower())
        shown = [i for i in items if os.path.splitext(i["file"])[1].lower() in SHOWABLE]
        vids = [i for i in items if i["file"].lower().endswith(".mp4")]
        rest = [i for i in items if i not in shown and i not in vids]
        out = []
        if shown:
            out.append(gallery(shown))
        out.extend(videos(vids))
        if rest:
            out.append(listing(rest))
        return out

    for key, title, intro in CLUB_FILE_SECTIONS:
        items = by_cat.get(key)
        if not items:
            continue
        blocks.append(f'<!-- wp:heading {{"level":2,"anchor":"{key}"}} -->'
                      f'<h2 class="wp-block-heading" id="{key}">{esc(title)}</h2><!-- /wp:heading -->')
        if intro:
            blocks.append(f"<!-- wp:paragraph --><p>{intro}</p><!-- /wp:paragraph -->")
        if key == "field-day":
            years: dict[str, list] = {}
            for item in items:
                year = "Other"
                for pattern, fmt in YEAR_FROM:
                    m = pattern.search(item["src"])
                    if m:
                        year = fmt(m)
                        break
                years.setdefault(year, []).append(item)
            for year in sorted(years, key=lambda y: (y == "Other", y)):
                blocks.append(f'<!-- wp:heading {{"level":3,"anchor":"field-day-{year.lower()}"}} -->'
                              f'<h3 class="wp-block-heading" id="field-day-{year.lower()}">'
                              f"{esc(year)}</h3><!-- /wp:heading -->")
                blocks.extend(section_blocks(years[year]))
        else:
            blocks.extend(section_blocks(items))

    placed = sum(len(v) for k, v in by_cat.items() if k in {c[0] for c in CLUB_FILE_SECTIONS})
    unplaced = [i["src"] for k, v in by_cat.items() if k not in {c[0] for c in CLUB_FILE_SECTIONS} for i in v]
    if unplaced:
        raise SystemExit(f"club files: categories with no section: {unplaced}")
    return {
        "slug": "club-files",
        "title": "Club files",
        "parent": None,
        "kind": "index",
        "sources": ["media/manifest.json"],
        "files": placed,
        "blocks": "\n\n".join(blocks),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--report", action="store_true", help="print what each page became")
    ap.add_argument("--mirror", default=MIRROR)
    args = ap.parse_args()

    if not os.path.isdir(args.mirror):
        print(f"no mirror at {args.mirror}")
        return 2

    media = media_map()
    pages = []
    all_unresolved: dict[str, list[str]] = {}

    def locate(name: str) -> str:
        for base in (args.mirror, FOLDER):
            path = os.path.join(base, name)
            if os.path.exists(path):
                return path
        return os.path.join(args.mirror, name)

    for spec in PAGES:
        paths = [locate(s) for s in spec["sources"]]
        missing = [p for p in paths if not os.path.exists(p)]
        if missing:
            print(f"  {spec['slug']}: source missing: {missing}")
            continue
        blocks, unresolved, stats = convert_page(paths, media, spec["kind"])
        blocks = drop_navigation(blocks)
        if len(spec["sources"]) > 1:
            blocks = dedupe_headings(blocks)
        blocks = drop_repeated_title(blocks, spec["title"])
        if spec.get("epilogue"):
            blocks.extend(spec["epilogue"])
        if spec.get("retired") and spec["kind"] != "roster":
            for path in paths:
                blocks.extend(retired_blocks(path, media))
        if spec.get("lede"):
            blocks.insert(0, '<!-- wp:paragraph {"className":"maars-lede"} -->'
                             f'<p class="maars-lede">{esc(spec["lede"])}</p>'
                             "<!-- /wp:paragraph -->")
        pages.append({
            "slug": spec["slug"],
            "title": spec["title"],
            "parent": spec["parent"],
            "kind": spec["kind"],
            "sources": spec["sources"],
            "source_paths": [("mirror/ks0man.com/" if p.startswith(args.mirror) else "webmaster-folder/")
                             + os.path.basename(p) for p in paths],
            "blocks": "\n\n".join(blocks),
        })
        if unresolved:
            all_unresolved[spec["slug"]] = sorted(set(unresolved))
        if args.report:
            print(f"  {spec['slug']:24} {stats['words_out']:5}w  "
                  f"{stats['headings']:3}h {stats['paragraphs']:3}p "
                  f"{stats['images']:3}img {stats['tables']:2}tbl   "
                  f"retention {stats['words_out']/max(1,stats['words_in']):.0%}")

    # Jump links whose target did not survive. "#TOP" pointed at an anchor in
    # the old layout's header, which is furniture; a bare "#" goes to the top of
    # the page. The announcements file was written to be pasted into the home
    # page, so its "#upcoming" means the home page's section of that name.
    ids_by_slug = {pg["slug"]: set(re.findall(r'id="([^"]+)"', pg["blocks"])) for pg in pages}

    def fix_fragments(pg):
        ids = ids_by_slug[pg["slug"]]

        def swap(m):
            frag = m.group(1)
            if frag in ids:
                return m.group(0)
            if frag.lower() == "top":
                return 'href="#"'
            if frag in ids_by_slug.get("old-home-page", set()):
                return f'href="/history/old-home-page/#{frag}"'
            return 'href="#"'
        pg["blocks"] = re.sub(r'href="#([^"]+)"', swap, pg["blocks"])

    for pg in pages:
        fix_fragments(pg)

    # "{names:roster-2014}": a roster's size, counted from the roster as shown.
    # Typed counts said twenty-nine and forty-six, counting rows the webmaster
    # had hidden in the pages' code, beside rosters showing seventeen and
    # thirty-five.
    counts = {pg["slug"]: roster_names(pg["blocks"]) for pg in pages if pg["kind"] == "roster"}

    def fill(m):
        n = counts.get(m.group(1))
        if n is None:
            raise SystemExit(f"no roster called {m.group(1)}")
        return number_words(n) + (" name" if n == 1 else " names")
    for pg in pages:
        pg["blocks"] = re.sub(r"\{names:([a-z0-9-]+)\}", fill, pg["blocks"])

    manifest = json.load(open(os.path.join(ROOT, "media", "manifest.json")))
    club = club_files_page(manifest)
    pages.append(club)
    if args.report:
        print(f"  {'club-files':24} {club['files']} files placed by topic")

    json.dump({"schema": "maars-mirror-pages/1",
               "generated": "2026-10-17",
               "note": "Pages of ks0man.com the archive migration did not carry. "
                       "Media and archive references are tokens; tools/push_pages.py "
                       "resolves them against a live site.",
               "pages": pages},
              open(OUT, "w"), indent=2, ensure_ascii=False)
    open(OUT, "a").write("\n")

    print(f"\n  wrote {OUT}: {len(pages)} pages, "
          f"{sum(len(p['blocks']) for p in pages)//1024} KB of block markup")
    if all_unresolved:
        print("\n  references that resolve to nothing (dropped, not published):")
        for slug, names in sorted(all_unresolved.items()):
            print(f"    {slug}: {', '.join(names)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
