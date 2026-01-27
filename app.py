import os
import uuid
import base64
import datetime
import threading
import time
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

def human_delay():
    """Simulate human typing delay"""
    time.sleep(1.2)

# ================= WHATSAPP SENDER =================
def send_whatsapp_message(to, text):
    sid = os.environ.get("TWILIO_ACCOUNT_SID")
    token = os.environ.get("TWILIO_AUTH_TOKEN")
    wa_number = os.environ.get("TWILIO_WHATSAPP_NUMBER")

    if not all([sid, token, wa_number]):
        print("⚠️ Missing Twilio credentials")
        return

    client = Client(sid, token)
    client.messages.create(
        from_=f"whatsapp:{wa_number}",
        to=to,
        body=text
    )

# ================= STK PUSH =================
def stk_push_async(order):
    try:
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

        requests.post(
            f"{MPESA_BASE}/mpesa/stkpush/v1/processrequest",
            json=payload,
            headers=headers,
            timeout=10
        )

    except Exception as e:
        print("❌ STK ERROR:", e)

# ================= WHATSAPP WEBHOOK =================
@app.route("/webhook/whatsapp", methods=["POST"])
def whatsapp():
    body = request.values.get("Body", "").strip()
    phone = request.values.get("From")
    profile_name = request.values.get("ProfileName", "").strip()

    resp = MessagingResponse()
    msg = resp.message()

    session = SESSIONS.get(phone, {"step": "START"})
    human_delay()

    if session["step"] == "START":
        session["name"] = profile_name if profile_name else None

        if not session["name"]:
            msg.body("👋 Hi! What should we call you?")
            session["step"] = "ASK_NAME"
        else:
            msg.body(f"👋 Hi {session['name']}!\nReply 1️⃣ to make a payment")
            session["step"] = "MENU"

    elif session["step"] == "ASK_NAME":
        session["name"] = body
        msg.body(f"Nice to meet you {body} 😊\nHow much would you like to pay? (KES ≥10)")
        session["step"] = "AMOUNT"

    elif session["step"] == "MENU" and body == "1":
        msg.body("💰 Enter amount to pay (KES ≥10)")
        session["step"] = "AMOUNT"

    elif session["step"] == "AMOUNT":
        try:
            amount = int(body)
            if amount < 10:
                raise ValueError
        except:
            msg.body("❌ Please enter a valid amount (KES ≥10)")
            return str(resp)

        order_id = "CP" + uuid.uuid4().hex[:6].upper()

        ORDERS[order_id] = {
            "id": order_id,
            "phone": phone,
            "customer_name": session["name"],
            "amount": amount,
            "status": "AWAITING_PAYMENT",
            "created_at": now()
        }

        session["order_id"] = order_id
        session["step"] = "CONFIRM"

        msg.body(
            f"🧾 Order Summary\n\n"
            f"Order ID: {order_id}\n"
            f"Amount: KES {amount}\n\n"
            f"Reply PAY to receive M-Pesa prompt"
        )

    elif session["step"] == "CONFIRM" and body.upper() == "PAY":
        msg.body("📲 Sending M-Pesa prompt… please enter your PIN")
        threading.Thread(
            target=stk_push_async,
            args=(ORDERS[session["order_id"]],)
        ).start()
        session["step"] = "WAIT"

    else:
        msg.body("Reply 1️⃣ to start a payment")

    SESSIONS[phone] = session
    return str(resp), 200

# ================= MPESA CALLBACK =================
@app.route("/mpesa/callback", methods=["POST"])
def mpesa_callback():
    cb = request.json["Body"]["stkCallback"]

    order_id = cb.get("AccountReference")
    result_code = cb["ResultCode"]
    result_desc = cb["ResultDesc"]

    order = ORDERS.get(order_id)
    if not order:
        return jsonify({"status": "ignored"})

    if result_code == 0:
        meta = cb["CallbackMetadata"]["Item"]
        receipt = next(i["Value"] for i in meta if i["Name"] == "MpesaReceiptNumber")

        order["status"] = "PAID"
        order["mpesa_receipt"] = receipt
        order["paid_at"] = now()

        threading.Thread(
            target=send_whatsapp_message,
            args=(
                order["phone"],
                f"✅ Payment successful!\n\n"
                f"Order: {order_id}\n"
                f"Amount: KES {order['amount']}\n"
                f"Receipt: {receipt}\n\n"
                f"Thank you {order['customer_name']} 🙏"
            )
        ).start()

    else:
        order["status"] = "FAILED"

        threading.Thread(
            target=send_whatsapp_message,
            args=(
                order["phone"],
                f"❌ Payment failed\n\n"
                f"Order: {order_id}\n"
                f"Reason: {result_desc}\n\n"
                f"Reply PAY to try again."
            )
        ).start()

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
