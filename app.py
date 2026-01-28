from flask import Flask, request, Response
from twilio.twiml.messaging_response import MessagingResponse
import logging
import os
import sys

app = Flask(__name__)

logging.basicConfig(
    level=logging.INFO,
    stream=sys.stdout,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

# -------------------------
# Helpers
# -------------------------
def normalize(text: str) -> str:
    return (text or "").strip().lower()

def build_reply(message: str) -> str:
    msg = normalize(message)

    if msg in ["hi", "hello", "hey", "start"]:
        return (
            "👋 Hi! Welcome to ChatPesa.\n\n"
            "Type:\n"
            "👉 *pay* to make a payment\n"
            "👉 *status* to check your payment\n"
        )

    if msg == "pay":
        return (
            "💳 *How to Pay*\n\n"
            "1️⃣ Type the amount\n"
            "2️⃣ You’ll receive an M-Pesa prompt\n"
            "3️⃣ Enter your PIN\n\n"
            "Example:\n"
            "`pay 100`"
        )

    if msg == "status":
        return (
            "📊 *Payment Status*\n\n"
            "If you’ve already paid, you’ll receive a confirmation here.\n"
            "If not, type *pay* to begin."
        )

    return (
        "🤖 Sorry, I didn’t understand that.\n\n"
        "Try typing:\n"
        "👉 *pay*\n"
        "👉 *status*"
    )

# -------------------------
# Health check
# -------------------------
@app.route("/health", methods=["GET"])
def health():
    return "OK", 200

# -------------------------
# WhatsApp webhook
# -------------------------
@app.route("/webhook/whatsapp", methods=["POST"])
def whatsapp_webhook():
    try:
        incoming_msg = request.values.get("Body", "")
        from_number = request.values.get("From", "")

        logging.info(f"WhatsApp from {from_number}: {incoming_msg}")

        reply_text = build_reply(incoming_msg)

        resp = MessagingResponse()
        resp.message(reply_text)

        return Response(str(resp), mimetype="application/xml")

    except Exception as e:
        logging.exception("Webhook error")
        resp = MessagingResponse()
        resp.message("⚠️ Temporary error. Please try again.")
        return Response(str(resp), mimetype="application/xml")

# -------------------------
# Render entry
# -------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
