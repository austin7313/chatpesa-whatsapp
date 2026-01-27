import os
import json
import time
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS
import psycopg2
from psycopg2.extras import RealDictCursor
from twilio.rest import Client

app = Flask(__name__)
CORS(app)

# ----------------------
# Configuration
# ----------------------
DATABASE_URL = os.environ.get("DATABASE_URL")
TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN")
TWILIO_WHATSAPP_NUMBER = os.environ.get("TWILIO_WHATSAPP_NUMBER")  # e.g., "whatsapp:+14155238886"

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL environment variable is required!")
if not (TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN and TWILIO_WHATSAPP_NUMBER):
    raise RuntimeError("Twilio env variables missing!")

twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

# ----------------------
# Database helper
# ----------------------
def get_db():
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    return conn

def init_db():
    print("[DB] Initializing database...")
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id TEXT PRIMARY KEY,
            customer_name TEXT,
            phone TEXT,
            amount NUMERIC,
            status TEXT,
            created_at TIMESTAMP DEFAULT NOW(),
            paid_at TIMESTAMP,
            mpesa_receipt TEXT
        )
    """)
    conn.commit()
    cur.close()
    conn.close()
    print("[DB] Database ready.")

# ----------------------
# Helper functions
# ----------------------
def normalize_phone(phone):
    # Normalize phone to E.164 WhatsApp format
    phone = phone.replace(" ", "").replace("-", "")
    if phone.startswith("0"):
        phone = "+254" + phone[1:]
    elif not phone.startswith("+"):
        phone = "+" + phone
    if not phone.startswith("whatsapp:"):
        phone = "whatsapp:" + phone
    return phone

def send_whatsapp(to, message):
    print(f"[TWILIO] Sending WhatsApp to {to}: {message}")
    try:
        msg = twilio_client.messages.create(
            body=message,
            from_=TWILIO_WHATSAPP_NUMBER,
            to=to
        )
        print(f"[TWILIO] Message SID: {msg.sid}")
    except Exception as e:
        print(f"[TWILIO] ERROR sending message: {e}")

# ----------------------
# Routes
# ----------------------
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
    data = request.get_json(force=True)
    print("[WEBHOOK] Incoming WhatsApp webhook:", data)

    phone = normalize_phone(data.get("From", ""))
    body = data.get("Body", "").strip()
    print(f"[WEBHOOK] Normalized phone: {phone}, Body: {body}")

    # Log human typing delay simulation
    print(f"[WEBHOOK] Simulating typing indicator for 2 seconds...")
    time.sleep(2)

    # Respond
    response_text = f"Received your message: {body}"
    send_whatsapp(phone, response_text)
    print("[WEBHOOK] Response sent.")

    return jsonify({"status": "ok"})

@app.route("/webhook/whatsapp-test", methods=["GET"])
def test_whatsapp():
    test_data = {
        "From": "whatsapp:+254722275271",
        "Body": "hi test"
    }
    print("[TEST WEBHOOK] Incoming WhatsApp webhook:", test_data)
    print(f"[TEST WEBHOOK] Replying to {test_data['From']}: Received your message: {test_data['Body']}")
    return jsonify({"status": "ok", "message": "Test webhook hit successfully"})

# ----------------------
# STK Push simulation
# ----------------------
@app.route("/stk-push", methods=["POST"])
def stk_push():
    data = request.get_json(force=True)
    print("[STK] Incoming STK request:", data)
    order_id = data.get("order_id")
    amount = data.get("amount")
    phone = normalize_phone(data.get("phone", ""))

    # Simulate STK push processing
    print(f"[STK] Simulating STK push of KES {amount} to {phone} for order {order_id}...")
    time.sleep(2)

    # Simulate random success/failure for testing
    import random
    success = random.choice([True, False])
    status = "PAID" if success else "FAILED"

    # Update DB
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "UPDATE orders SET status=%s, paid_at=NOW() WHERE id=%s",
        (status, order_id)
    )
    conn.commit()
    cur.close()
    conn.close()
    print(f"[STK] Order {order_id} marked as {status}")

    # Notify WhatsApp user
    message = f"Payment {status.lower()} for order {order_id}!"
    send_whatsapp(phone, message)
    return jsonify({"status": status})

# ----------------------
# Start app
# ----------------------
if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 5000))
    print(f"[APP] Starting server on port {port}...")
    app.run(host="0.0.0.0", port=port, debug=True)
