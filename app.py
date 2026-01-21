from flask import Flask, request, jsonify
from flask_cors import CORS
from twilio.twiml.messaging_response import MessagingResponse
from datetime import datetime, timedelta
import random
import threading
import requests

app = Flask(__name__)
CORS(app)

# -----------------------------
# MOCK DATABASES
# -----------------------------
orders_db = []
subscriptions_db = []

# -----------------------------
# CONFIG
# -----------------------------
RESTAURANT = {"name": "CHATPESA", "paybill": "247247"}

# M-Pesa / Safaricom config
MPESA_SHORTCODE = "4031193"
MPESA_PASSKEY = "5a64ad290753ed331b662cf6d83d3149367867c102f964f522390ccbd85cb282"
MPESA_CONSUMER_KEY = "B05zln19QXC3OBL6YuCkdhZ8zvYqZtXP"
MPESA_CONSUMER_SECRET = "MYRasd2p9gGFcuCR"

# -----------------------------
# HELPERS
# -----------------------------
def generate_order_id():
    return f"RCP{random.randint(1000,9999)}"

def parse_order_message(message):
    message_lower = message.lower()
    items = []
    amount = 0
    if "service" in message_lower:
        items.append("Service")
        amount += 1000
    else:
        items.append("Custom Order")
        amount += 1000
    return {"items": " + ".join(items), "amount": amount}

# -----------------------------
# ORDERS ENDPOINT
# -----------------------------
@app.route("/orders")
def get_orders():
    return jsonify({"status": "ok", "orders": orders_db})

# -----------------------------
# SUBSCRIPTIONS ENDPOINT
# -----------------------------
@app.route("/subscriptions")
def get_subscriptions():
    return jsonify({"status": "ok", "subscriptions": subscriptions_db})

# -----------------------------
# WHATSAPP WEBHOOK
# -----------------------------
@app.route("/webhook/whatsapp", methods=["POST"])
def whatsapp_webhook():
    try:
        incoming_msg = request.form.get("Body", "").strip()
        from_number = request.form.get("From", "").replace("whatsapp:", "")
        profile_name = request.form.get("ProfileName", "Customer")
        
        order_details = parse_order_message(incoming_msg)
        order_id = generate_order_id()

        order_data = {
            "id": order_id,
            "customer_phone": from_number,
            "customer_name": profile_name,  # Will update to M-Pesa name after payment
            "items": order_details["items"],
            "amount": order_details["amount"],
            "status": "AWAITING_PAYMENT",
            "created_at": datetime.utcnow().isoformat()
        }
        orders_db.append(order_data)

        # TwiML reply
        resp = MessagingResponse()
        resp.message(
            f"✅ Order received!\n\n"
            f"📋 {order_details['items']}\n"
            f"💰 KES {order_details['amount']}\n"
            f"💳 Paybill: {RESTAURANT['paybill']}\n"
            f"Account: {order_id}\n"
            f"Reply DONE when paid."
        )
        return str(resp), 200, {'Content-Type': 'text/xml'}
    except Exception as e:
        resp = MessagingResponse()
        resp.message("❌ Error processing your order, try again.")
        return str(resp), 200, {'Content-Type': 'text/xml'}

# -----------------------------
# SIMULATED STK PUSH
# -----------------------------
def initiate_stk_push(phone, amount, order_id):
    # Simulate payment success
    for order in orders_db:
        if order["id"] == order_id:
            order["status"] = "PAID"
            order["customer_name"] = f"M-Pesa {phone}"  # Capture M-Pesa name
            order["paid_at"] = datetime.utcnow().isoformat()

# -----------------------------
# SUBSCRIPTION CREATION
# -----------------------------
@app.route("/subscribe", methods=["POST"])
def subscribe():
    data = request.json
    phone = data.get("phone")
    name = data.get("name", phone)
    amount = data.get("amount", 1000)
    frequency_days = data.get("frequency_days", 30)

    sub = {
        "id": generate_order_id(),
        "customer_phone": phone,
        "customer_name": name,
        "amount": amount,
        "frequency_days": frequency_days,
        "next_payment_date": datetime.utcnow().isoformat(),
        "status": "ACTIVE",
        "last_paid_at": None
    }
    subscriptions_db.append(sub)
    return jsonify({"status": "ok", "subscription": sub})

# -----------------------------
# SUBSCRIPTION SCHEDULER
# -----------------------------
def subscription_scheduler():
    while True:
        now = datetime.utcnow()
        for sub in subscriptions_db:
            next_payment = datetime.fromisoformat(sub["next_payment_date"])
            if sub["status"] == "ACTIVE" and now >= next_payment:
                # Send WhatsApp reminder
                print(f"Reminder to {sub['customer_phone']}: pay KES {sub['amount']}")
                # Simulate STK push
                initiate_stk_push(sub["customer_phone"], sub["amount"], sub["id"])
                # Update next payment date
                sub["next_payment_date"] = (now + timedelta(days=sub["frequency_days"])).isoformat()
                sub["last_paid_at"] = now.isoformat()
        time.sleep(60)  # Check every minute

# Start scheduler thread
threading.Thread(target=subscription_scheduler, daemon=True).start()

# -----------------------------
# HEALTH CHECK
# -----------------------------
@app.route("/health")
def health():
    return {"status": "ok", "service": "chatpesa"}

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
