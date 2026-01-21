from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
from datetime import datetime
import random
import requests
import os

app = Flask(__name__)

# --- CONFIG ---
RESTAURANT = {
    "name": "CARIBOU KARIBU",
    "paybill": "247247"
}

MPESA_SHORTCODE = "4031193"
MPESA_PASSKEY = "5a64ad290753ed331b662cf6d83d3149367867c102f964f522390ccbd85cb282"
MPESA_CONSUMER_KEY = "B05zln19QXC3OBL6YuCkdhZ8zvYqZtXP"
MPESA_CONSUMER_SECRET = "MYRasd2p9gGFcuCR"

ORDERS = []  # In-memory store (replace with DB in production)

# --- UTILITIES ---
def generate_order_id():
    return f"ORD{random.randint(1000, 9999)}"

def parse_order_message(message):
    """Extract items and amount"""
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

# --- ROUTES ---
@app.route("/health")
def health():
    return {"status": "ok", "service": "chatpesa"}

@app.route("/orders")
def get_orders():
    return {"status": "ok", "orders": ORDERS}

@app.route("/webhook/whatsapp", methods=["POST"])
def whatsapp_webhook():
    incoming_msg = request.form.get("Body", "").strip()
    from_number = request.form.get("From", "").replace("whatsapp:", "")
    profile_name = request.form.get("ProfileName", "Customer")

    # Parse order
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
        "created_at": timestamp
    }

    ORDERS.append(order_data)

    # Twilio WhatsApp response
    resp = MessagingResponse()
    payment_message = f"""
✅ Order received from {RESTAURANT['name']}!

📋 Your Order:
{order_details['items']}

💰 Total: KES {order_details['amount']}

💳 Pay Now:
Paybill: {RESTAURANT['paybill']}
Account: {order_id}

Reply DONE when paid.
Order ID: {order_id}
"""
    resp.message(payment_message)
    return str(resp), 200, {'Content-Type': 'text/xml'}

# --- MPESA STK PUSH ---
def initiate_mpesa_stk(order):
    """Trigger STK Push to customer"""
    token = get_mpesa_access_token()
    payload = {
        "BusinessShortCode": MPESA_SHORTCODE,
        "Password": MPESA_PASSKEY,
        "Timestamp": datetime.utcnow().strftime("%Y%m%d%H%M%S"),
        "TransactionType": "CustomerPayBillOnline",
        "Amount": order['amount'],
        "PartyA": order['customer_phone'],
        "PartyB": MPESA_SHORTCODE,
        "PhoneNumber": order['customer_phone'],
        "CallBackURL": f"https://yourdomain.com/mpesa/callback",
        "AccountReference": order['id'],
        "TransactionDesc": f"Payment for {order['items']}"
    }
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.post("https://sandbox.safaricom.co.ke/mpesa/stkpush/v1/processrequest",
                             json=payload, headers=headers)
    return response.json()

def get_mpesa_access_token():
    import base64
    from requests.auth import HTTPBasicAuth
    url = "https://sandbox.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials"
    resp = requests.get(url, auth=HTTPBasicAuth(MPESA_CONSUMER_KEY, MPESA_CONSUMER_SECRET))
    return resp.json().get("access_token")

# --- SUBSCRIPTIONS REMINDER EXAMPLE ---
def send_subscription_reminder(customer_phone, amount, order_id):
    """Send WhatsApp reminder via Twilio"""
    from twilio.rest import Client
    client = Client(os.environ.get("TWILIO_SID"), os.environ.get("TWILIO_AUTH"))
    msg = f"📅 Reminder: Your subscription payment of KES {amount} is due. Order ID: {order_id}"
    client.messages.create(from_="whatsapp:+14155238886", body=msg, to=f"whatsapp:{customer_phone}")

if __name__ == "__main__":
    app.run(debug=True)
