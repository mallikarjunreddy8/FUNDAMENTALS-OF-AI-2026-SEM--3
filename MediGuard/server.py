"""
MediGuard - web server. Serves the phone app (web/) and lets it use the full dataset.

Run:   python server.py            then open http://localhost:8000  (Windows: run.bat -> option 1)
       On a phone in the same Wi-Fi: http://<your-PC-IP>:8000  (the photo button works;
       the live camera needs https or localhost)

API (JSON):
    POST /api/check          body = what the app collected -> the agent's report
    GET  /api/alternatives?name=Dolo 650
    GET  /api/search?q=dol
    GET  /api/info
"""

import os

from flask import Flask, jsonify, request, send_from_directory

from mediguard import dataset as D
from mediguard.detector import get_detector

WEB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
app = Flask(__name__, static_folder=None)


@app.get("/")
def index():
    return send_from_directory(WEB, "index.html")


@app.get("/<path:path>")
def static_files(path):
    return send_from_directory(WEB, path)


@app.get("/api/info")
def info():
    db = get_detector().db
    return jsonify({"medicines": len(db), "manufacturers": len(db.manufacturers),
                    "dataset": "A-Z Medicine Dataset of India (Kaggle)"})


@app.post("/api/check")
def check():
    body = request.get_json(silent=True) or {}
    report = get_detector().check(body)
    return jsonify(report)


@app.get("/api/alternatives")
def alternatives():
    det = get_detector()
    kind, key, _ = det.identify(request.args.get("name", ""), typed=True)
    if kind != "exact":
        return jsonify({"found": False, "alternatives": []})
    i = det.db.best_row(det.db.rows_for_brand(key))
    r = det.db.row(i)
    return jsonify({"found": True, "medicine": r["name"], "composition": D.composition_text(r["salts"]),
                    "price": float(r["price"]), "pack": r["pack"], "alternatives": det.alternatives(i, "ok", 10)})


@app.get("/api/search")
def search():
    db = get_detector().db
    out = []
    for i in db.search(request.args.get("q", ""), 10):
        r = db.row(i)
        out.append({"brand": r["name"], "composition": D.composition_text(r["salts"]), "company": r["manufacturer"],
                    "price": float(r["price"]), "pack": r["pack"], "discontinued": bool(r["discontinued"])})
    return jsonify(out)


if __name__ == "__main__":
    get_detector()   # load the dataset before the first request
    print("MediGuard is running: open http://localhost:8000  (Ctrl+C to stop)")
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
