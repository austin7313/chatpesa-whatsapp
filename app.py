from flask import Flask, request, jsonify
from flask_cors import CORS
from twilio.twiml.messaging_response import MessagingResponse
from datetime import datetime
import random

app = Flask(__name__)
CORS(app)

# --------------------
# IN-MEMORY STORE
# --------------------
ORDERS = []

RESTAURANT = {
    "name": "CARIBOU KARIBU",
    "paybill": "247247"
}

def generate_order_id():
    return f"RCP{random.randint(1000, 9999)}"

def parse_order(message):
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
        items.append("Custom Order")
        amount = 1000

    return " + ".join(items), amount


# --------------------
# WHATSAPP WEBHOOK
# --------------------
@app.route("/webhook/whatsapp", methods=["POST"])
def whatsapp_webhook():
    incoming_msg = request.form.get("Body", "")
    from_number = request.form.get("From", "")
    profile_name = request.form.get("ProfileName", "Customer")

    items, amount = parse_order(incoming_msg)
    order_id = generate_order_id()

    order = {
        "id": order_id,
        "customer": profile_name,
        "phone": from_number,
        "items": items,
        "amount": amount,
        "status": "AWAITING_PAYMENT",
        "created_at": datetime.utcnow().isoformat()
    }

    ORDERS.insert(0, order)

    resp = MessagingResponse()
    resp.message(
        f"✅ Order received from {RESTAURANT['name']}!\n\n"
        f"📋 Items: {items}\n"
        f"💰 Total: KES {amount}\n\n"
        f"💳 Paybill: {RESTAURANT['paybill']}\n"
        f"📌 Account: {order_id}\n\n"
        f"Reply DONE after payment."
    )

    return str(resp), 200, {"Content-Type": "text/xml"}


# --------------------
# ORDERS API (DASHBOARD)
# --------------------
@app.route("/orders", methods=["GET"])
def get_orders():
    return jsonify({
        "success": True,
        "orders": ORDERS
    })


# --------------------
# HEALTH CHECK
# --------------------
@app.route("/health")
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run()
