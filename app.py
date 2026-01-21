from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
from datetime import datetime
import random
import requests
import base64
import json

app = Flask(__name__)

# ====== M-PESA CONFIG ======
MPESA_SHORTCODE = "4031193"
MPESA_PASSKEY = "5a64ad290753ed331b662cf6d83d3149367867c102f964f522390ccbd85cb282"
MPESA_CONSUMER_KEY = "B05zln19QXC3OBL6YuCkdhZ8zYqZtXP"
MPESA_CONSUMER_SECRET = "MYRasd2p9gGFcuCR"
MPESA_ENV = "sandbox"  # change to 'live' in production

# ====== RESTAURANT CONFIG ======
RESTAURANT = {
    "name": "CARIBOU KARIBU",
    "paybill": "247247"
}

# In-memory store (replace with DB in production)
orders_db = []

# ====== HELPERS ======
def generate_order_id():
    return f"ORD{random.randint(100000, 999999)}"

def parse_order_message(msg):
    msg_lower = msg.lower()
    items, amount = [], 0
    if "burger" in msg_lower:
        items.append("Burger")
        amount += 500
    if "fries" in msg_lower:
        items.append("Fries")
        amount += 200
    if "pizza" in msg_lower:
        items.append("Pizza")
        amount += 800
    if not items:
        items.append("Custom Order")
        amount = 1000
    return {"items": " + ".join(items), "amount": amount}

def get_mpesa_token():
    auth = f"{MPESA_CONSUMER_KEY}:{MPESA_CONSUMER_SECRET}"
    b64 = base64.b64encode(auth.encode()).decode()
    url = f"https://sandbox.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials" if MPESA_ENV=="sandbox" else "https://api.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials"
    res = requests.get(url, headers={"Authorization": f"Basic {b64}"})
    return res.json().get("access_token")

def initiate_stk_push(order_id, amount, phone):
    token = get_mpesa_token()
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    password = base64.b64encode(f"{MPESA_SHORTCODE}{MPESA_PASSKEY}{timestamp}".encode()).decode()
    stk_url = "https://sandbox.safaricom.co.ke/mpesa/stkpush/v1/processrequest" if MPESA_ENV=="sandbox" else "https://api.safaricom.co.ke/mpesa/stkpush/v1/processrequest"
    payload = {
        "BusinessShortCode": MPESA_SHORTCODE,
        "Password": password,
        "Timestamp": timestamp,
        "TransactionType": "CustomerPayBillOnline",
        "Amount": amount,
        "PartyA": phone,
        "PartyB": MPESA_SHORTCODE,
        "PhoneNumber": phone,
        "CallBackURL": "https://chatpesa-whatsapp.onrender.com/mpesa/callback",
        "AccountReference": order_id,
        "TransactionDesc": f"Payment for {order_id}"
    }
    res = requests.post(stk_url, json=payload, headers={"Authorization": f"Bearer {token}"})
    return res.json()

# ====== ROUTES ======
@app.route("/webhook/whatsapp", methods=["POST"])
def whatsapp_webhook():
    try:
        incoming_msg = request.form.get("Body", "").strip()
        from_number = request.form.get("From", "").replace("whatsapp:", "")
        profile_name = request.form.get("ProfileName", "Customer")
        
        order_details = parse_order_message(incoming_msg)
        order_id = generate_order_id()
        
        # Initiate M-Pesa STK Push
        stk_res = initiate_stk_push(order_id, order_details["amount"], f"254{from_number[-9:]}")
        
        order_data = {
            "id": order_id,
            "customer_name": profile_name,
            "customer_phone": from_number,
            "items": order_details["items"],
            "amount": order_details["amount"],
            "status": "AWAITING_PAYMENT",
            "created_at": datetime.utcnow().isoformat(),
            "stk_response": stk_res
        }
        
        orders_db.append(order_data)
        
        resp = MessagingResponse()
        resp.message(
            f"✅ Order received!\n\n"
            f"📋 {order_details['items']}\n"
            f"💰 KES {order_details['amount']}\n"
            f"💳 Pay Now (M-Pesa prompt should appear on your phone)\n"
            f"Order ID: {order_id}"
        )
        return str(resp), 200, {"Content-Type": "text/xml"}
    
    except Exception as e:
        resp = MessagingResponse()
        resp.message("❌ Error processing your order. Try again.")
        return str(resp), 200, {"Content-Type": "text/xml"}

@app.route("/mpesa/callback", methods=["POST"])
def mpesa_callback():
    data = request.json
    order_ref = data.get("Body", {}).get("stkCallback", {}).get("CheckoutRequestID", "")
    result_code = data.get("Body", {}).get("stkCallback", {}).get("ResultCode", 1)
    phone = data.get("Body", {}).get("stkCallback", {}).get("CallbackMetadata", {}).get("Item", [{}])[1].get("Value", "")
    
    # Find order and update
    for order in orders_db:
        if order["id"] == order_ref:
            order["status"] = "PAID" if result_code == 0 else "FAILED"
            order["paid_at"] = datetime.utcnow().isoformat()
            break
    return {"success": True}

@app.route("/orders")
def get_orders():
    return {"status": "ok", "orders": orders_db}

@app.route("/health")
def health():
    return {"status": "ok", "service": "chatpesa"}

if __name__ == "__main__":
    app.run(debug=True)
