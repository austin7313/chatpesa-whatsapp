import os
import json
from datetime import datetime
from flask import Flask, request, jsonify
from flask_cors import CORS
import psycopg2
from psycopg2.extras import RealDictCursor
from twilio.rest import Client
import requests

# =======================
# Environment variables
# =======================
DATABASE_URL = os.environ.get("DATABASE_URL")
TWILIO_SID = os.environ.get("TWILIO_SID")
TWILIO_AUTH = os.environ.get("TWILIO_AUTH")
TWILIO_WHATSAPP_NUMBER = os.environ.get("TWILIO_WHATSAPP_NUMBER")

MPESA_CONSUMER_KEY = os.environ.get("MPESA_CONSUMER_KEY")
MPESA_CONSUMER_SECRET = os.environ.get("MPESA_CONSUMER_SECRET")
MPESA_SHORTCODE = os.environ.get("MPESA_SHORTCODE")
MPESA_PASSKEY = os.environ.get("MPESA_PASSKEY")
MPESA_CALLBACK_URL = os.environ.get("MPESA_CALLBACK_URL")
MPESA_BASE = "https://api.safaricom.co.ke"

# =======================
# Flask & CORS
# =======================
app = Flask(__name__)
CORS(app)

# =======================
# Twilio Client
# =======================
twilio_client = Client(TWILIO_SID, TWILIO_AUTH)

# =======================
# Database helpers
# =======================
def get_db():
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    return conn

def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id TEXT PRIMARY KEY,
            customer_name TEXT,
            phone TEXT,
            amount NUMERIC,
            service_requested TEXT,
            status TEXT,
            mpesa_receipt TEXT,
            created_at TIMESTAMP,
            paid_at TIMESTAMP
        )
    """)
    conn.commit()
    cur.close()
    conn.close()

# =======================
# Normalize phone numbers
# =======================
def normalize_phone(phone):
    phone = phone.replace(" ", "").replace("-", "")
    if phone.startswith("+254"):
        return phone
    elif phone.startswith("0"):
        return "+254" + phone[1:]
    else:
        return phone  # assume already normalized

# =======================
# Routes
# =======================
@app.route("/orders", methods=["GET"])
def get_orders():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM orders ORDER BY created_at DESC")
    orders = cur.fetchall()
    cur.close()
    conn.close()
    return jsonify({"status": "ok", "orders": orders})

@app.route("/webhook/whatsapp", methods=["POST"])
def whatsapp_webhook():
    data = request.form or request.json
    phone = normalize_phone(data.get("From", ""))
    body = data.get("Body", "").lower()

    # Example: Place order via WhatsApp
    if "order" in body:
        order_id = f"CP{int(datetime.utcnow().timestamp())}"
        customer_name = body.split()[1] if len(body.split()) > 1 else "Customer"
        amount = 10  # Example default
        service_requested = "Example item"  # Replace parsing logic if needed
        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO orders (id, customer_name, phone, amount, service_requested, status, created_at) VALUES (%s,%s,%s,%s,%s,%s,%s)",
            (order_id, customer_name, phone, amount, service_requested, "PENDING", datetime.utcnow()),
        )
        conn.commit()
        cur.close()
        conn.close()

        twilio_client.messages.create(
            from_="whatsapp:" + TWILIO_WHATSAPP_NUMBER,
            body=f"Thanks {customer_name}, your order {order_id} has been received. You'll get a payment link shortly.",
            to=phone,
        )
        return jsonify({"status": "ok", "message": "Order received"})

    return jsonify({"status": "ok", "message": "No action taken"})

@app.route("/mpesa/callback", methods=["POST"])
def mpesa_callback():
    data = request.json
    stk_callback = data.get("Body", {}).get("stkCallback", {})

    if stk_callback.get("ResultCode") == 0:  # Payment successful
        checkout_request_id = stk_callback.get("CheckoutRequestID")
        amount = stk_callback.get("CallbackMetadata", {}).get("Item", [{}])[0].get("Value", 0)
        receipt = next((i["Value"] for i in stk_callback.get("CallbackMetadata", {}).get("Item", []) if i["Name"] == "MpesaReceiptNumber"), "")
        phone = normalize_phone(next((i["Value"] for i in stk_callback.get("CallbackMetadata", {}).get("Item", []) if i["Name"] == "PhoneNumber"), ""))

        # Update order in DB
        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            "UPDATE orders SET status=%s, mpesa_receipt=%s, paid_at=%s WHERE phone=%s AND status=%s ORDER BY created_at DESC LIMIT 1",
            ("PAID", receipt, datetime.utcnow(), phone, "PENDING"),
        )
        conn.commit()
        cur.close()
        conn.close()

        # Send WhatsApp confirmation
        twilio_client.messages.create(
            from_="whatsapp:" + TWILIO_WHATSAPP_NUMBER,
            body=f"🎉 Payment received successfully! Receipt: {receipt}. Thank you for your order.",
            to=phone,
        )

    return jsonify({"status": "ok"})

# =======================
# Main
# =======================
if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
