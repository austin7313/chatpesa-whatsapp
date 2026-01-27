import os
import time
from flask import Flask, request, jsonify
from flask_cors import CORS
import psycopg2
from psycopg2.extras import RealDictCursor
import requests

# --- CONFIG ---
DATABASE_URL = os.getenv("DATABASE_URL")
TWILIO_WHATSAPP_TOKEN = os.getenv("TWILIO_WHATSAPP_TOKEN")  # Twilio Auth Token
TWILIO_WHATSAPP_FROM = os.getenv("TWILIO_WHATSAPP_FROM")    # WhatsApp number e.g. whatsapp:+14155238886

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL environment variable is required!")

app = Flask(__name__)
CORS(app)

# --- DATABASE ---
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
            status TEXT,
            mpesa_receipt TEXT,
            created_at TIMESTAMP DEFAULT NOW(),
            paid_at TIMESTAMP
        )
    """)
    conn.commit()
    cur.close()
    conn.close()

init_db()

# --- HELPERS ---
def normalize_phone(phone):
    """Convert to international format if needed"""
    phone = phone.replace(" ", "").replace("-", "")
    if phone.startswith("0"):
        phone = "+254" + phone[1:]
    if phone.startswith("254"):
        phone = "+" + phone
    return phone

def send_whatsapp_message(to, message):
    """Send WhatsApp message via Twilio"""
    url = f"https://api.twilio.com/2010-04-01/Accounts/{os.getenv('TWILIO_ACCOUNT_SID')}/Messages.json"
    data = {
        "From": TWILIO_WHATSAPP_FROM,
        "To": to,
        "Body": message
    }
    requests.post(url, data=data, auth=(os.getenv('TWILIO_ACCOUNT_SID'), TWILIO_WHATSAPP_TOKEN))

def simulate_typing(to, delay=2):
    """Simulate human typing indicator by delaying response"""
    time.sleep(delay)

# --- ROUTES ---
@app.route("/orders")
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
    """Receive incoming WhatsApp messages from Twilio"""
    payload = request.form
    phone = normalize_phone(payload.get("From", ""))
    body = payload.get("Body", "").strip()

    print(f"[WHATSAPP IN] {phone}: {body}")

    simulate_typing(phone, delay=1.5)

    # Simple menu example
    if body.lower() == "menu":
        reply = "Welcome! Send 'PAY' to start payment."
    elif body.lower().startswith("pay"):
        reply = "STK Push triggered! Please complete the payment on your phone."
        # Here you would trigger STK push via M-Pesa API
    else:
        reply = "Sorry, I didn't understand. Send 'MENU' for options."

    send_whatsapp_message(phone, reply)
    print(f"[WHATSAPP OUT] {phone}: {reply}")
    return "OK", 200

@app.route("/webhook/mpesa", methods=["POST"])
def mpesa_webhook():
    """Receive M-Pesa payment confirmation"""
    data = request.json
    # Example: parse payment info
    order_id = data.get("OrderID")
    status = data.get("Status")
    receipt = data.get("ReceiptNumber")

    conn = get_db()
    cur = conn.cursor()

    if status == "SUCCESS":
        cur.execute("""
            UPDATE orders
            SET status='PAID', mpesa_receipt=%s, paid_at=NOW()
            WHERE id=%s
        """, (receipt, order_id))
        conn.commit()
        # Send WhatsApp message to customer
        cur.execute("SELECT phone FROM orders WHERE id=%s", (order_id,))
        row = cur.fetchone()
        if row:
            phone = row["phone"]
            simulate_typing(phone, delay=1)
            send_whatsapp_message(phone, f"Payment successful! Receipt: {receipt}")
    else:
        cur.execute("UPDATE orders SET status='FAILED' WHERE id=%s", (order_id,))
        conn.commit()
        cur.execute("SELECT phone FROM orders WHERE id=%s", (order_id,))
        row = cur.fetchone()
        if row:
            phone = row["phone"]
            simulate_typing(phone, delay=1)
            send_whatsapp_message(phone, "Payment failed. Please try again.")

    cur.close()
    conn.close()
    return jsonify({"status": "ok"})

@app.route("/health")
def health():
    return "OK", 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"Starting ChatPesa API on port {port}")
    app.run(host="0.0.0.0", port=port, debug=False)
