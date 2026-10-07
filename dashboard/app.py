import os
import sys

from flask import Flask, jsonify, render_template, request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "server"))
from database import connect  # noqa: E402

app = Flask(__name__)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/dashboard")
def dashboard():
    return render_template("index.html")


@app.route("/api/status") #si un appareil a parlé récemment, utile pour un badge « en ligne / hors ligne
def status():
    conn = connect()
    row = conn.execute(
        "SELECT ts, device FROM readings ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conn.close()
    return jsonify({
        "online": row is not None,
        "last_device": row["device"] if row else None,
        "last_seen": row["ts"] if row else None,
    })


@app.route("/api/sensors") #la dernière mesure de chaque appareil
def sensors():
    conn = connect()
    rows = conn.execute(
        """
        SELECT device, ts, temperature, humidity, gas, presence, distance
        FROM readings
        WHERE id IN (SELECT MAX(id) FROM readings GROUP BY device)
        ORDER BY device
        """
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/api/alerts") #branchés sur la table alerts. Ça débloque déjà l'équipe dashboard pour coder l'écran des alertes.
def alerts():
    conn = connect()
    rows = conn.execute(
        "SELECT * FROM alerts ORDER BY id DESC LIMIT 50"
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/api/alert/ack", methods=["POST"])
def ack_alert():
    alert_id = request.json.get("id")
    conn = connect()
    with conn:
        conn.execute("UPDATE alerts SET acknowledged = 1 WHERE id = ?", (alert_id,))
    conn.close()
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5050, debug=True)