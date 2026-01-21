from flask import Flask, request, jsonify
from flask_cors import CORS
from twilio.twiml.messaging_response import MessagingResponse
import requests
from requests.auth import HTTPBasicAuth
from datetime import datetime
import random
import base64

app = Flask(__name__)
CORS(app)

# --- MPESA CONFIG ---
MPESA_SHORTCODE = "4031193"
MPESA_PASSKEY = "5a64ad290753ed331b662cf6d83d3149367867c102f964f522390ccbd85cb282"
MPESA_CONSUMER_KEY = "B05zln19QXC3OBL6YuCkdhZ8zvYqZtXP"
MPESA_CONSUMER_SECRET = "MYRasd2p9gGFcuCR"
MPESA_ENV = "sandbox"  # change to 'production' when live
CALLBACK_URL = "https://your-server.com/mpesa/callback"

# --- IN-MEMORY ORDERS DB ---
orders_db = []

# --- HELPERS ---
def generate_order_id():
    return f"RCP{random.randint(1000,9999)}"

def parse_order_message(msg):
    msg_lower = msg.lower()
    items, amount = [], 0
    if "item1" in msg_lower:
        items.append("Item1")
        amount += 100
    if "item2" in msg_lower:
        items.append("Item2")
        amount += 200
    if not items:
        items.append("Custom Order")
        amount = 1000
    return {"items": " + ".join(items), "amount": amount}

# --- MPESA FUNCTIONS ---
def get_mpesa_token():
    url = "https://sandbox.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials"
    r = requests.get(url, auth=HTTPBasicAuth(MPESA_CONSUMER_KEY, MPESA_CONSUMER_SECRET))
    r.raise_for_status()
    return r.json()['access_token']

def initiate_stk_push(phone, amount, order_id):
    token = get_mpesa_token()
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    password_str = f"{MPESA_SHORTCODE}{MPESA_PASSKEY}{timestamp}"
    password = base64.b64encode(password_str.encode()).decode()

    stk_url = "https://sandbox.safaricom.co.ke/mpesa/stkpush/v1/processrequest"
    headers = {"Authorization": f"Bearer {token}"}
    payload = {
        "BusinessShortCode": MPESA_SHORTCODE,
        "Password": password,
        "Timestamp": timestamp,
        "TransactionType": "CustomerPayBillOnline",
        "Amount": amount,
        "PartyA": phone,
        "PartyB": MPESA_SHORTCODE,
        "PhoneNumber": phone,
        "CallBackURL": CALLBACK_URL,
        "AccountReference": order_id,
        "TransactionDesc": f"Payment for {order_id}"
    }
    r = requests.post(stk_url, json=payload, headers=headers)
    return r.json()

# --- WHATSAPP WEBHOOK ---
@app.route("/webhook/whatsapp", methods=["POST"])
def whatsapp_webhook():
    try:
        incoming_msg = request.form.get("Body", "").strip()
        from_number = request.form.get("From", "").replace("whatsapp:", "")
        profile_name = request.form.get("ProfileName", "Customer")

        order_details = parse_order_message(incoming_msg)
        order_id = generate_order_id()
        order = {
            "id": order_id,
            "customer_phone": from_number,
            "customer_name": profile_name,
            "items": order_details["items"],
            "amount": order_details["amount"],
            "status": "AWAITING_PAYMENT",
            "created_at": datetime.utcnow().isoformat()
        }
        orders_db.append(order)

        # Trigger STK push
        stk_response = initiate_stk_push(from_number, order_details["amount"], order_id)
        print(f"STK push response: {stk_response}")

        # WhatsApp reply
        resp = MessagingResponse()
        resp.message(
            f"✅ Order received!\n\n"
            f"Order ID: {order_id}\n"
            f"Items: {order_details['items']}\n"
            f"Amount: KES {order_details['amount']}\n\n"
            f"You will receive an M-Pesa prompt to pay now.\n"
        )
        return str(resp), 200, {'Content-Type': 'text/xml'}

    except Exception as e:
        print(f"Error in webhook: {e}")
        resp = MessagingResponse()
        resp.message("Sorry, we couldn't process your order. Please try again.")
        return str(resp), 200, {'Content-Type': 'text/xml'}

# --- MPESA CALLBACK ---
@app.route("/mpesa/callback", methods=["POST"])
def mpesa_callback():
    try:
        data = request.get_json()
        # Example: data contains 'Body' -> 'stkCallback' -> 'CallbackMetadata'
        result_code = data['Body']['stkCallback']['ResultCode']
        metadata = data['Body']['stkCallback'].get('CallbackMetadata', {}).get('Item', [])
        mpesa_name = ""
        amount = 0
        for item in metadata:
            if item['Name'] == 'Amount':
                amount = item['Value']
            if item['Name'] == 'MpesaReceiptNumber':
                receipt = item['Value']
            if item['Name'] == 'PhoneNumber':
                phone = item['Value']

        # Update order
        account_ref = data['Body']['stkCallback']['MerchantRequestID']
        for order in orders_db:
            if order['id'] == account_ref:
                order['status'] = "PAID" if result_code == 0 else "FAILED"
                order['customer_name'] = mpesa_name or order['customer_name']
                order['paid_at'] = datetime.utcnow().isoformat()

        return jsonify({"success": True})
    except Exception as e:
        print(f"Error in MPESA callback: {e}")
        return jsonify({"success": False}), 500

# --- ORDERS ENDPOINT ---
@app.route("/orders", methods=["GET"])
def get_orders():
    return jsonify({"status": "ok", "orders": orders_db})

# --- HEALTH CHECK ---
@app.route("/health")
def health():
    return {"status": "ok"}

if __name__ == "__main__":
    app.run(debug=True)
