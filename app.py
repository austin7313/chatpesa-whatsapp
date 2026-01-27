import os
import uuid
import logging
from datetime import datetime

import psycopg2
from psycopg2.extras import RealDictCursor
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS
from twilio.twiml.messaging_response import MessagingResponse

# ---------------- CONFIG ----------------

logging.basicConfig(level=logging.INFO)

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is required")

MPESA_CALLBACK_URL = os.getenv("MPESA_CALLBACK_URL")  # set in Render
MPESA_STK_URL = os.getenv("MPESA_STK_URL")            # your STK endpoint
MPESA_TOKEN = os.getenv("MPESA_TOKEN")                # bearer token

# ---------------- APP ----------------

app = Flask(__name__)
CORS(app)

# ---------------- DB ----------------

def get_db():
    return psycopg2.connect(
        DATABASE_URL,
        cursor_factory=RealDictCursor,
        sslmode="require"
    )

def init_db():
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS orders (
                    id TEXT PRIMARY KEY,
                    phone TEXT,
                    customer_name TEXT,
                    amount INTEGER,
                    status TEXT,
                    mpesa_receipt TEXT,
                    created_at TIMESTAMP,
                    paid_at TIMESTAMP
                );
            """)
        conn.commit()

init_db()

# ---------------- HELPERS ----------------

def normalize_phone(phone: str) -> str:
    phone = phone.replace("whatsapp:", "").replace(" ", "")
    if phone.startswith("+"):
        return phone
    if phone.startswith("0"):
        return "+254" + phone[1:]
    return "+254" + phone

# ---------------- WHATSAPP ----------------

@app.route("/whatsapp", methods=["POST"])
def whatsapp_webhook():
    body = request.form.get("Body", "").strip()
    from_phone = normalize_phone(request.form.get("From", ""))

    resp = MessagingResponse()
    msg = resp.message()

    msg.body(
        "👋 Hi!\n\n"
        "Your payment request has been received.\n"
        "📲 Please check your phone to complete the M-Pesa prompt."
    )

    return str(resp)

# ---------------- CREATE ORDER ----------------

@app.route("/pay", methods=["POST"])
def create_payment():
    data = request.json
    phone = normalize_phone(data["phone"])
    amount = int(data["amount"])
    name = data.get("name", "Customer")

    order_id = "CP" + uuid.uuid4().hex[:6].upper()

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO orders
                (id, phone, customer_name, amount, status, created_at)
                VALUES (%s,%s,%s,%s,'PENDING',%s)
            """, (
                order_id,
                phone,
                name,
                amount,
                datetime.utcnow()
            ))
        conn.commit()

    # Trigger STK
    requests.post(
        MPESA_STK_URL,
        headers={"Authorization": f"Bearer {MPESA_TOKEN}"},
        json={
            "phone": phone,
            "amount": amount,
            "reference": order_id,
            "callback_url": MPESA_CALLBACK_URL
        },
        timeout=10
    )

    return jsonify({"status": "ok", "order_id": order_id})

# ---------------- MPESA CALLBACK ----------------

@app.route("/mpesa/callback", methods=["POST"])
def mpesa_callback():
    data = request.json

    result = data.get("Body", {}).get("stkCallback", {})
    code = result.get("ResultCode")
    meta = result.get("CallbackMetadata", {}).get("Item", [])

    order_id = next((i["Value"] for i in meta if i["Name"] == "AccountReference"), None)
    receipt = next((i["Value"] for i in meta if i["Name"] == "MpesaReceiptNumber"), None)

    if not order_id:
        return jsonify({"status": "ignored"})

    with get_db() as conn:
        with conn.cursor() as cur:
            if code == 0:
                cur.execute("""
                    UPDATE orders
                    SET status='PAID', mpesa_receipt=%s, paid_at=%s
                    WHERE id=%s
                """, (receipt, datetime.utcnow(), order_id))
            else:
                cur.execute("""
                    UPDATE orders
                    SET status='FAILED'
                    WHERE id=%s
                """, (order_id,))
        conn.commit()

    return jsonify({"status": "ok"})

# ---------------- DASHBOARD ----------------

@app.route("/orders", methods=["GET"])
def list_orders():
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM orders ORDER BY created_at DESC")
            rows = cur.fetchall()
    return jsonify({"status": "ok", "orders": rows})

# ---------------- RUN ----------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
