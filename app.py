from flask import Flask, request, jsonify
from flask_cors import CORS
from twilio.twiml.messaging_response import MessagingResponse
import datetime

app = Flask(__name__)
CORS(app)

# In-memory store for now (we’ll move to DB later)
ORDERS = []

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200


@app.route("/orders", methods=["GET"])
def get_orders():
    return jsonify({
        "status": "ok",
        "orders": ORDERS
    }), 200


@app.route("/webhook/whatsapp", methods=["GET", "POST"])
def whatsapp_webhook():
    try:
        print("🔥 WHATSAPP WEBHOOK HIT 🔥")

        # Allow browser test
        if request.method == "GET":
            return "Webhook is alive", 200

        data = request.form.to_dict()
        print("📩 Incoming form data:", data)

        from_number = data.get("From", "")
        body = data.get("Body", "").strip().lower()

        resp = MessagingResponse()
        msg = resp.message()

        # Basic command parsing
        if body.startswith("order"):
            parts = body.split()

            if len(parts) == 2 and parts[1].isdigit():
                amount = int(parts[1])

                order_id = len(ORDERS) + 1
                timestamp = datetime.datetime.utcnow().isoformat()

                order = {
                    "order_id": order_id,
                    "phone": from_number,
                    "amount": amount,
                    "status": "PENDING",
                    "receipt": None,
                    "time": timestamp
                }

                ORDERS.append(order)

                msg.body(
                    f"✅ Order #{order_id} received for KES {amount}.\n"
                    f"Reply PAY to complete payment."
                )

            else:
                msg.body("❌ Invalid format.\nUse: order 100")

        elif body == "pay":
            if len(ORDERS) == 0:
                msg.body("❌ No active order found. Send: order 100")
            else:
                last_order = ORDERS[-1]
                last_order["status"] = "PAID"
                last_order["receipt"] = f"RCP{last_order['order_id']:04d}"

                msg.body(
                    f"💳 Payment received!\n"
                    f"Order #{last_order['order_id']}\n"
                    f"Receipt: {last_order['receipt']}"
                )

        else:
            msg.body(
                "👋 Welcome to ChatPesa\n\n"
                "Send: order 100\n"
                "Then reply: PAY"
            )

        return str(resp), 200

    except Exception as e:
        print("❌ WEBHOOK ERROR:", str(e))
        return "Internal Server Error", 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
