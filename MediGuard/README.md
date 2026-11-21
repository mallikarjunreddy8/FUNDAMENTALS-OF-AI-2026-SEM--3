# 💊 MediGuard – Fake Medicine Detection with AI Agents

**Social problem.** WHO estimates that at least **1 in 10 medicines in low- and middle-income countries is
substandard or falsified** (S&F). A meta-analysis of 96 studies puts it at **13.6 %** (Ozawa et al., 2018). In India,
the National Drug Survey 2014-16 found **3.16 %** of retail samples not of standard quality and **0.0245 %** spurious.
Patients cannot see the difference, and fakes cause treatment failure, drug resistance and death.

**What MediGuard is.** A practical system with three parts, all built on one AI agent:

| Part | What it does | Tech |
|---|---|---|
| 📱 **Phone app** (`web/`) | Scan a strip: barcode / QR / GS1 DataMatrix + OCR of the print. The agent gives a verdict with reasons, reads it aloud, and suggests cheaper medicines with the **same composition**. Works offline. | HTML/JS, html5-qrcode, tesseract.js |
| 🧠 **Detection agent** (`mediguard/detector.py`) | Rule-based expert agent (perceive → reason → decide → act) checked against the **real 253,973-medicine dataset of India**: lookalike names, wrong maker/strength, discontinued brands, price below MRP, drug-alert batches, GS1 check digits, QR-vs-print mismatch, impossible dates. | Python, pandas, rapidfuzz |
| 🏙 **Town simulation** (`mediguard/model.py`) | **Mesa agent-based model**: patients, pharmacies, adaptive counterfeiters and drug inspectors. Every app scan runs the real detection agent. Answers: *how much bad medicine is avoided if X % of people use the app, and how do counterfeiters react?* | Mesa 3, Solara |

## Results (from `python experiments.py`, 5 runs × 180 days per point)

| Finding | Number |
|---|---|
| Crude fakes caught by the agent | **100 %** (93–99 % from the camera alone with 2–10 % misread characters) |
| False alarms on genuine packs (2 % of characters misread, user confirms details) | **3.5 %** (14 % if the user does not confirm) |
| Bad medicine actually taken, WHO 2017 scenario, 0 % → 100 % app use | **9.6 % → 6.3 %** (−35 %) |
| Harm per 1000 doses, same scenario | **38.9 → 24.5** (−37 %) |
| Best policy: app + patient reports + intelligence-led inspection (2 inspectors) | **10.3 % → 6.4 %** bad medicine taken |
| Arms race: counterfeiters move to perfect clones | **15 % → 100 %** of their production in ~140 days; app catch rate 62 % vs 85 % against non-adapting fakers |
| More medicines with a QR code (0 % → 100 %) | copied-QR fakes caught **33 % → 99 %**, false alarms 9 % → 6.4 % |

"5 runs × 180 days" means: every setting is simulated 5 times with different random **seeds** (each seed is one
possible, repeatable version of events), for **180 simulated days** (one step = one day), and we report the average.

Charts and CSV files are in `results/`. The full write-up with the literature review is in **`docs/REPORT.md`**.

## Try it now

**Phone app online:** https://claude.ai/artifact/5dNFNZHivyVE1jb2kGUUXM. Open it on your phone, tap
"Take a photo of the strip / box", or press a demo button. This online version uses the built-in list of 61 medicines
and works without the PC. For the full 253,973-medicine check, run `server.py` (below).

## Android app (APK) with automatic update roll-out

Download the newest **`MediGuard-1.0.N.apk`** from the repository's
[Releases page](https://github.com/mallikarjunreddy8/FUNDAMENTALS-OF-AI-2026-SEM--3/releases/latest) on your Android
phone, open it and allow installing from this source.

How updates roll out:

1. Every push that changes `MediGuard/web/` or `MediGuard/android-app/` runs the GitHub workflow
   `.github/workflows/mediguard-android.yml`. It runs the tests, builds the APK and publishes it as a new release
   (`v1.0.<build number>`).
2. When the app starts it asks GitHub for the latest release. If that is newer than the installed version, it shows
   **"Update available"**. Tapping **Update** downloads the new APK, and Android installs it over the old one.

Inside the app: photo scan, live barcode / QR scanning with the camera, offline text reading, manual check,
same-composition finder.

**Signing key (needed once for smooth updates).** Android only installs an update over the old app if both are
signed with the same key. The key is never stored in git. Add two repository secrets (Settings → Secrets and
variables → Actions → New repository secret):

| Secret | Value |
|---|---|
| `MEDIGUARD_KEYSTORE_BASE64` | the keystore file, base64-encoded |
| `MEDIGUARD_KEYSTORE_PASSWORD` | its password (key alias `mediguard`) |

Make a key with:
`keytool -genkeypair -keystore mediguard.keystore -alias mediguard -keyalg RSA -keysize 2048 -validity 10000`,
then `base64 -w0 mediguard.keystore`. Until the secrets exist, builds use a temporary debug key, and moving to the
real key needs one uninstall. Keep the keystore file safe: without it you cannot publish updates.

Build it yourself: `cd android-app && npm install && APP_VERSION=1.0.0 node scripts/build-www.js && npx cap sync android`,
then open `android-app/android` in Android Studio.

## Run it (Windows)

Double-click **`run.bat`**. The first time it makes a `venv`, installs the packages and downloads the dataset
(32 MB). Then choose:

1. **Phone app + full database** → http://localhost:8000 (try the demo buttons)
2. **Town simulation dashboard** → http://localhost:8765 (press ▶, move the sliders, Reset)
3. **Run all experiments** → `results/` (about 6 minutes)
4. **Run the tests**

Any OS, in a terminal:

```bash
pip install -r requirements.txt
python -m mediguard.dataset --download   # gets the dataset into data/
python server.py                         # phone app + API      http://localhost:8000
solara run sim_app.py                    # simulation dashboard http://localhost:8765
python experiments.py                    # all experiments -> results/   (--quick for a short run)
python -m pytest -q tests                # 25 Python tests
node web/test/agent.test.js              # 17 tests of the offline phone agent
```

**On a phone:** open `http://<your-PC-IP>:8000` on the same Wi-Fi. The 📷 photo button works everywhere;
the live camera needs `https` (for example GitHub Pages: `https://<user>.github.io/<repo>/MediGuard/web/`, which runs
the offline agent with the built-in list of 61 medicines).

## How the agent decides

```
PERCEIVE                         REASON (rule -> evidence + weight)                    DECIDE        ACT
camera OCR text  ─┐   1 name: exact / lookalike (1-2 letters off a real brand) / unknown   risk = Σ w     verdict + reasons
barcode / QR /   ─┼─► 2 discontinued in the dataset           3 strength matches salts ─► ≥60 fake    alternatives (same
GS1 DataMatrix    │   4 maker matches                           5 price vs MRP              ≥30 or one   salts, strength,
typed details    ─┤   6 batch on CDSCO alert list             7 dates (expired, future)      strong flag  form; cheapest)
what user noticed┘    8 GS1 check digit, QR vs print agree    9 seal / print / seller        = suspicious report: PvPI 1800-180-3024
```

It never says "Genuine" – only a lab can prove that – its best verdict is **"No red flags found"**.

## Files

```
MediGuard/
├── mediguard/
│   ├── dataset.py     loads + indexes the 253,973 medicines (brand index, composition index)
│   ├── detector.py    the detection agent (Python)
│   ├── packs.py       builds realistic genuine / substandard / fake packs from real products
│   ├── agents.py      Mesa agents: Patient, Pharmacy, Counterfeiter, Inspector
│   └── model.py       Mesa model + research scenarios (WHO, Ozawa, NDS India)
├── sim_app.py         Solara dashboard for the simulation
├── server.py          Flask: serves the phone app + /api/check, /api/alternatives, /api/search
├── experiments.py     the 5 experiments -> results/
├── web/               phone app (offline agent in agent.js, 61 medicines built in)
├── data/drug_alerts.csv   drug alert list (SAMPLE rows: replace with CDSCO's monthly list)
├── tests/             pytest
├── results/           charts + CSV
└── docs/REPORT.md     report: problem, literature, dataset, method, results, limits, references
```

## Dataset

**A-Z Medicine Dataset of India** (Shudhanshu Singh, Kaggle): 253,973 medicines, 7,648 manufacturers, price,
pack size, discontinued flag, composition. It is not stored in git; `python -m mediguard.dataset --download` fetches
a public copy, or download it from
[Kaggle](https://www.kaggle.com/datasets/shudhanshusingh/az-medicine-dataset-of-india) into `data/`.

## Important

MediGuard is a screening tool for a college project, not a lab test or medical advice. Always buy from licensed
pharmacies, keep the bill and ask a doctor or pharmacist before switching medicines. Report suspected fakes to the
**PvPI helpline 1800-180-3024** or your State Drug Controller / CDSCO.
