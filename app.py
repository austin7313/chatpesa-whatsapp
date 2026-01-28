import os
import json
import requests
from datetime import datetime
from flask import Flask, request, jsonify
from twilio.rest import Client
import psycopg2
from psycopg2.extras import RealDictCursor

app = Flask(__name__)

# ------------------------
# Environment Variables
# ------------------------
DATABASE_URL = os.environ.get("DATABASE_URL")

TWILIO_SID = os.environ.get("TWILIO_SID")
TWILIO_AUTH = os.environ.get("TWILIO_AUTH")
TWILIO_WHATSAPP_NUMBER = os.environ.get("TWILIO_WHATSAPP_NUMBER")

MPESA_SHORTCODE = os.environ.get("MPESA_SHORTCODE")
MPESA_PASSKEY = os.environ.get("MPESA_PASSKEY")
MPESA_CONSUMER_KEY = os.environ.get("MPESA_CONSUMER_KEY")
MPESA_CONSUMER_SECRET = os.environ.get("MPESA_CONSUMER_SECRET")
MPESA_CALLBACK_URL = os.environ.get("MPESA_CALLBACK_URL")
MPESA_BASE = "https://api.safaricom.co.ke"

# Twilio client
twilio_client = Client(TWILIO_SID, TWILIO_AUTH)

# ------------------------
# Database Helper
# ------------------------
def get_db():
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    return conn

def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id SERIAL PRIMARY KEY,
            order_id TEXT UNIQUE,
            customer_name TEXT,
            phone TEXT,
            amount NUMERIC,
            service_requested TEXT,
            status TEXT,
            mpesa_receipt TEXT,
            created_at TIMESTAMP DEFAULT NOW(),
            paid_at TIMESTAMP
        );
    """)
    conn.commit()
    cur.close()
    conn.close()

# ------------------------
# Logging
# ------------------------
def log(msg, data=None):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if data:
        print(f"{timestamp} | {msg}: {data}")
    else:
        print(f"{timestamp} | {msg}")

# ------------------------
# Helper: Send WhatsApp
# ------------------------
def send_whatsapp(to, body):
    try:
        msg = twilio_client.messages.create(
            body=body,
            from_=f"whatsapp:{TWILIO_WHATSAPP_NUMBER}",
            to=to
        )
        log("📩 WhatsApp sent", {"sid": msg.sid, "to": to})
    except Exception as e:
        log("❌ Failed to send WhatsApp", str(e))

# ------------------------
# Helper: Trigger STK Push
# ------------------------
def trigger_stk(phone, amount, order_id):
    log("💰 Triggering STK Push", {"phone": phone, "amount": amount, "order_id": order_id})
    # Normally: request token → STK push → wait callback
    # For simplicity, we log only here
    return {"status": "success", "note": "STK triggered (mock)"}

# ------------------------
# WhatsApp Webhook
# ------------------------
@app.route("/webhook/whatsapp", methods=["POST"])
def whatsapp_webhook():
    log("✅ Incoming WhatsApp message", request.form.to_dict())
    from_number = request.form.get("From")
    body = request.form.get("Body")
    if not from_number or not body:
        return "Bad Request", 400

    # Parse order from message (simple example: "Order: 2 Vodka, 4 T-shirts")
    service_requested = body.strip()

    # Create unique order ID
    order_id = f"CP{int(datetime.now().timestamp())}"

    # Save to DB
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO orders (order_id, customer_name, phone, amount, service_requested, status)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING id;
    """, (order_id, "WhatsApp User", from_number, 10, service_requested, "PENDING"))
    conn.commit()
    cur.close()
    conn.close()

    # Reply WhatsApp confirming order
    send_whatsapp(from_number, f"✅ Order received: {service_requested}. Your Order ID is {order_id}. You will receive payment prompt shortly.")

    # Trigger STK Push
    stk_response = trigger_stk(from_number, 10, order_id)

    return jsonify({"status": "ok", "order_id": order_id, "stk_response": stk_response})

# ------------------------
# MPESA Callback
# ------------------------
@app.route("/mpesa/callback", methods=["POST"])
def mpesa_callback():
    data = request.get_json()
    log("💰 MPESA callback received", data)

    order_id = data.get("order_id")
    mpesa_receipt = data.get("mpesa_receipt")
    amount = data.get("amount")
    phone = data.get("phone")

    # Update DB
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        UPDATE orders
        SET status='PAID', mpesa_receipt=%s, paid_at=NOW()
        WHERE order_id=%s;
    """, (mpesa_receipt, order_id))
    conn.commit()
    cur.close()
    conn.close()

    # WhatsApp user notification
    send_whatsapp(phone, f"💚 Payment received! Your Order {order_id} has been marked PAID. Receipt: {mpesa_receipt}")

    return jsonify({"status": "ok"}), 200

# ------------------------
# Dashboard route (JSON)
# ------------------------
@app.route("/orders", methods=["GET"])
def orders_list():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM orders ORDER BY created_at DESC;")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return jsonify({"orders": rows})

# ------------------------
# Health check
# ------------------------
@app.route("/", methods=["GET"])
def health_check():
    return "ChatPesa Production Server ✅", 200

# ------------------------
# Start server
# ------------------------
if __name__ == "__main__":
    init_db()
    log("🚀 Starting ChatPesa production server")
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
