import base64
import requests
from flask import Flask, request, jsonify
from twilio.twiml.messaging_response import MessagingResponse
from datetime import datetime
import random

app = Flask(__name__)

# M-Pesa credentials
MPESA_SHORTCODE = "4031193"
MPESA_PASSKEY = "5a64ad290753ed331b662cf6d83d3149367867c102f964f522390ccbd85cb"
MPESA_CONSUMER_KEY = "B05zln19QXC3OBL6YuCkdhZ8zvYqZtXP"
MPESA_CONSUMER_SECRET = "MYRasd2p9gGFcuCR"
CALLBACK_URL = "https://chatpesa-whatsapp.onrender.com/mpesa/callback"

# In-memory DB (replace with real DB in production)
ORDERS_DB = []

def generate_order_id():
    return f"ORD{random.randint(100000,999999)}"

def get_mpesa_token():
    auth = base64.b64encode(f"{MPESA_CONSUMER_KEY}:{MPESA_CONSUMER_SECRET}".encode()).decode()
    url = "https://sandbox.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials"
    headers = {"Authorization": f"Basic {auth}"}
    res = requests.get(url, headers=headers)
    return res.json()["access_token"]

def initiate_stk_push(phone, amount, order_id):
    token = get_mpesa_token()
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    password_str = f"{MPESA_SHORTCODE}{MPESA_PASSKEY}{timestamp}"
    password = base64.b64encode(password_str.encode()).decode()
    stk_url = "https://sandbox.safaricom.co.ke/mpesa/stkpush/v1/processrequest"
    payload = {
        "BusinessShortCode": MPESA_SHORTCODE,
        "Password": password,
        "Timestamp": timestamp,
        "TransactionType": "CustomerPayBillOnline",
        "Amount": amount,
        "PartyA": phone,
        "PartyB": MPESA_SHORTCODE,
        "PhoneNumber": phone,
        "CallBackURL": CALLBACK_URL,
        "AccountReference": order_id,
        "TransactionDesc": "ChatPesa Order Payment"
    }
    headers = {"Authorization": f"Bearer {token}"}
    r = requests.post(stk_url, json=payload, headers=headers)
    return r.json()

@app.route("/webhook/whatsapp", methods=["POST"])
def whatsapp_webhook():
    incoming_msg = request.form.get("Body", "").strip()
    from_number = request.form.get("From", "").replace("whatsapp:", "")
    profile_name = request.form.get("ProfileName", "Customer")

    order_id = generate_order_id()
    amount = 1000  # default, parse message if needed

    order = {
        "id": order_id,
        "customer_name": profile_name,
        "customer_phone": from_number,
        "amount": amount,
        "status": "AWAITING_PAYMENT",
        "created_at": datetime.utcnow().isoformat(),
        "mpesa_name": ""
    }
    ORDERS_DB.append(order)

    stk_response = initiate_stk_push(from_number, amount, order_id)
    print("STK PUSH RESPONSE:", stk_response)

    resp = MessagingResponse()
    resp.message(f"✅ Order {order_id} received! Initiating payment on M-Pesa...")

    return str(resp), 200, {'Content-Type': 'text/xml'}

@app.route("/mpesa/callback", methods=["POST"])
def mpesa_callback():
    data = request.json
    try:
        callback = data["Body"]["stkCallback"]
        order_id = callback["CheckoutRequestID"]
        result_code = callback["ResultCode"]
        items = callback.get("CallbackMetadata", {}).get("Item", [])

        amount = None
        mpesa_name = ""
        phone = ""
        for i in items:
            if i.get("Name") == "Amount":
                amount = i.get("Value")
            elif i.get("Name") == "MpesaReceiptNumber":
                mpesa_name = i.get("Value")
            elif i.get("Name") == "PhoneNumber":
                phone = i.get("Value")

        timestamp = datetime.utcnow().isoformat()

        for o in ORDERS_DB:
            if o["id"] == order_id:
                o["status"] = "PAID" if result_code == 0 else "FAILED"
                o["mpesa_name"] = mpesa_name
                o["amount"] = amount or o["amount"]
                o["paid_at"] = timestamp
                break

        print("✅ Payment callback processed:", order_id)
        return jsonify({"status": "ok"}), 200
    except Exception as e:
        print("❌ Callback error:", str(e))
        return jsonify({"status": "error"}), 200

@app.route("/orders")
def get_orders():
    return jsonify({"status": "ok", "orders": ORDERS_DB})

@app.route("/health")
def health():
    return {"status": "ok", "service": "chatpesa"}

if __name__ == "__main__":
    app.run(debug=True)
