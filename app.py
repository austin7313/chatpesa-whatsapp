from flask import Flask, request, jsonify
from flask_cors import CORS
from datetime import datetime
import pytz

app = Flask(__name__)
CORS(app)  # Enable CORS for dashboard

# In-memory orders store (replace with DB later)
orders = []
order_counter = 1

# East Africa Time
EAT = pytz.timezone("Africa/Nairobi")

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})

@app.route("/orders", methods=["GET"])
def get_orders():
    return jsonify({"orders": orders, "status": "ok"})

# Twilio webhook for WhatsApp
@app.route("/webhook/whatsapp", methods=["POST"])
@app.route("/webhook/whatsapp/", methods=["POST"])
def whatsapp_webhook():
    global order_counter
    try:
        data = request.get_json(force=True)
        # Example fields Twilio might send
        customer_phone = data.get("from") or "unknown"
        amount = data.get("amount") or 0
        message = data.get("message") or "—"

        # Timestamp in East Africa Time
        timestamp = datetime.now(EAT).isoformat()

        # Create order object
        order = {
            "id": f"{order_counter:04d}",
            "customer_phone": customer_phone,
            "items": message,
            "amount": amount,
            "status": "paid" if amount > 0 else "awaiting_payment",
            "receipt_number": f"RCP{order_counter:04d}",
            "created_at": timestamp
        }

        orders.append(order)
        order_counter += 1

        # Respond immediately with 200 for Twilio
        return jsonify({"status": "received", "order_id": order["id"]}), 200

    except Exception as e:
        print("Error processing webhook:", e)
        # Still respond 200 so Twilio doesn’t mark as failed
        return jsonify({"status": "error", "message": str(e)}), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
