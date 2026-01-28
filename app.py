from flask import Flask, request, Response, jsonify
from twilio.twiml.messaging_response import MessagingResponse
import logging, os, sys, time, base64, requests, re
from datetime import datetime

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
# ENV
# -------------------------
MPESA_CONSUMER_KEY = os.environ["MPESA_CONSUMER_KEY"]
MPESA_CONSUMER_SECRET = os.environ["MPESA_CONSUMER_SECRET"]
MPESA_SHORTCODE = os.environ["MPESA_SHORTCODE"]
MPESA_PASSKEY = os.environ["MPESA_PASSKEY"]
MPESA_CALLBACK_URL = os.environ["MPESA_CALLBACK_URL"]

# -------------------------
# IN-MEMORY STATE (TEMP)
# phone -> {amount, timestamp}
# -------------------------
PENDING = {}

# -------------------------
# HELPERS
# -------------------------
def normalize(text):
    return (text or "").strip().lower()

def parse_amount(text):
    m = re.search(r"pay\s*(\d+)", text)
    return int(m.group(1)) if m else None

def mpesa_token():
    r = requests.get(
        "https://api.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials",
        auth=(MPESA_CONSUMER_KEY, MPESA_CONSUMER_SECRET),
        timeout=10,
    )
    return r.json()["access_token"]

def stk_push(phone, amount):
    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    password = base64.b64encode(
        f"{MPESA_SHORTCODE}{MPESA_PASSKEY}{ts}".encode()
    ).decode()

    payload = {
        "BusinessShortCode": MPESA_SHORTCODE,
        "Password": password,
        "Timestamp": ts,
        "TransactionType": "CustomerPayBillOnline",
        "Amount": amount,
        "PartyA": phone,
        "PartyB": MPESA_SHORTCODE,
        "PhoneNumber": phone,
        "CallBackURL": MPESA_CALLBACK_URL,
        "AccountReference": "ChatPesa",
        "TransactionDesc": "ChatPesa Payment",
    }

    headers = {
        "Authorization": f"Bearer {mpesa_token()}",
        "Content-Type": "application/json",
    }

    r = requests.post(
        "https://api.safaricom.co.ke/mpesa/stkpush/v1/processrequest",
        json=payload,
        headers=headers,
        timeout=10,
    )
    return r.json()

# -------------------------
# HEALTH
# -------------------------
@app.route("/health")
def health():
    return "OK", 200

# -------------------------
# WHATSAPP WEBHOOK
# -------------------------
@app.route("/webhook/whatsapp", methods=["POST"])
def whatsapp():
    body = request.values.get("Body", "")
    sender = request.values.get("From", "")
    phone = sender.replace("whatsapp:", "")

    logging.info(f"WA from {phone}: {body}")

    msg = normalize(body)
    resp = MessagingResponse()

    if msg in ["hi", "hello", "hey", "start"]:
        resp.message("👋 Hi! Type *pay 100* to pay.")
        return Response(str(resp), mimetype="application/xml")

    amount = parse_amount(msg)
    if amount:
        PENDING[phone] = {"amount": amount, "time": time.time()}
        resp.message(
            f"💳 Amount *KES {amount}*\nReply *YES* to confirm or *NO* to cancel."
        )
        return Response(str(resp), mimetype="application/xml")

    if msg == "yes" and phone in PENDING:
        amount = PENDING[phone]["amount"]
        stk_push(phone, amount)
        resp.message("📲 STK sent. Enter your M-Pesa PIN.")
        return Response(str(resp), mimetype="application/xml")

    if msg == "no":
        PENDING.pop(phone, None)
        resp.message("❌ Payment cancelled.")
        return Response(str(resp), mimetype="application/xml")

    resp.message("❓ Try *pay 100*")
    return Response(str(resp), mimetype="application/xml")

# -------------------------
# MPESA CALLBACK
# -------------------------
@app.route("/webhook/mpesa", methods=["POST"])
def mpesa_callback():
    data = request.json
    logging.info(f"MPESA CALLBACK: {data}")

    cb = data["Body"]["stkCallback"]
    phone = cb.get("CallbackMetadata", {}).get("Item", [])[4].get("Value")

    if cb["ResultCode"] == 0:
        # SUCCESS
        from twilio.rest import Client
        client = Client(os.environ["TWILIO_SID"], os.environ["TWILIO_AUTH"])

        client.messages.create(
            from_="whatsapp:" + os.environ["TWILIO_WHATSAPP_NUMBER"],
            to="whatsapp:" + phone,
            body="✅ Payment successful. Thank you!",
        )
    return jsonify({"ok": True})

# -------------------------
# RUN
# -------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
