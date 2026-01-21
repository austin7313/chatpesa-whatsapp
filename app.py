from flask import Flask, request, jsonify
from twilio.twiml.messaging_response import MessagingResponse
from datetime import datetime
import random

app = Flask(__name__)

# In-memory storage (SAFE for now)
ORDERS = []

RESTAURANT = {
    "name": "CARIBOU KARIBU",
    "paybill": "247247"
}

def generate_order_id():
    return f"ORD{random.randint(100000, 999999)}"

def parse_order_message(message):
    msg = message.lower()
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
        items = ["Custom Order"]
        amount = 1000

    return " + ".join(items), amount


@app.route("/webhook/whatsapp", methods=["POST"])
def whatsapp_webhook():
    resp = MessagingResponse()

    try:
        body = request.form.get("Body", "")
        sender = request.form.get("From", "").replace("whatsapp:", "")
        name = request.form.get("ProfileName", "Customer")

        items, amount = parse_order_message(body)
        order_id = generate_order_id()

        order = {
            "id": order_id,
            "customer": name,
            "phone": sender,
            "items": items,
            "amount": amount,
            "status": "awaiting_payment",
            "created_at": datetime.utcnow().isoformat()
        }

        ORDERS.append(order)

        reply = f"""
✅ Order received – {RESTAURANT['name']}

📋 Items:
{items}

💰 Total: KES {amount}

💳 Paybill: {RESTAURANT['paybill']}
🧾 Account: {order_id}

Reply DONE after payment.
"""
        resp.message(reply.strip())

    except Exception as e:
        print("ERROR:", e)
        resp.message("⚠️ Something went wrong. Please try again.")

    return str(resp), 200, {"Content-Type": "text/xml"}


@app.route("/orders", methods=["GET"])
def get_orders():
    return jsonify({"orders": ORDERS})


@app.route("/health")
def health():
    return jsonify({"status": "ok"})
