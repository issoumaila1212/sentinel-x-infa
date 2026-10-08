import os
import sys
from datetime import datetime, timezone

from dotenv import load_dotenv
from flask import Flask, g, jsonify, render_template, request, send_from_directory

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(BASE_DIR, "..", "server"))
load_dotenv()  # reads the .env file at the project root

from database import connect, init_db  # noqa: E402
import auth  # noqa: E402
from auth import require_role  # noqa: E402

FRONTEND_DIST = os.path.join(BASE_DIR, "frontend", "dist")
ONLINE_WINDOW_S = 15  # a node is "online" if it sent data in the last 15 seconds

auth.check_config()
app = Flask(__name__, static_folder=None)
app.register_blueprint(auth.bp)


@app.after_request
def security_headers(resp):
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "no-referrer"
    resp.headers["Content-Security-Policy"] = (
        "default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
        "frame-ancestors 'none'"
    )
    if request.path.startswith("/api/"):
        resp.headers["Cache-Control"] = "no-store"
    return resp


@app.route("/api/status") #si un appareil a parlé récemment, utile pour un badge « en ligne / hors ligne
@require_role("user")
def status():
    conn = connect()
    row = conn.execute(
        "SELECT ts, device FROM readings ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conn.close()

    online = False
    age = None
    if row:
        last = datetime.fromisoformat(row["ts"].replace("Z", "+00:00"))
        age = (datetime.now(timezone.utc) - last).total_seconds()
        online = age <= ONLINE_WINDOW_S

    return jsonify({
        "online": online,
        "last_device": row["device"] if row else None,
        "last_seen": row["ts"] if row else None,
        "age_seconds": round(age, 1) if age is not None else None,
    })


@app.route("/api/sensors") #la dernière mesure de chaque appareil
@require_role("user")
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


@app.route("/api/readings") #historique pour les graphiques : /api/readings?device=node1&limit=60
@require_role("user")
def readings():
    device = request.args.get("device")
    limit = max(1, min(request.args.get("limit", default=60, type=int), 1000))

    query = "SELECT ts, device, temperature, humidity, gas, presence, distance FROM readings"
    params = []
    if device:
        query += " WHERE device = ?"
        params.append(device)
    query += " ORDER BY id DESC LIMIT ?"
    params.append(limit)

    conn = connect()
    rows = conn.execute(query, params).fetchall()
    conn.close()
    # newest first in SQL, returned oldest first so charts can use it directly
    return jsonify([dict(r) for r in reversed(rows)])


@app.route("/api/alerts") #branchés sur la table alerts. Ça débloque déjà l'équipe dashboard pour coder l'écran des alertes.
@require_role("user")
def alerts():
    conn = connect()
    rows = conn.execute(
        "SELECT * FROM alerts ORDER BY id DESC LIMIT 50"
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/api/alert/ack", methods=["POST"])
@require_role("admin")
def ack_alert():
    alert_id = (request.get_json(silent=True) or {}).get("id")
    conn = connect()
    with conn:
        conn.execute("UPDATE alerts SET acknowledged = 1 WHERE id = ?", (alert_id,))
    conn.close()
    auth.audit("alert_ack", g.user["username"], True, f"alert {alert_id}")
    return jsonify({"status": "ok"})


# Serves the built React app (npm run build). Any non-API path returns index.html (client-side routing).
@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def frontend(path):
    if path.startswith("api/"):
        return jsonify(error="Not found"), 404
    if os.path.isdir(FRONTEND_DIST):
        if path and os.path.isfile(os.path.join(FRONTEND_DIST, path)):
            return send_from_directory(FRONTEND_DIST, path)
        return send_from_directory(FRONTEND_DIST, "index.html")
    return render_template("index.html")  # fallback: the original placeholder page


if __name__ == "__main__":
    init_db()  # makes sure the tables exist even if the MQTT server has not run yet

    # Debug mode exposes an interactive console: only allowed on this PC (127.0.0.1).
    # Turn it on with FLASK_DEBUG=1 in .env while developing; leave it off otherwise.
    debug = os.getenv("FLASK_DEBUG", "0") == "1"
    cert = os.getenv("TLS_CERT", os.path.join(BASE_DIR, "..", "mosquitto", "certs", "server.crt"))
    key = os.getenv("TLS_KEY", os.path.join(BASE_DIR, "..", "mosquitto", "certs", "server.key"))
    if not (os.path.isfile(cert) and os.path.isfile(key)):
        raise SystemExit(f"Certificat TLS introuvable ({cert}). Lance gen_certs.sh d'abord.")

    app.run(
        host="127.0.0.1" if debug else "0.0.0.0",
        port=5050,
        debug=debug,
        ssl_context=(cert, key),
    )
