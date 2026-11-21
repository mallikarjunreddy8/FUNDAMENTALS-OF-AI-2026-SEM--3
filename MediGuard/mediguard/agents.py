"""
MediGuard simulation - the agents (Mesa 3).

    Patient        needs medicine now and then, picks a nearby pharmacy (trust + price), buys a pack.
                   If they have the MediGuard app, the detection agent checks the pack. A flagged pack
                   is not taken and may be reported. Taking a bad pack can cause harm.
    Pharmacy       licensed or not. Sells genuine, substandard and (if a counterfeiter supplies it)
                   falsified packs. Can be closed after a failed inspection.
    Counterfeiter  supplies falsified packs to the shops that take them, makes money, and ADAPTS:
                   when the app catches its packs it moves to harder-to-detect copies (arms race).
    Inspector      a drug inspector. Visits pharmacies (reported ones first when intelligence-led),
                   lab-tests samples, closes bad shops and publishes bad batches on the drug alert list,
                   which every app then checks (network effect).

Ideas follow Ackland et al. (2019, JASSS): trust between patients and sellers, built from experience,
shapes a pharmaceutical supply chain with poor-quality medicines.
"""

import mesa

from . import packs as P

# How likely a bad pack is to cause harm (treatment failure / side effect) when taken.
# Assumption for the model: falsified packs often have little or no active ingredient.
HARM = {"genuine": 0.0, "substandard": 0.25, "crude": 0.6, "copied_qr": 0.6, "perfect": 0.6}
COST = {"crude": 0.15, "copied_qr": 0.30, "perfect": 0.50}   # making cost, as a share of the MRP
SELL = 0.65                                                     # price the shop pays the counterfeiter


def distance(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


# =============================================================================
class Pharmacy(mesa.Agent):
    def __init__(self, model, licensed, substandard_rate):
        super().__init__(model)
        self.licensed = licensed
        self.substandard_rate = substandard_rate   # manufacturing quality problems (NSQ) in its stock
        self.falsified_rate = 0.0                   # set every day by the counterfeiters
        self.supplier = None                        # the counterfeiter that supplies it (if any)
        self.closed_until = -1
        self.reports = 0                            # complaints not yet inspected
        self.sold = 0
        self.bad_sold = 0
        self.last_inspected = -999

    @property
    def is_open(self):
        return self.model.steps > self.closed_until

    @property
    def price_factor(self):
        return 1.0 if self.licensed else 0.85      # unlicensed shops undercut the MRP

    def sell(self):
        """Pick the quality of the next pack sold."""
        rng = self.model.random
        x = rng.random()
        if x < self.falsified_rate and self.supplier is not None:
            quality = self.supplier.pick_type()
        elif x < self.falsified_rate + self.substandard_rate:
            quality = "substandard"
        else:
            quality = "genuine"
        self.sold += 1
        self.bad_sold += quality != "genuine"
        return quality


# =============================================================================
class Counterfeiter(mesa.Agent):
    def __init__(self, model, mix):
        super().__init__(model)
        self.mix = dict(mix)        # share of crude / copied_qr / perfect packs
        self.capital = 100.0
        self.batches = {}           # pharmacy -> the fake batch number printed on its packs
        self.sold = {q: 0 for q in P.FALSIFIED}
        self.caught = {q: 0 for q in P.FALSIFIED}
        self.window = []            # recent (quality, caught_by_app) for learning
        self.active = True

    def pick_type(self):
        r, acc = self.model.random.random(), 0
        for q in P.FALSIFIED:
            acc += self.mix[q]
            if r < acc:
                return q
        return P.FALSIFIED[-1]

    def record(self, quality, flagged, mrp):
        cost = COST[quality] * mrp
        self.capital += SELL * mrp - cost
        self.sold[quality] += 1
        self.caught[quality] += flagged
        self.window = (self.window + [(quality, flagged)])[-60:]

    def step(self):
        if not self.active:
            return
        m = self.model
        # 1. choose shops to supply: unlicensed ones accept, licensed ones rarely; avoid recently inspected
        for ph in m.pharmacies:
            if ph.supplier not in (None, self):
                continue
            if not ph.is_open or m.steps - ph.last_inspected < 10:
                ph.supplier, ph.falsified_rate = None, 0.0
                continue
            accepts = m.unlicensed_accept if not ph.licensed else m.licensed_accept
            if ph.supplier is self or m.random.random() < accepts / 10:
                ph.supplier = self
                ph.falsified_rate = m.falsified_rate_in(ph)
                self.batches.setdefault(ph, m._new_batch())   # the batch number printed on its fakes
        # 2. learn: if the app catches a type often, move production to a harder type
        if m.adaptive and len(self.window) >= 20:
            for easy, harder in (("crude", "copied_qr"), ("copied_qr", "perfect")):
                seen = [f for q, f in self.window if q == easy]
                if seen and sum(seen) / len(seen) > 0.3 and self.mix[easy] > 0.02:
                    shift = min(self.mix[easy], 0.05)
                    self.mix[easy] -= shift
                    self.mix[harder] += shift
        # 3. bankrupt (seizures, fines) -> leaves the market
        if self.capital < 0:
            self.active = False
            for ph in m.pharmacies:
                if ph.supplier is self:
                    ph.supplier, ph.falsified_rate = None, 0.0


# =============================================================================
class Patient(mesa.Agent):
    def __init__(self, model, has_app, price_sensitive):
        super().__init__(model)
        self.has_app = has_app
        self.price_sensitive = price_sensitive
        self.trust = {}             # pharmacy -> trust 0..1 (from own experience and reports)
        self.next_need = model.random.randint(0, model.buy_every)

    def choose_pharmacy(self):
        m = self.model
        shops = sorted((p for p in m.pharmacies if p.is_open), key=lambda p: distance(p.pos, self.pos))[:4]
        if not shops:
            return None
        weights = []
        for p in shops:
            # even a distrusted shop keeps a small chance: people still need their medicine
            w = max(0.05, self.trust.get(p, 0.7)) * (1 + 0.5 * m.public_trust(p))
            if self.price_sensitive and not p.licensed:
                w *= 1.6                                 # cheaper
            weights.append(w / (1 + distance(p.pos, self.pos) / 4))
        return m.random.choices(shops, weights=weights)[0]

    def step(self):
        m = self.model
        # wander around the town
        nxt = m.random.choice(m.grid.get_neighborhood(self.pos, moore=True, include_center=True))
        m.grid.move_agent(self, nxt)
        if m.steps < self.next_need:
            return
        self.next_need = m.steps + m.random.randint(m.buy_every // 2, m.buy_every * 3 // 2)
        shop = self.choose_pharmacy()
        if shop is None:
            return
        quality = shop.sell()
        row = m.random.choice(m.products)
        m.count("sold", quality)

        flagged = False
        if self.has_app:   # only an app user's pack needs to be "printed" and checked
            pack = m.pack_for(shop, row, quality)
            pack["text"] = P.ocr_noise(pack["text"], m.ocr_error, m.random)
            if m.random.random() < m.confirm_prob:
                P.confirm(pack)
            verdict = m.detector.check(pack, with_alternatives=False)["verdict"]["key"]
            flagged = verdict in ("fake", "suspicious", "expired")
            m.count("scanned", quality)
            if flagged:
                m.count("flagged", quality)
        if quality in P.FALSIFIED and shop.supplier is not None:
            shop.supplier.record(quality, flagged, m.mrp(row))

        if flagged:
            self.trust[shop] = max(0.0, self.trust.get(shop, 0.7) - 0.4)
            if m.random.random() < m.report_prob:
                shop.reports += 1
                m.reports += 1
            return
        # the pack is taken
        m.count("taken", quality)
        if m.random.random() < HARM[quality]:
            m.harm += 1
            self.trust[shop] = max(0.0, self.trust.get(shop, 0.7) - 0.2)   # "it didn't work"
            if m.random.random() < m.report_prob * 0.2:                     # some complain to the shop / doctor
                shop.reports += 1
                m.reports += 1
        else:
            self.trust[shop] = min(1.0, self.trust.get(shop, 0.7) + 0.02)


# =============================================================================
class Inspector(mesa.Agent):
    def __init__(self, model):
        super().__init__(model)
        self.target = None

    def pick_target(self):
        m = self.model
        open_shops = [p for p in m.pharmacies if p.is_open]
        if not open_shops:
            return None
        reported = [p for p in open_shops if p.reports > 0]
        if m.intelligence_led and reported:
            return max(reported, key=lambda p: (p.reports, -distance(p.pos, self.pos)))
        return m.random.choice(open_shops)

    def step(self):
        m = self.model
        if self.target is None or not self.target.is_open:
            self.target = self.pick_target()
            if self.target is None:
                return
        # walk 2 cells a day towards the shop
        for _ in range(2):
            if self.pos == self.target.pos:
                break
            x, y = self.pos
            tx, ty = self.target.pos
            step = (x + (tx > x) - (tx < x), y) if x != tx else (x, y + (ty > y) - (ty < y))
            m.grid.move_agent(self, step)
        if self.pos != self.target.pos:
            return
        # inspect: lab-test samples of each kind of stock the shop holds
        shop, self.target = self.target, None
        shop.last_inspected = m.steps
        shop.reports = 0
        m.inspections += 1
        found_false = shop.falsified_rate > 0 and m.random.random() < m.lab_detect(shop.falsified_rate)
        found_sub = shop.substandard_rate > 0 and m.random.random() < m.lab_detect(shop.substandard_rate)
        if found_sub:
            m.alert(m.substandard_batch(shop))           # the bad batch goes on the alert list
        if found_false:
            cf = shop.supplier
            m.alert(cf.batches.get(shop))
            cf.capital -= m.seizure_cost
            cf.batches.pop(shop, None)                    # they must print a new batch number
            shop.supplier, shop.falsified_rate = None, 0.0
            shop.closed_until = m.steps + m.closure_days
            m.closures += 1
