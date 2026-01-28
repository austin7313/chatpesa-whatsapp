from flask import Flask, request, Response
from twilio.twiml.messaging_response import MessagingResponse
import logging
import os
import sys
import re

app = Flask(__name__)

# -------------------------
# LOGGING
# -------------------------
logging.basicConfig(
    level=logging.INFO,
    stream=sys.stdout,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

# -------------------------
# HELPERS
# -------------------------
def normalize(text: str) -> str:
    return (text or "").strip().lower()

def parse_payment(text: str):
    """
    Accepts:
      pay 100
      pay100
      pay   250
    """
    match = re.search(r"pay\s*(\d+)", text)
    if not match:
        return None
    return int(match.group(1))

# -------------------------
# HEALTH
# -------------------------
@app.route("/health", methods=["GET"])
def health():
    return "OK", 200

# -------------------------
# WHATSAPP WEBHOOK
# -------------------------
@app.route("/webhook/whatsapp", methods=["POST"])
def whatsapp_webhook():
    try:
        body = request.values.get("Body", "")
        sender = request.values.get("From", "")

        logging.info(f"WhatsApp from {sender}: {body}")

        msg = normalize(body)
        resp = MessagingResponse()

        # Greeting
        if msg in ["hi", "hello", "hey", "start"]:
            resp.message(
                "👋 Hi! Welcome to ChatPesa.\n\n"
                "Type:\n"
                "👉 *pay 100* to make a payment\n"
                "👉 *status* to check payment"
            )
            return Response(str(resp), mimetype="application/xml")

        # Payment intent
        amount = parse_payment(msg)
        if amount:
            resp.message(
                f"💳 *Payment request received*\n\n"
                f"Amount: *KES {amount}*\n\n"
                "Reply *YES* to confirm or *NO* to cancel."
            )
            return Response(str(resp), mimetype="application/xml")

        # Status
        if msg == "status":
            resp.message(
                "📊 No completed payments yet.\n"
                "If you want to pay, type *pay 100*"
            )
            return Response(str(resp), mimetype="application/xml")

        # Fallback
        resp.message(
            "🤖 I didn’t understand that.\n\n"
            "Try:\n"
            "👉 *pay 100*\n"
            "👉 *status*"
        )
        return Response(str(resp), mimetype="application/xml")

    except Exception:
        logging.exception("WHATSAPP ERROR")
        resp = MessagingResponse()
        resp.message("⚠️ Temporary error. Please try again.")
        return Response(str(resp), mimetype="application/xml")

# -------------------------
# RENDER ENTRY
# -------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
