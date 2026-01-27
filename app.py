import os
import uuid
import base64
import datetime
import threading
import time
import requests
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, request, jsonify
from flask_cors import CORS
from twilio.rest import Client
from twilio.twiml.messaging_response import MessagingResponse

app = Flask(__name__)
CORS(app)

# ================= CONFIG =================
SHORTCODE = os.environ.get("SHORTCODE")
PASSKEY = os.environ.get("PASSKEY")
CONSUMER_KEY = os.environ.get("CONSUMER_KEY")
CONSUMER_SECRET = os.environ.get("CONSUMER_SECRET")
CALLBACK_URL = os.environ.get("CALLBACK_URL")
DATABASE_URL = os.environ.get("DATABASE_URL")
TWILIO_SID = os.environ.get("TWILIO_SID")
TWILIO_AUTH = os.environ.get("TWILIO_AUTH")
TWILIO_WHATSAPP = os.environ.get("TWILIO_WHATSAPP")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL environment variable is required!")

client = Client(TWILIO_SID, TWILIO_AUTH)

# ================= HELPERS =================
def now():
    return datetime.datetime.utcnow()

def normalize_phone(phone):
    phone = phone.replace("whatsapp:", "").replace("+", "").strip()
    if phone.startswith("0"):
        phone = "254" + phone[1:]
    if phone.startswith("7"):
        phone = "254" + phone
    return phone

def mpesa_token():
    r = requests.get(
        "https://api.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials",
        auth=(CONSUMER_KEY, CONSUMER_SECRET),
        timeout=10
    )
    r.raise_for_status()
    return r.json()["access_token"]

def send_whatsapp(phone, body):
    """Send WhatsApp message with typing indicator delay."""
    client.messages.create(
        from_=f"whatsapp:{TWILIO_WHATSAPP}",
        to=phone,
        body=body
    )

def stk_push_async(order_id):
    """STK push in background thread."""
    try:
        order = get_order(order_id)
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
        r = requests.post(f"https://api.safaricom.co.ke/mpesa/stkpush/v1/processrequest", json=payload, headers=headers, timeout=10)
        print(f"✅ STK push sent for {order_id}, status: {r.status_code}")
        print(r.text)
    except Exception as e:
        print(f"❌ STK error for {order_id}: {e}")
        send_whatsapp(order["phone"], "⚠️ Failed to initiate M-Pesa. Try again.")

# ================= DATABASE =================
def get_db():
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    return conn

def init_db():
    conn = get_db()
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id TEXT PRIMARY KEY,
                phone TEXT NOT NULL,
                customer_name TEXT,
                amount NUMERIC NOT NULL,
                status TEXT NOT NULL,
                created_at TIMESTAMP NOT NULL,
                paid_at TIMESTAMP,
                mpesa_receipt TEXT
            )
        """)
        conn.commit()
    conn.close()

def create_order(phone, customer_name, amount):
    order_id = "CP" + uuid.uuid4().hex[:6].upper()
    conn = get_db()
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO orders (id, phone, customer_name, amount, status, created_at)
            VALUES (%s,%s,%s,%s,%s,%s)
        """, (order_id, phone, customer_name, amount, "AWAITING_PAYMENT", now()))
        conn.commit()
    conn.close()
    return order_id

def get_order(order_id):
    conn = get_db()
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM orders WHERE id = %s", (order_id,))
        order = cur.fetchone()
    conn.close()
    return order

def update_order_paid(order_id, receipt):
    conn = get_db()
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE orders
            SET status='PAID', paid_at=%s, mpesa_receipt=%s
            WHERE id=%s
        """, (now(), receipt, order_id))
        conn.commit()
    conn.close()

def list_orders():
    conn = get_db()
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM orders ORDER BY created_at DESC")
        orders = cur.fetchall()
    conn.close()
    return orders

# ================= WHATSAPP =================
SESSIONS = {}

@app.route("/webhook/whatsapp", methods=["POST"])
def whatsapp():
    body = request.values.get("Body", "").strip()
    phone = request.values.get("From")
    name = request.values.get("ProfileName") or phone

    resp = MessagingResponse()
    msg = resp.message()
    session = SESSIONS.get(phone, {"step": "START"})

    def human_reply(text, delay=1.5):
        time.sleep(delay)
        msg.body(text)

    if session["step"] == "START":
        human_reply("👋 Welcome to ChatPesa\nReply 1️⃣ to make a payment")
        session["step"] = "MENU"

    elif session["step"] == "MENU" and body == "1":
        human_reply("💰 Enter amount to pay (KES)\nMinimum: 10")
        session["step"] = "AMOUNT"

    elif session["step"] == "AMOUNT":
        try:
            amount = int(body)
            if amount < 10:
                raise ValueError
        except:
            human_reply("❌ Invalid amount. Enter a number ≥ 10")
            return str(resp)

        order_id = create_order(phone, name, amount)
        session["order_id"] = order_id
        session["step"] = "CONFIRM"
        human_reply(f"🧾 Order ID: {order_id}\nAmount: KES {amount}\nReply PAY to receive M-Pesa prompt")

    elif session["step"] == "CONFIRM" and body.upper() == "PAY":
        order = get_order(session["order_id"])
        human_reply("📲 Sending M-Pesa prompt. Enter your PIN...")
        threading.Thread(target=stk_push_async, args=(order["id"],)).start()
        session["step"] = "DONE"

    else:
        human_reply("Reply 1️⃣ to start a payment")

    SESSIONS[phone] = session
    return str(resp), 200

# ================= MPESA CALLBACK =================
@app.route("/mpesa/callback", methods=["POST"])
def mpesa_callback():
    data = request.json
    cb = data["Body"]["stkCallback"]

    order_id = cb.get("MerchantRequestID") or cb.get("CheckoutRequestID")
    result = cb.get("ResultCode")
    meta = cb.get("CallbackMetadata", {}).get("Item", [])

    if result == 0:
        receipt = next((i["Value"] for i in meta if i["Name"]=="MpesaReceiptNumber"), None)
        phone = str(next((i["Value"] for i in meta if i["Name"]=="PhoneNumber"), ""))
        amount = next((i["Value"] for i in meta if i["Name"]=="Amount"), 0)
        # Match order by phone + amount
        orders = list_orders()
        match_order = next((o for o in orders if normalize_phone(o["phone"])==normalize_phone(phone) and float(o["amount"])==float(amount) and o["status"]=="AWAITING_PAYMENT"), None)
        if match_order:
            update_order_paid(match_order["id"], receipt)
            send_whatsapp(match_order["phone"], f"✅ Payment received! Receipt: {receipt}")
    else:
        # Failed payment
        send_whatsapp(phone, "❌ Payment failed or cancelled.")

    return jsonify({"status":"ok"})

# ================= DASHBOARD =================
@app.route("/orders")
def orders():
    return jsonify({"status":"ok","orders":list_orders()})

@app.route("/")
def root():
    return "ChatPesa API ONLINE", 200

# ================= INIT =================
if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
