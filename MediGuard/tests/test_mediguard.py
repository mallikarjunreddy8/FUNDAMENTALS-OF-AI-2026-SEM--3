"""
Tests:  python -m pytest -q

They use a small sample of rows copied from the real dataset, so they run without the 32 MB download.
"""

import datetime as dt
import io
import random

import pandas as pd
import pytest

from mediguard import dataset as D
from mediguard import packs as P
from mediguard.detector import Detector, gtin_valid, parse_date, parse_gs1

# Rows in the same format as A_Z_medicines_dataset_of_India.csv
SAMPLE = """id,name,price(₹),Is_discontinued,manufacturer_name,type,pack_size_label,short_composition1,short_composition2
1,Dolo 650 Tablet,34.27,FALSE,Micro Labs Ltd,allopathy,strip of 15 tablets,Paracetamol (650mg),
2,Pacimol 650 Tablet,30.5,FALSE,Ipca Laboratories Ltd,allopathy,strip of 15 tablets,Paracetamol (650mg),
3,Calpol 650 Tablet,30.0,FALSE,GlaxoSmithKline Pharmaceuticals Ltd,allopathy,strip of 15 tablets,Paracetamol (650mg),
4,Crocin Advance Tablet,22.62,FALSE,GlaxoSmithKline Consumer Healthcare,allopathy,strip of 20 tablets,Paracetamol (500mg),
5,Calpol 500mg Tablet,15.0,FALSE,GlaxoSmithKline Pharmaceuticals Ltd,allopathy,strip of 15 tablets,Paracetamol (500mg),
6,Augmentin 625 Duo Tablet,223.42,FALSE,Glaxo SmithKline Pharmaceuticals Ltd,allopathy,strip of 10 tablets,Amoxycillin  (500mg) ,  Clavulanic Acid (125mg)
7,Clavam 625 Tablet,201.47,FALSE,Alkem Laboratories Ltd,allopathy,strip of 10 tablets,Amoxycillin  (500mg) ,  Clavulanic Acid (125mg)
8,Glycomet 500 SR Tablet,47.71,FALSE,USV Ltd,allopathy,strip of 20 tablet sr,Metformin (500mg),
9,Glycomet 500mg Tablet,18.7,FALSE,USV Ltd,allopathy,strip of 20 tablets,Metformin (500mg),
10,Pantocid 40 Tablet,159.0,FALSE,Sun Pharmaceutical Industries Ltd,allopathy,strip of 15 tablets,Pantoprazole (40mg),
11,Pantodac 40 Tablet,140.0,FALSE,Zydus Cadila,allopathy,strip of 15 tablets,Pantoprazole (40mg),
12,Oldbrand 40 Tablet,50.0,TRUE,Old Pharma Ltd,allopathy,strip of 10 tablets,Pantoprazole (40mg),
13,Paracetamol Tablet,10.0,FALSE,Generic Labs,allopathy,strip of 10 tablets,Paracetamol (500mg),
14,Advance Injection,100.0,FALSE,Some Biotech,allopathy,vial of 1 Injection,Amoxycillin (1000mg),
"""
TODAY = "2026-11-20"


@pytest.fixture(scope="module")
def db():
    return D.MedicineDB(pd.read_csv(io.StringIO(SAMPLE)))


@pytest.fixture(scope="module")
def det(db):
    return Detector(db, alerts={"FAKE2291": {"batch": "FAKE2291", "product": "Crocin Advance", "status": "Spurious",
                                             "source": "test"}})


# ------------------------------------------------------------------ dataset
def test_split_name_keeps_release_type():
    assert D.split_name("Glycomet 500 SR Tablet") == ("GLYCOMET 500", "tablet sr")
    assert D.split_name("Dolo 650 Tablet") == ("DOLO 650", "tablet")


def test_parse_salt():
    assert D.parse_salt("Amoxycillin  (500mg) ") == ("AMOXYCILLIN", "500MG", 500.0, "MG")


def test_alternatives_same_composition_and_form(db):
    dolo = db.rows_for_brand("DOLO 650")[0]
    alts = [db.row(i)["name"] for i in db.alternatives(dolo)]
    assert set(alts) == {"Pacimol 650 Tablet", "Calpol 650 Tablet"}
    glyco_sr = db.rows_for_brand("GLYCOMET 500")
    sr = [i for i in glyco_sr if db.row(i)["form"] == "tablet sr"][0]
    assert all(db.row(i)["form"] == "tablet sr" for i in db.alternatives(sr))   # SR is not swapped for plain


def test_alternatives_skip_discontinued(db):
    i = db.rows_for_brand("PANTOCID 40")[0]
    assert "Oldbrand 40 Tablet" not in [db.row(j)["name"] for j in db.alternatives(i)]


def test_unit_price():
    assert D.unit_price(34.27, "strip of 15 tablets") == pytest.approx(34.27 / 15)


# ------------------------------------------------------------------ perception
def test_gtin_and_gs1():
    assert gtin_valid("8901234567890") and not gtin_valid("8901234567891")
    g = parse_gs1("]d2010890765432100517270131" + "10AB12\x1d21XYZ")
    assert g["gtin"] == "08907654321005" and g["exp"] == (2027, 1) and g["batch"] == "AB12"


@pytest.mark.parametrize("text", ["MAR 2027", "Mar.27", "03/27", "03/2027", "2027-03", "15/03/2027"])
def test_dates(text):
    assert parse_date(text) == (2027, 3)


# ------------------------------------------------------------------ reasoning
GENUINE = {"text": "DOLO-650\nParacetamol Tablets IP 650 mg\nB.No. DOBS3975\nMfg. 04/2026 Exp. 03/2030\n"
                   "Manufactured by: Micro Labs Limited, Bengaluru",
           "codes": [{"format": "QR_CODE", "text": "Brand: Dolo 650\nBatch: DOBS3975\nMfg: 04/2026\nExp: 03/2030"},
                     {"format": "EAN_13", "text": "8901234567890"}], "today": TODAY}


def test_genuine_pack(det):
    r = det.check(GENUINE)
    assert r["verdict"]["key"] == "ok", r["evidence"]
    assert r["medicine"]["brand"] == "Dolo 650 Tablet"


def test_lookalike_name_with_other_red_flags(det):
    r = det.check({"text": "CROSIN Advance\nParacetamol Tablets 650 mg\nB.No. FAKE2291\nMfg. 01/2027 Exp. 12/2035\n"
                           "Manufactured by: Healthline Pharma", "codes": [{"format": "EAN_13", "text": "8901234567891"}],
                   "today": TODAY})
    assert r["match"] == "lookalike" and r["medicine"]["brand"] == "Crocin Advance Tablet"
    assert r["verdict"]["key"] == "fake"


def test_salt_line_is_not_taken_as_brand(det):
    # "Paracetamol Tablet" is a real product, but here it is the composition line
    assert det.identify("CROSIN Advance\nParacetamol Tablets 650 mg")[0] == "lookalike"


def test_ocr_zero_for_o_is_not_a_fake(det):
    assert det.identify("D0L0 650 tablets")[:2] == ("exact", "DOLO 650")


def test_similar_real_brands_are_not_lookalikes(det):
    assert det.identify("PANTODAC 40")[:2] == ("exact", "PANTODAC 40")


def test_copied_qr(det):
    pack = dict(GENUINE, codes=[{"format": "QR_CODE", "text": "Brand: Dolo 650\nBatch: ZZ9911\nExp: 08/2027"}])
    titles = [e["title"] for e in det.check(pack)["evidence"]]
    assert "QR / barcode batch doesn't match the print" in titles


def test_price_far_below_mrp(det):
    r = det.check({"manual": {"brand": "Dolo 650", "batch": "X1234", "exp": "2028-01", "price": "10"}, "today": TODAY})
    assert "Much cheaper than the MRP" in [e["title"] for e in r["evidence"]]
    assert r["verdict"]["key"] == "suspicious"


def test_discontinued(det):
    r = det.check({"manual": {"brand": "Oldbrand 40", "batch": "X1234", "exp": "2028-01"}, "today": TODAY})
    assert "This product is discontinued" in [e["title"] for e in r["evidence"]]


def test_expired(det):
    r = det.check({"manual": {"brand": "Dolo 650", "batch": "X1234", "exp": "2026-08"}, "today": TODAY})
    assert r["verdict"]["key"] == "expired"


def test_alternatives_in_report(det):
    r = det.check(GENUINE)
    assert {a["brand"] for a in r["alternatives"]} == {"Pacimol 650 Tablet", "Calpol 650 Tablet"}


# ------------------------------------------------------------------ packs (used by the simulation)
def test_packs_are_detected_as_designed(db, det):
    rng = random.Random(1)
    today = dt.date(2026, 11, 20)
    rows = db.rows_for_brand("DOLO 650") + db.rows_for_brand("AUGMENTIN 625 DUO")
    for _ in range(30):
        row = rng.choice(rows)
        flag = lambda q, **kw: det.check(P.make_pack(db, row, q, today, rng, **kw), False)["verdict"]["key"] != "ok"  # noqa: E731
        assert not flag("genuine")
        assert flag("crude")
        assert flag("copied_qr", has_qr=True)
        assert not flag("perfect")      # a perfect clone needs a lab - the agent is honest about it


# ------------------------------------------------------------------ the Mesa model
def test_model_runs_and_app_users_catch_fakes(db):
    from mediguard.model import MediGuardModel
    m = MediGuardModel(db=db, app_adoption=1.0, scenario="LMIC meta-analysis (Ozawa 2018)", seed=3, ocr_error=0.0)
    for _ in range(60):
        m.step()
    s = m.summary()
    assert s["caught crude (%)"] == 100.0           # every crude fake bought by an app user is flagged
    assert s["False alarms (%)"] == 0.0             # no camera errors -> no false alarms
    assert s["S&F taken (%)"] < s["S&F sold (%)"]   # flagged packs are not taken
    df = m.datacollector.get_model_vars_dataframe()
    assert len(df) == 61 and "Perfect clones (%)" in df


def test_model_without_app(db):
    from mediguard.model import MediGuardModel
    m = MediGuardModel(db=db, app_adoption=0.0, seed=3)
    for _ in range(30):
        m.step()
    s = m.summary()
    assert s["Caught by app (%)"] is None and s["S&F taken (%)"] == s["S&F sold (%)"]
