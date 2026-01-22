import os, uuid, base64, datetime, requests
from flask import Flask, request, jsonify
from flask_cors import CORS
from twilio.twiml.messaging_response import MessagingResponse

app = Flask(__name__)
CORS(app)

# ====== MPESA CONFIG (PRODUCTION) ======
SHORTCODE = "4031193"
PASSKEY = "5a64ad290753ed331b662cf6d83d3149367867c102f964f522390ccbd85cb282"
CONSUMER_KEY = "B05zln19QXC3OBL6YuCkdhZ8zvYqZtXP"
CONSUMER_SECRET = "MYRasd2p9gGFcuCR"
CALLBACK_URL = "https://chatpesa-whatsapp.onrender.com/mpesa/callback"

MPESA_BASE = "https://api.safaricom.co.ke"

ORDERS = {}
SESSIONS = {}

# ====== HELPERS ======
def now():
    return datetime.datetime.utcnow().isoformat()

def token():
    auth = base64.b64encode(f"{CONSUMER_KEY}:{CONSUMER_SECRET}".encode()).decode()
    r = requests.get(
        f"{MPESA_BASE}/oauth/v1/generate?grant_type=client_credentials",
        headers={"Authorization": f"Basic {auth}"}
    )
    return r.json()["access_token"]

def stk_push(order):
    ts = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    password = base64.b64encode(f"{SHORTCODE}{PASSKEY}{ts}".encode()).decode()

    payload = {
        "BusinessShortCode": SHORTCODE,
        "Password": password,
        "Timestamp": ts,
        "TransactionType": "CustomerPayBillOnline",
        "Amount": order["amount"],
        "PartyA": order["phone"],
        "PartyB": SHORTCODE,
        "PhoneNumber": order["phone"],
        "CallBackURL": CALLBACK_URL,
        "AccountReference": order["id"],
        "TransactionDesc": "ChatPesa Payment"
    }

    requests.post(
        f"{MPESA_BASE}/mpesa/stkpush/v1/processrequest",
        json=payload,
        headers={"Authorization": f"Bearer {token()}"}
    )

# ====== WHATSAPP WEBHOOK ======
@app.route("/webhook/whatsapp", methods=["POST"])
def whatsapp():
    msg_in = request.values.get("Body", "").strip()
    phone = request.values.get("From", "").replace("whatsapp:", "")
    resp = MessagingResponse()
    msg = resp.message()

    session = SESSIONS.get(phone, {"step": "start"})
    step = session["step"]

    if step == "start":
        msg.body(
            "👋 Welcome to ChatPesa\n\n"
            "1️⃣ Make a payment\n"
            "Reply with 1 to continue"
        )
        session["step"] = "choose"
    
    elif step == "choose" and msg_in == "1":
        msg.body("💳 Enter amount to pay (KES)\nMinimum: 10")
        session["step"] = "amount"

    elif step == "amount":
        try:
            amount = int(msg_in)
            if amount < 10:
                raise ValueError
        except:
            msg.body("❌ Invalid amount. Enter number ≥ 10")
            return str(resp)

        order_id = "CP" + uuid.uuid4().hex[:6].upper()
        ORDERS[order_id] = {
            "id": order_id,
            "phone": phone,
            "amount": amount,
            "status": "AWAITING_PAYMENT",
            "created_at": now(),
            "customer_name": phone
        }

        session["order_id"] = order_id
        session["step"] = "confirm"

        msg.body(
            f"🧾 Order Summary\n"
            f"Amount: KES {amount}\n\n"
            f"Reply PAY to confirm"
        )

    elif step == "confirm" and msg_in.lower() == "pay":
        order = ORDERS[session["order_id"]]
        stk_push(order)
        msg.body("📲 M-Pesa prompt sent. Enter your PIN.")
        session["step"] = "done"

    else:
        msg.body("Reply 1 to start a payment")

    SESSIONS[phone] = session
    return str(resp), 200

# ====== MPESA CALLBACK ======
@app.route("/mpesa/callback", methods=["POST"])
def mpesa_callback():
    data = request.json
    stk = data["Body"]["stkCallback"]

    if stk["ResultCode"] == 0:
        meta = stk["CallbackMetadata"]["Item"]
        receipt = next(i["Value"] for i in meta if i["Name"] == "MpesaReceiptNumber")

        for o in ORDERS.values():
            if o["status"] == "AWAITING_PAYMENT":
                o["status"] = "PAID"
                o["customer_name"] = receipt
                o["created_at"] = now()
                break

    return jsonify({"status": "ok"})

# ====== DASHBOARD ======
@app.route("/orders")
def orders():
    return jsonify({"status": "ok", "orders": list(ORDERS.values())})

@app.route("/")
def root():
    return "ChatPesa API ONLINE", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
