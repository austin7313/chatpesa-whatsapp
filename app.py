from flask import Flask, request
from flask_cors import CORS
from twilio.twiml.messaging_response import MessagingResponse
import random
from datetime import datetime

app = Flask(__name__)
CORS(app)  # ✅ Enable CORS for React frontend

# Restaurant config
RESTAURANT = {
    "name": "CARIBOU KARIBU",
    "paybill": "247247"
}

# In-memory order storage (replace with DB in prod)
ORDERS = []

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

@app.route("/webhook/whatsapp", methods=["POST"])
def whatsapp_webhook():
    incoming_msg = request.form.get("Body", "").strip()
    from_number = request.form.get("From", "").replace("whatsapp:", "")
    profile_name = request.form.get("ProfileName", "Customer")

    # Parse order
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

    # Twilio reply
    resp = MessagingResponse()
    payment_message = f"""✅ Order received from {RESTAURANT['name']}!

📋 Your Order:
{order_details['items']}

💰 Total: KES {order_details['amount']:,}

💳 Pay Now:
Paybill: {RESTAURANT['paybill']}
Account: {order_id}

Reply DONE when paid.
Order ID: {order_id}"""
    resp.message(payment_message)

    return str(resp), 200, {'Content-Type': 'text/xml'}

# Orders endpoint
@app.route("/orders")
def get_orders():
    return {"status": "ok", "orders": ORDERS}

# Health check
@app.route("/health")
def health():
    return {"status": "ok", "service": "chatpesa"}

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
