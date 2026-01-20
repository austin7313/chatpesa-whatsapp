from flask import Flask, request, jsonify
from flask_cors import CORS
from twilio.twiml.messaging_response import MessagingResponse
import pytz
from datetime import datetime
import os

app = Flask(__name__)
CORS(app)  # 🔥 CRITICAL: allow browser dashboard access

orders = []

EAST_AFRICA = pytz.timezone("Africa/Nairobi")

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200


@app.route("/orders", methods=["GET"])
def get_orders():
    try:
        return jsonify({
            "status": "ok",
            "orders": orders
        }), 200
    except Exception as e:
        print("❌ /orders error:", e)
        return jsonify({
            "status": "error",
            "message": str(e),
            "orders": []
        }), 500


@app.route("/webhook/whatsapp", methods=["POST"])
def whatsapp_webhook():
    try:
        incoming_msg = request.values.get("Body", "").strip()
        from_number = request.values.get("From", "")

        now = datetime.now(EAST_AFRICA).isoformat()
        receipt_number = f"RCP{len(orders) + 1:04d}"

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

        resp = MessagingResponse()
        resp.message(
            f"✅ Received: '{incoming_msg}'.\n"
            f"Receipt: {receipt_number}\n"
            f"Reply PAY to complete payment."
        )

        return str(resp), 200

    except Exception as e:
        print("❌ Webhook error:", e)
        return str(e), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
