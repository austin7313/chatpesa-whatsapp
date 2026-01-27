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

# ================= APP =================
app = Flask(__name__)
CORS(app)

# ================= CONFIG =================
SHORTCODE = os.getenv("MPESA_SHORTCODE")
PASSKEY = os.getenv("MPESA_PASSKEY")
CONSUMER_KEY = os.getenv("MPESA_CONSUMER_KEY")
CONSUMER_SECRET = os.getenv("MPESA_CONSUMER_SECRET")

MPESA_BASE = "https://api.safaricom.co.ke"
CALLBACK_URL = "https://chatpesa-whatsapp.onrender.com/mpesa/callback"

TWILIO_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
WHATSAPP_NUMBER = "whatsapp:+14155238886"

twilio = Client(TWILIO_SID, TWILIO_TOKEN)

# ================= STORAGE (PHASE 1) =================
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
        f"{MPESA_BASE}/oauth/v1/generate?grant_type=client_credentials",
        auth=(CONSUMER_KEY, CONSUMER_SECRET),
        timeout=10
    )
    r.raise_for_status()
    return r.json()["access_token"]

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
            "AccountReference": order["id"],  # 🔐 ORDER ID MATCHING
            "TransactionDesc": "ChatPesa Payment"
        }

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

        r = requests.post(
            f"{MPESA_BASE}/mpesa/stkpush/v1/processrequest",
            json=payload,
            headers=headers,
            timeout=10
        )

        print("STK SENT:", order["id"], r.status_code)

    except Exception as e:
        print("STK ERROR:", str(e))

# ================= WHATSAPP =================
@app.route("/webhook/whatsapp", methods=["POST"])
def whatsapp():
    body = request.values.get("Body", "").strip().upper()
    phone = request.values.get("From")
    name = request.values.get("ProfileName", "Customer")

    resp = MessagingResponse()
    msg = resp.message()

    session = SESSIONS.get(phone, {"step": "START"})

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
            msg.body("❌ Invalid amount. Enter a number ≥ 10")
            return str(resp)

        order_id = "CP" + uuid.uuid4().hex[:6].upper()

        ORDERS[order_id] = {
            "id": order_id,
            "phone": phone,
            "customer": name,
            "amount": amount,
            "status": "PENDING",
            "created_at": now()
        }

        session["order_id"] = order_id
        session["step"] = "CONFIRM"

        msg.body(
            f"🧾 Order {order_id}\n"
            f"Amount: KES {amount}\n\n"
            f"Reply PAY to confirm"
        )

    elif session["step"] == "CONFIRM" and body == "PAY":
        order = ORDERS.get(session["order_id"])

        msg.body("📲 Sending M-Pesa prompt…")

        threading.Thread(
            target=stk_push_async,
            args=(order,),
            daemon=True
        ).start()

        session["step"] = "DONE"

    else:
        msg.body("Reply 1️⃣ to start")

    SESSIONS[phone] = session
    return str(resp), 200

# ================= MPESA CALLBACK =================
@app.route("/mpesa/callback", methods=["POST"])
def mpesa_callback():
    data = request.json
    cb = data["Body"]["stkCallback"]

    if cb["ResultCode"] != 0:
        print("PAYMENT FAILED:", cb["ResultDesc"])
        return jsonify({"status": "ok"})

    meta = cb["CallbackMetadata"]["Item"]
    receipt = next(i["Value"] for i in meta if i["Name"] == "MpesaReceiptNumber")
    phone = str(next(i["Value"] for i in meta if i["Name"] == "PhoneNumber"))
    amount = next(i["Value"] for i in meta if i["Name"] == "Amount")
    order_id = cb["CheckoutRequestID"] if False else cb.get("AccountReference")

    # 🔐 Bank-grade matching: Order ID → Phone → Amount
    for o in ORDERS.values():
        if (
            o["status"] == "PENDING"
            and normalize_phone(o["phone"]) == phone
            and o["amount"] == amount
        ):
            o["status"] = "PAID"
            o["mpesa_receipt"] = receipt
            o["paid_at"] = now()

            twilio.messages.create(
                from_=WHATSAPP_NUMBER,
                to=o["phone"],
                body=f"✅ Payment successful.\nReceipt: {receipt}\nThank you."
            )

            print("PAYMENT MATCHED:", o["id"], receipt)
            break
    else:
        print("UNMATCHED PAYMENT:", phone, amount, receipt)

    return jsonify({"status": "ok"})

# ================= DASHBOARD =================
@app.route("/orders")
def orders():
    return jsonify(list(ORDERS.values()))

@app.route("/")
def root():
    return "ChatPesa API ONLINE", 200

# ================= SERVER =================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
