import os
import base64
import requests
from datetime import datetime
from flask import Flask, request, jsonify
from flask_cors import CORS
from twilio.twiml.messaging_response import MessagingResponse

app = Flask(__name__)
CORS(app)

# ===============================
# CONFIG
# ===============================
MPESA_SHORTCODE = "4031193"
MPESA_PASSKEY = "5a64ad290753ed331b662cf6d83d3149367867c102f964f522390ccbd85cb282"
MPESA_CONSUMER_KEY = "B05zln19QXC3OBL6YuCkdhZ8zvYqZtXP"
MPESA_CONSUMER_SECRET = "MYRasd2p9gGFcuCR"

CALLBACK_URL = "https://chatpesa-whatsapp.onrender.com/mpesa/callback"

# In-memory store (replace with DB later)
orders = {}

# ===============================
# MPESA HELPERS
# ===============================
def mpesa_access_token():
    auth = base64.b64encode(
        f"{MPESA_CONSUMER_KEY}:{MPESA_CONSUMER_SECRET}".encode()
    ).decode()

    res = requests.get(
        "https://api.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials",
        headers={"Authorization": f"Basic {auth}"},
        timeout=30
    )
    return res.json().get("access_token")


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
        "Amount": int(order["amount"]),
        "PartyA": order["phone"],
        "PartyB": MPESA_SHORTCODE,
        "PhoneNumber": order["phone"],
        "CallBackURL": CALLBACK_URL,
        "AccountReference": order["id"],
        "TransactionDesc": "ChatPesa Payment"
    }

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    res = requests.post(
        "https://api.safaricom.co.ke/mpesa/stkpush/v1/processrequest",
        json=payload,
        headers=headers,
        timeout=30
    )

    print("STK STATUS:", res.status_code)
    print("STK RESPONSE:", res.text)

    return res.json()

# ===============================
# WHATSAPP WEBHOOK
# ===============================
@app.route("/webhook/whatsapp", methods=["POST"])
def whatsapp_webhook():
    body = request.form.get("Body", "")
    body = body.strip().upper().replace(" ", "")

    phone = request.form.get("From", "")
    phone = phone.replace("whatsapp:", "").replace("+", "")

    resp = MessagingResponse()

    # CREATE ORDER
    if body.startswith("ORDER"):
        order_id = f"CP{os.urandom(3).hex().upper()}"
        amount = 1000  # dynamic later

        orders[order_id] = {
            "id": order_id,
            "phone": phone,
            "customer_name": phone,
            "items": body,
            "amount": amount,
            "status": "AWAITING_PAYMENT",
            "created_at": datetime.utcnow().isoformat()
        }

        resp.message(
            f"Order received.\n"
            f"Order ID: {order_id}\n"
            f"Amount: KES {amount}\n\n"
            f"Reply PAY to pay via M-Pesa."
        )
        return str(resp)

    # PAY CONFIRMATION
    if body == "PAY":
        pending = next(
            (o for o in orders.values()
             if o["phone"] == phone and o["status"] == "AWAITING_PAYMENT"),
            None
        )

        if not pending:
            resp.message("No pending order found.")
            return str(resp)

        send_stk_push(pending)
        pending["status"] = "STK_SENT"

        resp.message("M-Pesa prompt sent. Check your phone.")
        return str(resp)

    resp.message("Send ORDER <details> to begin.")
    return str(resp)

# ===============================
# MPESA CALLBACK
# ===============================
@app.route("/mpesa/callback", methods=["POST"])
def mpesa_callback():
    data = request.json
    print("CALLBACK:", data)

    stk = data["Body"]["stkCallback"]
    if stk["ResultCode"] != 0:
        return jsonify({"ok": True})

    meta = stk["CallbackMetadata"]["Item"]
    info = {i["Name"]: i.get("Value") for i in meta}

    receipt = info.get("MpesaReceiptNumber")
    phone = str(info.get("PhoneNumber"))
    name = info.get("TransactionDesc", "Paid User")

    for o in orders.values():
        if o["phone"] == phone and o["status"] == "STK_SENT":
            o["status"] = "PAID"
            o["mpesa_receipt"] = receipt
            o["customer_name"] = name
            o["paid_at"] = datetime.utcnow().isoformat()

    return jsonify({"ok": True})

# ===============================
# DASHBOARD API
# ===============================
@app.route("/orders")
def get_orders():
    return jsonify({
        "status": "ok",
        "orders": list(orders.values())
    })

@app.route("/health")
def health():
    return jsonify({"status": "ok"})

# ===============================
# RUN (RENDER SAFE)
# ===============================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
