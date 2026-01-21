from flask import Flask, request, jsonify
from flask_cors import CORS
from twilio.twiml.messaging_response import MessagingResponse
import random
from datetime import datetime
import requests
import base64

app = Flask(__name__)
CORS(app)

# -------------------------
# Config
# -------------------------
RESTAURANT = {"name": "CARIBOU KARIBU", "paybill": "247247"}
MPESA = {
    "shortcode": "4031193",
    "passkey": "5a64ad290753ed331b662cf6d83d3149367867c102f964f522390ccbd85cb282",
    "consumer_key": "B05zln19QXC3OBL6YuCkdhZ8zvYqZtXP",
    "consumer_secret": "MYRasd2p9gGFcuCR",
    "env": "sandbox",  # switch to "production" when live
}
ORDERS = []

# -------------------------
# Helpers
# -------------------------
def generate_order_id():
    return f"ORD{random.randint(100000, 999999)}"

def parse_order_message(message):
    message_lower = message.lower()
    items = []
    amount = 0
    if "burger" in message_lower:
        items.append("Burger")
        amount += 500
    if "fries" in message_lower:
        items.append("Fries")
        amount += 200
    if "pizza" in message_lower:
        items.append("Pizza")
        amount += 800
    if not items:
        items.append("Custom Order")
        amount = 1000
    return {"items": " + ".join(items), "amount": amount}

def get_mpesa_token():
    url = f"https://{ 'sandbox.safaricom.co.ke' if MPESA['env']=='sandbox' else 'api.safaricom.co.ke' }/oauth/v1/generate?grant_type=client_credentials"
    auth = base64.b64encode(f"{MPESA['consumer_key']}:{MPESA['consumer_secret']}".encode()).decode()
    res = requests.get(url, headers={"Authorization": f"Basic {auth}"})
    return res.json()["access_token"]

# -------------------------
# WhatsApp Webhook
# -------------------------
@app.route("/webhook/whatsapp", methods=["POST"])
def whatsapp_webhook():
    incoming_msg = request.form.get("Body", "").strip()
    from_number = request.form.get("From", "").replace("whatsapp:", "")
    profile_name = request.form.get("ProfileName", "Customer")

    order_details = parse_order_message(incoming_msg)
    order_id = generate_order_id()
    order_data = {
        "id": order_id,
        "customer_phone": from_number,
        "customer_name": profile_name,
        "items": order_details["items"],
        "amount": order_details["amount"],
        "status": "AWAITING_PAYMENT",
        "payment_code": order_id,
        "raw_message": incoming_msg,
        "created_at": datetime.utcnow().isoformat()
    }
    ORDERS.append(order_data)

    resp = MessagingResponse()
    payment_message = f"""✅ Order received from {RESTAURANT['name']}!
📋 Your Order: {order_details['items']}
💰 Total: KES {order_details['amount']:,}
💳 Pay Now: Paybill {RESTAURANT['paybill']}, Account: {order_id}
Reply DONE when paid. Order ID: {order_id}"""
    resp.message(payment_message)
    return str(resp), 200, {'Content-Type': 'text/xml'}

# -------------------------
# Initiate M-Pesa STK Push
# -------------------------
@app.route("/mpesa/stkpush", methods=["POST"])
def stk_push():
    data = request.json
    order_id = data.get("order_id")
    phone = data.get("phone")
    order = next((o for o in ORDERS if o["id"]==order_id), None)
    if not order:
        return jsonify({"status": "error", "msg": "Order not found"}), 404

    token = get_mpesa_token()
    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    password = base64.b64encode(f"{MPESA['shortcode']}{MPESA['passkey']}{timestamp}".encode()).decode()

    url = f"https://{ 'sandbox.safaricom.co.ke' if MPESA['env']=='sandbox' else 'api.safaricom.co.ke' }/mpesa/stkpush/v1/processrequest"
    payload = {
        "BusinessShortCode": MPESA["shortcode"],
        "Password": password,
        "Timestamp": timestamp,
        "TransactionType": "CustomerPayBillOnline",
        "Amount": order["amount"],
        "PartyA": phone,
        "PartyB": MPESA["shortcode"],
        "PhoneNumber": phone,
        "CallBackURL": "https://yourdomain.com/mpesa/callback",
        "AccountReference": order_id,
        "TransactionDesc": f"Payment for order {order_id}"
    }
    res = requests.post(url, json=payload, headers={"Authorization": f"Bearer {token}"})
    return res.json()

# -------------------------
# M-Pesa Callback
# -------------------------
@app.route("/mpesa/callback", methods=["POST"])
def mpesa_callback():
    data = request.json
    try:
        stk_result = data["Body"]["stkCallback"]
        checkout_id = stk_result["CheckoutRequestID"]
        result_code = stk_result["ResultCode"]

        order = next((o for o in ORDERS if o["payment_code"]==checkout_id), None)
        if order and result_code == 0:
            item = order
            item["status"] = "PAID"
            item["mpesa_time"] = datetime.utcnow().isoformat()
            items_meta = stk_result.get("CallbackMetadata", {}).get("Item", [])
            if items_meta:
                item["mpesa_phone"] = items_meta[0]["Value"]
                item["mpesa_name"] = items_meta[1]["Value"]
    except Exception as e:
        print("MPESA CALLBACK ERROR:", e)
    return jsonify({"status": "ok"}), 200

# -------------------------
# Orders endpoint
# -------------------------
@app.route("/orders")
def get_orders():
    return {"status": "ok", "orders": ORDERS}

# -------------------------
# Health
# -------------------------
@app.route("/health")
def health():
    return {"status": "ok"}

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
