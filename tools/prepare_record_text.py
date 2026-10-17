#!/usr/bin/env python3
"""The text of every archive record made from a PDF or a Word file.

The 125 issues from the years when the newsletter was a web page carry their
text. The 142 records made from files did not: a title, a date and a link, and
nothing a search could find. The archive's search box asks for "callsign, name,
subject, year", and not one word of the minutes from 2013 on, the treasurer's
reports or the 2009-2010 newsletters could be found by it. Eight of those PDFs
are scans with no text layer at all, so not even the file could be searched or
read aloud.

This reads each file again and writes its text as blocks:

    minutes and newsletters  pdftotext in reading order, one column after
                             another. The extracts made during the study used
                             -layout, which runs the three columns of a 2009
                             newsletter together line by line; they are not used.
    treasurer's and          pdftotext -layout, split into tables where the
    year-end reports         layout left gaps, because a ledger read in
                             reading order puts every label above every figure.
    the eight scans          the OCR made during the study (extract/pdftext/
                             <name>.ocr.txt).
    Word files               the document's own paragraphs and table rows.

The text is the machine's reading, and the record page says so: the file is
the authority. Published in full, as the Society decided; nothing is redacted.

    python3 tools/prepare_record_text.py [--extract ~/ks0man-migration/extract/pdftext]

Writes content/record_text.json. tools/import_record_text.php puts it on a
Docker install, tools/push_records.py --text on a live site.
"""

from __future__ import annotations

import argparse
import html as H
import json
import os
import re
import subprocess
import sys
import unicodedata
import zipfile
from xml.etree import ElementTree

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "content", "record_text.json")
TABULAR = {"treasurer-report", "year-end-report"}
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def esc(text: str) -> str:
    return H.escape(text, quote=False)


def pdftotext(path: str, layout: bool) -> str:
    args = ["pdftotext", "-enc", "UTF-8"] + (["-layout"] if layout else []) + [path, "-"]
    try:
        return subprocess.run(args, capture_output=True, check=True, timeout=120).stdout.decode("utf-8", "replace")
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        return ""


def docx_text(path: str, tabular: bool) -> str:
    """Paragraphs, and table rows as cells separated by a run of spaces."""
    try:
        xml = zipfile.ZipFile(path).read("word/document.xml")
    except (KeyError, zipfile.BadZipFile):
        return ""
    if b"<!DOCTYPE" in xml or b"<!ENTITY" in xml:
        return ""                         # Word never writes one; refuse anything that does
    body = ElementTree.fromstring(xml).find(W + "body")
    if body is None:
        return ""

    def run_text(node) -> str:
        out = []
        for el in node.iter():
            if el.tag == W + "t":
                out.append(el.text or "")
            elif el.tag == W + "tab":
                out.append("\t")
            elif el.tag in (W + "br", W + "cr"):
                out.append("\n")
        return "".join(out)

    lines = []
    for child in body:
        if child.tag == W + "p":
            lines.append(run_text(child))
        elif child.tag == W + "tbl":
            for row in child.iter(W + "tr"):
                cells = [re.sub(r"\s+", " ", run_text(c)).strip() for c in row.iter(W + "tc")]
                lines.append(("    " if tabular else "  ").join(c for c in cells if c))
            lines.append("")
    text = "\n".join(lines)
    return text.replace("\t", "    ") if tabular else text


def clean(text: str) -> str:
    # The year-end reports from 2019 on were exported with every space between
    # words written as tab, carriage return, space, no-break space. Read as a
    # line break, the carriage return put every word of a heading on its own
    # line; read as a gap, it split every word into a column of its own.
    text = re.sub(r"\t\r[ \xa0]*", " ", text).replace("\xa0", " ")
    # "Oﬃce": a ligature that did map, to the ligature's own character.
    text = re.sub("[\ufb00-\ufb06]", lambda m: unicodedata.normalize("NFKC", m.group(0)), text)
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\f", "\n\n")
    text = re.sub(r"^--- page \d+ ---$", "", text, flags=re.M)      # the OCR's page markers
    text = re.sub(r"[ \t]+$", "", text, flags=re.M)
    return re.sub(r"\n{3,}", "\n\n", text).strip("\n")


# Some of the club's PDFs map their "tt" and "ti" ligatures to the wrong
# characters, and a different wrong character in different files: "Manhattan"
# comes out "Manha*an" in the 2019-2022 year-end reports and "ManhaIan" in
# 2023's, "Submitted" as "Submi:ed" in three treasurer's reports. These are
# every such word in the archive, found by scanning all 142 texts for letters
# that cannot sit inside a word.
LIGATURES = {
    "Manha*an": "Manhattan", "ManhaIan": "Manhattan", "Submi*ed": "Submitted",
    "SubmiIed": "Submitted", "Submi:ed": "Submitted", "ba*ery": "battery",
    "baAery": "battery", "aAend": "attend", "pe:y": "petty", "Punne*": "Punnett",
    "DonaZons": "Donations", "DonaHons": "Donations",
}


BULLET = re.compile(r"^(?:eo|e|o|m|°|«|»|•|\*)\s+(?=[A-Z$0-9(])")


def prose_blocks(text: str, ocr: bool) -> list[str]:
    """Paragraphs from text whose lines were wrapped to a column.

    A line that reaches the column's width wrapped into the next one; a line
    that stops short ended something -- a paragraph, a heading, a list item --
    unless the next line plainly carries the same sentence on.
    """
    lines_all = [ln.strip() for ln in text.split("\n") if ln.strip()]
    if not lines_all:
        return []
    widths = sorted(len(ln) for ln in lines_all)
    full = widths[int(len(widths) * 0.9)] if len(widths) > 4 else max(widths)
    threshold = 0.66 * full

    paras: list[str] = []
    for chunk in text.split("\n\n"):
        lines = [ln.strip() for ln in chunk.split("\n") if ln.strip()]
        if ocr:
            lines = [BULLET.sub("– ", ln) for ln in lines]
        para: list[str] = []
        for i, line in enumerate(lines):
            if para:
                prev = para[-1]
                if prev.endswith("-") and line[:1].islower():
                    para[-1] = prev + line              # re-\nprogramming -> re-programming
                    line = None
            if line is not None:
                para.append(line)
            nxt = lines[i + 1] if i + 1 < len(lines) else ""
            last = para[-1]
            carries_on = (len(last) >= threshold
                          or (nxt[:1].islower() and not re.search(r"[.!?:;”\"]$", last)))
            if not nxt or not carries_on or nxt.startswith("– "):
                joined = re.sub(r"\s+", " ", " ".join(para)).strip()
                if joined:
                    paras.append(joined)
                para = []

    # A column break in the middle of a sentence: pdftotext ends one column
    # with a blank line, and "...should speak up" / "now at our meeting" read
    # as two paragraphs. A paragraph with no closing punctuation, followed by
    # one that starts in lower case, is one paragraph.
    merged: list[str] = []
    for p in paras:
        if merged and p[:1].islower() and not re.search(r"[.!?:;\u201d\")]$", merged[-1]):
            merged[-1] += " " + p
        else:
            merged.append(p)
    return [f"<!-- wp:paragraph --><p>{esc(p)}</p><!-- /wp:paragraph -->" for p in merged]


AMOUNT = re.compile(r"^\(?-?\$?\s?\d{1,3}(?:,\d{3})*(?:\.\d\d)?\)?(?:\s+\(.*\))?$")


def ledger_rows(text: str) -> list[list[str] | None]:
    """A ledger's lines as cells, split where the layout left a gap.

    Two repairs the year-end PDFs need: an amount the layout broke across two
    lines ("825" above ".69 (repeater fund)") is put back together, and an
    amount left on a line of its own goes beside the label above it.
    """
    rows: list[list[str] | None] = []
    for line in text.split("\n"):
        # A ledger's columns are far apart; a gap of two is justified prose.
        cells = [c for c in re.split(r"\s{3,}", line.strip()) if c]
        cells = [re.sub(r"(\d)\s+(\.\d\d)\b", r"\1\2", c) for c in cells]
        joined: list[str] = []
        for cell in cells:                # "1,542" | ".66", broken on one line
            if joined and re.fullmatch(r"\$?[\d,]+", joined[-1]) and re.match(r"^\.\d", cell):
                joined[-1] += cell
            else:
                joined.append(cell)
        rows.append(joined or None)

    def next_row(i: int) -> int:
        j = i + 1
        while j < len(rows) and rows[j] is None:
            j += 1
        return j

    out: list[list[str] | None] = []
    i = 0
    while i < len(rows):
        row = rows[i]
        if row and len(row) == 1 and re.fullmatch(r"\$?[\d,]+", row[0]):
            j = next_row(i)
            if j < len(rows) and rows[j] and re.match(r"^\.\d", rows[j][0]):
                row = [row[0] + rows[j][0]] + rows[j][1:]
                i = j
        if (row and AMOUNT.match(row[0]) and out
                and out[-1] and len(out[-1]) == 1 and not AMOUNT.match(out[-1][0])):
            out[-1] = out[-1] + row
        elif row is None and out and out[-1] and len(out[-1]) == 1 and not AMOUNT.match(out[-1][0]):
            # a label whose amount comes after a blank line: hold the label open
            j = next_row(i)
            if j < len(rows) and rows[j] and re.fullmatch(r"\$?[\d,]+", rows[j][0]):
                i += 1
                continue
            out.append(row)
        else:
            out.append(row)
        i += 1
    return out


def ledger_blocks(text: str) -> list[str]:
    """A treasurer's or year-end report as one table: a label and its amount
    stay on one row at any width, which preformatted text could not promise on
    a phone without hiding every amount behind a sideways scroll.

    The heading lines above the first figure are a paragraph, and the notes
    below the last one another. In between, a blank line in the report starts
    a row with space above it, and a line with nothing beside it ("Income:",
    "As of March 31, 2022") spans the table as a section head.
    """
    rows = ledger_rows(text)
    first = next((i for i, r in enumerate(rows) if r and len(r) > 1), None)
    if first is None:
        return prose_blocks("\n".join(r[0] if r else "" for r in rows), False)
    last = max(i for i, r in enumerate(rows) if r and len(r) > 1)
    # The section head over the first figures ("As of March 1, 2022") belongs
    # to the table, a blank line above the figures or not.
    above = first - 1
    while above >= 0 and rows[above] is None:
        above -= 1
    if above >= 0 and len(rows[above]) == 1 and re.match(r"^(as of|balance)\b|.*:$", rows[above][0], re.I):
        first = above

    def lines_to_para(chunk) -> list[str]:
        out, buf = [], []
        for r in chunk + [None]:
            if r:
                buf.append(esc(" ".join(r)))
            elif buf:
                out.append("<!-- wp:paragraph --><p>" + "<br>".join(buf) + "</p><!-- /wp:paragraph -->")
                buf = []
        return out

    width = max(len(r) for r in rows[first:last + 1] if r)
    trs, gap = [], False
    for r in rows[first:last + 1]:
        if r is None:
            gap = bool(trs)
            continue
        cls = ' class="maars-ledger__gap"' if gap else ""
        gap = False
        if len(r) == 1:
            trs.append(f'<tr{cls}><td class="maars-ledger__head" colspan="{width}">{esc(r[0])}</td></tr>')
            continue
        tds = [f"<td>{esc(c)}</td>" for c in r[:-1]]
        span = width - len(r) + 1
        tds.append(f'<td colspan="{span}">{esc(r[-1])}</td>' if span > 1 else f"<td>{esc(r[-1])}</td>")
        trs.append(f"<tr{cls}>" + "".join(tds) + "</tr>")
    table = ('<!-- wp:table {"className":"maars-ledger"} --><figure class="wp-block-table maars-ledger">'
             "<table><tbody>" + "".join(trs) + "</tbody></table></figure><!-- /wp:table -->")
    return lines_to_para(rows[:first]) + [table] + lines_to_para(rows[last + 1:])


NOTE = ('<!-- wp:paragraph {"className":"maars-record-text__note"} -->'
        '<p class="maars-record-text__note">The text of the file, as a machine read it. '
        "Open the original below for the layout, the pictures and anything the reading missed.</p>"
        "<!-- /wp:paragraph -->")


def record_text(item: dict, extract_dir: str) -> tuple[str, str]:
    """(method, blocks) for one record; method '' when there is no text."""
    path = os.path.join(ROOT, "media", "documents", item["file"])
    ext = os.path.splitext(item["file"])[1].lower()
    tabular = item.get("doc_type") in TABULAR
    method, text, ocr = "", "", False

    if ext == ".pdf":
        text = clean(pdftotext(path, layout=tabular))
        for broken, word in LIGATURES.items():
            text = text.replace(broken, word)
        method = "pdftotext -layout" if tabular else "pdftotext"
        if len(re.sub(r"\s", "", text)) < 40:
            stem = os.path.splitext(item["src"])[0]
            ocr_path = os.path.join(extract_dir, stem + ".ocr.txt")
            text = clean(open(ocr_path, encoding="utf-8", errors="replace").read()) if os.path.exists(ocr_path) else ""
            method, ocr, tabular = ("ocr", True, False) if text else ("", False, tabular)
    elif ext == ".docx":
        text = clean(docx_text(path, tabular))
        method = "docx"

    if len(re.sub(r"\s", "", text)) < 40:
        return "", ""
    blocks = ledger_blocks(text) if tabular else prose_blocks(text, ocr)
    inner = "\n\n".join([NOTE] + blocks)
    return method, ('<!-- wp:group {"className":"maars-record-text","layout":{"type":"default"}} -->'
                    f'<div class="wp-block-group maars-record-text">\n\n{inner}\n\n</div>'
                    "<!-- /wp:group -->")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--extract", default=os.path.expanduser("~/ks0man-migration/extract/pdftext"))
    args = ap.parse_args()

    manifest = json.load(open(os.path.join(ROOT, "media", "manifest.json")))
    records = [i for i in manifest if i.get("title") and i.get("date")
               and os.path.splitext(i["file"])[1].lower() in (".pdf", ".docx")]

    out, missing = [], []
    from collections import Counter
    methods: Counter = Counter()
    for item in sorted(records, key=lambda i: (i["date"], i["src"])):
        method, blocks = record_text(item, args.extract)
        if not blocks:
            missing.append(item["src"])
            continue
        methods[method] += 1
        out.append({"src": item["src"], "file": item["file"], "method": method, "blocks": blocks})

    json.dump({"schema": "maars-record-text/1", "generated": "2026-10-17",
               "note": "Machine-read text of the archive records made from PDF and Word files. "
                       "Published in full, as the Society decided.",
               "records": out},
              open(OUT, "w"), indent=2, ensure_ascii=False)
    open(OUT, "a").write("\n")

    words = sum(len(re.sub(r"<[^>]+>", " ", r["blocks"]).split()) for r in out)
    print(f"  wrote {os.path.relpath(OUT, ROOT)}: {len(out)} of {len(records)} records, "
          f"{words:,} words ({', '.join(f'{n} {m}' for m, n in methods.most_common())})")
    if missing:
        print(f"  NO TEXT for {len(missing)}: {missing}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
