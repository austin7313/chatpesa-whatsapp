import os
import uuid
import base64
import datetime
import threading
import requests

from flask import Flask, request, jsonify
from flask_cors import CORS
from twilio.twiml.messaging_response import MessagingResponse
from twilio.rest import Client

app = Flask(__name__)
CORS(app)

# ================= CONFIG =================
SHORTCODE = "4031193"
PASSKEY = "5a64ad290753ed331b662cf6d83d3149367867c102f964f522390ccbd85cb282"

CONSUMER_KEY = "B05zln19QXC3OBL6YuCkdhZ8zvYqZtXP"
CONSUMER_SECRET = "MYRasd2p9gGFcuCR"

MPESA_BASE = "https://api.safaricom.co.ke"
CALLBACK_URL = "https://chatpesa-whatsapp.onrender.com/mpesa/callback"

ORDERS = {}
SESSIONS = {}

# ================= HELPERS =================
def now():
    return datetime.datetime.utcnow().isoformat()

def normalize_phone(phone):
    phone = phone.replace("whatsapp:", "").replace("+", "")
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

# ================= WHATSAPP =================
def send_whatsapp_message(to, text):
    client = Client(
        os.environ["TWILIO_ACCOUNT_SID"],
        os.environ["TWILIO_AUTH_TOKEN"]
    )

    client.messages.create(
        from_=f"whatsapp:{os.environ['TWILIO_WHATSAPP_NUMBER']}",
        to=to,
        body=text
    )

# ================= STK =================
def stk_push(order):
    token = mpesa_token()
    timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    password = base64.b64encode(
        f"{SHORTCODE}{PASSKEY}{timestamp}".encode()
    ).decode()

    phone = normalize_phone(order["phone"])

    payload = {
        "BusinessShortCode": SHORTCODE,
        "Password": password,
        "Timestamp": timestamp,
        "TransactionType": "CustomerPayBillOnline",
        "Amount": order["amount"],
        "PartyA": phone,
        "PartyB": SHORTCODE,
        "PhoneNumber": phone,
        "CallBackURL": CALLBACK_URL,
        "AccountReference": order["id"],
        "TransactionDesc": "ChatPesa"
    }

    requests.post(
        f"{MPESA_BASE}/mpesa/stkpush/v1/processrequest",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
        timeout=10
    )

# ================= WHATSAPP WEBHOOK =================
@app.route("/webhook/whatsapp", methods=["POST"])
def whatsapp():
    body = request.values.get("Body", "").strip()
    phone = request.values.get("From")
    profile = request.values.get("ProfileName", "").strip()

    session = SESSIONS.get(phone, {"step": "START"})
    resp = MessagingResponse()
    msg = resp.message()

    if session["step"] == "START":
        session["name"] = profile or None
        msg.body(
            f"👋 Hi {session['name'] or ''}\nReply 1️⃣ to make a payment"
        )
        session["step"] = "MENU"

    elif session["step"] == "MENU" and body == "1":
        msg.body("💰 Enter amount (KES)")
        session["step"] = "AMOUNT"

    elif session["step"] == "AMOUNT":
        try:
            amount = int(body)
            if amount < 10:
                raise ValueError
        except:
            msg.body("❌ Invalid amount")
            return str(resp)

        order_id = "CP" + uuid.uuid4().hex[:6].upper()

        ORDERS[order_id] = {
            "id": order_id,
            "phone": phone,
            "customer": session["name"],
            "amount": amount,
            "status": "PENDING",
            "created_at": now()
        }

        session["order"] = order_id
        session["step"] = "CONFIRM"

        msg.body(
            f"🧾 Order {order_id}\n"
            f"Amount: KES {amount}\n\n"
            f"Reply PAY to confirm"
        )

    elif session["step"] == "CONFIRM" and body.upper() == "PAY":
        msg.body("📲 Sending M-Pesa prompt…")

        threading.Thread(
            target=stk_push,
            args=(ORDERS[session["order"]],)
        ).start()

        session["step"] = "WAIT"

    SESSIONS[phone] = session
    return str(resp), 200

# ================= MPESA CALLBACK =================
@app.route("/mpesa/callback", methods=["POST"])
def mpesa_callback():
    cb = request.json["Body"]["stkCallback"]

    metadata = cb.get("CallbackMetadata", {}).get("Item", [])
    data = {i["Name"]: i.get("Value") for i in metadata}

    order_id = data.get("AccountReference")
    receipt = data.get("MpesaReceiptNumber")

    order = ORDERS.get(order_id)
    if not order:
        return jsonify({"ignored": True})

    if cb["ResultCode"] == 0:
        order["status"] = "PAID"
        order["receipt"] = receipt
        order["paid_at"] = now()

        threading.Thread(
            target=send_whatsapp_message,
            args=(
                order["phone"],
                f"✅ Payment successful!\n\n"
                f"Order: {order_id}\n"
                f"Amount: KES {order['amount']}\n"
                f"Receipt: {receipt}\n\n"
                f"Thank you 🙏"
            )
        ).start()
    else:
        order["status"] = "FAILED"

        threading.Thread(
            target=send_whatsapp_message,
            args=(
                order["phone"],
                f"❌ Payment failed\nOrder: {order_id}\nTry again."
            )
        ).start()

    return jsonify({"status": "ok"})

# ================= DASHBOARD =================
@app.route("/orders")
def orders():
    return jsonify(list(ORDERS.values()))

@app.route("/")
def root():
    return "ChatPesa API ONLINE", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
