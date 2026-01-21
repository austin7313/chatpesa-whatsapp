from flask import Flask, request, jsonify
from flask_cors import CORS
from twilio.twiml.messaging_response import MessagingResponse
from datetime import datetime
import random

app = Flask(__name__)
CORS(app)

# ======================
# IN-MEMORY STORE (SAFE FOR NOW)
# ======================
ORDERS = []

def generate_order_id():
    return f"RCP{random.randint(1000,9999)}"

# ======================
# HEALTH CHECK
# ======================
@app.route("/health", methods=["GET"])
def health():
    return {"status": "ok"}

# ======================
# WHATSAPP WEBHOOK (CRITICAL)
# ======================
@app.route("/webhook/whatsapp", methods=["POST"])
def whatsapp_webhook():
    try:
        body = request.form.get("Body", "").strip()
        from_number = request.form.get("From", "")
        profile_name = request.form.get("ProfileName", "Customer")

        order_id = generate_order_id()

        order = {
            "id": order_id,
            "customer_name": profile_name,
            "customer_phone": from_number,
            "items": body if body else "Custom Order",
            "amount": 1000,
            "status": "AWAITING_PAYMENT",
            "created_at": datetime.utcnow().isoformat()
        }

        ORDERS.append(order)

        resp = MessagingResponse()
        resp.message(
            f"Order received.\n\n"
            f"Order ID: {order_id}\n"
            f"Amount: KES 1000\n\n"
            f"Pay via M-Pesa.\n"
            f"Reply DONE after payment."
        )

        return str(resp), 200, {"Content-Type": "text/xml"}

    except Exception as e:
        resp = MessagingResponse()
        resp.message("System error. Please try again.")
        return str(resp), 200, {"Content-Type": "text/xml"}

# ======================
# DASHBOARD ORDERS API
# ======================
@app.route("/orders", methods=["GET"])
def get_orders():
    return jsonify({
        "status": "ok",
        "orders": ORDERS
    })
