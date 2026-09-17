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
OUT = os.path.join(ROOT, "content", "mirror_pages.json")

# Furniture from a 1998 web page: rules, arrows, "back to top" hands, the
# Acrobat badge, the GeoCities counter. None of it is the record.
CHROME = {
    "spacebar.gif", "blueline_6px.gif", "maroon_line.gif", "top.gif", "home.gif",
    "goback.gif", "acrobat.gif", "email.gif", "e-mail.png", "lefthand.gif",
    "mac-blk.gif", "FDpulsarani.gif", "rcbackbg.gif", "gc_icon.gif",
    "newsart.jpg", "newscollage.gif", "news40wpm.jpg", "favicon.ico",
}
CHROME_RE = re.compile(r"^(news[a-z0-9]*\.gif|maarslogo|newscollage|visit\.gif)", re.I)

# The pages, what they become, and what they are made of. A photo story the old
# site split across nine pages becomes one page here: nine clicks to see eight
# photographs is a 1997 constraint, not a decision worth migrating.
PAGES = [
    {"slug": "members", "title": "Members", "parent": None,
     "sources": ["members.html"], "kind": "roster",
     "lede": "The Society's roster as it stood on the old site: name, callsign "
             "and town, published by the club about the club."},
    {"slug": "silent-keys", "title": "Silent Keys", "parent": None,
     "sources": ["silentkey.html"], "kind": "memorial",
     "lede": "Members the Society has lost. Each notice is as the club published "
             "it at the time."},
    {"slug": "field-day-1997", "title": "Field Day 1997", "parent": "events",
     "sources": ["FD97.html", "FD97-1.html", "FD97-2.html", "FD97-3.html",
                 "FD97-4.html", "FD97-5.html", "FD97-6.html", "FD97-7.html",
                 "FD97-8.html"], "kind": "gallery"},
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
    {"slug": "downloads", "title": "Downloads", "parent": None,
     "sources": ["downloads.html"], "kind": "article",
     "lede": "Repeater lists and forms the Society keeps for its members to load "
             "into a radio."},
]

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
for _n in range(1, 9):
    PAGE_LINKS[f"FD97-{_n}.html"] = "/events/field-day-1997/"

DOC_RE = re.compile(r"\.(pdf|docx?|csv|zip|mp4)$", re.I)
IMG_RE = re.compile(r"\.(jpe?g|png|gif)$", re.I)
NEWSLETTER_RE = re.compile(r"^newsletter_[\w.-]+\.(pdf|html?|docx?)$", re.I)


def read(path: str) -> str:
    raw = open(path, "rb").read()
    for enc in ("utf-8", "cp1252", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1", "replace")


def media_map() -> dict[str, str]:
    """Original name on ks0man.com -> the name the file ships under."""
    manifest = json.load(open(os.path.join(ROOT, "media", "manifest.json")))
    return {item["src"]: item["file"] for item in manifest}


def esc(text: str) -> str:
    return H.escape(text, quote=False)


def resolve_ref(href: str, media: dict[str, str], unresolved: list[str]) -> str | None:
    """Rewrite one href from the old site. None means 'drop the link'."""
    href = (href or "").strip()
    if not href or href.startswith(("mailto:", "#", "javascript:")):
        return href or None
    if href.startswith("http"):
        if "ks0man.com" not in href:
            return href                      # a genuine outbound link, kept
        href = urllib.parse.urlparse(href).path
    name = urllib.parse.unquote(os.path.basename(href.split("?")[0].split("#")[0]))
    if not name:
        return "/"
    if NEWSLETTER_RE.match(name):
        return "{{pub:" + name + "}}"
    if name in PAGE_LINKS:
        return PAGE_LINKS[name]
    if DOC_RE.search(name) or IMG_RE.search(name):
        if name in media:
            return "{{media:" + media[name] + "}}"
        unresolved.append(name)
        return None
    if name.endswith(".html"):
        unresolved.append(name)
        return None
    return href


def inline(node, media, unresolved) -> str:
    """Inline content, keeping emphasis and links, dropping <font> and chrome."""
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
            out.append(f'<a href="{H.escape(target, quote=True)}">{text}</a>'
                       if target else text)
        elif tag == "br":
            out.append("<br>")
        elif tag in ("script", "style"):
            continue
        else:
            out.append(inline(child, media, unresolved))
    return re.sub(r"[ \t]+", " ", "".join(out))


def image_block(src: str, media, unresolved, caption: str = "") -> str | None:
    name = urllib.parse.unquote(os.path.basename(src or ""))
    if not name or name in CHROME or CHROME_RE.match(name):
        return None
    if name not in media:
        unresolved.append(name)
        return None
    token = "{{media:" + media[name] + "}}"
    figcaption = (f'<figcaption class="wp-element-caption">{esc(caption)}</figcaption>'
                  if caption else "")
    return ('<!-- wp:image {"sizeSlug":"large"} -->'
            f'<figure class="wp-block-image size-large"><img src="{token}" alt=""/>'
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
    rows = tbl.find_all("tr", recursive=False) or tbl.find_all("tr")
    if len(rows) < 3:
        return False
    widths, lengths = [], []
    for tr in rows:
        cells = tr.find_all(["td", "th"], recursive=False) or tr.find_all(["td", "th"])
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


def table_block(tbl, media, unresolved) -> str | None:
    head, body = [], []
    rows = tbl.find_all("tr")
    for i, tr in enumerate(rows):
        cells = tr.find_all(["td", "th"])
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
                    continue
                only_strong = re.fullmatch(r"\s*<strong>(.*?)</strong>\s*", chunk, re.S)
                if only_strong and len(bare) < 90:
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
                    items = "".join(
                        f"<li>{inline(li, media, unresolved)}</li>"
                        for li in child.find_all("li", recursive=False))
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
                elif tag in ("b", "strong", "i", "em", "a", "font", "br", "span",
                             "sup", "sub", "small", "big", "u", "tt", "code"):
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


# "click here", "next", "back to the index": the navigation of a 1997 photo
# gallery, which is furniture and not content. The captions it points at are on
# the page already, under the photographs themselves, so what is left after this
# is the gallery rather than an index of a gallery that no longer has pages.
NAV_TEXT = re.compile(r"^\s*(click|here|next|prev(ious)?|back|more|index|top|home)\b",
                      re.I)
ANCHOR = re.compile(r"<a\b[^>]*>(.*?)</a>", re.S)


# What a 1997 page carried that was never the club's: the hosting company's
# advertisement at the foot of every GeoCities page, and the index of a photo
# gallery whose pages have all been folded into one.
JUNK = [
    re.compile(r"hosted by GeoCities", re.I),
    re.compile(r"free home page", re.I),
    re.compile(r"^\s*click\b", re.I),          # "click  Willard Fischer on the air"
    re.compile(r"gallery index\s*$", re.I),
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
        anchors = ANCHOR.findall(block)
        if anchors and all(NAV_TEXT.match(re.sub(r"<[^>]+>", "", a)) for a in anchors):
            if block.startswith("<!-- wp:paragraph"):
                continue
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

    for spec in PAGES:
        paths = [os.path.join(args.mirror, s) for s in spec["sources"]]
        missing = [p for p in paths if not os.path.exists(p)]
        if missing:
            print(f"  {spec['slug']}: source missing: {missing}")
            continue
        blocks, unresolved, stats = convert_page(paths, media, spec["kind"])
        blocks = drop_navigation(blocks)
        blocks = dedupe_headings(blocks)
        blocks = drop_repeated_title(blocks, spec["title"])
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
            "blocks": "\n\n".join(blocks),
        })
        if unresolved:
            all_unresolved[spec["slug"]] = sorted(set(unresolved))
        if args.report:
            print(f"  {spec['slug']:24} {stats['words_out']:5}w  "
                  f"{stats['headings']:3}h {stats['paragraphs']:3}p "
                  f"{stats['images']:3}img {stats['tables']:2}tbl   "
                  f"retention {stats['words_out']/max(1,stats['words_in']):.0%}")

    json.dump({"schema": "maars-mirror-pages/1",
               "generated": "2026-09-17",
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
