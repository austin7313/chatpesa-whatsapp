from flask import Flask, request, jsonify
from flask_cors import CORS
from twilio.twiml.messaging_response import MessagingResponse
import random
from datetime import datetime
import requests
import base64

app = Flask(__name__)
CORS(app)

# In-memory storage
orders = []

# Config
RESTAURANT = {"name": "ChatPesa", "paybill": "247247"}
MPESA_SHORTCODE = "4031193"
MPESA_PASSKEY = "5a64ad290753ed331b662cf6d83d3149367867c102f964f522390ccbd85cb282"
CONSUMER_KEY = "B05zln19QXC3OBL6YuCkdhZ8zvYqZtXP"
CONSUMER_SECRET = "MYRasd2p9gGFcuCR"
MPESA_BASE = "https://sandbox.safaricom.co.ke"  # switch to live for production

def generate_order_id():
    return f"CP{random.randint(100000, 999999):06X}"

def parse_order_message(msg):
    msg = msg.lower()
    items = []
    amount = 0
    if "burger" in msg:
        items.append("Burger")
        amount += 500
    if "fries" in msg:
        items.append("Fries")
        amount += 200
    if "pizza" in msg:
        items.append("Pizza")
        amount += 800
    if not items:
        items.append("Custom Order")
        amount = 1000
    return {"items": " + ".join(items), "amount": amount}

def get_mpesa_token():
    auth = base64.b64encode(f"{CONSUMER_KEY}:{CONSUMER_SECRET}".encode()).decode()
    res = requests.get(f"{MPESA_BASE}/oauth/v1/generate?grant_type=client_credentials",
                       headers={"Authorization": f"Basic {auth}"})
    return res.json()["access_token"]

def stk_push(phone, amount, order_id):
    token = get_mpesa_token()
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    password = base64.b64encode(f"{MPESA_SHORTCODE}{MPESA_PASSKEY}{timestamp}".encode()).decode()
    payload = {
        "BusinessShortCode": MPESA_SHORTCODE,
        "Password": password,
        "Timestamp": timestamp,
        "TransactionType": "CustomerPayBillOnline",
        "Amount": amount,
        "PartyA": phone,
        "PartyB": MPESA_SHORTCODE,
        "PhoneNumber": phone,
        "CallBackURL": f"https://yourdomain.com/mpesa/callback",
        "AccountReference": order_id,
        "TransactionDesc": "ChatPesa Order Payment"
    }
    res = requests.post(f"{MPESA_BASE}/mpesa/stkpush/v1/processrequest",
                        json=payload,
                        headers={"Authorization": f"Bearer {token}"})
    return res.json()

@app.route("/webhook/whatsapp", methods=["POST"])
def whatsapp_webhook():
    incoming_msg = request.form.get("Body", "").strip()
    from_number = request.form.get("From", "").replace("whatsapp:", "")
    profile_name = request.form.get("ProfileName", from_number)

    order_details = parse_order_message(incoming_msg)
    order_id = generate_order_id()

    order = {
        "id": order_id,
        "customer_name": profile_name,
        "customer_phone": from_number,
        "items": order_details["items"],
        "amount": order_details["amount"],
        "status": "AWAITING_PAYMENT",
        "created_at": datetime.utcnow().isoformat()
    }
    orders.append(order)

    resp = MessagingResponse()
    resp.message(
        f"✅ Order received!\nOrder ID: {order_id}\nItems: {order['items']}\n"
        f"Amount: KES {order['amount']}\nReply 'PAY' to pay via M-Pesa."
    )

    return str(resp), 200, {'Content-Type': 'text/xml'}

@app.route("/webhook/pay", methods=["POST"])
def whatsapp_pay():
    incoming_msg = request.form.get("Body", "").strip().lower()
    from_number = request.form.get("From", "").replace("whatsapp:", "")
    
    if incoming_msg != "pay":
        resp = MessagingResponse()
        resp.message("Please reply with 'PAY' to initiate payment.")
        return str(resp), 200, {'Content-Type': 'text/xml'}

    # Find order
    order = next((o for o in orders if o["customer_phone"] == from_number and o["status"]=="AWAITING_PAYMENT"), None)
    resp = MessagingResponse()
    if not order:
        resp.message("No pending order found. Send a message to place an order first.")
        return str(resp), 200, {'Content-Type': 'text/xml'}

    # Initiate STK push
    stk_resp = stk_push(from_number, order["amount"], order["id"])
    resp.message("📲 Payment request sent. Check your M-Pesa and complete the payment.")
    return str(resp), 200, {'Content-Type': 'text/xml'}

@app.route("/mpesa/callback", methods=["POST"])
def mpesa_callback():
    data = request.get_json()
    # parse result
    if data and "Body" in data:
        callback = data["Body"]["stkCallback"]
        order_id = callback["CheckoutRequestID"]
        result_code = callback["ResultCode"]
        amount = callback["CallbackMetadata"]["Item"][0]["Value"]
        mpesa_name = callback["CallbackMetadata"]["Item"][1]["Value"]
        phone = callback["CallbackMetadata"]["Item"][4]["Value"]
        
        # Update order
        order = next((o for o in orders if o["id"] == order_id), None)
        if order:
            order["status"] = "PAID" if result_code==0 else "FAILED"
            order["customer_name"] = mpesa_name
            order["amount"] = amount
            order["customer_phone"] = phone
            order["paid_at"] = datetime.utcnow().isoformat()
    return jsonify({"ResultCode": 0, "ResultDesc": "Accepted"})

@app.route("/orders", methods=["GET"])
def get_orders():
    return {"status": "ok", "orders": orders}

@app.route("/health", methods=["GET"])
def health():
    return {"status": "ok", "service": "chatpesa"}

if __name__ == "__main__":
    app.run(debug=True)
