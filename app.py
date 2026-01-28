import os
import logging
from flask import Flask, request, jsonify
from twilio.twiml.messaging_response import MessagingResponse

# --------------------
# App setup
# --------------------
app = Flask(__name__)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

# --------------------
# Helpers
# --------------------
def normalize_phone(phone: str) -> str:
    """
    Normalizes WhatsApp phone numbers
    Input: 'whatsapp:+254722275271'
    Output: '+254722275271'
    """
    if not phone:
        return ""
    phone = phone.replace("whatsapp:", "").strip()
    return phone

# --------------------
# Health check
# --------------------
@app.route("/", methods=["GET"])
def health():
    return "✅ App is running", 200

# --------------------
# Test webhook (browser safe)
# --------------------
@app.route("/webhook/whatsapp-test", methods=["GET", "POST"])
def whatsapp_test():
    logging.info("✅ TEST WEBHOOK HIT")
    logging.info(f"Method: {request.method}")
    logging.info(f"Headers: {dict(request.headers)}")
    logging.info(f"Body: {request.get_data(as_text=True)}")

    return jsonify({
        "status": "ok",
        "message": "Test webhook working"
    }), 200

# --------------------
# WhatsApp webhook (Twilio)
# --------------------
@app.route("/webhook/whatsapp", methods=["POST"])
def whatsapp_webhook():
    try:
        logging.info("📩 WhatsApp webhook hit")

        from_number = normalize_phone(request.form.get("From"))
        to_number = normalize_phone(request.form.get("To"))
        body = (request.form.get("Body") or "").strip()

        logging.info(f"From: {from_number}")
        logging.info(f"To: {to_number}")
        logging.info(f"Message: {body}")

        # --- Build reply ---
        resp = MessagingResponse()

        if not body:
            resp.message("⚠️ Empty message received.")
        else:
            resp.message(
                "✅ WhatsApp reply working!\n\n"
                f"You said: *{body}*\n\n"
                "ChatPesa webhook is alive 🚀"
            )

        # IMPORTANT: Always return 200 + XML
        return str(resp), 200

    except Exception as e:
        logging.exception("❌ WhatsApp webhook error")

        # Even on error, RETURN 200 so Twilio doesn't break
        resp = MessagingResponse()
        resp.message("⚠️ Temporary error. Please try again.")
        return str(resp), 200

# --------------------
# Render entrypoint
# --------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
