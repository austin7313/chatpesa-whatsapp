from flask import Flask, request, jsonify
from twilio.twiml.messaging_response import MessagingResponse
import random
from datetime import datetime

app = Flask(__name__)

# --- Config ---
RESTAURANT = {
    "name": "CARIBOU KARIBU",
    "paybill": "247247"
}

# --- In-memory orders store (replace with DB in production) ---
ORDERS = []

# --- Helpers ---
def generate_order_id():
    return f"RCP{random.randint(1000, 9999)}"

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

    return {
        "items": " + ".join(items),
        "amount": amount
    }

# --- WhatsApp Webhook ---
@app.route("/webhook/whatsapp", methods=["POST"])
def whatsapp_webhook():
    try:
        incoming_msg = request.form.get("Body", "").strip()
        from_number = request.form.get("From", "").replace("whatsapp:", "")
        profile_name = request.form.get("ProfileName", "Customer")

        print(f"📱 WhatsApp message received: {from_number} | {profile_name} | {incoming_msg}")

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
        print(f"✅ Order created: {order_id}")

        resp = MessagingResponse()
        payment_message = (
            f"✅ Order received from {RESTAURANT['name']}!\n\n"
            f"📋 Your Order:\n{order_details['items']}\n\n"
            f"💰 Total: KES {order_details['amount']:,}\n\n"
            f"💳 Pay Now:\nPaybill: {RESTAURANT['paybill']}\nAccount: {order_id}\n\n"
            f"Reply DONE when paid.\nOrder ID: {order_id}"
        )
        resp.message(payment_message)

        return str(resp), 200, {'Content-Type': 'text/xml'}

    except Exception as e:
        print(f"❌ Error in webhook: {str(e)}")
        error_resp = MessagingResponse()
        error_resp.message("Sorry, error processing your order. Try again or call us.")
        return str(error_resp), 200, {'Content-Type': 'text/xml'}

# --- Orders endpoint for React dashboard ---
@app.route("/orders")
def get_orders():
    return jsonify({"orders": ORDERS, "status": "ok"})

# --- Health check ---
@app.route("/health")
def health():
    return jsonify({"status": "ok", "service": "chatpesa"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
