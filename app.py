from flask import Flask, request, jsonify
from flask_cors import CORS
from twilio.twiml.messaging_response import MessagingResponse
from datetime import datetime

app = Flask(__name__)
CORS(app)

# -----------------------
# HEALTH CHECK
# -----------------------
@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "ok",
        "service": "chatpesa",
        "time": datetime.utcnow().isoformat()
    })


# -----------------------
# WHATSAPP WEBHOOK (BASELINE – MUST REPLY)
# -----------------------
@app.route("/whatsapp", methods=["POST"])
def whatsapp():
    """
    BASELINE WHATSAPP HANDLER
    This MUST reply or Twilio will stay silent.
    """
    incoming_msg = request.form.get("Body", "").strip()
    from_number = request.form.get("From", "")

    print("📩 WhatsApp message received")
    print("From:", from_number)
    print("Message:", incoming_msg)

    resp = MessagingResponse()
    resp.message(f"✅ ChatPesa ACK\n\nYou said:\n{incoming_msg}")

    return str(resp), 200, {"Content-Type": "text/xml"}


# -----------------------
# DASHBOARD ORDERS (EMPTY BUT ONLINE)
# -----------------------
@app.route("/orders", methods=["GET"])
def orders():
    return jsonify({
        "status": "ok",
        "orders": []
    })


# -----------------------
# ENTRY POINT
# -----------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
