import os
import uuid
import datetime
import threading
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS
from twilio.rest import Client
from twilio.twiml.messaging_response import MessagingResponse

app = Flask(__name__)
CORS(app)

# ================= CONFIG =================
SHORTCODE = os.getenv("MPESA_SHORTCODE", "4031193")
PASSKEY = os.getenv("MPESA_PASSKEY", "YOUR_PASSKEY")
CONSUMER_KEY = os.getenv("MPESA_CONSUMER_KEY", "YOUR_KEY")
CONSUMER_SECRET = os.getenv("MPESA_CONSUMER_SECRET", "YOUR_SECRET")
CALLBACK_URL = os.getenv("MPESA_CALLBACK_URL", "https://yourapp.com/mpesa/callback")

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_CLIENT = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

ORDERS = {}
SESSIONS = {}

# ================= HELPERS =================
def now():
    return datetime.datetime.utcnow().isoformat()

def normalize_phone(phone):
    phone = phone.replace("whatsapp:", "").replace("+", "").strip()
    if phone.startswith("0"):
        phone = "254" + phone[1:]
    if phone.startswith("7"):
        phone = "254" + phone
    return phone

def mpesa_token():
    r = requests.get(
        "https://api.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials",
        auth=(CONSUMER_KEY, CONSUMER_SECRET),
        timeout=10
    )
    r.raise_for_status()
    return r.json()["access_token"]

def stk_push_async(order):
    try:
        token = mpesa_token()
        timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        password = base64.b64encode(f"{SHORTCODE}{PASSKEY}{timestamp}".encode()).decode()
        phone = normalize_phone(order["phone"])

        payload = {
            "BusinessShortCode": SHORTCODE,
            "Password": password,
            "Timestamp": timestamp,
            "TransactionType": "CustomerPayBillOnline",
            "Amount": int(order["amount"]),
            "PartyA": phone,
            "PartyB": SHORTCODE,
            "PhoneNumber": phone,
            "CallBackURL": CALLBACK_URL,
            "AccountReference": order["id"],
            "TransactionDesc": "ChatPesa Payment"
        }

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

        r = requests.post(f"https://api.safaricom.co.ke/mpesa/stkpush/v1/processrequest",
                          json=payload, headers=headers, timeout=10)
        print("STK Push Status:", r.status_code, r.text)
    except Exception as e:
        print("STK Push Error:", str(e))

# ================= WHATSAPP DEBUG =================
@app.route("/whatsapp", methods=["POST"])
def whatsapp():
    try:
        phone = request.values.get("From", "")
        body = request.values.get("Body", "").strip()
        print(f"📥 Incoming WhatsApp Message from {phone}: {body}")

        resp = MessagingResponse()
        msg = resp.message()

        session = SESSIONS.get(phone, {"step": "START"})
        print(f"Current session: {session}")

        if session["step"] == "START":
            msg.body("👋 Welcome to ChatPesa\nReply 1 to make a payment")
            session["step"] = "MENU"

        elif session["step"] == "MENU" and body == "1":
            msg.body("💰 Enter amount to pay (KES), min 10")
            session["step"] = "AMOUNT"

        elif session["step"] == "AMOUNT":
            try:
                amount = int(body)
                if amount < 10:
                    raise ValueError
            except:
                msg.body("❌ Invalid amount. Enter a number ≥ 10")
                return str(resp)

            order_id = "CP" + uuid.uuid4().hex[:6].upper()
            ORDERS[order_id] = {
                "id": order_id,
                "phone": phone,
                "amount": amount,
                "status": "PENDING",
                "customer_name": phone,
                "created_at": now()
            }
            session["order_id"] = order_id
            session["step"] = "CONFIRM"
            msg.body(f"🧾 Order {order_id} for KES {amount}\nReply PAY to proceed")

        elif session["step"] == "CONFIRM" and body.upper() == "PAY":
            order = ORDERS.get(session["order_id"])
            msg.body("📲 Sending M-Pesa prompt...")
            threading.Thread(target=stk_push_async, args=(order,)).start()
            session["step"] = "DONE"

        else:
            msg.body("Reply 1 to start a payment")

        SESSIONS[phone] = session
        print(f"Updated session: {SESSIONS[phone]}")
        return str(resp)
    except Exception as e:
        print("Error in WhatsApp handler:", str(e))
        return "OK", 200

# ================= MPESA CALLBACK =================
@app.route("/mpesa/callback", methods=["POST"])
def mpesa_callback():
    try:
        data = request.json
        cb = data["Body"]["stkCallback"]
        order = None

        if cb["ResultCode"] == 0:
            meta = cb["CallbackMetadata"]["Item"]
            receipt = next(i["Value"] for i in meta if i["Name"] == "MpesaReceiptNumber")
            phone = str(next(i["Value"] for i in meta if i["Name"] == "PhoneNumber"))
            amount = next(i["Value"] for i in meta if i["Name"] == "Amount")

            for o in ORDERS.values():
                if normalize_phone(o["phone"]) == normalize_phone(phone) and int(o["amount"]) == int(amount):
                    o["status"] = "PAID"
                    o["mpesa_receipt"] = receipt
                    o["paid_at"] = now()
                    order = o
                    break

            # Send WhatsApp confirmation
            if order:
                TWILIO_CLIENT.messages.create(
                    body=f"✅ Payment received for Order {order['id']} KES {order['amount']}",
                    from_="whatsapp:+14155238886",
                    to=order["phone"]
                )
        else:
            print("❌ STK Failed:", cb)
    except Exception as e:
        print("Error in M-Pesa callback:", str(e))
    return jsonify({"status": "ok"})

# ================= DASHBOARD =================
@app.route("/orders")
def orders():
    return jsonify({"status": "ok", "orders": list(ORDERS.values())})

@app.route("/")
def root():
    return "ChatPesa API ONLINE", 200

# ================= SERVER =================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
