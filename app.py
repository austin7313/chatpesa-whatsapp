import os
import uuid
import base64
import datetime
import threading
import time
import requests

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from twilio.twiml.messaging_response import MessagingResponse

import psycopg2
from psycopg2.extras import RealDictCursor

app = Flask(__name__, static_folder="dashboard_build", static_url_path="/")
CORS(app)

# ================= CONFIG =================
SHORTCODE = os.getenv("MPESA_SHORTCODE", "4031193")
PASSKEY = os.getenv("MPESA_PASSKEY", "YOUR_PASSKEY")
CONSUMER_KEY = os.getenv("MPESA_KEY", "YOUR_KEY")
CONSUMER_SECRET = os.getenv("MPESA_SECRET", "YOUR_SECRET")
MPESA_BASE = "https://api.safaricom.co.ke"
CALLBACK_URL = os.getenv("MPESA_CALLBACK", "https://your-app-url.onrender.com/mpesa/callback")
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL environment variable is required!")

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

def get_db():
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)

def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id TEXT PRIMARY KEY,
            phone TEXT,
            customer_name TEXT,
            amount INT,
            status TEXT,
            mpesa_receipt TEXT,
            created_at TIMESTAMP,
            paid_at TIMESTAMP
        )
    """)
    conn.commit()
    cur.close()
    conn.close()
    print("✅ DB Initialized")

# ================= STK PUSH =================
def stk_push(order):
    try:
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
        print(f"✅ STK Push Sent for {order['id']}, Status: {r.status_code}")

    except Exception as e:
        print("❌ STK Error:", str(e))

def stk_push_async(order):
    threading.Thread(target=stk_push, args=(order,)).start()

# ================= WHATSAPP =================
SESSIONS = {}

def send_typing_delay(resp, message, delay=1.5):
    """Simulate human typing on WhatsApp"""
    time.sleep(delay)
    resp.message(message)

@app.route("/webhook/whatsapp", methods=["POST"])
def whatsapp():
    body = request.values.get("Body", "").strip()
    phone = request.values.get("From")
    resp = MessagingResponse()
    session = SESSIONS.get(phone, {"step": "START"})

    if session["step"] == "START":
        send_typing_delay(resp, "👋 Welcome to ChatPesa\nReply 1️⃣ to make a payment")
        session["step"] = "MENU"

    elif session["step"] == "MENU" and body == "1":
        send_typing_delay(resp, "💰 Enter amount to pay (KES)\nMinimum: 10")
        session["step"] = "AMOUNT"

    elif session["step"] == "AMOUNT":
        try:
            amount = int(body)
            if amount < 10:
                raise ValueError
        except:
            send_typing_delay(resp, "❌ Invalid amount. Enter a number ≥ 10")
            return str(resp)

        order_id = "CP" + uuid.uuid4().hex[:6].upper()
        customer_name = request.values.get("ProfileName", phone)

        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO orders (id, phone, customer_name, amount, status, created_at)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (order_id, phone, customer_name, amount, "PENDING", now()))
        conn.commit()
        cur.close()
        conn.close()

        session["order_id"] = order_id
        session["step"] = "CONFIRM"
        send_typing_delay(resp, f"🧾 Order ID: {order_id}\nAmount: KES {amount}\nReply PAY to receive M-Pesa prompt")

    elif session["step"] == "CONFIRM" and body.upper() == "PAY":
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT * FROM orders WHERE id = %s", (session["order_id"],))
        order = cur.fetchone()
        cur.close()
        conn.close()

        send_typing_delay(resp, "📲 Sending M-Pesa prompt. Enter your PIN...")
        stk_push_async(order)
        session["step"] = "DONE"

    else:
        send_typing_delay(resp, "Reply 1️⃣ to start a payment")

    SESSIONS[phone] = session
    return str(resp)

# ================= MPESA CALLBACK =================
@app.route("/mpesa/callback", methods=["POST"])
def mpesa_callback():
    data = request.json
    cb = data["Body"]["stkCallback"]
    order_id = cb.get("MerchantRequestID", None)

    if cb["ResultCode"] == 0:
        meta = cb["CallbackMetadata"]["Item"]
        receipt = next(i["Value"] for i in meta if i["Name"] == "MpesaReceiptNumber")
        phone = str(next(i["Value"] for i in meta if i["Name"] == "PhoneNumber"))
        amount = next(i["Value"] for i in meta if i["Name"] == "Amount")

        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            UPDATE orders SET status=%s, mpesa_receipt=%s, paid_at=%s
            WHERE phone=%s AND amount=%s AND status='PENDING'
        """, ("PAID", receipt, now(), phone, amount))
        conn.commit()
        cur.close()
        conn.close()

        # Notify WhatsApp user
        resp = MessagingResponse()
        resp.message(f"✅ Payment of KES {amount} successful! Receipt: {receipt}")
        try:
            # send reply via Twilio API (async)
            requests.post(
                "https://api.twilio.com/2010-04-01/Accounts/YOUR_ACCOUNT/messages.json",
                auth=("YOUR_SID", "YOUR_AUTH_TOKEN"),
                data={"To": phone, "From": "whatsapp:+YOUR_TWILIO_NUMBER",
                      "Body": f"✅ Payment of KES {amount} successful! Receipt: {receipt}"}
            )
        except Exception as e:
            print("❌ WhatsApp callback send error:", e)

    else:
        # Payment failed
        phone = data["Body"]["stkCallback"].get("CallbackMetadata", {}).get("Item", [{}])[0].get("Value", "")
        resp = MessagingResponse()
        resp.message("❌ Payment failed or cancelled.")

    return jsonify({"status": "ok"})

# ================= DASHBOARD =================
@app.route("/orders")
def orders():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM orders ORDER BY created_at DESC")
    data = cur.fetchall()
    cur.close()
    conn.close()
    return jsonify({"status": "ok", "orders": data})

# Serve frontend
@app.route("/")
def root():
    return send_from_directory(app.static_folder, "index.html")

# ================= SERVER =================
if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
