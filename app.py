import os
from flask import Flask, request, jsonify
from flask_cors import CORS
from datetime import datetime
import pytz
from twilio.rest import Client

app = Flask(__name__)
CORS(app)

# ===== Timezone setup =====
EAT = pytz.timezone("Africa/Nairobi")

# ===== In-memory orders storage =====
orders = []

# ===== Twilio config (set via environment variables) =====
TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN")
TWILIO_WHATSAPP_NUMBER = os.environ.get("TWILIO_WHATSAPP_NUMBER")

twilio_client = None
if TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN:
    twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

# ===== Utilities =====
def generate_order_id():
    return f"RCP{str(len(orders) + 1).zfill(4)}"

def get_current_time_iso():
    return datetime.now(EAT).isoformat()

# ===== Health check =====
@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200

# ===== Get all orders =====
@app.route("/orders", methods=["GET"])
def get_orders():
    return jsonify({"status": "ok", "orders": orders}), 200

# ===== Twilio WhatsApp webhook =====
@app.route("/webhook/whatsapp", methods=["POST"])
def whatsapp_webhook():
    try:
        incoming = request.form.to_dict() or request.get_json() or {}
        customer_phone = incoming.get("From") or incoming.get("from")
        body = incoming.get("Body") or incoming.get("body") or ""
        
        if not customer_phone:
            return jsonify({"error": "Missing customer phone"}), 400

        order_amount = 0
        try:
            order_amount = int(body.strip())
        except:
            pass

        new_order = {
            "id": generate_order_id(),
            "customer_phone": customer_phone,
            "items": f"Order from WhatsApp: {body.strip()}",
            "amount": order_amount,
            "status": "paid" if order_amount > 0 else "awaiting_payment",
            "receipt_number": generate_order_id(),
            "created_at": get_current_time_iso(),
            "raw_message": body.strip()
        }
        orders.append(new_order)

        # ===== Auto-reply via Twilio =====
        if twilio_client:
            try:
                twilio_client.messages.create(
                    from_=f"whatsapp:{TWILIO_WHATSAPP_NUMBER}",
                    to=customer_phone,
                    body=f"✅ Your order {new_order['receipt_number']} has been received. Amount: KES {order_amount}"
                )
            except Exception as e:
                print("Twilio send error:", e)

        return jsonify({"status": "ok", "order": new_order}), 200
    except Exception as e:
        print("Webhook error:", e)
        return jsonify({"status": "error", "message": str(e)}), 500

# ===== Main =====
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
