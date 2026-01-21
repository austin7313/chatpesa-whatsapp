from flask import Flask, request, jsonify
from flask_cors import CORS
from twilio.twiml.messaging_response import MessagingResponse
import random
from datetime import datetime
import requests
import base64

app = Flask(__name__)
CORS(app)  # Allow frontend to access API

# -------------------------------
# CONFIGURATION - M-PESA + BUSINESS
# -------------------------------
MPESA_SHORTCODE = "4031193"
MPESA_PASSKEY = "5a64ad290753ed331b662cf6d83d3149367867c102f964f522390ccbd85cb282"
MPESA_CONSUMER_KEY = "B05zln19QXC3OBL6YuCkdhZ8zvYqZtXP"
MPESA_CONSUMER_SECRET = "MYRasd2p9gGFcuCR"

BUSINESS_NAME = "ChatPesa Business"

# -------------------------------
# IN-MEMORY DATABASE (replace with supabase/postgres in prod)
# -------------------------------
ORDERS = []  # Each order: {id, customer_name, phone, items, amount, status, created_at}

# -------------------------------
# HELPERS
# -------------------------------
def generate_order_id():
    return f"RCP{random.randint(1000,9999)}"

def parse_order_message(message):
    """Simple parsing example; extend as needed"""
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

def get_status_color(status):
    mapping = {
        "PAID": "#16a34a",
        "AWAITING_PAYMENT": "#f59e0b",
        "FAILED": "#dc2626"
    }
    return mapping.get(status, "#6b7280")

# -------------------------------
# TWILIO WHATSAPP WEBHOOK
# -------------------------------
@app.route("/webhook/whatsapp", methods=["POST"])
def whatsapp_webhook():
    try:
        incoming_msg = request.form.get("Body", "").strip()
        from_number = request.form.get("From", "").replace("whatsapp:", "")
        profile_name = request.form.get("ProfileName", "Customer")

        # Parse order
        order_details = parse_order_message(incoming_msg)
        order_id = generate_order_id()
        created_at = datetime.utcnow().isoformat()

        # Save order
        order = {
            "id": order_id,
            "customer_name": profile_name,
            "customer_phone": from_number,
            "items": order_details["items"],
            "amount": order_details["amount"],
            "status": "AWAITING_PAYMENT",
            "created_at": created_at
        }
        ORDERS.append(order)

        # TwiML response
        resp = MessagingResponse()
        payment_msg = (
            f"✅ Order received from {BUSINESS_NAME}!\n\n"
            f"📋 Your Order:\n{order_details['items']}\n\n"
            f"💰 Total: KES {order_details['amount']:,}\n\n"
            f"💳 Paybill: {MPESA_SHORTCODE}\n"
            f"Account: {order_id}\n\n"
            f"Reply DONE when paid."
        )
        resp.message(payment_msg)
        return str(resp), 200, {'Content-Type': 'text/xml'}

    except Exception as e:
        resp = MessagingResponse()
        resp.message("❌ Error processing your order. Try again later.")
        print(f"Webhook error: {e}")
        return str(resp), 200, {'Content-Type': 'text/xml'}

# -------------------------------
# ORDERS ENDPOINT
# -------------------------------
@app.route("/orders", methods=["GET"])
def get_orders():
    try:
        return jsonify({"status": "ok", "orders": ORDERS})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# -------------------------------
# HEALTH CHECK
# -------------------------------
@app.route("/health")
def health():
    return {"status": "ok", "service": "chatpesa"}

# -------------------------------
# RUN
# -------------------------------
if __name__ == "__main__":
    app.run(debug=True)
