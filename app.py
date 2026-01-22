import os
import base64
import json
import requests
from datetime import datetime
from flask import Flask, request, jsonify
from twilio.twiml.messaging_response import MessagingResponse

app = Flask(__name__)

# =========================
# CONFIG (ENV VARS SAFE)
# =========================
MPESA_SHORTCODE = "4031193"
MPESA_PASSKEY = "5a64ad290753ed331b662cf6d83d3149367867c102f964f522390ccbd85cb282"
MPESA_CONSUMER_KEY = "B05zln19QXC3OBL6YuCkdhZ8zvYqZtXP"
MPESA_CONSUMER_SECRET = "MYRasd2p9gGFcuCR"

BASE_URL = "https://chatpesa-whatsapp.onrender.com"

# =========================
# IN-MEMORY STORE (SAFE FOR NOW)
# =========================
orders = {}

# =========================
# HELPERS
# =========================
def generate_order_id():
    return f"CP{os.urandom(3).hex().upper()}"

def mpesa_access_token():
    auth = base64.b64encode(
        f"{MPESA_CONSUMER_KEY}:{MPESA_CONSUMER_SECRET}".encode()
    ).decode()

    res = requests.get(
        "https://sandbox.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials",
        headers={"Authorization": f"Basic {auth}"}
    )
    return res.json()["access_token"]

def stk_push(phone, amount, order_id):
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    password = base64.b64encode(
        f"{MPESA_SHORTCODE}{MPESA_PASSKEY}{timestamp}".encode()
    ).decode()

    payload = {
        "BusinessShortCode": MPESA_SHORTCODE,
        "Password": password,
        "Timestamp": timestamp,
        "TransactionType": "CustomerPayBillOnline",
        "Amount": amount,
        "PartyA": phone,
        "PartyB": MPESA_SHORTCODE,
        "PhoneNumber": phone,
        "CallBackURL": f"{BASE_URL}/mpesa/callback",
        "AccountReference": order_id,
        "TransactionDesc": "ChatPesa Payment"
    }

    token = mpesa_access_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    return requests.post(
        "https://sandbox.safaricom.co.ke/mpesa/stkpush/v1/processrequest",
        headers=headers,
        json=payload
    ).json()

# =========================
# WHATSAPP WEBHOOK
# =========================
@app.route("/webhook/whatsapp", methods=["POST"])
def whatsapp_webhook():
    resp = MessagingResponse()

    body = request.form.get("Body", "").strip().upper()
    phone = request.form.get("From", "").replace("whatsapp:", "")

    # CREATE ORDER
    if body.startswith("ORDER"):
        try:
            amount = int(body.replace("ORDER", "").strip())
            if amount < 10:
                raise ValueError
        except:
            amount = 10

        order_id = generate_order_id()

        orders[order_id] = {
            "id": order_id,
            "customer_name": phone,
            "customer_phone": phone,
            "items": f"Order KES {amount}",
            "amount": amount,
            "status": "AWAITING_PAYMENT",
            "created_at": datetime.utcnow().isoformat()
        }

        resp.message(
            f"Order created ✅\n\n"
            f"Order ID: {order_id}\n"
            f"Amount: KES {amount}\n\n"
            f"Reply PAY to receive M-Pesa prompt."
        )
        return str(resp), 200, {"Content-Type": "text/xml"}

    # PAY FLOW
    if body == "PAY":
        pending = next(
            (o for o in orders.values()
             if o["customer_phone"] == phone and o["status"] == "AWAITING_PAYMENT"),
            None
        )

        if not pending:
            resp.message("No pending order found. Send ORDER <amount> first.")
            return str(resp), 200, {"Content-Type": "text/xml"}

        stk_push(phone, pending["amount"], pending["id"])
        resp.message("M-Pesa prompt sent 📲\nEnter your PIN to complete payment.")
        return str(resp), 200, {"Content-Type": "text/xml"}

    resp.message(
        "Welcome to ChatPesa 💬\n\n"
        "To start:\n"
        "ORDER 10\n"
        "ORDER 50\n"
        "ORDER 100"
    )
    return str(resp), 200, {"Content-Type": "text/xml"}

# =========================
# MPESA CALLBACK
# =========================
@app.route("/mpesa/callback", methods=["POST"])
def mpesa_callback():
    data = request.json

    try:
        stk = data["Body"]["stkCallback"]
        if stk["ResultCode"] == 0:
            meta = stk["CallbackMetadata"]["Item"]
            receipt = meta[1]["Value"]
            phone = meta[4]["Value"]

            for o in orders.values():
                if o["customer_phone"] == str(phone):
                    o["status"] = "PAID"
                    o["mpesa_receipt"] = receipt
                    o["paid_at"] = datetime.utcnow().isoformat()
        return jsonify({"ok": True})
    except:
        return jsonify({"ok": False})

# =========================
# DASHBOARD ENDPOINTS
# =========================
@app.route("/orders")
def get_orders():
    return jsonify({
        "status": "ok",
        "orders": list(orders.values())
    })

@app.route("/")
def health():
    return "ChatPesa API ONLINE"

# =========================
# RUN (RENDER SAFE)
# =========================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=False)
