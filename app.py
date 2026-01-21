from flask import Flask, request
from flask_cors import CORS
from twilio.twiml.messaging_response import MessagingResponse
from datetime import datetime
import random

app = Flask(__name__)
CORS(app)  # Allow React frontend to access

# -----------------------------
# Global Orders Store (temporary, replace with DB)
orders = []

# M-Pesa & WhatsApp Config (replace with your creds)
MPESA_SHORTCODE = "4031193"
MPESA_PASSKEY = "5a64ad290753ed331b662cf6d83d3149367867c102f964f522390ccbd85cb"
TWILIO_SANDBOX = True

# -----------------------------
def generate_order_id():
    return f"ORD{random.randint(1000,9999)}"

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
    if not items:
        items.append("Custom Order")
        amount = 1000
    return {"items": " + ".join(items), "amount": amount}

# -----------------------------
@app.route("/health")
def health():
    return {"status": "ok", "service": "chatpesa"}

@app.route("/orders")
def get_orders():
    return {"status": "ok", "orders": orders}

# -----------------------------
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

        # Save order
        orders.append(order_data)
        print(f"New order: {order_data}")

        # Respond via WhatsApp
        resp = MessagingResponse()
        resp.message(
            f"✅ Order received!\n\n📋 {order_details['items']}\n💰 KES {order_details['amount']}\n"
            f"💳 Paybill: {MPESA_SHORTCODE}\nAccount: {order_id}\n\nReply DONE when paid."
        )
        return str(resp), 200, {"Content-Type": "text/xml"}

    except Exception as e:
        print(f"Webhook error: {str(e)}")
        resp = MessagingResponse()
        resp.message("❌ Error processing order. Please try again.")
        return str(resp), 200, {"Content-Type": "text/xml"}

# -----------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
