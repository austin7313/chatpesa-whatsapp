from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import base64
from datetime import datetime
import os

app = Flask(__name__)
CORS(app)

# ---------------- CONFIG ----------------
MPESA_SHORTCODE = os.getenv("MPESA_SHORTCODE")
MPESA_PASSKEY = os.getenv("MPESA_PASSKEY")
MPESA_CONSUMER_KEY = os.getenv("MPESA_CONSUMER_KEY")
MPESA_CONSUMER_SECRET = os.getenv("MPESA_CONSUMER_SECRET")
BASE_URL = os.getenv("BASE_URL")  # https://your-app.onrender.com

orders = []

# ---------------- HELPERS ----------------
def get_access_token():
    url = "https://sandbox.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials"
    r = requests.get(url, auth=(MPESA_CONSUMER_KEY, MPESA_CONSUMER_SECRET))
    return r.json()["access_token"]

def stk_password():
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    data = f"{MPESA_SHORTCODE}{MPESA_PASSKEY}{timestamp}"
    encoded = base64.b64encode(data.encode()).decode()
    return encoded, timestamp

# ---------------- API ----------------
@app.route("/health")
def health():
    return {"status": "ok"}

@app.route("/orders")
def get_orders():
    return jsonify({"status": "ok", "orders": orders})

@app.route("/order/create", methods=["POST"])
def create_order():
    data = request.json
    order_id = f"CP{len(orders)+1001}"

    order = {
        "id": order_id,
        "customer_phone": data["phone"],
        "customer_name": data["phone"],  # temporary
        "items": data.get("items", "Custom Order"),
        "amount": data["amount"],
        "status": "AWAITING_PAYMENT",
        "created_at": datetime.now().isoformat(),
        "paid_at": None,
        "mpesa_receipt": None
    }

    orders.insert(0, order)
    send_stk(order)
    return jsonify(order)

def send_stk(order):
    token = get_access_token()
    password, timestamp = stk_password()

    payload = {
        "BusinessShortCode": MPESA_SHORTCODE,
        "Password": password,
        "Timestamp": timestamp,
        "TransactionType": "CustomerPayBillOnline",
        "Amount": order["amount"],
        "PartyA": order["customer_phone"],
        "PartyB": MPESA_SHORTCODE,
        "PhoneNumber": order["customer_phone"],
        "CallBackURL": f"{BASE_URL}/mpesa/callback",
        "AccountReference": order["id"],
        "TransactionDesc": "ChatPesa Payment"
    }

    headers = {"Authorization": f"Bearer {token}"}
    requests.post(
        "https://sandbox.safaricom.co.ke/mpesa/stkpush/v1/processrequest",
        json=payload,
        headers=headers
    )

# ---------------- MPESA CALLBACK ----------------
@app.route("/mpesa/callback", methods=["POST"])
def mpesa_callback():
    data = request.json
    stk = data["Body"]["stkCallback"]

    if stk["ResultCode"] != 0:
        return jsonify({"status": "failed"})

    meta = stk["CallbackMetadata"]["Item"]

    def get(name):
        for i in meta:
            if i["Name"] == name:
                return i.get("Value")
        return None

    receipt = get("MpesaReceiptNumber")
    phone = get("PhoneNumber")
    paid_at = get("TransactionDate")
    first = get("FirstName") or ""
    middle = get("MiddleName") or ""
    last = get("LastName") or ""
    payer_name = f"{first} {middle} {last}".strip()

    order_id = stk["MerchantRequestID"]

    for o in orders:
        if o["id"] == order_id:
            o["customer_name"] = payer_name
            o["status"] = "PAID"
            o["mpesa_receipt"] = receipt
            o["paid_at"] = paid_at

    return jsonify({"status": "ok"})

# ---------------- RUN ----------------
if __name__ == "__main__":
    app.run()
