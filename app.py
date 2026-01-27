import os
import uuid
import base64
import datetime
import threading
import time
import psycopg2
from psycopg2.extras import RealDictCursor
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS
from twilio.rest import Client
from twilio.twiml.messaging_response import MessagingResponse

app = Flask(__name__)
CORS(app)

# ================= CONFIG =================
SHORTCODE = os.getenv("SHORTCODE", "4031193")
PASSKEY = os.getenv("PASSKEY", "YOUR_PASSKEY")
CONSUMER_KEY = os.getenv("CONSUMER_KEY", "YOUR_CONSUMER_KEY")
CONSUMER_SECRET = os.getenv("CONSUMER_SECRET", "YOUR_CONSUMER_SECRET")
MPESA_BASE = "https://api.safaricom.co.ke"
CALLBACK_URL = os.getenv("CALLBACK_URL", "https://yourdomain.com/mpesa/callback")
DATABASE_URL = os.getenv("DATABASE_URL")

TWILIO_SID = os.getenv("TWILIO_SID")
TWILIO_AUTH = os.getenv("TWILIO_AUTH")
TWILIO_WHATSAPP = os.getenv("TWILIO_WHATSAPP")  # e.g., "whatsapp:+1234567890"

# Twilio client
twilio_client = Client(TWILIO_SID, TWILIO_AUTH)

# ================= HELPERS =================
def now():
    return datetime.datetime.utcnow()

def normalize_phone(phone):
    phone = phone.replace("whatsapp:", "").replace("+", "").strip()
    if phone.startswith("0"):
        phone = "254" + phone[1:]
    elif phone.startswith("7"):
        phone = "254" + phone
    return phone

def mpesa_token():
    r = requests.get(
        f"{MPESA_BASE}/oauth/v1/generate?grant_type=client_credentials",
        auth=(CONSUMER_KEY, CONSUMER_SECRET),
        timeout=10
    )
    r.raise_for_status()
    return r.json()["access_token"]

# ---------------- Postgres connection ----------------
def get_db():
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    return conn

def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id TEXT PRIMARY KEY,
            phone TEXT NOT NULL,
            name TEXT NOT NULL,
            amount BIGINT NOT NULL,
            status TEXT NOT NULL DEFAULT 'PENDING',
            mpesa_receipt TEXT UNIQUE,
            checkout_request_id TEXT UNIQUE,
            merchant_request_id TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS idx_orders_phone ON orders(phone);
        CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
        CREATE INDEX IF NOT EXISTS idx_orders_created ON orders(created_at DESC);
    """)
    conn.commit()
    cur.close()
    conn.close()

init_db()

# ================= STK PUSH =================
def stk_push_async(order_id):
    try:
        # Get order from DB
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT * FROM orders WHERE id=%s", (order_id,))
        order = cur.fetchone()
        cur.close()
        conn.close()

        token = mpesa_token()
        timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        password = base64.b64encode(f"{SHORTCODE}{PASSKEY}{timestamp}".encode()).decode()
        phone = normalize_phone(order["phone"])

        payload = {
            "BusinessShortCode": SHORTCODE,
            "Password": password,
            "Timestamp": timestamp,
            "TransactionType": "CustomerPayBillOnline",
            "Amount": int(order["amount"]),
            "PartyA": phone,
            "PartyB": SHORTCODE,
            "PhoneNumber": phone,
            "CallBackURL": CALLBACK_URL,
            "AccountReference": order["id"],
            "TransactionDesc": "ChatPesa Payment"
        }
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        r = requests.post(f"{MPESA_BASE}/mpesa/stkpush/v1/processrequest", json=payload, headers=headers, timeout=10)
        print("✅ STK STATUS:", r.status_code, r.text)
    except Exception as e:
        print("❌ STK ERROR:", str(e))

# ================= WHATSAPP =================
@app.route("/webhook/whatsapp", methods=["POST"])
def whatsapp():
    body = request.values.get("Body", "").strip()
    phone = request.values.get("From")
    name = request.values.get("ProfileName", phone)  # fallback to phone

    resp = MessagingResponse()
    msg = resp.message()
    session = {}

    # Simulate typing
    msg.body("")  # required to start Twilio typing
    time.sleep(1 + len(body)/20)  # human-like delay

    # --------- Simple flow ---------
    if body == "1":
        msg.body("💰 Enter amount to pay (KES). Minimum: 10")
        session["step"] = "AMOUNT"
    elif body.isdigit() and int(body) >= 10:
        order_id = "CP" + uuid.uuid4().hex[:6].upper()
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO orders (id, phone, name, amount)
            VALUES (%s, %s, %s, %s)
        """, (order_id, phone, name, int(body)))
        conn.commit()
        cur.close()
        conn.close()
        msg.body(f"🧾 Order ID: {order_id}\nAmount: KES {body}\nReply PAY to complete payment")
    elif body.upper() == "PAY":
        # fetch last pending order
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT * FROM orders WHERE phone=%s AND status='PENDING' ORDER BY created_at DESC LIMIT 1", (phone,))
        order = cur.fetchone()
        cur.close()
        conn.close()
        if not order:
            msg.body("❌ No pending order found. Reply 1 to start a new payment.")
        else:
            msg.body("📲 Sending M-Pesa prompt. Enter your PIN.")
            threading.Thread(target=stk_push_async, args=(order["id"],)).start()
    else:
        msg.body("👋 Welcome to ChatPesa\nReply 1️⃣ to make a payment")

    return str(resp), 200

# ================= MPESA CALLBACK =================
@app.route("/mpesa/callback", methods=["POST"])
def mpesa_callback():
    data = request.json
    cb = data["Body"]["stkCallback"]

    conn = get_db()
    cur = conn.cursor()
    if cb["ResultCode"] == 0:
        meta = cb["CallbackMetadata"]["Item"]
        receipt = next(i["Value"] for i in meta if i["Name"] == "MpesaReceiptNumber")
        phone = str(next(i["Value"] for i in meta if i["Name"] == "PhoneNumber"))
        amount = next(i["Value"] for i in meta if i["Name"] == "Amount"))

        # Update order if matches pending
        cur.execute("""
            UPDATE orders
            SET status='PAID', mpesa_receipt=%s, updated_at=NOW()
            WHERE phone=%s AND amount=%s AND status='PENDING' AND mpesa_receipt IS NULL
            RETURNING id, name, phone
        """, (receipt, phone, amount))
        updated = cur.fetchone()
        if updated:
            # send WhatsApp confirmation
            msg_body = f"✅ Payment successful!\nOrder ID: {updated['id']}\nAmount: KES {amount}"
            twilio_client.messages.create(
                body=msg_body,
                from_=TWILIO_WHATSAPP,
                to=updated["phone"]
            )
    else:
        # Failed payment
        phone = data.get("phone") or "unknown"
        msg_body = f"❌ Payment failed. Please try again."
        twilio_client.messages.create(body=msg_body, from_=TWILIO_WHATSAPP, to=phone)

    conn.commit()
    cur.close()
    conn.close()
    return jsonify({"status": "ok"})

# ================= DASHBOARD =================
@app.route("/orders")
def orders():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM orders ORDER BY created_at DESC LIMIT 50")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return jsonify({"status": "ok", "orders": rows})

@app.route("/")
def root():
    return "ChatPesa API ONLINE", 200

# ================= SERVER =================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

