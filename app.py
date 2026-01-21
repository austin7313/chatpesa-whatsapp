from flask import Flask, request, jsonify
from flask_cors import CORS
from twilio.twiml.messaging_response import MessagingResponse
from datetime import datetime
import random

app = Flask(__name__)
CORS(app)  # Allow React dashboard to fetch

# In-memory orders store
ORDERS = []

# Restaurant config
RESTAURANT = {
    "name": "CARIBOU KARIBU",
    "paybill": "247247"
}

def generate_order_id():
    """Unique order ID"""
    return f"RCP{random.randint(1000, 9999)}"

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


@app.route("/webhook/whatsapp", methods=["POST"])
def whatsapp_webhook():
    try:
        incoming_msg = request.form.get("Body", "").strip()
        from_number = request.form.get("From", "").replace("whatsapp:", "")
        profile_name = request.form.get("ProfileName", "Customer")

        # Parse order
        order_details = parse_order_message(incoming_msg)
        order_id = generate_order_id()

        order_data = {
            "id": order_id,
            "customer_name": profile_name,
            "customer_phone": from_number,
            "items": order_details["items"],
            "amount": order_details["amount"],
            "status": "AWAITING_PAYMENT",
            "created_at": datetime.utcnow().isoformat()
        }

        # Save order in memory
        ORDERS.append(order_data)

        # Build Twilio reply
        resp = MessagingResponse()
        resp.message(
            f"✅ Order received from {RESTAURANT['name']}!\n\n"
            f"📋 Your Order:\n{order_details['items']}\n\n"
            f"💰 Total: KES {order_details['amount']:,}\n\n"
            f"💳 Pay Now:\nPaybill: {RESTAURANT['paybill']}\n"
            f"Account: {order_id}\n\n"
            f"Reply DONE when paid.\nOrder ID: {order_id}"
        )

        return str(resp), 200, {'Content-Type': 'text/xml'}

    except Exception as e:
        resp = MessagingResponse()
        resp.message("❌ Sorry, we could not process your order. Please try again.")
        return str(resp), 200, {'Content-Type': 'text/xml'}


@app.route("/orders")
def get_orders():
    return jsonify({"status": "ok", "orders": ORDERS})


@app.route("/health")
def health():
    return jsonify({"status": "ok", "service": "chatpesa"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
