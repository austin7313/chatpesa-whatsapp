import os, sys, time, base64, logging, requests
from datetime import datetime
from flask import Flask, request, jsonify, Response
from twilio.rest import Client
from twilio.twiml.messaging_response import MessagingResponse

app = Flask(__name__)

# -------------------------# -------------------------
# ENV / CREDENTIALS (SAFE)
# -------------------------
def get_env(name):
    value = os.environ.get(name)
    if not value:
        logging.error(f"❌ Environment variable {name} is not set!")
        sys.exit(1)
    return value

MPESA_CONSUMER_KEY = get_env("MPESA_CONSUMER_KEY")
MPESA_CONSUMER_SECRET = get_env("MPESA_CONSUMER_SECRET")
MPESA_SHORTCODE = get_env("MPESA_SHORTCODE")
MPESA_PASSKEY = get_env("MPESA_PASSKEY")
MPESA_CALLBACK_URL = get_env("MPESA_CALLBACK_URL")  # must match /webhook/mpesa

TWILIO_SID = get_env("TWILIO_SID")
TWILIO_AUTH = get_env("TWILIO_AUTH")
TWILIO_WHATSAPP_NUMBER = get_env("TWILIO_WHATSAPP_NUMBER")

# -------------------------
# IN-MEMORY STATE (TEMP)
# -------------------------
PENDING = {}  # phone -> {amount, timestamp}

# -------------------------
# HELPERS
# -------------------------
def normalize(text):
    return (text or "").strip().lower()

def normalize_phone(phone):
    phone = phone.replace("whatsapp:", "").replace("+", "")
    if phone.startswith("0"):
        phone = "254" + phone[1:]
    return phone

def parse_amount(text):
    import re
    m = re.search(r"pay\s*(\d+)", text)
    return int(m.group(1)) if m else None

def get_mpesa_token():
    r = requests.get(
        "https://api.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials",
        auth=(MPESA_CONSUMER_KEY, MPESA_CONSUMER_SECRET),
        timeout=10,
    )
    r.raise_for_status()
    return r.json()["access_token"]

def stk_push(phone, amount):
    phone = normalize_phone(phone)
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    password = base64.b64encode(
        f"{MPESA_SHORTCODE}{MPESA_PASSKEY}{timestamp}".encode()
    ).decode()

    payload = {
        "BusinessShortCode": MPESA_SHORTCODE,
        "Password": password,
        "Timestamp": timestamp,
        "TransactionType": "CustomerPayBillOnline",
        "Amount": int(amount),
        "PartyA": phone,
        "PartyB": MPESA_SHORTCODE,
        "PhoneNumber": phone,
        "CallBackURL": MPESA_CALLBACK_URL,
        "AccountReference": "ChatPesa",
        "TransactionDesc": "ChatPesa Payment",
    }

    headers = {
        "Authorization": f"Bearer {get_mpesa_token()}",
        "Content-Type": "application/json",
    }

    r = requests.post(
        "https://api.safaricom.co.ke/mpesa/stkpush/v1/processrequest",
        json=payload,
        headers=headers,
        timeout=10,
    )
    logging.info(f"STK PUSH RESPONSE: {r.text}")
    return r.json()

def send_whatsapp(phone, message):
    phone = normalize_phone(phone)
    client = Client(TWILIO_SID, TWILIO_AUTH)
    client.messages.create(
        from_="whatsapp:" + TWILIO_WHATSAPP_NUMBER,
        to="whatsapp:" + phone,
        body=message,
    )

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
    phone = normalize_phone(sender)

    logging.info(f"WhatsApp from {phone}: {body}")
    msg = normalize(body)
    resp = MessagingResponse()

    if msg in ["hi", "hello", "hey", "start"]:
        resp.message("👋 Hi! Type *pay 100* to pay.")
        return Response(str(resp), mimetype="application/xml")

    amount = parse_amount(msg)
    if amount:
        PENDING[phone] = {"amount": amount, "time": time.time()}
        resp.message(f"💳 Amount KES {amount}\nReply *YES* to confirm or *NO* to cancel.")
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

    cb = data.get("Body", {}).get("stkCallback", {})
    result_code = cb.get("ResultCode")
    metadata_items = cb.get("CallbackMetadata", {}).get("Item", [])

    phone = None
    if metadata_items:
        # Safaricom always returns PhoneNumber somewhere in CallbackMetadata
        for item in metadata_items:
            if item.get("Name") == "PhoneNumber":
                phone = str(item.get("Value"))

    if phone and result_code == 0:
        send_whatsapp(phone, "✅ Payment successful. Thank you!")
        PENDING.pop(phone, None)
    elif phone:
        send_whatsapp(phone, "❌ Payment failed. Try again.")

    return jsonify({"ok": True})

# -------------------------
# RUN
# -------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
