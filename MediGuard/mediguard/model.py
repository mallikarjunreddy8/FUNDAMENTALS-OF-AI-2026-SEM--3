"""
MediGuard simulation - the model (Mesa 3). One step = one day in a small town.

Question it answers: if more people check their medicine with a phone app, how much less
substandard and falsified (S&F) medicine is actually taken - and how do counterfeiters react?

Starting levels of bad medicine come from published surveys (see SCENARIOS and docs/REPORT.md).
"""

import datetime as dt
from collections import Counter, deque

import mesa

from . import dataset as D
from . import packs as P
from .agents import Counterfeiter, Inspector, Patient, Pharmacy
from .detector import Detector

# =============================================================================
# SCENARIOS: share of medicines that are substandard or falsified (S&F)
#   sf         total S&F share
#   falsified  share of all medicines that are falsified (spurious); the rest of sf is substandard
# =============================================================================
SCENARIOS = {
    # National Drug Survey 2014-16 (MoHFW / NIB, India): retail outlets 3.16% NSQ, 0.0245% spurious
    "India retail (NDS 2014-16)": {"sf": 0.0316 + 0.000245, "falsified": 0.000245},
    # same survey, government supply chain: 10.02% NSQ, 0.059% spurious
    "India govt supply (NDS 2014-16)": {"sf": 0.1002 + 0.00059, "falsified": 0.00059},
    # WHO 2017 (GSMS study): 10.5% of medical products in LMICs are S&F. The falsified share is
    # not separated in that estimate: 50/50 is a MODEL ASSUMPTION
    "LMIC average (WHO 2017)": {"sf": 0.105, "falsified": 0.0525},
    # Ozawa et al. 2018, JAMA Netw Open: 13.6% S&F prevalence in LMICs (96 studies, 67,839 samples)
    "LMIC meta-analysis (Ozawa 2018)": {"sf": 0.136, "falsified": 0.068},
}
DEFAULT_SCENARIO = "LMIC average (WHO 2017)"

START_MIX = {"crude": 0.6, "copied_qr": 0.25, "perfect": 0.15}   # counterfeiters start with cheap copies
WINDOW = 30                                                      # days used for the rolling measures


class MediGuardModel(mesa.Model):
    def __init__(self, n_patients=200, n_pharmacies=12, unlicensed_share=0.25, scenario=DEFAULT_SCENARIO,
                 app_adoption=0.3, report_prob=0.5, n_inspectors=1, intelligence_led=True, adaptive=True,
                 n_counterfeiters=2, qr_share=0.5, buy_every=10, ocr_error=0.02, confirm_prob=0.7,
                 width=20, height=20, seed=None, db=None):
        super().__init__(seed=seed)
        self.db = db or D.load(verbose=False)
        self.detector = Detector(self.db, alerts={})       # this town's own drug alert list
        self.start_date = dt.date(2026, 1, 1)
        self.scenario = scenario
        sc = SCENARIOS[scenario]
        self.target_falsified = sc["falsified"]
        self.unlicensed_share = unlicensed_share
        self.report_prob = report_prob
        self.intelligence_led = intelligence_led
        self.adaptive = adaptive
        self.buy_every = buy_every
        self.ocr_error = ocr_error          # share of characters the phone camera misreads
        self.confirm_prob = confirm_prob    # share of app users who check the details in step 2
        self.unlicensed_accept, self.licensed_accept = 0.8, 0.05
        self.closure_days, self.seizure_cost = 30, 60.0

        self.products = P.basket_products(self.db)
        self.qr_rows = set(self.random.sample(self.products, round(qr_share * len(self.products))))
        self.genuine_batches = {r: [self._new_batch() for _ in range(3)] for r in self.products}
        self.sub_batches = {}

        self.grid = mesa.space.MultiGrid(width, height, torus=False)

        # pharmacies: unlicensed shops have twice the substandard stock of licensed ones
        n_unlic = round(unlicensed_share * n_pharmacies)
        sub = sc["sf"] - sc["falsified"]
        sub_licensed = sub / (1 + unlicensed_share)
        cells = self.random.sample([(x, y) for x in range(1, width - 1) for y in range(1, height - 1)], n_pharmacies)
        self.pharmacies = []
        for i, cell in enumerate(cells):
            licensed = i >= n_unlic
            ph = Pharmacy(self, licensed, sub_licensed * (1 if licensed else 2))
            self.grid.place_agent(ph, cell)
            self.pharmacies.append(ph)

        for _ in range(n_patients):
            p = Patient(self, has_app=self.random.random() < app_adoption, price_sensitive=self.random.random() < 0.4)
            self.grid.place_agent(p, (self.random.randrange(width), self.random.randrange(height)))
        self.counterfeiters = [Counterfeiter(self, START_MIX) for _ in range(n_counterfeiters)]
        for _ in range(n_inspectors):
            self.grid.place_agent(Inspector(self), (0, 0))

        # bookkeeping
        self.days = deque(maxlen=WINDOW)
        self.today_tally = Counter()
        self.total = Counter()
        self.harm = self.reports = self.inspections = self.closures = 0

        self.datacollector = mesa.DataCollector(model_reporters={
            "S&F taken (%)": lambda m: m.rate("taken", bad=True),
            "S&F sold (%)": lambda m: m.rate("sold", bad=True),
            "Caught by app (%)": lambda m: m.share("flagged", "scanned", bad=True),
            "False alarms (%)": lambda m: m.share("flagged", "scanned", bad=False),
            "Harm events": lambda m: m.harm,
            "Reports": lambda m: m.reports,
            "Inspections": lambda m: m.inspections,
            "Shops closed": lambda m: m.closures,
            "Alerted batches": lambda m: len(m.detector.alerts),
            "Crude fakes (%)": lambda m: m.mix("crude"),
            "Copied-QR fakes (%)": lambda m: m.mix("copied_qr"),
            "Perfect clones (%)": lambda m: m.mix("perfect"),
            "Counterfeiter capital": lambda m: round(sum(c.capital for c in m.counterfeiters if c.active), 1),
        })
        self.datacollector.collect(self)

    # ------------------------------------------------------------------ helpers used by the agents
    def _new_batch(self):
        return "".join(self.random.choices("ABCDEFGHJKLMNPRSTUVWXYZ", k=2)) + str(self.random.randint(1000, 99999))

    @property
    def today(self):
        return self.start_date + dt.timedelta(days=self.steps)

    def mrp(self, row):
        return float(self.db.row(row)["price"])

    def falsified_rate_in(self, shop):
        """Share of a supplied shop's stock that is falsified (so the town total is near the scenario)."""
        base = self.target_falsified / max(self.unlicensed_share, 0.05)
        return min(0.6, base if not shop.licensed else base * 0.3)

    def substandard_batch(self, shop):
        return self.sub_batches.setdefault(shop, self._new_batch())

    def pack_for(self, shop, row, quality):
        if quality == "genuine":
            batch = self.random.choice(self.genuine_batches[row])
            price = shop.price_factor
        elif quality == "substandard":
            batch, price = self.substandard_batch(shop), shop.price_factor
        else:
            batch = shop.supplier.batches.setdefault(shop, self._new_batch())
            price = shop.price_factor * self.random.uniform(0.45, 0.9)   # fakes are sold cheaper
        return P.make_pack(self.db, row, quality, self.today, self.random, batch=batch,
                           has_qr=row in self.qr_rows, price_factor=price)

    def alert(self, batch):
        if batch:
            key = "".join(ch for ch in batch.upper() if ch.isalnum())
            self.detector.alerts[key] = {"batch": batch, "product": "", "status": "Failed lab test",
                                         "source": f"Drug inspector, day {self.steps}"}

    def lab_detect(self, bad_rate, samples=10, sensitivity=0.95):
        return sensitivity * (1 - (1 - bad_rate) ** samples)

    def public_trust(self, shop):
        return 1 / (1 + shop.reports)

    def count(self, kind, quality):
        self.today_tally[(kind, quality)] += 1
        self.total[(kind, quality)] += 1

    # ------------------------------------------------------------------ measures
    def _sum(self, kind, bad, source=None):
        rows = source if source is not None else self.days
        qs = [q for q in P.QUALITIES if (q != "genuine") == bad]
        return sum(day[(kind, q)] for day in rows for q in qs)

    def rate(self, kind, bad=True):
        bad_n, good_n = self._sum(kind, True), self._sum(kind, False)
        return round(100 * bad_n / (bad_n + good_n), 2) if bad_n + good_n else 0.0

    def share(self, num, den, bad):
        d = self._sum(den, bad)
        return round(100 * self._sum(num, bad) / d, 1) if d else 0.0

    def mix(self, q):
        active = [c for c in self.counterfeiters if c.active]
        return round(100 * sum(c.mix[q] for c in active) / len(active), 1) if active else 0.0

    def summary(self):
        """Whole-run totals (used by the experiments)."""
        t = self.total
        bad = [q for q in P.QUALITIES if q != "genuine"]
        taken = sum(t[("taken", q)] for q in P.QUALITIES)
        scanned_bad = sum(t[("scanned", q)] for q in bad)
        return {
            "S&F taken (%)": round(100 * sum(t[("taken", q)] for q in bad) / taken, 3) if taken else 0,
            "S&F sold (%)": round(100 * sum(t[("sold", q)] for q in bad) / max(1, sum(t[("sold", q)] for q in P.QUALITIES)), 3),
            "Caught by app (%)": round(100 * sum(t[("flagged", q)] for q in bad) / scanned_bad, 1) if scanned_bad else None,
            "False alarms (%)": round(100 * t[("flagged", "genuine")] / t[("scanned", "genuine")], 2) if t[("scanned", "genuine")] else None,
            "Harm per 1000 doses": round(1000 * self.harm / taken, 2) if taken else 0,
            "Shops closed": self.closures,
            "Alerted batches": len(self.detector.alerts),
            **{f"caught {q} (%)": (round(100 * t[("flagged", q)] / t[("scanned", q)], 1) if t[("scanned", q)] else None)
               for q in bad},
        }

    # ------------------------------------------------------------------ one day
    def step(self):
        self.today_tally = Counter()
        self.agents_by_type[Counterfeiter].shuffle_do("step")
        self.agents_by_type[Patient].shuffle_do("step")
        self.agents_by_type[Inspector].shuffle_do("step")
        # a new counterfeiter tries the market now and then if the old ones went bust
        if not any(c.active for c in self.counterfeiters) and self.random.random() < 0.02:
            self.counterfeiters.append(Counterfeiter(self, START_MIX))
        self.days.append(self.today_tally)
        self.datacollector.collect(self)
