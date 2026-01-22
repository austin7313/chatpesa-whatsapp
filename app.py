import os
import uuid
import json
import base64
import datetime
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS
from twilio.twiml.messaging_response import MessagingResponse

app = Flask(__name__)
CORS(app)

# =========================
# CONFIG
# =========================
MPESA_SHORTCODE = "4031193"
MPESA_PASSKEY = "5a64ad290753ed331b662cf6d83d3149367867c102f964f522390ccbd85cb282"
MPESA_CONSUMER_KEY = "B05zln19QXC3OBL6YuCkdhZ8zvYqZtXP"
MPESA_CONSUMER_SECRET = "MYRasd2p9gGFcuCR"

CALLBACK_URL = "https://chatpesa-whatsapp.onrender.com/mpesa/callback"

# =========================
# IN-MEMORY STORE (OK FOR MVP)
# =========================
ORDERS = {}

# =========================
# HELPERS
# =========================
def now():
    return datetime.datetime.utcnow().isoformat()

def generate_order_id():
    return "CP" + uuid.uuid4().hex[:6].upper()

def mpesa_token():
    auth = base64.b64encode(
        f"{MPESA_CONSUMER_KEY}:{MPESA_CONSUMER_SECRET}".encode()
    ).decode()
    r = requests.get(
        "https://sandbox.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials",
        headers={"Authorization": f"Basic {auth}"}
    )
    return r.json()["access_token"]

def stk_push(order):
    timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    password = base64.b64encode(
        f"{MPESA_SHORTCODE}{MPESA_PASSKEY}{timestamp}".encode()
    ).decode()

    payload = {
        "BusinessShortCode": MPESA_SHORTCODE,
        "Password": password,
        "Timestamp": timestamp,
        "TransactionType": "CustomerPayBillOnline",
        "Amount": order["amount"],
        "PartyA": order["phone"].replace("whatsapp:", ""),
        "PartyB": MPESA_SHORTCODE,
        "PhoneNumber": order["phone"].replace("whatsapp:", ""),
        "CallBackURL": CALLBACK_URL,
        "AccountReference": order["id"],
        "TransactionDesc": "ChatPesa Payment"
    }

    token = mpesa_token()
    headers = {"Authorization": f"Bearer {token}"}

    requests.post(
        "https://sandbox.safaricom.co.ke/mpesa/stkpush/v1/processrequest",
        json=payload,
        headers=headers
    )

# =========================
# WHATSAPP WEBHOOK
# =========================
@app.route("/webhook/whatsapp", methods=["POST"])
def whatsapp():
    body = request.values.get("Body", "").strip()
    sender = request.values.get("From", "")

    resp = MessagingResponse()
    msg = resp.message()

    active_order = next(
        (o for o in ORDERS.values() if o["phone"] == sender and o["status"] == "AWAITING_PAYMENT"),
        None
    )

    # 1️⃣ Greeting
    if body.lower() in ["hi", "hello", "start"]:
        msg.body(
            "👋 Welcome to ChatPesa\n\n"
            "Send an order like:\n"
            "`order 50` (KES 50)\n\n"
            "Minimum amount: KES 10"
        )

    # 2️⃣ Create Order
    elif body.lower().startswith("order"):
        try:
            amount = int(body.split()[1])
            if amount < 10:
                raise ValueError
        except:
            msg.body("❌ Invalid format.\nExample: `order 50`")
            return str(resp)

        order_id = generate_order_id()

        ORDERS[order_id] = {
            "id": order_id,
            "customer_name": sender,
            "phone": sender,
            "items": "Custom Order",
            "amount": amount,
            "status": "AWAITING_PAYMENT",
            "created_at": now(),
            "mpesa_name": None
        }

        msg.body(
            f"🧾 Order Created\n\n"
            f"Order ID: {order_id}\n"
            f"Amount: KES {amount}\n\n"
            f"Reply *PAY* to confirm payment."
        )

    # 3️⃣ PAY → STK PUSH
    elif body.lower() == "pay" and active_order:
        stk_push(active_order)
        msg.body(
            f"📲 M-Pesa prompt sent\n\n"
            f"Order ID: {active_order['id']}\n"
            f"Complete payment on your phone."
        )

    else:
        msg.body(
            "❓ I didn’t understand.\n\n"
            "Send:\n"
            "`order 50` to create order\n"
            "`PAY` to pay"
        )

    return str(resp), 200

# =========================
# MPESA CALLBACK
# =========================
@app.route("/mpesa/callback", methods=["POST"])
def mpesa_callback():
    data = request.json
    stk = data["Body"]["stkCallback"]

    order_id = stk["MerchantRequestID"] or stk["CheckoutRequestID"]

    for order in ORDERS.values():
        if order["id"] in json.dumps(data):
            if stk["ResultCode"] == 0:
                meta = stk["CallbackMetadata"]["Item"]
                name = next(i["Value"] for i in meta if i["Name"] == "MpesaReceiptNumber")

                order["status"] = "PAID"
                order["customer_name"] = name
                order["created_at"] = now()
            else:
                order["status"] = "FAILED"

    return jsonify({"status": "ok"})

# =========================
# DASHBOARD API
# =========================
@app.route("/orders", methods=["GET"])
def orders():
    return jsonify({"status": "ok", "orders": list(ORDERS.values())})

@app.route("/", methods=["GET"])
def root():
    return "ChatPesa API ONLINE", 200

# =========================
# START SERVER (RENDER SAFE)
# =========================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=False)
