from flask import Flask, request
from flask_cors import CORS
from twilio.twiml.messaging_response import MessagingResponse
import random
from datetime import datetime

app = Flask(__name__)
CORS(app)

# In-memory orders (replace with database in production)
orders = []

# Config
RESTAURANT = {
    "name": "ChatPesa",
    "paybill": "247247"
}

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
        f"✅ Order received!\n\n"
        f"Order ID: {order_id}\n"
        f"Items: {order['items']}\n"
        f"Amount: KES {order['amount']}\n\n"
        f"Reply 'PAY' to proceed with M-Pesa payment."
    )

    return str(resp), 200, {'Content-Type': 'text/xml'}

@app.route("/orders", methods=["GET"])
def get_orders():
    return {"status": "ok", "orders": orders}

@app.route("/health", methods=["GET"])
def health():
    return {"status": "ok", "service": "chatpesa"}

if __name__ == "__main__":
    app.run(debug=True)
