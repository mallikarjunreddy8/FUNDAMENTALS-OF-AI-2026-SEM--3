"""
MediGuard - makes realistic medicine packs for the simulation and the evaluation.

Each pack is built from a REAL product in the dataset (name, composition, maker, MRP) and then,
for bad quality, changed the way real fakes are changed:

  genuine       correct everything
  substandard   genuine-looking pack, real batch, but the tablets fail the lab test (NSQ).
                A phone cannot see this - only a lab, or the batch later appearing on a drug alert.
  crude         falsified, cheap copy: lookalike name, wrong maker or strength, bad barcode,
                odd dates, no QR, blurry print, big discount
  copied_qr     falsified, real name and maker, but the QR code is copied from one genuine pack,
                so the QR batch / expiry don't match the printed ones
  perfect       falsified, a careful clone: everything printed is consistent. Only the price,
                the drug alert list or a lab test can catch it.
"""

import random
import string

from . import dataset as D

QUALITIES = ["genuine", "substandard", "crude", "copied_qr", "perfect"]
FALSIFIED = ["crude", "copied_qr", "perfect"]

# Common medicines in an Indian pharmacy (all are in the dataset). The simulation sells these.
BASKET = ["DOLO 650", "CROCIN ADVANCE", "CALPOL 500", "AUGMENTIN 625 DUO", "AZEE 500", "AZITHRAL 500",
          "TELMA 40", "COMBIFLAM", "PAN 40", "PANTOCID 40", "GLYCOMET 500", "MONTAIR 10", "ALLEGRA 120",
          "THYRONORM 50", "ECOSPRIN 75", "ATORVA 10", "STAMLO 5", "CIPLOX 500", "TAXIM O 200", "OMEZ 20",
          "MEFTAL SPAS", "SHELCAL 500", "OKACET", "ZIFI 200", "LIPITOR 10"]

FAKE_MAKERS = ["Healthline Pharma Pvt Ltd", "Medicure Labs", "Sunrise Formulations", "Global Remedies Ltd"]
SWAPS = {"C": "S", "S": "C", "O": "A", "A": "O", "I": "L", "L": "I", "E": "A", "N": "M", "M": "N", "U": "O"}


def basket_products(db):
    """Row numbers of the basket medicines (the best row for each brand)."""
    rows = []
    for key in BASKET:
        r = db.best_row(db.rows_for_brand(key))
        if r is not None and db.row(r)["salts"]:
            rows.append(r)
    return rows


def ean_for(row_i):
    """A valid EAN-13 with India's GS1 prefix 890, made from the row number."""
    body = "890" + f"{row_i:09d}"
    total = sum(int(c) * (3 if i % 2 else 1) for i, c in enumerate(body))
    return body + str((10 - total % 10) % 10)


def lookalike(db, word, rng):
    """'CROCIN' -> 'CROSIN': one letter changed, and not a real brand."""
    for _ in range(20):
        pos = rng.randrange(1, len(word))
        ch = word[pos]
        new = SWAPS.get(ch, rng.choice(string.ascii_uppercase))
        cand = word[:pos] + new + word[pos + 1:]
        if cand != word and cand not in db.by_first_word:
            return cand
    return word + "E"


def month_add(ym, k):
    y, m = ym
    n = y * 12 + (m - 1) + k
    return n // 12, n % 12 + 1


def ym(d):
    return f"{d[1]:02d}/{d[0]}"


def make_pack(db, row_i, quality, today, rng=random, batch=None, has_qr=True, price_factor=1.0):
    """-> dict ready for Detector.check(), plus 'quality' and 'batch' for bookkeeping."""
    r = db.row(row_i)
    brand = r["brand_key"].title()
    words = brand.split(" ")
    composition = D.composition_text(r["salts"])
    maker = r["manufacturer"]
    now = (today.year, today.month)
    mfg = month_add(now, -rng.randint(1, 10))
    exp = month_add(mfg, rng.choice([24, 36]))
    batch = batch or "".join(rng.choices(string.ascii_uppercase, k=2)) + str(rng.randint(1000, 99999))
    ean = ean_for(row_i)
    checklist = {}
    qr_batch, qr_exp = batch, exp
    mrp = float(r["price"])

    if quality == "crude":
        words[0] = lookalike(db, words[0].upper(), rng).title()
        if rng.random() < 0.5:
            maker = rng.choice(FAKE_MAKERS)
        if rng.random() < 0.3:  # wrong strength printed
            composition = composition.replace(str(int(r["salts"][0][2] or 0)), str(int((r["salts"][0][2] or 0) * 0.8)), 1)
        if rng.random() < 0.5:  # made-up barcode number
            ean = ean[:-1] + str((int(ean[-1]) + 1) % 10)
        if rng.random() < 0.25:
            mfg = month_add(now, rng.randint(1, 4))  # date in the future
        if rng.random() < 0.3:
            exp = month_add(mfg, rng.choice([72, 96]))  # impossible shelf life
        has_qr = False
        checklist = {"poorPrint": rng.random() < 0.35}
    elif quality == "copied_qr":
        if has_qr:
            qr_batch = "QX" + str(rng.randint(100, 999))     # the one genuine pack they copied
            qr_exp = month_add(exp, rng.choice([-7, 5, 11]))
    # "genuine", "substandard" and "perfect" print a consistent pack

    lines = [" ".join(words), composition, f"B.No. {batch}", f"Mfg. {ym(mfg)}   Exp. {ym(exp)}",
             f"Manufactured by: {maker}"]
    codes = [{"format": "EAN_13", "text": ean}]
    if has_qr:
        codes.append({"format": "QR_CODE", "text": f"Brand: {r['name']}\nManufacturer: {r['manufacturer']}\n"
                                                    f"Batch: {qr_batch}\nMfg: {ym(mfg)}\nExp: {ym(qr_exp)}"})
    return {
        "text": "\n".join(lines), "codes": codes, "checklist": checklist,
        "manual": {"price": round(mrp * price_factor, 2)}, "today": today.isoformat(),
        "quality": quality, "batch": batch, "row": row_i,
        # what the user types in step 2 after checking the camera's reading against the pack
        "confirmed": {"brand": " ".join(words), "batch": batch, "mfg": f"{mfg[0]}-{mfg[1]:02d}",
                      "exp": f"{exp[0]}-{exp[1]:02d}", "manufacturer": maker},
    }


def confirm(pack):
    """The user corrects the camera's reading (step 2 of the app)."""
    pack["manual"] = {**pack["manual"], **pack["confirmed"]}
    return pack


def ocr_noise(text, rate, rng=random):
    """Simulate a bad photo: swap, drop or add characters at the given rate."""
    confusable = {"O": "0", "0": "O", "I": "1", "1": "I", "S": "5", "5": "S", "B": "8", "E": "F", "C": "G"}
    out = []
    for ch in text:
        x = rng.random()
        if ch != "\n" and x < rate / 3:
            continue                                   # dropped
        if ch != "\n" and x < 2 * rate / 3:
            ch = confusable.get(ch.upper(), rng.choice(string.ascii_uppercase))  # misread
        elif ch != "\n" and x < rate:
            ch = ch + rng.choice(" .,'")              # speck of dirt
        out.append(ch)
    return "".join(out)
