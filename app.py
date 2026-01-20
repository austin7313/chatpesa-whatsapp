from flask import Flask, request, jsonify
from twilio.twiml.messaging_response import MessagingResponse
import pytz
from datetime import datetime
import os

app = Flask(__name__)

# In-memory order storage (replace with DB for production)
orders = []

EAST_AFRICA = pytz.timezone("Africa/Nairobi")

@app.route("/health", methods=["GET"])
def health():
    return "OK", 200

@app.route("/orders", methods=["GET"])
def get_orders():
    try:
        return jsonify({"status": "ok", "orders": orders}), 200
    except Exception as e:
        print("Orders endpoint error:", e)
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/webhook/whatsapp", methods=["POST"])
def whatsapp_webhook():
    try:
        incoming_msg = request.values.get("Body", "").strip()
        from_number = request.values.get("From", "")

        # Record order
        now = datetime.now(EAST_AFRICA).isoformat()
        receipt_number = f"RCP{len(orders)+1:04d}"
        order = {
            "id": receipt_number,
            "customer_phone": from_number,
            "raw_message": incoming_msg,
            "items": f"Order from WhatsApp: {incoming_msg}",
            "amount": 0,
            "status": "awaiting_payment",
            "receipt_number": receipt_number,
            "created_at": now
        }
        orders.append(order)

        # Twilio response
        resp = MessagingResponse()
        resp.message(f"✅ Received: '{incoming_msg}'. Receipt: {receipt_number}")

        return str(resp), 200

    except Exception as e:
        print("Webhook Error:", e)
        return str(e), 500

if __name__ == "__main__":
    # Bind to Render's dynamic PORT
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
