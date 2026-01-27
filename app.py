import os
import json
import time
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS
from psycopg2.extras import RealDictCursor
import psycopg2

# --------------------
# Configuration
# --------------------
DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL environment variable is required!")

MPESA_API_URL = os.environ.get("MPESA_API_URL", "")
MPESA_SHORTCODE = os.environ.get("MPESA_SHORTCODE", "")
TWILIO_WHATSAPP_REPLY_NUMBER = os.environ.get("TWILIO_WHATSAPP_REPLY_NUMBER", "")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "")
TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID", "")

# --------------------
# App initialization
# --------------------
app = Flask(__name__)
CORS(app)

# --------------------
# Database helpers
# --------------------
def get_db():
    try:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        print("[DB] Connected successfully")
        return conn
    except Exception as e:
        print("[DB ERROR]", e)
        raise

def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS orders (
        id TEXT PRIMARY KEY,
        customer_name TEXT,
        phone TEXT,
        amount TEXT,
        status TEXT,
        mpesa_receipt TEXT,
        created_at TIMESTAMP DEFAULT now(),
        paid_at TIMESTAMP
    )
    """)
    conn.commit()
    cur.close()
    conn.close()
    print("[DB] Initialized")

# --------------------
# Utility functions
# --------------------
def log(msg, *args):
    print(f"[LOG] {msg}", *args)

def normalize_phone(phone):
    phone = phone.strip()
    if phone.startswith("whatsapp:"):
        phone = phone.replace("whatsapp:", "")
    if phone.startswith("0"):
        phone = "+254" + phone[1:]
    return phone

# --------------------
# Routes
# --------------------
@app.route("/orders", methods=["GET"])
def get_orders():
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT * FROM orders ORDER BY created_at DESC")
        orders = cur.fetchall()
        cur.close()
        conn.close()
        return jsonify({"status": "ok", "orders": orders})
    except Exception as e:
        log("Failed to fetch orders:", e)
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/webhook/whatsapp", methods=["POST"])
def whatsapp_webhook():
    data = request.form.to_dict() if request.form else request.json
    log("Incoming WhatsApp webhook:", data)

    from_number = data.get("From") or data.get("from")
    body = data.get("Body") or data.get("body")
    log("From:", from_number, "Message:", body)

    # Echo back message for diagnostics
    response_message = f"Received your message: {body}"
    send_whatsapp_message(from_number, response_message)

    return "OK", 200

# --------------------
# WhatsApp send helper
# --------------------
def send_whatsapp_message(to, message):
    log(f"Sending WhatsApp message to {to}: {message}")
    try:
        url = f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_ACCOUNT_SID}/Messages.json"
        data = {
            "From": f"whatsapp:{TWILIO_WHATSAPP_REPLY_NUMBER}",
            "To": to,
            "Body": message
        }
        r = requests.post(url, data=data, auth=(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN))
        log("Twilio response:", r.status_code, r.text)
    except Exception as e:
        log("Failed to send WhatsApp message:", e)

# --------------------
# MPESA STK simulation (diagnostics)
# --------------------
@app.route("/mpesa/test", methods=["POST"])
def mpesa_test():
    data = request.json
    log("STK Test request received:", data)
    return jsonify({"status": "ok", "message": "STK request logged"}), 200

# --------------------
# Run app
# --------------------
if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
