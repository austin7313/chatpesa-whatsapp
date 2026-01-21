from flask import Flask, request, jsonify
from flask_cors import CORS
from twilio.twiml.messaging_response import MessagingResponse
import random
from datetime import datetime
import requests

app = Flask(__name__)
CORS(app)

# ===== M-PESA CONFIG =====
MPESA_SHORTCODE = "4031193"
MPESA_PASSKEY = "5a64ad290753ed331b662cf6d83d3149367867c102f964f522390ccbd85cb282"
CONSUMER_KEY = "B05zln19QXC3OBL6YuCkdhZ8zvYqZtXP"
CONSUMER_SECRET = "MYRasd2p9gGFcuCR"
MPESA_API_BASE = "https://sandbox.safaricom.co.ke"  # Change to production for live

# In-memory orders DB (replace with your DB later)
orders_db = []

def generate_order_id():
    return f"ORD{random.randint(100000, 999999)}"

def parse_order_message(message):
    message_lower = message.lower()
    items = []
    amount = 0
    if "subscription" in message_lower:
        items.append("Subscription")
        amount += 1500
    if "service" in message_lower:
        items.append("Service")
        amount += 1000
    if not items:
        items.append("Custom Order")
        amount = 1000
    return {"items": " + ".join(items), "amount": amount}

def get_mpesa_token():
    auth_url = f"{MPESA_API_BASE}/oauth/v1/generate?grant_type=client_credentials"
    r = requests.get(auth_url, auth=(CONSUMER_KEY, CONSUMER_SECRET))
    return r.json().get("access_token")

def initiate_stk_push(phone, amount, order_id):
    token = get_mpesa_token()
    stk_url = f"{MPESA_API_BASE}/mpesa/stkpush/v1/processrequest"
    payload = {
        "BusinessShortCode": MPESA_SHORTCODE,
        "Password": MPESA_PASSKEY,  # Normally base64 encoded (simplified here)
        "Timestamp": datetime.utcnow().strftime("%Y%m%d%H%M%S"),
        "TransactionType": "CustomerPayBillOnline",
        "Amount": amount,
        "PartyA": phone,
        "PartyB": MPESA_SHORTCODE,
        "PhoneNumber": phone,
        "CallBackURL": "https://chatpesa-whatsapp.onrender.com/mpesa/callback",
        "AccountReference": order_id,
        "TransactionDesc": "Payment for ChatPesa order",
    }
    headers = {"Authorization": f"Bearer {token}"}
    r = requests.post(stk_url, json=payload, headers=headers)
    return r.json()

# ===== WhatsApp Webhook =====
@app.route("/webhook/whatsapp", methods=["POST"])
def whatsapp_webhook():
    incoming_msg = request.form.get("Body", "").strip()
    from_number = request.form.get("From", "").replace("whatsapp:", "")
    profile_name = request.form.get("ProfileName", "Customer")
    
    order_details = parse_order_message(incoming_msg)
    order_id = generate_order_id()
    
    # Save order
    order_data = {
        "id": order_id,
        "customer_phone": from_number,
        "customer_name": profile_name,
        "items": order_details["items"],
        "amount": order_details["amount"],
        "status": "AWAITING_PAYMENT",
        "created_at": datetime.utcnow().isoformat(),
        "mpesa_transaction": None
    }
    orders_db.append(order_data)
    
    # Initiate STK Push
    stk_response = initiate_stk_push(from_number, order_details["amount"], order_id)
    
    # Send WhatsApp reply
    resp = MessagingResponse()
    resp.message(
        f"✅ Order received!\n\n"
        f"📋 {order_details['items']}\n"
        f"💰 Amount: KES {order_details['amount']}\n"
        f"💳 Pay via M-Pesa (STK push sent)\n"
        f"Order ID: {order_id}"
    )
    
    return str(resp), 200, {'Content-Type': 'text/xml'}

# ===== M-PESA Callback =====
@app.route("/mpesa/callback", methods=["POST"])
def mpesa_callback():
    data = request.json
    # Example fields: {"Body":{"stkCallback":{"MerchantRequestID":"","CheckoutRequestID":"","ResultCode":0,"ResultDesc":"Success","CallbackMetadata":{"Item":[{"Name":"Amount","Value":1000},{"Name":"MpesaReceiptNumber","Value":"ABC123"},{"Name":"PhoneNumber","Value":2547XXXXXXX},{"Name":"TransactionDate","Value":20260122}]}}}}
    
    callback = data.get("Body", {}).get("stkCallback", {})
    result_code = callback.get("ResultCode")
    metadata_items = callback.get("CallbackMetadata", {}).get("Item", [])
    
    mpesa_data = {item["Name"]: item["Value"] for item in metadata_items}
    checkout_id = callback.get("CheckoutRequestID")
    
    # Find order by ID
    for o in orders_db:
        if o["id"] == mpesa_data.get("AccountReference", o["id"]):
            if result_code == 0:
                o["status"] = "PAID"
                o["mpesa_transaction"] = mpesa_data.get("MpesaReceiptNumber")
                o["customer_name"] = mpesa_data.get("FirstName", o["customer_name"])
            else:
                o["status"] = "FAILED"
            break
    
    return jsonify({"status": "ok"})

# ===== Orders Endpoint =====
@app.route("/orders")
def get_orders():
    return jsonify({"status": "ok", "orders": orders_db})

# ===== Health =====
@app.route("/health")
def health():
    return jsonify({"status": "ok", "service": "chatpesa"})

if __name__ == "__main__":
    app.run(debug=True)
