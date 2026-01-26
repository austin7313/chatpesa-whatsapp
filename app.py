import os
import uuid
import base64
import datetime
import threading
import requests

from flask import Flask, request, jsonify
from flask_cors import CORS
from twilio.twiml.messaging_response import MessagingResponse

app = Flask(__name__)
CORS(app)

# ================= CONFIG =================
SHORTCODE = "4031193"
PASSKEY = "5a64ad290753ed331b662cf6d83d3149367867c102f964f522390ccbd85cb282"

CONSUMER_KEY = "B05zln19QXC3OBL6YuCkdhZ8zvYqZtXP"
CONSUMER_SECRET = "MYRasd2p9gGFcuCR"

MPESA_BASE = "https://api.safaricom.co.ke"
CALLBACK_URL = "https://chatpesa-whatsapp.onrender.com/mpesa/callback"

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
    """Run STK push in background thread."""
    try:
        token = mpesa_token()
        timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")

        password = base64.b64encode(
            f"{SHORTCODE}{PASSKEY}{timestamp}".encode()
        ).decode()

        phone = normalize_phone(order["customer_phone"])

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

        r = requests.post(
            f"{MPESA_BASE}/mpesa/stkpush/v1/processrequest",
            json=payload,
            headers=headers,
            timeout=10
        )

        print(f"✅ STK Push for {order['id']}: {r.status_code}")
        print(f"   Response: {r.text}")

        # Update order with STK response
        if r.status_code == 200:
            response_data = r.json()
            if response_data.get("ResponseCode") == "0":
                ORDERS[order["id"]]["stk_sent"] = True
            else:
                ORDERS[order["id"]]["status"] = "failed"
                ORDERS[order["id"]]["error"] = response_data.get("ResponseDescription")
        else:
            ORDERS[order["id"]]["status"] = "failed"

    except Exception as e:
        print(f"❌ STK ERROR for {order['id']}: {str(e)}")
        ORDERS[order["id"]]["status"] = "failed"
        ORDERS[order["id"]]["error"] = str(e)

# ================= WHATSAPP =================
@app.route("/webhook/whatsapp", methods=["POST"])
def whatsapp():
    body = request.values.get("Body", "").strip().upper()
    phone = request.values.get("From")
    profile_name = request.values.get("ProfileName", "Customer")

    resp = MessagingResponse()
    msg = resp.message()

    session = SESSIONS.get(phone, {"step": "START"})

    if session["step"] == "START":
        msg.body(
            "👋 Welcome to ChatPesa\n\n"
            "Reply 1️⃣ to make a payment"
        )
        session["step"] = "MENU"

    elif session["step"] == "MENU" and body == "1":
        msg.body("💰 Enter amount to pay (KES)\nMinimum: 10")
        session["step"] = "AMOUNT"

    elif session["step"] == "AMOUNT":
        try:
            amount = int(body)
            if amount < 10:
                raise ValueError
        except:
            msg.body("❌ Invalid amount. Enter a number ≥ 10")
            return str(resp), 200

        order_id = "CP" + uuid.uuid4().hex[:6].upper()

        # ✅ Fixed order structure for dashboard
        ORDERS[order_id] = {
            "id": order_id,
            "customer_phone": normalize_phone(phone),
            "customer_name": profile_name,
            "items": f"Payment of KES {amount}",  # Dashboard displays this
            "amount": amount,
            "status": "awaiting_payment",  # ✅ Lowercase
            "payment_method": "mpesa",
            "receipt_number": None,
            "created_at": now(),
            "paid_at": None,
            "stk_sent": False
        }

        session["order_id"] = order_id
        session["step"] = "CONFIRM"

        msg.body(
            f"🧾 Order ID: {order_id}\n"
            f"Amount: KES {amount}\n\n"
            f"Reply PAY to receive M-Pesa prompt"
        )

    elif session["step"] == "CONFIRM" and body == "PAY":
        order = ORDERS.get(session["order_id"])
        
        if not order:
            msg.body("❌ Order not found. Reply 1️⃣ to start again")
            session["step"] = "START"
        else:
            # 🚀 CRITICAL: Respond to WhatsApp FIRST
            msg.body("📲 Sending M-Pesa prompt to your phone. Enter your PIN to complete payment.")

            # 🚀 Then trigger STK in background
            threading.Thread(target=stk_push_async, args=(order,), daemon=True).start()

            session["step"] = "DONE"

    else:
        msg.body("Reply 1️⃣ to start a payment")
        session["step"] = "MENU"

    SESSIONS[phone] = session
    return str(resp), 200

# ================= MPESA CALLBACK =================
@app.route("/mpesa/callback", methods=["POST"])
def mpesa_callback():
    try:
        data = request.json
        print(f"💰 M-Pesa Callback: {data}")
        
        cb = data["Body"]["stkCallback"]

        if cb["ResultCode"] == 0:
            # Payment successful
            meta = cb["CallbackMetadata"]["Item"]

            receipt = next(i["Value"] for i in meta if i["Name"] == "MpesaReceiptNumber")
            phone = str(next(i["Value"] for i in meta if i["Name"] == "PhoneNumber"))
            amount = next(i["Value"] for i in meta if i["Name"] == "Amount")

            # Match order
            for o in ORDERS.values():
                if (
                    o["status"] == "awaiting_payment"
                    and normalize_phone(o["customer_phone"]) == normalize_phone(str(phone))
                    and o["amount"] == amount
                ):
                    o["status"] = "paid"  # ✅ Lowercase
                    o["receipt_number"] = receipt  # ✅ Dashboard field name
                    o["paid_at"] = now()
                    print(f"✅ Order {o['id']} marked as PAID - Receipt: {receipt}")
                    break
        else:
            # Payment failed
            print(f"❌ M-Pesa payment failed: {cb.get('ResultDesc')}")
            
        return jsonify({"ResultCode": 0, "ResultDesc": "Success"}), 200
        
    except Exception as e:
        print(f"❌ Callback error: {str(e)}")
        return jsonify({"ResultCode": 1, "ResultDesc": "Error"}), 200

# ================= DASHBOARD API =================
@app.route("/health")
def health():
    """Health check for dashboard"""
    return jsonify({
        "status": "ok",
        "service": "chatpesa",
        "timestamp": now(),
        "orders_count": len(ORDERS)
    })

@app.route("/orders")
def orders():
    """Get all orders - dashboard endpoint"""
    orders_list = list(ORDERS.values())
    
    # Sort by created_at descending (newest first)
    orders_list.sort(key=lambda x: x.get('created_at', ''), reverse=True)
    
    return jsonify({
        "success": True,  # ✅ Dashboard expects this
        "orders": orders_list,
        "count": len(orders_list)
    })

@app.route("/")
def root():
    """API info page"""
    return jsonify({
        "service": "ChatPesa API",
        "status": "online",
        "version": "1.0",
        "endpoints": {
            "health": "/health",
            "orders": "/orders",
            "whatsapp_webhook": "/webhook/whatsapp",
            "mpesa_callback": "/mpesa/callback"
        }
    }), 200

# ================= SERVER =================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=False)
