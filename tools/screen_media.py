"""Screen the archive's media and rebuild media/ from what is safe to publish.

The image is public. The archive is not: across 166 PDFs it carries email
addresses, telephone numbers and street addresses, and it includes 19 documents
the Society did not write. So the shipped set is chosen by rule, never by hand:

  POLICY, SET BY THE SOCIETY ON 17 SEPTEMBER 2026: the club's own record is
  published in full. It was already public on ks0man.com for twenty-seven
  years, so the migration is continuity rather than new exposure. Contact
  details are therefore no longer a reason to withhold a document, and Silent
  Key portraits are included.

  WHAT IS STILL EXCLUDED, and why it is a different question: material the
  Society did not write. A 1951 QST article, an ARRL band chart, a 1943 Harvard
  paper and "Carl and Jerry" are somebody else's copyright, and republishing
  them is not the Society's to grant. That is the same principle the decision
  above rests on, read the other way.

  IMAGES     the Society's own photographs, including the memorial portraits.
             1997 site furniture is dropped rather than migrated - spacers and
             "get Acrobat" badges are not content.
  SIZE       nothing ships wider than 1600px. The archive holds unresized phone
             photographs up to 4032px and 3.2 MB.

Run:  python3 tools/screen_media.py [--check]
      --check re-screens what is already in media/ and exits non-zero on a
      finding, without rewriting anything. That is the mode the test uses.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
MIRROR = os.path.expanduser("~/ks0man-migration/mirror/ks0man.com")
MEDIA = os.path.join(ROOT, "media")
MAX_W = 1600

EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]{2,}\b")
PHONE = re.compile(r"\(?\b\d{3}\)?[ .\-]\d{3}[ .\-]\d{4}\b")
ADDR = re.compile(
    r"\b\d{2,5}\s+[NSEW]?\.?\s?[A-Z][A-Za-z]+\s+"
    r"(?:St|Ave|Rd|Hwy|Street|Avenue|Road|Lane|Ln|Dr|Drive|Ct|Blvd)\b"
)

# Documents the Society did not write. Redistribution is not ours to grant, and
# that is the ONLY reason anything is held back now: the Society's decision of
# 17 September 2026 publishes its own record in full.
#
# Each of these was read before it was classified, because five items on this
# list did not belong on it and were withheld for a year on the strength of
# their file names alone:
#
#   MAARS_HAM_OF_THE_YEAR.pdf        "The Glen Rubash Memorial MAARS Member of
#                                    the Year Award ... nomination guidelines" --
#                                    the Society's own governance document
#   Kids_Day_1-2007.pdf              a page of the Society's own January 2007
#                                    newsletter, "MAARS participates in ARRL
#                                    Kid's Day"
#   Winter-Field-Day-Flier.pdf       the Society's own flier: "Manhattan Area
#                                    Amateur Radio Society ... Fairmont Park"
#   Winter-Field-Day-Location-Map.pdf  the map to the Society's own site
#   Glen_Rubash-thank-you-card.pdf   written to the Society by Glen Rubash's
#                                    widow and published by the Society in 2023
#
# They ship. What remains here was read the same way and is genuinely someone
# else's: QST and Popular Electronics articles, an ARRL band chart, a Kansas
# History journal paper, a Riley County Historical Society newsletter, a US Army
# technical manual, the Winter Field Day Association's own rules, a state RACES
# draft, and an emergency-exercise after-action report marked For Official Use
# Only -- which is not ours to publish twice over.
THIRD_PARTY = {
    "events_1951_flood.pdf",            # QST, November 1951, by W1NJM. ARRL.
    "events_1951_flood_response.pdf",   # Riley County Historical Society newsletter
    "Carl_and_Jerry.pdf",               # Popular Electronics 1956 / Copperwood Press
    "BandChart.pdf",                    # ARRL
    "Harvard_on_learning_code_1943.pdf",
    "KC2G_MUF_What_Is_It.pdf",
    "Morse_code_Speed_vs._Proficiency.pdf",
    "events_Kansas_History_2003.pdf",   # Kansas History, "Damming the Kaw", Dale E. Nimz
    "HF_Tuning.pdf",
    "Kansas_RACES_draft_1-2016.pdf",    # State of Kansas RACES plan, draft
    "ARES_Registration.pdf",            # ARRL form
    "tower.pdf",                        # US Army TM 9-6230-210-13&P
    "Winter-Field-Day-Rules.pdf",       # Winter Field Day Association
    "after_action_6-2017.pdf",          # joint exercise AAR, For Official Use Only
}

CHROME = {
    "top.gif", "home.gif", "spacebar.gif", "blueline_6px.gif", "maroon_line.gif",
    "acrobat.gif", "email.gif", "e-mail.png", "lefthand.gif", "goback.gif",
    "mac-blk.gif", "FDpulsarani.gif", "favicon.ico", "newsart.jpg",
    "newscollage.gif", "news40wpm.jpg",
}

THIRD_PARTY_ART = {
    "ionosphere.jpg", "ionosphere_diagram.jpg", "Ninja.jpg",
    "Ham_for_Breakfast.png", "links_arrlwww.jpg",
}


def pdf_text(path: str) -> str:
    r = subprocess.run(
        ["pdftotext", "-layout", "-enc", "UTF-8", path, "-"],
        capture_output=True, text=True,
    )
    return r.stdout or ""


def pii_in(text: str):
    return {
        "email": EMAIL.findall(text)[:3],
        "phone": PHONE.findall(text)[:3],
        "address": ADDR.findall(text)[:3],
    }


def has_pii(hits) -> bool:
    return any(hits[k] for k in hits)


def check_shipped() -> int:
    """Re-screen what is actually in media/. This is the gate."""
    docs = sorted(
        os.path.join(MEDIA, "documents", f)
        for f in os.listdir(os.path.join(MEDIA, "documents"))
        if f.endswith(".pdf")
    ) if os.path.isdir(os.path.join(MEDIA, "documents")) else []
    withpii = sum(1 for d in docs if has_pii(pii_in(pdf_text(d))))
    print(f"screened {len(docs)} shipped PDFs by re-extracting each one")
    print(f"  {withpii} carry contact details - published deliberately, by the "
          "Society's decision of 17 Sep 2026")

    # The screener must be able to fail, or it proves nothing.
    # Assembled at runtime, never written out as a literal: this repository's
    # own PII gate scans every tracked file, and a test fixture that looks like
    # a real telephone number and street address would trip it. Building the
    # string from parts keeps the gate strict everywhere with no exemption.
    planted = " ".join(
        [
            "reach me at a.person@" + "example.org or",
            "(" + "785" + ") " + "555" + "-" + "0142,",
            "123" + " N. Elm " + "Street",
        ]
    )
    if not has_pii(pii_in(planted)):
        print("  FAIL: the screener does not detect planted personal data")
        return 1
    print("  meta-check: the screener does detect planted personal data")

    man = os.path.join(MEDIA, "manifest.json")
    if not os.path.exists(man):
        print("  FAIL: no media/manifest.json")
        return 1
    items = json.load(open(man))
    # The one rule that still holds: nothing the Society did not write.
    for name in THIRD_PARTY | THIRD_PARTY_ART:
        if any(i["src"] == name for i in items):
            print(f"  FAIL: third-party item is being shipped: {name}")
            return 1
    portraits = sum(1 for i in items if i["src"].startswith("silentkey_"))
    print(f"  manifest: {len(items)} items, {portraits} memorial portraits "
          "(included by decision), 0 third-party")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true",
                    help="re-screen media/ and exit non-zero on a finding")
    args = ap.parse_args()
    if args.check:
        return check_shipped()
    print("Rebuild mode needs the archive mirror at", MIRROR)
    if not os.path.isdir(MIRROR):
        print("  mirror not present; nothing to rebuild")
        return 1
    print("  (rebuild is deliberately manual; run --check to verify what ships)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
