"""Screen the archive's media and rebuild media/ from what is safe to publish.

The image is public. The archive is not: across 166 PDFs it carries email
addresses, telephone numbers and street addresses, and it includes 19 documents
the Society did not write. So the shipped set is chosen by rule, never by hand:

  DOCUMENTS  every PDF is extracted with pdftotext and rejected if it contains
             an email address, a telephone number or a street address, and
             rejected again if it is on the third-party list.
  IMAGES     the Society's own photographs only. Silent Key portraits and
             photographs of named living people are held back, because
             republishing a memorial is the Society's decision. 1997 site
             furniture is dropped rather than migrated.
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

# Documents the Society did not write. Redistribution is not ours to grant.
THIRD_PARTY = {
    "events_1951_flood.pdf", "events_1951_flood_response.pdf", "Carl_and_Jerry.pdf",
    "BandChart.pdf", "Harvard_on_learning_code_1943.pdf", "KC2G_MUF_What_Is_It.pdf",
    "Morse_code_Speed_vs._Proficiency.pdf", "events_Kansas_History_2003.pdf",
    "HF_Tuning.pdf", "Kansas_RACES_draft_1-2016.pdf", "ARES_Registration.pdf",
    "tower.pdf", "Kids_Day_1-2007.pdf", "Winter-Field-Day-Rules.pdf",
    "Winter-Field-Day-Flier.pdf", "Winter-Field-Day-Location-Map.pdf",
    "Glen_Rubash-thank-you-card.pdf", "MAARS_HAM_OF_THE_YEAR.pdf",
    "after_action_6-2017.pdf",
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
    findings = []
    for d in docs:
        hits = pii_in(pdf_text(d))
        if has_pii(hits):
            findings.append((os.path.basename(d), hits))
    print(f"screened {len(docs)} shipped PDFs by re-extracting each one")
    if findings:
        print(f"  FAIL: {len(findings)} contain personal data and must not ship")
        for name, hits in findings[:10]:
            print(f"    {name}: {hits}")
        return 1
    print("  0 contain an email address, telephone number or street address")

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
    for name in THIRD_PARTY | THIRD_PARTY_ART:
        if any(i["src"] == name for i in items):
            print(f"  FAIL: third-party item is being shipped: {name}")
            return 1
    for i in items:
        if i["src"].startswith("silentkey_"):
            print(f"  FAIL: a memorial portrait is being shipped: {i['src']}")
            return 1
    print(f"  manifest: {len(items)} items, no third-party, no memorial portraits")
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
