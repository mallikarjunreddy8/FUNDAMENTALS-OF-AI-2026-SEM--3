"""
MediGuard - the detection agent (Python version, uses the full 253,973-medicine dataset).

    PERCEIVE  read the pack: OCR text, barcode / QR / GS1 DataMatrix, typed details, what the user noticed
    REASON    expert rules -> evidence, each with a weight (how strongly it points to "fake")
    DECIDE    risk score = sum of weights -> verdict
    ACT       advice, how to report, cheaper alternatives with the same composition

It gives the same report as the phone version (web/agent.js), plus 4 rules that need the real data:
    * the name is not in India's medicine list but is 1-2 letters away from a real brand  (lookalike)
    * the strength / maker printed does not match the dataset
    * the brand is discontinued, so fresh stock is suspicious
    * the price is far below the MRP in the dataset

The agent can never PROVE a medicine is genuine (only a lab test can), so its best verdict is
"No red flags found".
"""

import datetime as dt
import os
import re
from dataclasses import dataclass, field
from functools import lru_cache
from urllib.parse import urlparse

from rapidfuzz import fuzz, process
from rapidfuzz.distance import Levenshtein

from . import dataset as D

# =============================================================================
# SETTINGS YOU CAN CHANGE
# =============================================================================
HIGH_RISK = 60          # risk score at or above this -> "Likely fake"
SUSPICIOUS = 30         # risk score at or above this -> "Suspicious"
MAX_SHELF_MONTHS = 60   # most tablets have 2 to 5 years of shelf life
CHEAP_PRICE = 0.5       # paying less than half the MRP is a red flag
ALERTS_CSV = os.path.join(D.DATA_DIR, "drug_alerts.csv")

MONTHS = {"JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6, "JUL": 7, "AUG": 8,
          "SEP": 9, "SEPT": 9, "OCT": 10, "NOV": 11, "DEC": 12}
SHORTENERS = {"bit.ly", "tinyurl.com", "goo.gl", "t.ly", "is.gd", "cutt.ly", "rb.gy", "shorturl.at", "ow.ly"}

CHECKLIST = {
    "sealBroken": (25, "Seal, foil or strip is broken, re-glued or tampered"),
    "spelling": (25, "Spelling or grammar mistakes on the pack"),
    "poorPrint": (20, "Print or logo is blurry, smudged, faded or uneven"),
    "differentLook": (25, "Colour, size, shape, taste or smell differs from usual"),
    "tooCheap": (15, "Price is far lower than usual / unusual big discount"),
    "noBill": (15, "Bought without a bill, or from an unlicensed / unknown seller"),
    "noEffect": (15, "It didn't work as before, or caused an unusual reaction"),
}

VERDICTS = {
    "fake": ("HIGH RISK - likely fake", "danger", "Do not take this medicine."),
    "expired": ("EXPIRED - do not use", "danger", "This medicine is expired. Do not take it."),
    "suspicious": ("SUSPICIOUS - verify", "warn", "Some things don't look right. Check with the pharmacist before taking it."),
    "ok": ("No red flags found", "ok", "No warning signs were found. Keep the bill and buy from licensed pharmacies."),
    "unknown": ("Not enough information", "info",
                "Scan the barcode / QR and take a clear photo of the printed side, or type the details."),
}


# =============================================================================
# 1. PERCEIVE
# =============================================================================
@dataclass
class Pack:
    """Everything the phone saw about one medicine pack."""
    text: str = ""                                   # OCR text
    codes: list = field(default_factory=list)        # [{"format": "QR_CODE", "text": "..."}]
    brand: str = ""                                  # typed by the user (beats OCR)
    batch: str = ""
    mfg: str = ""
    exp: str = ""
    manufacturer: str = ""
    barcode: str = ""
    price: float = None                              # what the user paid for the pack (Rs)
    checklist: dict = field(default_factory=dict)    # {"poorPrint": True, ...}
    today: dt.date = None

    @classmethod
    def from_dict(cls, d):
        m = d.get("manual") or {}
        price = m.get("price", d.get("price"))
        try:
            price = float(price) if price not in (None, "") else None
        except ValueError:
            price = None
        today = d.get("today")
        return cls(text=d.get("text") or "", codes=d.get("codes") or [], brand=m.get("brand", ""),
                   batch=m.get("batch", ""), mfg=m.get("mfg", ""), exp=m.get("exp", ""),
                   manufacturer=m.get("manufacturer", ""), barcode=m.get("barcode", ""), price=price,
                   checklist=d.get("checklist") or {},
                   today=dt.date.fromisoformat(today[:10]) if today else None)


DATE_RE = (r"(?:(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEPT|SEP|OCT|NOV|DEC)[A-Z]*[.\s\-/']*(\d{4}|\d{2})(?!\d)"
           r"|(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4}|\d{2})(?!\d)"
           r"|(\d{1,2})[/\-.](\d{4}|\d{2})(?!\d)"
           r"|(\d{4})-(\d{2}))")


def _year(y):
    y = int(y)
    return 2000 + y if y < 100 else y


def _date_from(m, offset=0):
    g = lambda k: m.group(k + offset)  # noqa: E731
    if g(1):
        d = (_year(g(2)), MONTHS[g(1)])
    elif g(3):
        d = (_year(g(5)), int(g(4)))
    elif g(6):
        d = (_year(g(7)), int(g(6)))
    elif g(8):
        d = (int(g(8)), int(g(9)))
    else:
        return None
    return d if 1 <= d[1] <= 12 else None


def parse_date(text):
    """'MAR 2027', '03/27', '2027-03', '15/03/2027' -> (2027, 3)"""
    if not text:
        return None
    m = re.match(DATE_RE, str(text).upper().strip())
    return _date_from(m) if m else None


def months(d):
    return d[0] * 12 + d[1] - 1


def show(d):
    return f"{d[1]:02d}/{d[0]}" if d else None


def gtin_valid(code):
    """GS1 check digit (EAN-8, UPC-A, EAN-13, GTIN-14)."""
    if not re.fullmatch(r"\d{8}|\d{12,14}", code or ""):
        return False
    nums = [int(c) for c in code]
    check = nums.pop()
    total = sum(n * (3 if i % 2 == 0 else 1) for i, n in enumerate(reversed(nums)))
    return (10 - total % 10) % 10 == check


def parse_gs1(raw):
    """GS1 DataMatrix: (01) GTIN, (17) expiry YYMMDD, (11) mfg date, (10) batch, (21) serial."""
    s = re.sub(r"^\](d2|C1|Q3|e0)", "", raw)
    out = {}
    if s.startswith("("):
        out = {k: v.strip() for k, v in re.findall(r"\((\d{2})\)([^(]*)", s)}
    else:
        fixed = {"01": 14, "17": 6, "11": 6, "15": 6}
        for _ in range(10):
            if len(s) <= 2:
                break
            ai, s = s[:2], s[2:]
            if ai in fixed:
                out[ai], s = s[:fixed[ai]], s[fixed[ai]:]
            elif ai in ("10", "21"):
                val, _, s = s.partition("\x1d")
                out[ai] = val
            else:
                break
            s = s.lstrip("\x1d")
    if "01" not in out:
        return None
    yymmdd = lambda v: (2000 + int(v[:2]), int(v[2:4])) if re.fullmatch(r"\d{6}", v or "") else None  # noqa: E731
    return {"kind": "gs1", "gtin": out["01"], "gtin_valid": gtin_valid(out["01"]),
            "exp": yymmdd(out.get("17")), "mfg": yymmdd(out.get("11")), "batch": out.get("10")}


def parse_code(code):
    raw = str(code.get("text", "")).strip()
    fmt = str(code.get("format", "CODE")).upper()
    if not raw:
        return None
    gs1 = parse_gs1(raw) if len(raw) > 16 else None
    if gs1:
        return {"format": fmt, "raw": raw, **gs1}
    if re.fullmatch(r"\d{8}|\d{12,14}", raw):
        return {"format": fmt, "raw": raw, "kind": "gtin", "gtin": raw, "gtin_valid": gtin_valid(raw)}
    if re.match(r"https?://", raw, re.I):
        return {"format": fmt, "raw": raw, "kind": "url", "domain": urlparse(raw).netloc.lower().removeprefix("www.")}
    # India's medicine QR (Schedule H2): "Batch: X", "Exp: 03/2030", "Brand: ...", "Manufacturer: ..."
    out, fields = {"format": fmt, "raw": raw, "kind": "qr-data"}, 0
    for part in re.split(r"[\n\r|;]+", raw):
        m = re.match(r"\s*([A-Za-z .\/#()]+?)\s*[:=]\s*(.+)$", part)
        if not m:
            continue
        key, val = m.group(1).lower(), m.group(2).strip()
        if re.search(r"batch|lot|b\.?\s?no", key):
            out["batch"] = val
        elif "exp" in key:
            out["exp"] = parse_date(val)
        elif re.search(r"mfg|mfd|manufactur\w*\s*date|dom", key) and parse_date(val):
            out["mfg"] = parse_date(val)
        elif "brand" in key:
            out["brand"] = val
        elif re.search(r"manufacturer|mfr|company|marketed", key):
            out["manufacturer"] = val
        elif re.search(r"generic|composition|salt|unique|upi|product|lic", key):
            pass
        else:
            continue
        fields += 1
    out["fields"] = fields
    return out if fields >= 2 else {"format": fmt, "raw": raw, "kind": "text"}


def read_printed(text):
    """Batch, dates, maker line and strengths from the OCR text."""
    t = text.upper()
    out = {"batch": None, "mfg": None, "exp": None, "maker": None, "strengths": []}
    m = re.search(r"(?:\bB\.?\s?NO|\bBATCH\s*(?:NO|NUMBER)?|\bLOT\s*(?:NO)?)\s*\.?\s*[:.#]?\s*([A-Z0-9][A-Z0-9\-/]{2,14})", t)
    if m:
        out["batch"] = m.group(1)
    m = re.search(r"(?:MFG|MFD|MANUFACTURED\s+ON|MANUFACTURING\s+DATE|DOM)\.?\s*(?:DATE|DT)?\.?\s*[:.\-]?\s*" + DATE_RE, t)
    if m:
        out["mfg"] = _date_from(m)
    m = re.search(r"(?:EXP(?:IRY)?|USE\s+BEFORE|BEST\s+BEFORE)\.?\s*(?:DATE|DT)?\.?\s*[:.\-]?\s*" + DATE_RE, t)
    if m:
        out["exp"] = _date_from(m)
    for line in text.splitlines():
        if re.search(r"(MANUFACTURED|MFD\.?|MFG\.?|MARKETED|MKTD\.?)\s*(BY|FOR)", line, re.I):
            out["maker"] = line.strip()
            break
    for v, u in re.findall(r"(\d+(?:\.\d+)?)\s*(MG|MCG|IU|G)(?![A-Z])", t):
        out["strengths"].append((float(v), u))
    return out


# =============================================================================
# THE DRUG ALERT LIST (CDSCO publishes one every month)
# =============================================================================
def load_alerts(path=ALERTS_CSV):
    alerts = {}
    if os.path.exists(path):
        import csv
        with open(path, encoding="utf-8") as f:
            for row in csv.DictReader(line for line in f if not line.startswith("#")):
                alerts[re.sub(r"[^A-Z0-9]", "", row["batch"].upper())] = row
    return alerts


# =============================================================================
# 2. REASON
# =============================================================================
OCR_FIX = str.maketrans({"0": "O", "1": "I", "5": "S", "8": "B"})


class Detector:
    def __init__(self, db=None, alerts=None):
        self.db = db or D.load()
        self.alerts = load_alerts() if alerts is None else alerts

    # ---------------------------------------------------------------- identify
    @lru_cache(maxsize=4096)
    def _fuzzy(self, name):
        """Nearest real brand name (for lookalike detection)."""
        first = name.split(" ")[0]
        pool = [k for k in self.db.brand_list if abs(len(k) - len(name)) <= 2 and k[:1] == first[:1]]
        hit = process.extractOne(name, pool, scorer=fuzz.ratio, score_cutoff=80)
        return hit[0] if hit else None

    @lru_cache(maxsize=4096)
    def identify(self, text, typed=False):
        """-> (kind, brand_key, seen)  kind: exact | lookalike | None"""
        db = self.db
        lines = [text] if typed else [ln for ln in text.splitlines() if D.norm_text(ln)]
        fix = lambda s: " ".join(w if w.isdigit() else w.translate(OCR_FIX) for w in D.norm_text(s).split())  # noqa: E731
        def at_line_start(lns):
            # OCR often reads 0/O, 1/I, 5/S wrong: also try the letters
            for ln in lns:
                for variant in (ln, fix(ln)):
                    key, _ = db.find_in_text(variant, line_start=True)
                    if key and (typed or (len(key) >= 4 and key not in db.salt_names)):
                        return key
            return None

        # 1. a brand name at the start of the first line (packs print the brand first)
        key = at_line_start(lines[:1])
        if key:
            return "exact", key, key
        # 2. lookalike: the first line is 1-2 letters away from a real brand
        head = D.norm_text(lines[0] if lines else "").split()
        for n in (3, 2, 1):
            if len(head) < n:
                continue
            cand = " ".join(head[:n])
            if len(cand) < 5 or cand in db.by_brand:
                continue
            near = self._fuzzy(cand)
            if near and 0 < Levenshtein.distance(cand, near) <= (2 if len(cand) >= 8 else 1):
                return "lookalike", near, cand
        # 3. a brand at the start of any other line
        key = at_line_start(lines[1:])
        if key:
            return "exact", key, key
        # 4. a longer name (with its strength) anywhere in the text, e.g. "... DOLO 650 ..."
        key, _ = db.find_in_text(text)
        if key and " " in key and any(ch.isdigit() for ch in key):
            return "exact", key, key
        return None, None, None

    # ---------------------------------------------------------------- the rules
    def check(self, pack, with_alternatives=True):
        if isinstance(pack, dict):
            pack = Pack.from_dict(pack)
        db = self.db
        today = pack.today or dt.date.today()
        now = today.year * 12 + today.month - 1
        ev = []

        def add(level, weight, title, detail=""):
            ev.append({"level": level, "weight": weight, "title": title, "detail": detail})

        # ---------- perceive ----------
        codes = [c for c in (parse_code(c) for c in pack.codes) if c]
        if pack.barcode and not any(c["raw"] == pack.barcode for c in codes):
            typed = parse_code({"format": "TYPED", "text": re.sub(r"\s", "", pack.barcode)})
            if typed:
                codes.append(typed)
        printed = read_printed(pack.text)
        if pack.batch:
            printed["batch"] = pack.batch.upper().strip()
        printed["mfg"] = parse_date(pack.mfg) or printed["mfg"]
        printed["exp"] = parse_date(pack.exp) or printed["exp"]
        if pack.manufacturer:
            printed["maker"] = pack.manufacturer

        # ---------- rule 1: which medicine is it? (searches all 253,973 names) ----------
        kind, key, seen = (None, None, None)
        from_ocr = False          # True when the name was only read by the camera (not typed / not from a code)
        if pack.brand:
            kind, key, seen = self.identify(pack.brand, typed=True)
        if kind != "exact" and pack.text:
            k2 = self.identify(pack.text)
            if k2[0] and (kind is None or k2[0] == "exact"):
                kind, key, seen = k2
                from_ocr = not pack.brand
        qr_brand = next((c["brand"] for c in codes if c.get("brand")), None)
        if qr_brand and kind != "exact":
            k3 = self.identify(qr_brand, typed=True)
            if k3[0] == "exact" and (kind is None or (kind == "lookalike" and from_ocr and k3[1] == key)):
                # the QR names the same real brand: the "lookalike" was just the camera misreading
                kind, key, seen = k3
                from_ocr = False
        row_i = db.best_row(db.rows_for_brand(key), printed["maker"] or pack.text) if key else None
        med = db.row(row_i) if row_i is not None else None

        if kind is None:
            if pack.brand or len(pack.text) > 20:
                add("warn", 10, "Name not found in India's medicine list",
                    f"Not among the {len(db):,} medicines in the dataset. It may be new or rare - "
                    "or not a registered product. Ask the pharmacist.")
            else:
                add("info", 0, "Medicine not identified", "Type the brand name or scan the printed side.")
        elif kind == "lookalike":
            msg = (f'The pack reads "{seen}". That name is not in the list of {len(db):,} medicines, but it is '
                   f'{Levenshtein.distance(seen, key)} letter(s) away from the real brand. ')
            if from_ocr:   # the camera may have misread one letter: ask the user to confirm
                add("warn", 30, f'Name may be a copy of "{med["name"]}"',
                    msg + "The camera can misread letters - check the spelling by eye and type it in step 2.")
            else:
                add("danger", 35, f'Name looks like a copy of "{med["name"]}"', msg + "Fakers often change one letter.")
        else:
            add("pass", 0, f"Recognised: {med['name']}",
                f"{D.composition_text(med['salts'])} - {med['manufacturer']}.")

        # ---------- rule 2: discontinued ----------
        if med is not None and kind == "exact" and med["discontinued"]:
            add("warn", 20, "This product is discontinued",
                "It is marked discontinued in the dataset. Fresh stock with a recent Mfg date is suspicious.")

        # ---------- rule 3: strength matches the composition ----------
        if med is not None and kind == "exact" and len(pack.text) > 40 and printed["strengths"]:
            want = [(v, u) for _, _, v, u in med["salts"] if v is not None and u in ("MG", "MCG", "IU", "G")]
            found = printed["strengths"]
            missing = [w for w in want if w not in found]
            # a strength that is printed but belongs to none of the salts (an unreadable number is not evidence)
            odd = [(fv, fu) for fv, fu in found if (fv, fu) not in want]
            near = lambda f: any(u == f[1] and Levenshtein.distance(f"{v:g}", f"{f[0]:g}") <= 1 for v, u in want)  # noqa: E731
            if want and missing and odd and all(near(f) for f in odd) and not pack.brand:
                add("warn", 10, "Strength may not match - check by eye",
                    f"{med['name']} should contain {D.composition_text(med['salts'])}. "
                    "The camera read a slightly different number.")
            elif want and missing and not odd:
                add("info", 0, "Strength not readable", f"It should be {D.composition_text(med['salts'])}.")
            elif want and missing:
                add("danger", 30, "Strength doesn't match the medicine",
                    f"{med['name']} contains {D.composition_text(med['salts'])}, but the pack shows "
                    + ", ".join(f"{v:g} {u.lower()}" for v, u in printed["strengths"]) + ".")
            elif want:
                add("pass", 0, "Strength matches", D.composition_text(med["salts"]))

        # ---------- rule 4: manufacturer ----------
        maker_text = D.norm_text((printed["maker"] or "") + " " + pack.text)
        if med is not None and kind == "exact" and len(maker_text) > 40 and med["manufacturer"]:
            words = [w for w in D.norm_text(med["manufacturer"]).split()
                     if len(w) > 2 and w not in {"LTD", "PVT", "PRIVATE", "LIMITED", "INDIA", "PHARMA",
                                                 "PHARMACEUTICALS", "LABORATORIES", "HEALTHCARE", "THE", "AND"}]
            maker_words = maker_text.split()
            if words and any(w in maker_text or any(Levenshtein.distance(w, x) <= max(1, len(w) // 4)
                                                    for x in maker_words) for w in words[:2]):
                add("pass", 0, "Manufacturer matches", med["manufacturer"])
            elif printed["maker"]:
                add("danger", 30, "Different manufacturer",
                    f"{med['name']} is made by {med['manufacturer']}, but the pack says \"{printed['maker']}\".")

        # ---------- rule 5: price vs MRP ----------
        if med is not None and kind == "exact" and pack.price:
            mrp = float(med["price"])
            if pack.price < CHEAP_PRICE * mrp:
                add("warn", 20, "Much cheaper than the MRP",
                    f"You paid Rs {pack.price:g}; the listed price is Rs {mrp:g} ({med['pack']}). "
                    "Fakes are often sold at big discounts.")
            elif pack.price > mrp * 1.05:
                add("info", 0, "Charged above the MRP",
                    f"Rs {pack.price:g} vs MRP Rs {mrp:g}. Selling above the printed MRP is not allowed.")

        # ---------- rule 6: drug alert list ----------
        batches = [b for b in [printed["batch"]] + [c.get("batch") for c in codes] if b]
        alert = next((self.alerts[k] for k in (re.sub(r"[^A-Z0-9]", "", b.upper()) for b in batches)
                      if k in self.alerts), None)
        if alert:
            add("danger", 70, f"Batch {alert['batch']} is on the drug alert list",
                f"{alert.get('product', '')}: {alert.get('status', '')} ({alert.get('source', '')}).")
        elif batches:
            add("pass", 0, "Batch not on the alert list", f"Batch {batches[0]}.")
        else:
            add("warn", 10, "No batch number found", "Every genuine medicine prints a batch number (B.No.).")

        # ---------- rule 7: dates ----------
        code_exp = next((c["exp"] for c in codes if c.get("exp")), None)
        code_mfg = next((c["mfg"] for c in codes if c.get("mfg")), None)
        if not printed["exp"] and code_exp:
            add("info", 0, "Expiry taken from the QR / barcode", "The printed date couldn't be read.")
        mfg, exp = printed["mfg"] or code_mfg, printed["exp"] or code_exp
        if code_exp and printed["exp"] and not pack.exp and printed["exp"] != code_exp \
                and Levenshtein.distance(show(code_exp), show(printed["exp"])) <= 1:
            exp = code_exp   # one misread digit: trust the machine-readable code for the date checks
        if exp:
            if months(exp) < now:
                add("danger", 50, "EXPIRED", f"It expired in {show(exp)}. Do not take it.")
            else:
                add("pass", 0, "Not expired", f"Expiry {show(exp)}.")
        else:
            add("warn", 10, "No expiry date found", "Every genuine medicine prints an expiry date.")
        if mfg and months(mfg) > now:
            add("danger", 40, "Manufacturing date is in the future", f"Mfg {show(mfg)} hasn't happened yet.")
        if mfg and exp:
            shelf = months(exp) - months(mfg)
            if shelf <= 0:
                add("danger", 40, "Expiry is before manufacture", f"Mfg {show(mfg)}, Exp {show(exp)}.")
            elif shelf > MAX_SHELF_MONTHS:
                add("warn", 20, "Shelf life is unusually long", f"{shelf / 12:.1f} years. Most tablets have 2 to 5.")

        # ---------- rule 8: barcodes & QR codes ----------
        for c in codes:
            if c["kind"] in ("gs1", "gtin"):
                if c["gtin_valid"]:
                    add("pass", 0, "Barcode number is valid", f"{c['gtin']} passes the GS1 check digit test.")
                else:
                    add("danger", 40, "Barcode number is invalid", f"{c['gtin']} fails the GS1 check digit test.")
            pb = printed["batch"]
            if c.get("batch") and pb:
                cb, pbn = re.sub(r"[^A-Z0-9]", "", c["batch"].upper()), re.sub(r"[^A-Z0-9]", "", pb.upper())
                if cb != pbn and Levenshtein.distance(cb, pbn.translate(OCR_FIX)) <= 1 or \
                        cb != pbn and Levenshtein.distance(cb, pbn) <= 1:
                    add("warn", 10, "Code batch almost matches the print",
                        f"Code says {c['batch']}, camera read {pb}. Probably a misread - check by eye.")
                elif cb != pbn:
                    add("danger", 45, "QR / barcode batch doesn't match the print",
                        f"Code says {c['batch']}, pack says {pb}. Fakers copy QR codes from real packs.")
                else:
                    add("pass", 0, "Code batch matches the print", f"Both say {pb}.")
            if c.get("exp") and exp and c["exp"] != exp and Levenshtein.distance(show(c["exp"]), show(exp)) <= 1 \
                    and printed["exp"] and not pack.exp:
                add("warn", 10, "Code expiry almost matches the print",
                    f"Code says {show(c['exp'])}, camera read {show(exp)}. Check the printed date by eye.")
            elif c.get("exp") and exp and c["exp"] != exp:
                add("danger", 35, "QR / barcode expiry doesn't match the print",
                    f"Code says {show(c['exp'])}, pack says {show(exp)}.")
            if c["kind"] == "qr-data":
                add("pass" if c["fields"] >= 4 else "info", 0, "QR code has product details",
                    f"{c['fields']} details found. India requires this QR on top-selling brands (Schedule H2).")
            if c["kind"] == "url":
                if c["domain"] in SHORTENERS:
                    add("warn", 25, "QR uses a short link", f"It opens {c['domain']}, not the maker's website.")
                else:
                    add("info", 0, "QR opens a website", f"{c['domain']} - is it the manufacturer's official site?")
        if not codes:
            add("info", 0, "No barcode / QR scanned", "Scan it if the pack has one, for extra checks.")

        # ---------- rule 9: what the user noticed ----------
        for k, (w, label) in CHECKLIST.items():
            if pack.checklist.get(k):
                add("warn", w, "You noticed: " + label)

        return self._decide(ev, med, row_i if with_alternatives else None, kind, printed, codes)

    # =========================================================================
    # 3. DECIDE + 4. ACT
    # =========================================================================
    def _decide(self, ev, med, row_i, kind, printed, codes):
        risk = min(100, sum(e["weight"] for e in ev))
        passes = sum(e["level"] == "pass" for e in ev)
        expired = any(e["title"] == "EXPIRED" for e in ev)
        other_danger = sum(e["weight"] for e in ev if e["level"] == "danger" and e["title"] != "EXPIRED")
        if other_danger >= HIGH_RISK or (risk >= HIGH_RISK and not expired):
            key = "fake"
        elif expired:
            key = "expired"
        elif risk >= SUSPICIOUS or any(e["weight"] >= 20 for e in ev):
            key = "suspicious"   # a strong warning on its own is enough to ask for a second look
        elif med is not None and passes >= 2:
            key = "ok"
        elif risk > 0 and med is not None:
            key = "suspicious"
        else:
            key = "unknown"
        label, tone, say = VERDICTS[key]
        order = {"danger": 0, "warn": 1, "info": 2, "pass": 3}
        return {
            "verdict": {"key": key, "label": label, "tone": tone, "say": say, "risk": risk, "passes": passes},
            "medicine": None if med is None else {
                "brand": med["name"], "company": med["manufacturer"], "composition": D.composition_text(med["salts"]),
                "form": med["form"], "pack": med["pack"], "price": float(med["price"]),
                "discontinued": bool(med["discontinued"]), "rx": None, "use": "",
            },
            "match": kind,
            "evidence": sorted(ev, key=lambda e: (order[e["level"]], -e["weight"])),
            "extracted": {"batch": printed["batch"], "mfg": show(printed["mfg"]), "exp": show(printed["exp"]),
                          "manufacturer": printed["maker"],
                          "codes": [{"kind": c["kind"], "format": c["format"], "raw": c["raw"]} for c in codes]},
            "alternatives": self.alternatives(row_i, key) if row_i is not None else [],
            "actions": actions(key),
            "source": f"Checked against {len(self.db):,} medicines (A-Z Medicine Dataset of India)",
        }

    def alternatives(self, row_i, verdict_key="ok", limit=6):
        db = self.db
        med = db.row(row_i)
        out = []
        if verdict_key in ("fake", "suspicious"):
            out.append(self._alt(row_i, med, original=True))
        for j in db.alternatives(row_i, limit):
            out.append(self._alt(j, med))
        return out

    def _alt(self, j, ref, original=False):
        r = self.db.row(j)
        up, ref_up = D.unit_price(r["price"], r["pack"]), D.unit_price(ref["price"], ref["pack"])
        saving = round(100 * (1 - up / ref_up)) if ref_up and ref_up != float("inf") and up < ref_up else 0
        return {"brand": r["name"], "company": r["manufacturer"], "composition": D.composition_text(r["salts"]),
                "form": r["form"], "price": float(r["price"]), "pack": r["pack"], "saving": saving,
                "generic": False, "original": original, "rx": None}


def actions(key):
    report = ["Report it: Pharmacovigilance Programme of India helpline 1800-180-3024 (toll free) or the ADR PvPI app.",
              "Complain to your State Drug Controller or CDSCO (cdsco.gov.in) with the batch no., shop name and bill."]
    return {
        "fake": ["Do NOT take it. Keep the strip, box and bill as evidence.",
                 "Show it to a pharmacist / doctor and buy a fresh pack from another licensed pharmacy.", *report],
        "expired": ["Do NOT take it. Return it or dispose of it safely.", "Always check the expiry before paying."],
        "suspicious": ["Don't take it until a pharmacist has checked it.",
                       "Compare it with a pack you know is genuine.", "If it is still doubtful, report it:", *report],
        "ok": ["No warning signs found. This is not a lab test - stay alert to how the medicine looks and works.",
               "Keep the bill. Buy only from licensed pharmacies."],
        "unknown": ["Scan the barcode / QR code.", "Photograph the side with B.No., Mfg and Exp in good light.",
                    "Or type the brand, batch and expiry."],
    }[key]


_DETECTOR = None


def get_detector():
    global _DETECTOR
    if _DETECTOR is None:
        _DETECTOR = Detector()
    return _DETECTOR


if __name__ == "__main__":
    import json
    import sys
    text = " ".join(sys.argv[1:]) or "DOLO-650 Paracetamol 650 mg B.No. DOBS3975 Mfg. 04/2026 Exp. 03/2030 Micro Labs"
    print(json.dumps(get_detector().check(Pack(text=text)), indent=2, default=str))
