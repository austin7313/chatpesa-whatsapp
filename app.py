import os
import json
import requests
from flask import Flask, request, jsonify
from twilio.rest import Client
from datetime import datetime

app = Flask(__name__)

# Load environment variables
TWILIO_SID = os.environ.get("TWILIO_SID")
TWILIO_AUTH = os.environ.get("TWILIO_AUTH")
TWILIO_WHATSAPP_NUMBER = os.environ.get("TWILIO_WHATSAPP_NUMBER")

MPESA_SHORTCODE = os.environ.get("MPESA_SHORTCODE")
MPESA_PASSKEY = os.environ.get("MPESA_PASSKEY")
MPESA_CONSUMER_KEY = os.environ.get("MPESA_CONSUMER_KEY")
MPESA_CONSUMER_SECRET = os.environ.get("MPESA_CONSUMER_SECRET")
MPESA_CALLBACK_URL = os.environ.get("MPESA_CALLBACK_URL")

# Twilio client
client = Client(TWILIO_SID, TWILIO_AUTH)

# ------------------------
# Diagnostic logging helper
# ------------------------
def log(msg, data=None):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if data:
        print(f"{timestamp} | {msg}: {data}")
    else:
        print(f"{timestamp} | {msg}")

# ------------------------
# WhatsApp webhook route
# ------------------------
@app.route("/webhook/whatsapp", methods=["POST"])
def whatsapp_webhook():
    log("✅ Incoming WhatsApp message", request.form.to_dict())

    from_number = request.form.get("From")
    body = request.form.get("Body")

    if not from_number or not body:
        log("❌ Missing From or Body in request", request.form)
        return "Bad Request", 400

    # Example: Echo message back for testing
    try:
        message = client.messages.create(
            body=f"Received your message: {body}",
            from_=f"whatsapp:{TWILIO_WHATSAPP_NUMBER}",
            to=from_number
        )
        log("📩 WhatsApp reply sent", {"sid": message.sid, "to": from_number})
    except Exception as e:
        log("❌ Failed to send WhatsApp reply", str(e))

    return "OK", 200

# ------------------------
# STK Push diagnostic route
# ------------------------
@app.route("/mpesa/test", methods=["POST"])
def mpesa_test():
    data = request.get_json()
    log("💰 STK Push test request", data)

    # Dummy response
    return jsonify({"status": "ok", "note": "STK diagnostic received"}), 200

# ------------------------
# Health check
# ------------------------
@app.route("/", methods=["GET"])
def health_check():
    return "ChatPesa Diagnostic Server ✅", 200

# ------------------------
# Run server
# ------------------------
if __name__ == "__main__":
    log("🚀 Starting ChatPesa diagnostic server")
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
