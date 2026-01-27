import os
import uuid
import base64
import datetime
import threading
import requests
import time
import psycopg2

from flask import Flask, request, jsonify
from flask_cors import CORS
from psycopg2.extras import RealDictCursor
from twilio.twiml.messaging_response import MessagingResponse
from twilio.rest import Client

# ================= CONFIG =================
SHORTCODE = os.getenv("MPESA_SHORTCODE")
PASSKEY = os.getenv("MPESA_PASSKEY")
CONSUMER_KEY = os.getenv("MPESA_CONSUMER_KEY")
CONSUMER_SECRET = os.getenv("MPESA_CONSUMER_SECRET")
CALLBACK_URL = os.getenv("MPESA_CALLBACK_URL")

DATABASE_URL = os.getenv("DATABASE_URL")

TWILIO_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_WHATSAPP = os.getenv("TWILIO_WHATSAPP_NUMBER")

MPESA_BASE = "https://api.safaricom.co.ke"

app = Flask(__name__)
CORS(app)

twilio_client = Client(TWILIO_SID, TWILIO_TOKEN)

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

def get_db():
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)

# ================= DB INIT =================
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
                )
            """)
        conn.commit()

init_db()

# ================= MPESA =================
def mpesa_token():
    r = requests.get(
        f"{MPESA_BASE}/oauth/v1/generate?grant_type=client_credentials",
        auth=(CONSUMER_KEY, CONSUMER_SECRET),
        timeout=10
    )
    r.raise_for_status()
    return r.json()["access_token"]

def stk_push_async(order):
    try:
        token = mpesa_token()
        timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")

        password = base64.b64encode(
            f"{SHORTCODE}{PASSKEY}{timestamp}".encode()
        ).decode()

        payload = {
            "BusinessShortCode": SHORTCODE,
            "Password": password,
            "Timestamp": timestamp,
            "TransactionType": "CustomerPayBillOnline",
            "Amount": order["amount"],
            "PartyA": order["phone"],
            "PartyB": SHORTCODE,
            "PhoneNumber": order["phone"],
            "CallBackURL": CALLBACK_URL,
            "AccountReference": order["id"],
            "TransactionDesc": "ChatPesa Payment"
        }

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

        requests.post(
            f"{MPESA_BASE}/mpesa/stkpush/v1/processrequest",
            json=payload,
            headers=headers,
            timeout=10
        )

    except Exception as e:
        print("STK ERROR:", e)

# ================= WHATSAPP =================
SESSIONS = {}

@app.route("/webhook/whatsapp", methods=["POST"])
def whatsapp():
    body = request.values.get("Body", "").strip()
    from_phone = request.values.get("From")

    resp = MessagingResponse()
    msg = resp.message()

    session = SESSIONS.get(from_phone, {"step": "START"})

    if session["step"] == "START":
        msg.body("👋 Welcome to ChatPesa\nReply 1️⃣ to make a payment")
        session["step"] = "MENU"

    elif session["step"] == "MENU" and body == "1":
        msg.body("💰 Enter amount (KES)\nMinimum 10")
        session["step"] = "AMOUNT"

    elif session["step"] == "AMOUNT":
        try:
            amount = int(body)
            if amount < 10:
                raise ValueError
        except:
            msg.body("❌ Invalid amount. Enter number ≥ 10")
            return str(resp)

        order_id = "CP" + uuid.uuid4().hex[:6].upper()
        phone = normalize_phone(from_phone)

        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO orders
                    (id, phone, customer_name, amount, status, created_at)
                    VALUES (%s,%s,%s,%s,%s,%s)
                """, (
                    order_id,
                    phone,
                    from_phone.replace("whatsapp:", ""),
                    amount,
                    "PENDING",
                    now()
                ))
            conn.commit()

        session["order_id"] = order_id
        session["step"] = "CONFIRM"

        msg.body(
            f"🧾 Order {order_id}\n"
            f"Amount: KES {amount}\n\n"
            f"Reply PAY to confirm"
        )

    elif session["step"] == "CONFIRM" and body.upper() == "PAY":
        msg.body("📲 Sending M-Pesa prompt…")

        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM orders WHERE id=%s", (session["order_id"],))
                order = cur.fetchone()

        threading.Thread(target=stk_push_async, args=(order,)).start()
        session["step"] = "DONE"

    else:
        msg.body("Reply 1️⃣ to start")

    SESSIONS[from_phone] = session
    return str(resp), 200

# ================= MPESA CALLBACK =================
@app.route("/mpesa/callback", methods=["POST"])
def mpesa_callback():
    data = request.json
    cb = data["Body"]["stkCallback"]

    if cb["ResultCode"] == 0:
        meta = cb["CallbackMetadata"]["Item"]
        receipt = next(i["Value"] for i in meta if i["Name"] == "MpesaReceiptNumber")
        account_ref = next(i["Value"] for i in meta if i["Name"] == "AccountReference")

        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE orders
                    SET status='PAID',
                        mpesa_receipt=%s,
                        paid_at=%s
                    WHERE id=%s
                """, (receipt, now(), account_ref))
            conn.commit()

        # WhatsApp success message
        cur.execute("SELECT phone FROM orders WHERE id=%s", (account_ref,))
        phone = cur.fetchone()["phone"]

        twilio_client.messages.create(
            from_=TWILIO_WHATSAPP,
            to=f"whatsapp:+{phone}",
            body=f"✅ Payment received.\nReceipt: {receipt}"
        )

    return jsonify({"status": "ok"})

# ================= DASHBOARD =================
@app.route("/orders")
def orders():
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM orders ORDER BY created_at DESC")
            return jsonify({"status": "ok", "orders": cur.fetchall()})

@app.route("/")
def root():
    return "ChatPesa API ONLINE", 200

# ================= SERVER =================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
