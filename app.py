import os
import json
import base64
import logging
import requests
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from twilio.twiml.messaging_response import MessagingResponse

# ------------------------------------------------------------------
# BASIC APP SETUP
# ------------------------------------------------------------------

app = Flask(__name__, static_folder=None)
CORS(app)
logging.basicConfig(level=logging.INFO)

PORT = int(os.environ.get("PORT", 5000))

# ------------------------------------------------------------------
# ENVIRONMENT VARIABLES (SAFE READ)
# ------------------------------------------------------------------

def must_get(key):
    val = os.environ.get(key)
    if not val:
        logging.error(f"❌ Missing environment variable: {key}")
        raise RuntimeError(f"Missing environment variable: {key}")
    return val

DATABASE_URL = must_get("DATABASE_URL")

MPESA_SHORTCODE = must_get("MPESA_SHORTCODE")
MPESA_PASSKEY = must_get("MPESA_PASSKEY")
MPESA_CONSUMER_KEY = must_get("MPESA_CONSUMER_KEY")
MPESA_CONSUMER_SECRET = must_get("MPESA_CONSUMER_SECRET")
MPESA_CALLBACK_URL = must_get("MPESA_CALLBACK_URL")
MPESA_BASE = "https://api.safaricom.co.ke"

TWILIO_SID = must_get("TWILIO_SID")
TWILIO_AUTH = must_get("TWILIO_AUTH")
TWILIO_WHATSAPP_NUMBER = must_get("TWILIO_WHATSAPP_NUMBER")

# ------------------------------------------------------------------
# DATABASE
# ------------------------------------------------------------------

def get_db():
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)

def init_db():
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS orders (
                    id TEXT PRIMARY KEY,
                    customer_name TEXT,
                    phone TEXT,
                    amount INTEGER,
                    status TEXT,
                    mpesa_receipt TEXT,
                    created_at TIMESTAMP,
                    paid_at TIMESTAMP
                )
            """)
        conn.commit()
    logging.info("✅ Database ready")

# ------------------------------------------------------------------
# HELPERS
# ------------------------------------------------------------------

def normalize_phone(phone):
    phone = phone.replace("whatsapp:", "").replace(" ", "")
    if phone.startswith("0"):
        phone = "254" + phone[1:]
    if phone.startswith("+"):
        phone = phone[1:]
    return phone

def mpesa_access_token():
    auth = base64.b64encode(
        f"{MPESA_CONSUMER_KEY}:{MPESA_CONSUMER_SECRET}".encode()
    ).decode()

    r = requests.get(
        f"{MPESA_BASE}/oauth/v1/generate?grant_type=client_credentials",
        headers={"Authorization": f"Basic {auth}"}
    )
    r.raise_for_status()
    return r.json()["access_token"]

# ------------------------------------------------------------------
# MPESA STK PUSH
# ------------------------------------------------------------------

def send_stk_push(phone, amount, order_id):
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    password = base64.b64encode(
        f"{MPESA_SHORTCODE}{MPESA_PASSKEY}{timestamp}".encode()
    ).decode()

    payload = {
        "BusinessShortCode": MPESA_SHORTCODE,
        "Password": password,
        "Timestamp": timestamp,
        "TransactionType": "CustomerPayBillOnline",
        "Amount": amount,
        "PartyA": phone,
        "PartyB": MPESA_SHORTCODE,
        "PhoneNumber": phone,
        "CallBackURL": MPESA_CALLBACK_URL,
        "AccountReference": order_id,
        "TransactionDesc": f"Payment {order_id}"
    }

    token = mpesa_access_token()

    r = requests.post(
        f"{MPESA_BASE}/mpesa/stkpush/v1/processrequest",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        },
        json=payload,
        timeout=20
    )

    logging.info(f"📲 STK response: {r.text}")
    return r.json()

# ------------------------------------------------------------------
# WHATSAPP WEBHOOK
# ------------------------------------------------------------------

@app.route("/webhook/whatsapp", methods=["POST"])
def whatsapp_webhook():
    incoming = request.values.get("Body", "").strip().lower()
    sender = request.values.get("From", "")
    phone = normalize_phone(sender)

    resp = MessagingResponse()
    msg = resp.message()

    if incoming.isdigit():
        amount = int(incoming)
        order_id = f"CP{datetime.now().strftime('%H%M%S%f')[:8]}"

        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO orders
                    (id, customer_name, phone, amount, status, created_at)
                    VALUES (%s,%s,%s,%s,%s,%s)
                """, (
                    order_id,
                    "WhatsApp User",
                    f"whatsapp:+{phone}",
                    amount,
                    "PENDING",
                    datetime.utcnow()
                ))
            conn.commit()

        send_stk_push(phone, amount, order_id)
        msg.body(f"📲 Payment request sent.\nEnter your M-Pesa PIN to pay KES {amount}.")
    else:
        msg.body("Send the amount (e.g. 100) to pay via M-Pesa.")

    return str(resp)

# ------------------------------------------------------------------
# MPESA CALLBACK
# ------------------------------------------------------------------

@app.route("/mpesa/callback", methods=["POST"])
def mpesa_callback():
    data = request.json
    logging.info(f"💰 MPESA CALLBACK: {json.dumps(data)}")

    try:
        stk = data["Body"]["stkCallback"]
        if stk["ResultCode"] != 0:
            return jsonify({"status": "failed"})

        meta = stk["CallbackMetadata"]["Item"]
        receipt = next(i["Value"] for i in meta if i["Name"] == "MpesaReceiptNumber")
        amount = int(next(i["Value"] for i in meta if i["Name"] == "Amount"))

        order_id = stk["CheckoutRequestID"]

        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE orders
                    SET status='PAID',
                        mpesa_receipt=%s,
                        paid_at=%s
                    WHERE amount=%s AND status='PENDING'
                    ORDER BY created_at DESC
                    LIMIT 1
                """, (receipt, datetime.utcnow(), amount))
            conn.commit()

        return jsonify({"status": "ok"})
    except Exception as e:
        logging.exception("❌ Callback error")
        return jsonify({"error": str(e)}), 500

# ------------------------------------------------------------------
# ORDERS API (DASHBOARD)
# ------------------------------------------------------------------

@app.route("/orders")
def orders():
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM orders ORDER BY created_at DESC")
            rows = cur.fetchall()
    return jsonify({"status": "ok", "orders": rows})

# ------------------------------------------------------------------
# SERVE REACT DASHBOARD
# ------------------------------------------------------------------

@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def serve_dashboard(path):
    build_dir = os.path.join("dashboard", "build")
    if path and os.path.exists(os.path.join(build_dir, path)):
        return send_from_directory(build_dir, path)
    return send_from_directory(build_dir, "index.html")

# ------------------------------------------------------------------
# STARTUP
# ------------------------------------------------------------------

if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=PORT)
