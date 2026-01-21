from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
from datetime import datetime
import random, requests, os, base64
from requests.auth import HTTPBasicAuth

app = Flask(__name__)

# CONFIG
RESTAURANT = {"name": "CARIBOU KARIBU", "paybill": "247247"}
MPESA_SHORTCODE = "4031193"
MPESA_PASSKEY = "5a64ad290753ed331b662cf6d83d3149367867c102f964f522390ccbd85cb282"
MPESA_CONSUMER_KEY = "B05zln19QXC3OBL6YuCkdhZ8zvYqZtXP"
MPESA_CONSUMER_SECRET = "MYRasd2p9gGFcuCR"

ORDERS = []

# UTILITIES
def generate_order_id():
    return f"ORD{random.randint(1000,9999)}"

def parse_order_message(msg):
    msg_lower = msg.lower()
    items, amount = [], 0
    if "burger" in msg_lower: items.append("Burger"); amount += 500
    if "fries" in msg_lower: items.append("Fries"); amount += 200
    if "pizza" in msg_lower: items.append("Pizza"); amount += 800
    if not items: items.append("Custom Order"); amount = 1000
    return {"items": " + ".join(items), "amount": amount}

def get_mpesa_access_token():
    url = "https://sandbox.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials"
    resp = requests.get(url, auth=HTTPBasicAuth(MPESA_CONSUMER_KEY, MPESA_CONSUMER_SECRET))
    return resp.json().get("access_token")

def initiate_stk_push(order):
    token = get_mpesa_access_token()
    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    password = base64.b64encode(f"{MPESA_SHORTCODE}{MPESA_PASSKEY}{timestamp}".encode()).decode()
    payload = {
        "BusinessShortCode": MPESA_SHORTCODE,
        "Password": password,
        "Timestamp": timestamp,
        "TransactionType": "CustomerPayBillOnline",
        "Amount": order["amount"],
        "PartyA": order["customer_phone"],
        "PartyB": MPESA_SHORTCODE,
        "PhoneNumber": order["customer_phone"],
        "CallBackURL": f"https://yourdomain.com/mpesa/callback",
        "AccountReference": order["id"],
        "TransactionDesc": f"Payment for {order['items']}"
    }
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.post("https://sandbox.safaricom.co.ke/mpesa/stkpush/v1/processrequest",
                             json=payload, headers=headers)
    return response.json()

# ROUTES
@app.route("/health")
def health(): return {"status": "ok", "service": "chatpesa"}

@app.route("/orders")
def get_orders(): return {"status": "ok", "orders": ORDERS}

@app.route("/webhook/whatsapp", methods=["POST"])
def whatsapp_webhook():
    incoming_msg = request.form.get("Body", "").strip()
    from_number = request.form.get("From", "").replace("whatsapp:", "")
    profile_name = request.form.get("ProfileName", "Customer")

    order_details = parse_order_message(incoming_msg)
    order_id = generate_order_id()
    timestamp = datetime.utcnow().isoformat()

    order_data = {
        "id": order_id,
        "customer_name": profile_name,
        "customer_phone": from_number,
        "items": order_details["items"],
        "amount": order_details["amount"],
        "status": "AWAITING_PAYMENT",
        "created_at": timestamp,
        "transaction_id": None,
        "paid_at": None
    }
    ORDERS.append(order_data)

    # Trigger STK push
    stk_resp = initiate_stk_push(order_data)

    # WhatsApp reply
    resp = MessagingResponse()
    msg_text = f"""
✅ Order received from {RESTAURANT['name']}!
📋 Your Order: {order_data['items']}
💰 Total: KES {order_data['amount']}
💳 Pay Now: Paybill {RESTAURANT['paybill']}, Account {order_id}
Reply DONE when paid.
Order ID: {order_id}
"""
    resp.message(msg_text)
    return str(resp), 200, {'Content-Type': 'text/xml'}

@app.route("/mpesa/callback", methods=["POST"])
def mpesa_callback():
    data = request.get_json()
    # Extract M-Pesa transaction details
    try:
        account_ref = data['Body']['stkCallback']['CallbackMetadata']['Item'][1]['Value'] # AccountReference
        mpesa_id = data['Body']['stkCallback']['CheckoutRequestID']
        paid_amount = data['Body']['stkCallback']['CallbackMetadata']['Item'][0]['Value']
        paid_time = datetime.utcnow().isoformat()

        # Update order
        for o in ORDERS:
            if o['id'] == account_ref:
                o['status'] = "PAID"
                o['transaction_id'] = mpesa_id
                o['paid_at'] = paid_time
        return {"result": "success"}, 200
    except Exception as e:
        print("MPESA CALLBACK ERROR:", e)
        return {"result": "failed"}, 500

if __name__ == "__main__":
    app.run(debug=True)
