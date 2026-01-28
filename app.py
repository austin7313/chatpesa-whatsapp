import os
import json
import requests
from flask import Flask, request, jsonify
from twilio.rest import Client
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime

app = Flask(__name__)

# Environment variables
DATABASE_URL = os.environ.get("DATABASE_URL")
TWILIO_SID = os.environ.get("TWILIO_SID")
TWILIO_AUTH = os.environ.get("TWILIO_AUTH")
TWILIO_WHATSAPP_NUMBER = os.environ.get("TWILIO_WHATSAPP_NUMBER")
MPESA_SHORTCODE = os.environ.get("MPESA_SHORTCODE")
MPESA_PASSKEY = os.environ.get("MPESA_PASSKEY")
MPESA_CONSUMER_KEY = os.environ.get("MPESA_CONSUMER_KEY")
MPESA_CONSUMER_SECRET = os.environ.get("MPESA_CONSUMER_SECRET")
MPESA_CALLBACK_URL = os.environ.get("MPESA_CALLBACK_URL")

twilio_client = Client(TWILIO_SID, TWILIO_AUTH)

def log(*args):
    print("🔹", *args)

# Database connection
def get_db():
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    return conn

def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id SERIAL PRIMARY KEY,
            order_id TEXT,
            customer_name TEXT,
            phone TEXT,
            amount TEXT,
            status TEXT,
            service TEXT,
            mpesa_receipt TEXT,
            created_at TIMESTAMP DEFAULT NOW(),
            paid_at TIMESTAMP
        )
    """)
    conn.commit()
    cur.close()
    conn.close()
    log("✅ Database initialized")

init_db()

# WhatsApp Webhook
@app.route("/webhook/whatsapp", methods=["POST"])
def whatsapp_webhook():
    form = request.form.to_dict()
    log("Incoming WhatsApp:", form)

    from_number = form.get("From")  # e.g. whatsapp:+254722275271
    body = form.get("Body", "").strip()

    if not from_number or not body:
        log("❌ Missing From or Body")
        return jsonify({"status": "error", "message": "Missing fields"}), 400

    # For simplicity, every message creates a PENDING order
    order_id = f"CP{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO orders (order_id, customer_name, phone, amount, status, service)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING id
    """, (order_id, "WhatsApp User", from_number, "10", "PENDING", body))
    conn.commit()
    cur.close()
    conn.close()

    reply_text = f"Hi! Your order {order_id} for '{body}' has been received. Amount: KES 10. Status: PENDING."

    try:
        msg = twilio_client.messages.create(
            body=reply_text,
            from_=f"whatsapp:{TWILIO_WHATSAPP_NUMBER}",
            to=from_number
        )
        log("✅ WhatsApp reply sent:", msg.sid)
    except Exception as e:
        log("❌ WhatsApp send error:", e)

    return jsonify({"status": "ok", "order_id": order_id})

# STK Callback
@app.route("/mpesa/callback", methods=["POST"])
def mpesa_callback():
    data = request.json
    log("💰 MPESA Callback:", data)

    # Extract receipt and update DB
    try:
        receipt = data.get("Body", {}).get("stkCallback", {}).get("CallbackMetadata", {}).get("Item", [])
        phone = data.get("Body", {}).get("stkCallback", {}).get("CallbackMetadata", {}).get("PhoneNumber")
        amount = next((i["Value"] for i in receipt if i["Name"]=="Amount"), None)
        receipt_number = next((i["Value"] for i in receipt if i["Name"]=="MpesaReceiptNumber"), None)

        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            UPDATE orders SET status='PAID', mpesa_receipt=%s, paid_at=NOW()
            WHERE phone=%s AND status='PENDING'
        """, (receipt_number, f"whatsapp:{phone}"))
        conn.commit()
        cur.close()
        conn.close()

        # Reply via WhatsApp
        try:
            twilio_client.messages.create(
                body=f"🎉 Payment received! KES {amount} paid. Receipt: {receipt_number}",
                from_=f"whatsapp:{TWILIO_WHATSAPP_NUMBER}",
                to=f"whatsapp:{phone}"
            )
            log("✅ Payment WhatsApp reply sent")
        except Exception as e:
            log("❌ Payment WhatsApp reply error:", e)

    except Exception as e:
        log("❌ MPESA callback processing error:", e)

    return jsonify({"status": "ok"})

# Dashboard Orders API
@app.route("/orders", methods=["GET"])
def get_orders():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM orders ORDER BY created_at DESC LIMIT 50")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return jsonify({"orders": rows, "status": "ok"})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    log(f"🚀 Running on port {port}")
    app.run(host="0.0.0.0", port=port)
