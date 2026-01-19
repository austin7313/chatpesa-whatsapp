import os
import base64
import datetime
import requests
from flask import Flask, request, jsonify
from twilio.twiml.messaging_response import MessagingResponse

app = Flask(__name__)

# =========================
# CONFIG — PRODUCTION
# =========================
MPESA_CONSUMER_KEY = os.getenv("MPESA_CONSUMER_KEY")
MPESA_CONSUMER_SECRET = os.getenv("MPESA_CONSUMER_SECRET")
MPESA_SHORTCODE = os.getenv("MPESA_SHORTCODE")
MPESA_PASSKEY = os.getenv("MPESA_PASSKEY")

MPESA_BASE_URL = "https://api.safaricom.co.ke"

# In-memory store (OK for MVP)
orders = {}

# =========================
# HELPERS
# =========================
def get_mpesa_access_token():
    url = f"{MPESA_BASE_URL}/oauth/v1/generate?grant_type=client_credentials"
    response = requests.get(url, auth=(MPESA_CONSUMER_KEY, MPESA_CONSUMER_SECRET))
    response.raise_for_status()
    return response.json()["access_token"]

def lipa_na_mpesa(phone, amount, account_ref):
    token = get_mpesa_access_token()

    timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
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
        "CallBackURL": os.getenv("MPESA_CALLBACK_URL"),
        "AccountReference": account_ref,
        "TransactionDesc": "WhatsApp Order Payment"
    }

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    url = f"{MPESA_BASE_URL}/mpesa/stkpush/v1/processrequest"
    res = requests.post(url, json=payload, headers=headers)
    res.raise_for_status()
    return res.json()

# =========================
# ROUTES
# =========================
@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "service": "ChatPesa WhatsApp Payments",
        "status": "running",
        "endpoints": [
            "/health",
            "/webhook/whatsapp",
            "/mpesa/callback"
        ]
    })

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})

@app.route("/webhook/whatsapp", methods=["POST"])
def whatsapp_webhook():
    incoming = request.form.get("Body", "").strip().lower()
    from_number = request.form.get("From", "")

    resp = MessagingResponse()

    if incoming.startswith("order"):
        try:
            amount = int(incoming.split(" ")[1])
            order_id = str(len(orders) + 1)

            orders[order_id] = {
                "phone": from_number.replace("whatsapp:", ""),
                "amount": amount,
                "status": "created"
            }

            msg = f"Order #{order_id} created. Amount KES {amount}. Reply 'pay {order_id}' to pay now."
            resp.message(msg)
        except:
            resp.message("Invalid order format. Use: order 100")

    elif incoming.startswith("pay"):
        try:
            order_id = incoming.split(" ")[1]
            order = orders.get(order_id)

            if not order:
                resp.message("Order not found.")
            elif order["status"] == "paid":
                resp.message("This order is already paid.")
            else:
                phone = order["phone"].replace("+", "")
                amount = order["amount"]

                lipa_na_mpesa(phone, amount, f"ORDER{order_id}")
                order["status"] = "payment_requested"

                resp.message(f"STK push sent for Order #{order_id}. Enter your M-Pesa PIN to pay KES {amount}.")
        except Exception as e:
            print("Payment error:", e)
            resp.message(f"Payment error: {e}")

    else:
        resp.message("Welcome to ChatPesa.\n\nCommands:\norder 100\npay 1")

    return str(resp)

@app.route("/mpesa/callback", methods=["POST"])
def mpesa_callback():
    data = request.get_json()
    print("M-Pesa Callback:", data)
    return jsonify({"ResultCode": 0, "ResultDesc": "Accepted"})

# =========================
# START
# =========================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
