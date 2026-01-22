import os
import base64
import json
import requests
from datetime import datetime
from flask import Flask, request, jsonify
from flask_cors import CORS
from twilio.twiml.messaging_response import MessagingResponse

app = Flask(__name__)
CORS(app)

# ---------------- CONFIG ---------------- #

MPESA_SHORTCODE = "4031193"
MPESA_PASSKEY = "5a64ad290753ed331b662cf6d83d3149367867c102f964f522390ccbd85cb282"
MPESA_CONSUMER_KEY = "B05zln19QXC3OBL6YuCkdhZ8zvYqZtXP"
MPESA_CONSUMER_SECRET = "MYRasd2p9gGFcuCR"

CALLBACK_URL = "https://chatpesa-whatsapp.onrender.com/mpesa/callback"

# ---------------- STORAGE (TEMP) ---------------- #
# Replace with DB later
orders = {}

# ---------------- HELPERS ---------------- #

def now():
    return datetime.utcnow().isoformat()

def generate_order_id():
    return "CP" + os.urandom(4).hex().upper()

def mpesa_access_token():
    auth = base64.b64encode(
        f"{MPESA_CONSUMER_KEY}:{MPESA_CONSUMER_SECRET}".encode()
    ).decode()

    res = requests.get(
        "https://api.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials",
        headers={"Authorization": f"Basic {auth}"}
    )
    return res.json()["access_token"]

def stk_password(timestamp):
    raw = f"{MPESA_SHORTCODE}{MPESA_PASSKEY}{timestamp}"
    return base64.b64encode(raw.encode()).decode()

def send_stk_push(order):
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    token = mpesa_access_token()

    payload = {
        "BusinessShortCode": MPESA_SHORTCODE,
        "Password": stk_password(timestamp),
        "Timestamp": timestamp,
        "TransactionType": "CustomerPayBillOnline",
        "Amount": order["amount"],
        "PartyA": order["phone"],
        "PartyB": MPESA_SHORTCODE,
        "PhoneNumber": order["phone"],
        "CallBackURL": CALLBACK_URL,
        "AccountReference": order["id"],
        "TransactionDesc": "ChatPesa Payment"
    }

    res = requests.post(
        "https://api.safaricom.co.ke/mpesa/stkpush/v1/processrequest",
        json=payload,
        headers={"Authorization": f"Bearer {token}"}
    )

    return res.json()

# ---------------- ROUTES ---------------- #

@app.route("/")
def root():
    return "ChatPesa API ONLINE", 200

@app.route("/orders")
def get_orders():
    return jsonify({
        "status": "ok",
        "orders": list(orders.values())
    })

# -------- WHATSAPP WEBHOOK -------- #

@app.route("/webhook/whatsapp", methods=["POST"])
def whatsapp():
    body = request.form.get("Body", "").strip().upper()
    phone = request.form.get("From", "").replace("whatsapp:", "")
    name = request.form.get("ProfileName", phone)

    resp = MessagingResponse()

    # PAY command
    if body == "PAY":
        pending = next(
            (o for o in orders.values()
             if o["phone"] == phone and o["status"] == "AWAITING_PAYMENT"),
            None
        )

        if not pending:
            resp.message("❌ No pending order found.")
            return str(resp)

        stk = send_stk_push(pending)
        pending["status"] = "STK_SENT"

        resp.message(
            f"📲 Payment request sent.\n"
            f"Check your phone and enter M-Pesa PIN.\n\n"
            f"Order ID: {pending['id']}"
        )
        return str(resp)

    # NEW ORDER
    order_id = generate_order_id()

    order = {
        "id": order_id,
        "customer_name": name,
        "phone": phone,
        "items": body or "Custom Order",
        "amount": 1000,
        "status": "AWAITING_PAYMENT",
        "mpesa_name": "",
        "mpesa_receipt": "",
        "created_at": now(),
        "paid_at": ""
    }

    orders[order_id] = order

    resp.message(
        f"✅ Order created\n\n"
        f"Order ID: {order_id}\n"
        f"Amount: KES 1000\n\n"
        f"Reply PAY to pay via M-Pesa"
    )

    return str(resp)

# -------- MPESA CALLBACK -------- #

@app.route("/mpesa/callback", methods=["POST"])
def mpesa_callback():
    data = request.json
    callback = data["Body"]["stkCallback"]

    if callback["ResultCode"] != 0:
        return jsonify({"status": "failed"})

    meta = {i["Name"]: i["Value"] for i in callback["CallbackMetadata"]["Item"]}

    order_id = meta["AccountReference"]
    order = orders.get(order_id)

    if not order:
        return jsonify({"status": "unknown_order"})

    order["status"] = "PAID"
    order["mpesa_receipt"] = meta.get("MpesaReceiptNumber", "")
    order["mpesa_name"] = meta.get("CustomerName", "")
    order["paid_at"] = now()

    return jsonify({"status": "ok"})

# ---------------- START ---------------- #

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=False)
