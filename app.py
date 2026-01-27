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

# ================= APP =================
app = Flask(__name__)
CORS(app)

# ================= CONFIG =================
SHORTCODE = os.environ.get("MPESA_SHORTCODE", "4031193")
PASSKEY = os.environ.get("MPESA_PASSKEY", "YOUR_PASSKEY_HERE")
CONSUMER_KEY = os.environ.get("MPESA_CONSUMER_KEY", "YOUR_CONSUMER_KEY")
CONSUMER_SECRET = os.environ.get("MPESA_CONSUMER_SECRET", "YOUR_CONSUMER_SECRET")

CALLBACK_URL = os.environ.get(
    "MPESA_CALLBACK_URL", "https://chatpesa-whatsapp.onrender.com/mpesa/callback"
)
MPESA_BASE = "https://api.safaricom.co.ke"

TWILIO_SID = os.environ.get("TWILIO_ACCOUNT_SID")
TWILIO_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN")
WHATSAPP_NUMBER = os.environ.get(
    "WHATSAPP_NUMBER", "whatsapp:+14155238886"
)  # Twilio sandbox / prod

twilio_client = Client(TWILIO_SID, TWILIO_TOKEN)

# In-memory storage (upgrade to DB/Redis for persistence)
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
        f"{MPESA_BASE}/oauth/v1/generate?grant_type=client_credentials",
        auth=(CONSUMER_KEY, CONSUMER_SECRET),
        timeout=10,
    )
    r.raise_for_status()
    return r.json()["access_token"]


def send_whatsapp(to, text, delay=1.5):
    """Send WhatsApp message asynchronously with human-like delay."""
    def _send():
        time.sleep(delay)
        twilio_client.messages.create(
            from_=WHATSAPP_NUMBER,
            to=to,
            body=text,
        )

    threading.Thread(target=_send).start()


# ================= STK PUSH =================
def stk_push_async(order):
    """Trigger STK push asynchronously."""
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
            "TransactionDesc": "ChatPesa Payment",
        }

        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        r = requests.post(
            f"{MPESA_BASE}/mpesa/stkpush/v1/processrequest", json=payload, headers=headers, timeout=10
        )
        print("✅ STK Push Sent:", r.status_code, r.text)

    except Exception as e:
        print("❌ STK ERROR:", e)


# ================= WHATSAPP =================
@app.route("/webhook/whatsapp", methods=["POST"])
def whatsapp():
    body = request.values.get("Body", "").strip()
    phone = request.values.get("From")
    profile_name = request.values.get("ProfileName") or ""

    resp = MessagingResponse()
    msg = resp.message()

    session = SESSIONS.get(phone, {"step": "START"})

    if session["step"] == "START":
        msg.body("👋 Hi! Welcome to ChatPesa\n\nReply 1️⃣ to make a payment")
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
            "customer": profile_name or phone,
            "amount": amount,
            "status": "PENDING",
            "created_at": now(),
        }

        session["order_id"] = order_id
        session["step"] = "CONFIRM"

        msg.body(
            f"🧾 Order {order_id}\nAmount: KES {amount}\n\nReply PAY to receive M-Pesa prompt"
        )

    elif session["step"] == "CONFIRM" and body.upper() == "PAY":
        order = ORDERS.get(session["order_id"])
        msg.body("📲 Sending M-Pesa prompt…")
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
    cb = data.get("Body", {}).get("stkCallback", {})
    meta = cb.get("CallbackMetadata", {}).get("Item", [])

    order_id = None
    receipt = None
    amount = None
    phone = None

    # Extract all possible fields
    for item in meta:
        if item["Name"] == "AccountReference":
            order_id = item["Value"]
        elif item["Name"] == "MpesaReceiptNumber":
            receipt = item["Value"]
        elif item["Name"] == "Amount":
            amount = item["Value"]
        elif item["Name"] == "PhoneNumber":
            phone = str(item["Value"])

    # Fallback: use TransactionDesc if AccountReference missing
    if not order_id:
        order_id = cb.get("TransactionDesc", "")

    matched_order = ORDERS.get(order_id)

    if cb.get("ResultCode") == 0 and matched_order:
        matched_order["status"] = "PAID"
        matched_order["mpesa_receipt"] = receipt
        matched_order["paid_at"] = now()
        send_whatsapp(
            matched_order["phone"],
            f"✅ Payment successful!\n\nOrder: {order_id}\nAmount: KES {matched_order['amount']}\nReceipt: {receipt}\n\nThank you 🙏",
        )
    elif cb.get("ResultCode") != 0 and matched_order:
        matched_order["status"] = "FAILED"
        send_whatsapp(
            matched_order["phone"],
            f"❌ Payment failed or cancelled.\n\nOrder: {order_id}\nReply PAY to try again.",
        )
    else:
        print("❌ Callback received but order not found:", order_id)

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
