from flask import Flask, jsonify, request
from flask_cors import CORS
import os
from datetime import datetime

app = Flask(__name__)

# ✅ Allow ALL origins (dashboard, localhost, vercel)
CORS(app, resources={r"/*": {"origins": "*"}})

# -------------------------
# HEALTH CHECK (CRITICAL)
# -------------------------
@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "ok"
    }), 200

# -------------------------
# ROOT (OPTIONAL)
# -------------------------
@app.route("/", methods=["GET"])
def root():
    return jsonify({
        "service": "ChatPesa Backend",
        "status": "online",
        "timestamp": datetime.utcnow().isoformat()
    })

# -------------------------
# ORDERS (MOCK SAFE)
# -------------------------
@app.route("/orders", methods=["GET"])
def orders():
    return jsonify([]), 200

# -------------------------
# DIAGNOSTICS (KEEP)
# -------------------------
@app.route("/diagnostics", methods=["GET"])
def diagnostics():
    return jsonify({
        "service": "ChatPesa Backend",
        "status": "online",
        "timestamp": datetime.utcnow().isoformat(),
        "environment": {
            "DATABASE_URL": bool(os.getenv("DATABASE_URL")),
            "TWILIO_ACCOUNT_SID": bool(os.getenv("TWILIO_ACCOUNT_SID")),
            "TWILIO_AUTH_TOKEN": bool(os.getenv("TWILIO_AUTH_TOKEN")),
            "TWILIO_WHATSAPP_NUMBER": bool(os.getenv("TWILIO_WHATSAPP_NUMBER")),
        }
    })

# -------------------------
# WHATSAPP WEBHOOK (STUB)
# -------------------------
@app.route("/webhook/whatsapp", methods=["POST"])
def whatsapp_webhook():
    return "OK", 200

# -------------------------
# RUN
# -------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
