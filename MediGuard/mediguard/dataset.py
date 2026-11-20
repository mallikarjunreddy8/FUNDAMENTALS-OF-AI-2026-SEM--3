"""
MediGuard - the real medicine dataset.

Dataset: "A-Z Medicine Dataset of India" (Shudhanshu Singh, Kaggle)
         253,973 allopathic medicines sold in India with price (Rs), manufacturer,
         pack size, discontinued flag and composition (up to 2 salts).
         https://www.kaggle.com/datasets/shudhanshusingh/az-medicine-dataset-of-india

The CSV is not stored in git (32 MB). Get it with:
    python -m mediguard.dataset --download
or download it from Kaggle and put it at  data/A_Z_medicines_dataset_of_India.csv

What this file builds from it (class MedicineDB):
    brand index        "DOLO 650"  -> rows        (to recognise the medicine on a pack)
    composition index  "PARACETAMOL 650MG | tablet" -> rows   (to find alternatives)
"""

import os
import pickle
import re
import sys
import urllib.request
from collections import defaultdict

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(os.path.dirname(HERE), "data")
CSV_PATH = os.path.join(DATA_DIR, "A_Z_medicines_dataset_of_India.csv")
CACHE_PATH = os.path.join(DATA_DIR, "medicine_db.pkl")

# Public copies of the Kaggle file (Kaggle itself needs a login)
MIRRORS = [
    "https://media.githubusercontent.com/media/framesxsab/SimPrescribe-/main/A_Z_medicines_dataset_of_India.csv",
    "https://media.githubusercontent.com/media/chrisharris1/mediai/main/ai-models/data/raw_indian_medicines/A_Z_medicines_dataset_of_India.csv",
]

# Words at the end of a name that describe the dosage form, not the brand
FORM_WORDS = {
    "TABLET", "TABLETS", "CAPSULE", "CAPSULES", "INJECTION", "SYRUP", "SUSPENSION", "CREAM", "DROP", "DROPS",
    "OINTMENT", "GEL", "LOTION", "SOLUTION", "INFUSION", "SOAP", "SPRAY", "POWDER", "EXPECTORANT", "SACHET",
    "INHALER", "RESPULES", "SHAMPOO", "LINIMENT", "SOFTGEL", "VIAL", "KIT", "LOZENGES", "GRANULES", "PESSARY",
    "SUPPOSITORY", "TRANSCAP", "ROTACAP", "REDICAPS", "OIL", "FACEWASH", "SERUM", "CHEWABLE", "ORAL",
}
# Release-type words: kept in the form, because "500 SR" is not the same as "500"
MODIFIERS = {"SR", "ER", "DT", "MD", "PR", "CR", "MR", "XR", "XL", "OD", "LS", "FREE", "SUGAR"}


# =============================================================================
# DOWNLOAD
# =============================================================================
def download(path=CSV_PATH):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    for url in MIRRORS:
        try:
            print("Downloading", url)
            urllib.request.urlretrieve(url, path + ".part")
            with open(path + ".part", encoding="utf-8") as f:
                header = f.readline()
            if header.startswith("id,name,price"):
                os.replace(path + ".part", path)
                print("Saved", path)
                return path
            print("  not the dataset, trying the next copy")
        except Exception as err:  # noqa: BLE001 - try the next mirror
            print("  failed:", err)
    if os.path.exists(path + ".part"):
        os.remove(path + ".part")
    raise SystemExit(
        "Could not download the dataset. Download it from Kaggle:\n"
        "  https://www.kaggle.com/datasets/shudhanshusingh/az-medicine-dataset-of-india\n"
        f"and save it as {path}"
    )


# =============================================================================
# CLEANING HELPERS
# =============================================================================
def norm_text(s):
    """'Dolo-650 Tablet' -> 'DOLO 650 TABLET' (letters and digits only)."""
    return re.sub(r"[^A-Z0-9]+", " ", str(s).upper()).strip()


def split_name(name):
    """'Glycomet 500 SR Tablet' -> ('GLYCOMET 500', 'tablet sr')."""
    words = norm_text(name).split()
    form, mods = [], []
    while len(words) > 1 and (words[-1] in FORM_WORDS or words[-1] in MODIFIERS):
        w = words.pop()
        (form if w in FORM_WORDS else mods).append(w)
    # a modifier written before the strength ("Glycomet 500 SR") also stays in the form
    while len(words) > 1 and words[-1] in MODIFIERS:
        mods.append(words.pop())
    form_txt = " ".join(sorted(w.lower().rstrip("s") for w in form) + sorted(m.lower() for m in mods))
    return " ".join(words), form_txt or "other"


SALT_RE = re.compile(r"^\s*(.+?)\s*\(([^)]*)\)\s*$")


def parse_salt(text):
    """'Amoxycillin  (500mg) ' -> ('AMOXYCILLIN', '500MG', 500.0, 'MG')"""
    if not isinstance(text, str) or not text.strip():
        return None
    m = SALT_RE.match(text)
    salt = (m.group(1) if m else text).strip()
    strength = (m.group(2) if m else "").strip()
    salt = re.sub(r"\s+", " ", salt).upper()
    strength = re.sub(r"\s+", "", strength).upper()
    num = re.match(r"^(\d+(?:\.\d+)?)(MG|MCG|G|IU|%)", strength)
    value, unit = (float(num.group(1)), num.group(2)) if num else (None, None)
    return salt, strength, value, unit


# =============================================================================
# THE DATABASE
# =============================================================================
class MedicineDB:
    """All medicines, plus the indexes the agent needs."""

    def __init__(self, df):
        df = df.rename(columns={"price(₹)": "price", "Is_discontinued": "discontinued",
                                "manufacturer_name": "manufacturer", "pack_size_label": "pack"})
        df = df[["name", "price", "discontinued", "manufacturer", "pack",
                 "short_composition1", "short_composition2"]].copy()
        df["discontinued"] = df["discontinued"].astype(str).str.upper().eq("TRUE")
        df["manufacturer"] = df["manufacturer"].fillna("").str.replace(r"\s+", " ", regex=True).str.strip()
        df = df.dropna(subset=["name"]).reset_index(drop=True)

        brand_keys, forms, salts, comp_keys = [], [], [], []
        for name, c1, c2 in zip(df["name"], df["short_composition1"], df["short_composition2"]):
            key, form = split_name(name)
            parts = [p for p in (parse_salt(c1), parse_salt(c2)) if p]
            brand_keys.append(key)
            forms.append(form)
            salts.append(parts)
            comp = " + ".join(sorted(f"{s} {st}".strip() for s, st, _, _ in parts))
            comp_keys.append(f"{comp} | {form}" if comp else "")
        df["brand_key"] = brand_keys
        df["form"] = forms
        df["salts"] = salts
        df["comp_key"] = comp_keys
        self.df = df

        self.by_brand = defaultdict(list)
        self.by_comp = defaultdict(list)
        self.by_first_word = defaultdict(set)
        for i, (bk, ck) in enumerate(zip(df["brand_key"], df["comp_key"])):
            self.by_brand[bk].append(i)
            if ck:
                self.by_comp[ck].append(i)
            self.by_first_word[bk.split(" ")[0]].add(bk)
        self.brand_list = list(self.by_brand.keys())
        # salt names like "PARACETAMOL": a line starting with one is the composition line, not the brand
        self.salt_names = {norm_text(p[0]) for parts in df["salts"] for p in parts}
        self.manufacturers = set(df["manufacturer"])

    # ------------------------------------------------------------------ lookups
    def __len__(self):
        return len(self.df)

    def row(self, i):
        return self.df.iloc[i]

    def rows_for_brand(self, brand_key):
        return self.by_brand.get(brand_key, [])

    def best_row(self, rows, manufacturer_text=""):
        """Several products can share a brand name: prefer the one in production and
        whose maker is printed on the pack."""
        if not rows:
            return None
        mt = norm_text(manufacturer_text)

        def score(i):
            r = self.df.iloc[i]
            maker_hit = any(w in mt for w in norm_text(r["manufacturer"]).split()[:1]) if mt else False
            return (maker_hit, not r["discontinued"], "tablet" in r["form"], -i)
        return max(rows, key=score)

    def find_in_text(self, text, max_words=5, line_start=False):
        """Longest brand name that appears in the text, e.g. 'DOLO 650'. -> (brand_key, start word)
        line_start=True only accepts a name at the start of the text (brand names lead a line)."""
        words = norm_text(text).split()
        best = None
        for start in range(1 if line_start else len(words)):
            if words[start] not in self.by_first_word:
                continue
            for n in range(min(max_words, len(words) - start), 0, -1):
                cand = " ".join(words[start:start + n])
                if cand in self.by_brand:
                    if not best or n > best[2]:
                        best = (cand, start, n)
                    break
        return (best[0], best[1]) if best else (None, None)

    def alternatives(self, i, limit=8):
        """Same salts, same strengths, same dosage form, still sold. Cheapest first."""
        key = self.df.at[i, "comp_key"]
        if not key:
            return []
        if not hasattr(self, "_alt_cache"):
            self._alt_cache = {}
        if key not in self._alt_cache:   # all products with this composition, cheapest per tablet first
            rows = [j for j in self.by_comp[key] if not self.df.at[j, "discontinued"]]
            alt = self.df.loc[rows, ["name", "price", "pack"]].copy()
            alt["unit_price"] = [unit_price(p, pk) for p, pk in zip(alt["price"], alt["pack"])]
            self._alt_cache[key] = list(alt.sort_values("unit_price").drop_duplicates("name").index)
        return [j for j in self._alt_cache[key] if j != i][:limit]

    def search(self, query, limit=10):
        q = norm_text(query)
        if len(q) < 2:
            return []
        hits = [k for k in self.brand_list if k.startswith(q)][:limit]
        return [self.best_row(self.by_brand[k]) for k in hits]


def unit_price(price, pack):
    """Price of one tablet / capsule (or of the whole pack if it isn't a strip)."""
    m = re.search(r"of\s+(\d+)\s+(tablet|capsule)", str(pack), re.I)
    try:
        return float(price) / (int(m.group(1)) if m else 1)
    except (TypeError, ValueError, ZeroDivisionError):
        return float("inf")


def composition_text(salts):
    return " + ".join(f"{s.title()} {st.lower()}".strip() for s, st, _, _ in salts)


# =============================================================================
# LOAD (with a cache, so the 254k rows are cleaned only once)
# =============================================================================
_DB = None


def load(csv_path=CSV_PATH, cache_path=CACHE_PATH, verbose=True):
    global _DB
    if _DB is not None:
        return _DB
    if not os.path.exists(csv_path):
        raise FileNotFoundError(
            f"Dataset not found at {csv_path}. Run:  python -m mediguard.dataset --download")
    if os.path.exists(cache_path) and os.path.getmtime(cache_path) > os.path.getmtime(csv_path):
        try:
            with open(cache_path, "rb") as f:
                _DB = pickle.load(f)
            return _DB
        except Exception:  # noqa: BLE001 - old or broken cache: rebuild it
            pass
    if verbose:
        print("Preparing the medicine database (first run only, a few seconds)...")
    _DB = MedicineDB(pd.read_csv(csv_path))
    with open(cache_path, "wb") as f:
        pickle.dump(_DB, f)
    return _DB


def main():
    if "--download" in sys.argv:
        download()
    db = load()
    df = db.df
    print(f"{len(df):,} medicines, {df['manufacturer'].nunique():,} manufacturers, "
          f"{len(db.by_brand):,} brand names, {len(db.by_comp):,} compositions, "
          f"{int(df['discontinued'].sum()):,} discontinued")


if __name__ == "__main__":
    # import through the package so the cache can be loaded by other scripts
    from mediguard import dataset as _self
    _self.main()
