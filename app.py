from flask import Flask, request, Response
import logging
import sys
import os
from twilio.twiml.messaging_response import MessagingResponse

app = Flask(__name__)

# -------------------------
# LOGGING (CRITICAL)
# -------------------------
logging.basicConfig(
    level=logging.INFO,
    stream=sys.stdout,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

@app.before_request
def log_request():
    logging.info("---- INCOMING REQUEST ----")
    logging.info(f"Method: {request.method}")
    logging.info(f"URL: {request.url}")
    logging.info(f"Headers: {dict(request.headers)}")
    logging.info(f"Body: {request.get_data(as_text=True)}")

@app.after_request
def log_response(response):
    logging.info("---- OUTGOING RESPONSE ----")
    logging.info(f"Status: {response.status}")
    logging.info(f"Body: {response.get_data(as_text=True)}")
    return response


# -------------------------
# HEALTH CHECK (TEST THIS FIRST)
# -------------------------
@app.route("/health", methods=["GET"])
def health():
    return "OK - App is running", 200


# -------------------------
# WHATSAPP WEBHOOK
# -------------------------
@app.route("/webhook/whatsapp", methods=["POST"])
def whatsapp_webhook():
    try:
        incoming_msg = request.values.get("Body", "").strip()
        from_number = request.values.get("From", "")

        logging.info(f"WhatsApp message from {from_number}: {incoming_msg}")

        resp = MessagingResponse()
        resp.message("Webhook alive ✅ Message received.")

        return Response(str(resp), mimetype="application/xml")

    except Exception as e:
        logging.exception("WHATSAPP WEBHOOK ERROR")
        return Response("Internal Server Error", status=500)


# -------------------------
# RENDER PORT BINDING
# -------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
