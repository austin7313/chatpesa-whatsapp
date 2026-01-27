import os
import uuid
import base64
import datetime
import threading
import requests

from flask import Flask, request, jsonify
from flask_cors import CORS
from twilio.twiml.messaging_response import MessagingResponse

app = Flask(__name__)
CORS(app)

# ================= CONFIG =================
SHORTCODE = os.environ.get("MPESA_SHORTCODE", "4031193")
PASSKEY = os.environ.get("MPESA_PASSKEY", "5a64ad290753ed331b662cf6d83d3149367867c102f964f522390ccbd85cb282")
CONSUMER_KEY = os.environ.get("MPESA_CONSUMER_KEY", "B05zln19QXC3OBL6YuCkdhZ8zvYqZtXP")
CONSUMER_SECRET = os.environ.get("MPESA_CONSUMER_SECRET", "MYRasd2p9gGFcuCR")
MPESA_BASE = "https://api.safaricom.co.ke"
CALLBACK_URL = os.environ.get("CALLBACK_URL", "https://<YOUR_APP_URL>/mpesa/callback")

ORDERS = {}
SESSIONS = {}

# ================= HELPERS =================
def now():
    return datetime.datetime.utcnow().isoformat()

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

def stk_push_async(order):
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

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

        r = requests.post(f"{MPESA_BASE}/mpesa/stkpush/v1/processrequest",
                          json=payload, headers=headers, timeout=10)
        print("✅ STK Push Sent:", r.status_code, r.text)
    except Exception as e:
        print("❌ STK Push Error:", str(e))

# ================= WHATSAPP =================
@app.route("/whatsapp", methods=["POST"])
def whatsapp():
    body = request.form.get("Body", "").strip().upper()
    phone = request.form.get("From", "").strip()
    resp = MessagingResponse()
    msg = resp.message()

    session = SESSIONS.get(phone, {"step": "START"})

    # ----------------- MENU -----------------
    if session["step"] == "START":
        msg.body("👋 Welcome to ChatPesa!\nReply 1️⃣ to make a payment")
        session["step"] = "MENU"

    elif session["step"] == "MENU" and body == "1":
        msg.body("💰 Enter amount to pay (KES)\nMinimum: 10")
        session["step"] = "AMOUNT"

    elif session["step"] == "AMOUNT":
        try:
            amount = int(body)
            if amount < 10:
                raise ValueError
        except:
            msg.body("❌ Invalid amount. Enter a number ≥ 10")
            return str(resp)

        order_id = "CP" + uuid.uuid4().hex[:6].upper()
        ORDERS[order_id] = {
            "id": order_id,
            "phone": phone,
            "customer_name": phone,  # capture WhatsApp number
            "amount": amount,
            "status": "PENDING",
            "created_at": now(),
            "mpesa_receipt": None,
            "paid_at": None
        }
        session["order_id"] = order_id
        session["step"] = "CONFIRM"
        msg.body(f"🧾 Order ID: {order_id}\nAmount: KES {amount}\n\nReply PAY to receive M-Pesa prompt")

    elif session["step"] == "CONFIRM" and body == "PAY":
        order = ORDERS.get(session["order_id"])
        msg.body("📲 Sending M-Pesa prompt. Enter your PIN now…")
        threading.Thread(target=stk_push_async, args=(order,)).start()
        session["step"] = "DONE"

    else:
        msg.body("Reply 1️⃣ to start a payment")

    SESSIONS[phone] = session
    return str(resp), 200

# ================= MPESA CALLBACK =================
@app.route("/mpesa/callback", methods=["POST"])
def mpesa_callback():
    data = request.json
    cb = data["Body"]["stkCallback"]

    order_updated = None
    if cb["ResultCode"] == 0:
        meta = cb["CallbackMetadata"]["Item"]
        receipt = next(i["Value"] for i in meta if i["Name"] == "MpesaReceiptNumber")
        phone = str(next(i["Value"] for i in meta if i["Name"] == "PhoneNumber"))
        amount = next(i["Value"] for i in meta if i["Name"] == "Amount")

        # Match order by phone + amount + PENDING
        for o in ORDERS.values():
            if o["status"] == "PENDING" and normalize_phone(o["phone"]) == normalize_phone(phone) and o["amount"] == amount:
                o["status"] = "PAID"
                o["mpesa_receipt"] = receipt
                o["paid_at"] = now()
                order_updated = o
                break

    else:
        # failed transaction
        for o in ORDERS.values():
            if o["status"] == "PENDING" and o.get("order_id"):
                o["status"] = "FAILED"
                order_updated = o
                break

    # Send WhatsApp notification
    if order_updated:
        from twilio.rest import Client
        TWILIO_SID = os.environ.get("TWILIO_ACCOUNT_SID")
        TWILIO_AUTH = os.environ.get("TWILIO_AUTH_TOKEN")
        client = Client(TWILIO_SID, TWILIO_AUTH)
        status_msg = "✅ Payment Successful!" if order_updated["status"] == "PAID" else "❌ Payment Failed."
        client.messages.create(
            from_="whatsapp:+14155238886",  # Twilio Sandbox number
            body=f"Order {order_updated['id']}: {status_msg}",
            to=order_updated["phone"]
        )

    return jsonify({"status": "ok"})

# ================= DASHBOARD =================
@app.route("/orders")
def orders():
    return jsonify({"status": "ok", "orders": list(ORDERS.values())})

@app.route("/")
def root():
    return "ChatPesa API ONLINE", 200

# ================= SERVER =================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
