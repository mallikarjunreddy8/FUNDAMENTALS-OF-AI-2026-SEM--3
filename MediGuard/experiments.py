"""
MediGuard - the experiments for the report. Results go to results/ (CSV tables + PNG charts).

    python experiments.py            all experiments (about 5 minutes)
    python experiments.py --quick    fewer runs, to try it out (under a minute)

Experiment 1  How good is the detection agent?   packs made from the real dataset, each kind of
              fake, with camera (OCR) errors added -> detection rate and false alarms
Experiment 2  Does the app help a town?          Mesa model, share of people using the app 0..100%,
              in the 4 research scenarios -> share of bad medicine actually taken, harm
Experiment 3  Arms race                          how counterfeiters change their fakes over time
Experiment 4  Policies                           app alone / inspectors alone / both / adaptive or not
"""

import datetime as dt
import os
import random
import sys
import time

import matplotlib
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from mediguard import dataset as D  # noqa: E402
from mediguard import packs as P  # noqa: E402
from mediguard.detector import Detector  # noqa: E402
from mediguard.model import SCENARIOS, MediGuardModel  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")
QUICK = "--quick" in sys.argv
SEEDS = 2 if QUICK else 5
DAYS = 90 if QUICK else 180
COLORS = ["#0f766e", "#2f5f9e", "#c2410c", "#7c3aed", "#b42318"]


def save(fig, name):
    path = os.path.join(OUT, name)
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print("  saved", path)


# =============================================================================
def exp1_detector(db):
    print("\nExperiment 1: detection agent on realistic packs")
    det = Detector(db, alerts={})
    rng = random.Random(7)
    rows = P.basket_products(db)
    today = dt.date(2026, 11, 20)
    n = 100 if QUICK else 400
    records = []
    for mode in ("camera only", "camera + user confirms"):
        for noise in (0.0, 0.02, 0.05, 0.10):
            for q in P.QUALITIES:
                flagged = 0
                for _ in range(n):
                    pack = P.make_pack(db, rng.choice(rows), q, today, rng, has_qr=rng.random() < 0.5,
                                       price_factor=1.0 if q in ("genuine", "substandard") else rng.uniform(0.45, 0.9))
                    pack["text"] = P.ocr_noise(pack["text"], noise, rng)
                    if mode != "camera only":
                        P.confirm(pack)
                    v = det.check(pack, with_alternatives=False)["verdict"]["key"]
                    flagged += v in ("fake", "suspicious", "expired")
                records.append({"mode": mode, "OCR error rate": noise, "pack": q,
                                "flagged (%)": round(100 * flagged / n, 1), "n": n})
    df = pd.DataFrame(records)
    df.to_csv(os.path.join(OUT, "exp1_detector.csv"), index=False)
    labels = ["genuine\n(= false alarm)", "substandard", "crude fake", "copied-QR\nfake", "perfect\nclone"]
    fig, axes = plt.subplots(1, 2, figsize=(12, 4), sharey=True)
    for ax, mode in zip(axes, ("camera only", "camera + user confirms")):
        table = df[df["mode"] == mode].pivot(index="pack", columns="OCR error rate", values="flagged (%)").loc[P.QUALITIES]
        print(f"  {mode}:\n" + table.to_string())
        width = 0.2
        for k, noise in enumerate(table.columns):
            ax.bar([i + (k - 1.5) * width for i in range(len(table))], table[noise], width,
                   label=f"{int(noise * 100)}% characters misread", color=COLORS[k])
        ax.set_xticks(range(len(table)), labels, fontsize=8)
        ax.set_title(mode)
        ax.spines[["top", "right"]].set_visible(False)
    axes[0].set_ylabel("packs flagged (%)")
    axes[1].legend(frameon=False, fontsize=8)
    fig.suptitle(f"Experiment 1 - what the phone agent catches ({n} packs per bar, built from the real dataset)")
    save(fig, "exp1_detector.png")
    return df


# =============================================================================
def run(db, days=DAYS, **params):
    m = MediGuardModel(db=db, **params)
    for _ in range(days):
        m.step()
    return m


def exp2_adoption(db):
    print("\nExperiment 2: share of people using the app")
    levels = [0, 0.25, 0.5, 0.75, 1.0] if QUICK else [0, 0.1, 0.25, 0.5, 0.75, 1.0]
    records = []
    for sc in SCENARIOS:
        for a in levels:
            for seed in range(SEEDS):
                s = run(db, scenario=sc, app_adoption=a, seed=seed).summary()
                records.append({"scenario": sc, "app adoption": a, "seed": seed, **s})
            print(f"  {sc:34s} adoption {a:.2f} done")
    df = pd.DataFrame(records)
    df.to_csv(os.path.join(OUT, "exp2_adoption_runs.csv"), index=False)
    agg = df.groupby(["scenario", "app adoption"])[["S&F taken (%)", "Harm per 1000 doses", "Caught by app (%)",
                                                     "False alarms (%)"]].agg(["mean", "std"]).round(3)
    agg.to_csv(os.path.join(OUT, "exp2_adoption_summary.csv"))
    print(agg.to_string())

    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    for k, sc in enumerate(SCENARIOS):
        g = df[df.scenario == sc].groupby("app adoption")
        for ax, col in zip(axes, ["S&F taken (%)", "Harm per 1000 doses"]):
            mean, std = g[col].mean(), g[col].std().fillna(0)
            ax.plot(mean.index * 100, mean, marker="o", color=COLORS[k], label=sc)
            ax.fill_between(mean.index * 100, mean - std, mean + std, color=COLORS[k], alpha=0.12)
    for ax, col in zip(axes, ["Bad medicine actually taken (%)", "Harm events per 1000 doses"]):
        ax.set_xlabel("people using the MediGuard app (%)")
        ax.set_ylabel(col)
        ax.spines[["top", "right"]].set_visible(False)
    axes[0].legend(frameon=False, fontsize=8)
    fig.suptitle(f"Experiment 2 - effect of app adoption (mean ± sd of {SEEDS} runs, {DAYS} days)")
    save(fig, "exp2_adoption.png")
    return df


def exp3_arms_race(db):
    print("\nExperiment 3: arms race")
    frames = []
    for adaptive in (True, False):
        for seed in range(SEEDS):
            m = run(db, scenario="LMIC average (WHO 2017)", app_adoption=0.75, adaptive=adaptive, seed=seed,
                    days=DAYS * 2)
            d = m.datacollector.get_model_vars_dataframe()
            d["day"], d["adaptive"], d["seed"] = d.index, adaptive, seed
            frames.append(d)
    df = pd.concat(frames)
    df.to_csv(os.path.join(OUT, "exp3_arms_race.csv"), index=False)
    ad = df[df.adaptive].groupby("day").mean(numeric_only=True)
    fixed = df[~df.adaptive].groupby("day").mean(numeric_only=True)

    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    for k, col in enumerate(["Crude fakes (%)", "Copied-QR fakes (%)", "Perfect clones (%)"]):
        axes[0].plot(ad.index, ad[col], color=COLORS[k], label=col.replace(" (%)", ""))
    axes[0].set_ylabel("share of the counterfeiters' production (%)")
    axes[0].set_title("Counterfeiters adapt to the app")
    axes[1].plot(ad.index, ad["Caught by app (%)"], color=COLORS[3], label="adaptive counterfeiters")
    axes[1].plot(fixed.index, fixed["Caught by app (%)"], color=COLORS[0], ls="--", label="counterfeiters that don't adapt")
    axes[1].set_ylabel("bad packs caught by the app, last 30 days (%)")
    axes[1].set_title("So the app catches less over time")
    for ax in axes:
        ax.set_xlabel("day")
        ax.legend(frameon=False, fontsize=8)
        ax.spines[["top", "right"]].set_visible(False)
    fig.suptitle("Experiment 3 - arms race (WHO 2017 scenario, 75% of people use the app)")
    save(fig, "exp3_arms_race.png")
    print(f"  day {int(ad.index[-1])}: perfect clones {ad['Perfect clones (%)'].iloc[-1]:.0f}% of production, "
          f"app catch rate {ad['Caught by app (%)'].iloc[-60:].mean():.0f}% (adaptive) vs "
          f"{fixed['Caught by app (%)'].iloc[-60:].mean():.0f}% (not adaptive)")
    return df


def exp4_policies(db):
    print("\nExperiment 4: policies")
    policies = {
        "Nothing (no app,\nroutine inspection)": dict(app_adoption=0.0, intelligence_led=False),
        "Inspectors use\nreports only": dict(app_adoption=0.0, intelligence_led=True),
        "App only (50%)": dict(app_adoption=0.5, intelligence_led=False, report_prob=0.0),
        "App + reports +\nled inspection": dict(app_adoption=0.5, intelligence_led=True),
        "App + reports +\n2 inspectors": dict(app_adoption=0.5, intelligence_led=True, n_inspectors=2),
    }
    records = []
    for name, p in policies.items():
        for seed in range(SEEDS):
            s = run(db, scenario="LMIC average (WHO 2017)", seed=seed, **p).summary()
            records.append({"policy": name.replace("\n", " "), **s})
    df = pd.DataFrame(records)
    df.to_csv(os.path.join(OUT, "exp4_policies.csv"), index=False)
    agg = df.groupby("policy", sort=False)[["S&F taken (%)", "Harm per 1000 doses", "Shops closed"]].agg(["mean", "std"]).round(2)
    print(agg.to_string())

    fig, ax = plt.subplots(figsize=(9, 4))
    mean = df.groupby("policy", sort=False)["S&F taken (%)"].mean()
    std = df.groupby("policy", sort=False)["S&F taken (%)"].std()
    ax.bar(range(len(mean)), mean, yerr=std, color=COLORS[0], capsize=4)
    ax.set_xticks(range(len(mean)), list(policies.keys()), fontsize=8)
    ax.set_ylabel("bad medicine actually taken (%)")
    ax.set_title("Experiment 4 - policies (WHO 2017 scenario)")
    ax.spines[["top", "right"]].set_visible(False)
    save(fig, "exp4_policies.png")
    return df


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    t0 = time.time()
    database = D.load()
    print(f"Dataset: {len(database):,} medicines")
    exp1_detector(database)
    exp2_adoption(database)
    exp3_arms_race(database)
    exp4_policies(database)
    print(f"\nAll done in {time.time() - t0:.0f} s. Results are in {OUT}")
