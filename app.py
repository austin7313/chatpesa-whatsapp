from flask import Flask, request, jsonify
from flask_cors import CORS
from twilio.twiml.messaging_response import MessagingResponse
from datetime import datetime
import requests

app = Flask(__name__)
CORS(app)

# In-memory orders storage (replace with DB in prod)
orders = {}

# M-Pesa credentials
MPESA_SHORTCODE = "4031193"
MPESA_PASSKEY = "5a64ad290753ed331b662cf6d83d3149367867c102f964f522390ccbd85cb282"
MPESA_CONSUMER_KEY = "B05zln19QXC3OBL6YuCkdhZ8zvYqZtXP"
MPESA_CONSUMER_SECRET = "MYRasd2p9gGFcuCR"
MPESA_ENV = "sandbox"  # change to 'production' in prod
MPESA_BASE = "https://sandbox.safaricom.co.ke" if MPESA_ENV == "sandbox" else "https://api.safaricom.co.ke"

def get_mpesa_token():
    from requests.auth import HTTPBasicAuth
    url = f"{MPESA_BASE}/oauth/v1/generate?grant_type=client_credentials"
    res = requests.get(url, auth=HTTPBasicAuth(MPESA_CONSUMER_KEY, MPESA_CONSUMER_SECRET))
    token = res.json().get("access_token")
    return token

def initiate_stk_push(phone_number, amount, order_id):
    token = get_mpesa_token()
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    import base64
    password = base64.b64encode(f"{MPESA_SHORTCODE}{MPESA_PASSKEY}{timestamp}".encode()).decode()
    stk_url = f"{MPESA_BASE}/mpesa/stkpush/v1/processrequest"
    headers = {"Authorization": f"Bearer {token}"}
    payload = {
        "BusinessShortCode": MPESA_SHORTCODE,
        "Password": password,
        "Timestamp": timestamp,
        "TransactionType": "CustomerPayBillOnline",
        "Amount": amount,
        "PartyA": phone_number,
        "PartyB": MPESA_SHORTCODE,
        "PhoneNumber": phone_number,
        "CallBackURL": "https://yourdomain.com/callback",  # Replace with your callback
        "AccountReference": order_id,
        "TransactionDesc": f"Payment for order {order_id}"
    }
    res = requests.post(stk_url, json=payload, headers=headers)
    return res.json()

@app.route("/webhook/whatsapp", methods=["POST"])
def whatsapp_webhook():
    incoming_msg = request.values.get('Body', '').strip().lower()
    from_number = request.values.get('From', '')
    response = MessagingResponse()
    msg = response.message()

    # Check if user has existing pending order
    user_order = None
    for o in orders.values():
        if o['phone'] == from_number and o['status'] == 'AWAITING_PAYMENT':
            user_order = o
            break

    if "order" in incoming_msg:
        # Create new order
        order_id = f"CP{datetime.now().strftime('%H%M%S')}"
        order = {
            "id": order_id,
            "phone": from_number,
            "customer_name": from_number,  # Will be updated with M-Pesa name after payment
            "items": incoming_msg.replace("order", "").strip() or "Custom Order",
            "amount": 1000,  # Default; can later parse actual amounts
            "status": "AWAITING_PAYMENT",
            "created_at": datetime.now().isoformat()
        }
        orders[order_id] = order
        msg.body(f"✅ Order {order_id} created. Reply with 'PAY' to proceed with M-Pesa payment.")
        return str(response)

    elif "pay" in incoming_msg and user_order:
        # Initiate STK push
        res = initiate_stk_push(user_order['phone'].replace("whatsapp:", ""), user_order['amount'], user_order['id'])
        msg.body(f"💳 Payment request sent! Check your phone for M-Pesa prompt.\n\n{res}")
        return str(response)

    else:
        msg.body("Hi! Send 'Order <item>' to create a new order or 'PAY' to pay an existing order.")
        return str(response)

@app.route("/orders", methods=["GET"])
def get_orders():
    return jsonify({"status": "ok", "orders": list(orders.values())})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
