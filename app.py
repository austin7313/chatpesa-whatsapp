import base64
import datetime
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

# =========================
# M-PESA PRODUCTION CONFIG
# =========================

MPESA_ENV = "production"

MPESA_CONSUMER_KEY = "B05zln19QXC3OBL6YuCkdhZ8zvYqZtXP"
MPESA_CONSUMER_SECRET = "MYRasd2p9gGFcuCR"

MPESA_SHORTCODE = "4031193"
MPESA_PASSKEY = "5a64ad290753ed331b662cf6d83d3149367867c102f964f522390ccbd85cb282"

CALLBACK_URL = "https://flowstack-caribou-1.onrender.com/mpesa/callback"

if MPESA_ENV == "sandbox":
    TOKEN_URL = "https://sandbox.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials"
    STK_PUSH_URL = "https://sandbox.safaricom.co.ke/mpesa/stkpush/v1/processrequest"
else:
    TOKEN_URL = "https://api.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials"
    STK_PUSH_URL = "https://api.safaricom.co.ke/mpesa/stkpush/v1/processrequest"

# =========================
# IN-MEMORY ORDER STORE
# =========================

orders = {}
order_counter = 1


# =========================
# UTILITIES
# =========================

def get_access_token():
    credentials = f"{MPESA_CONSUMER_KEY}:{MPESA_CONSUMER_SECRET}"
    encoded = base64.b64encode(credentials.encode()).decode()

    headers = {
        "Authorization": f"Basic {encoded}"
    }

    response = requests.get(TOKEN_URL, headers=headers, timeout=30)
    response.raise_for_status()
    return response.json()["access_token"]


def generate_password(timestamp):
    data = MPESA_SHORTCODE + MPESA_PASSKEY + timestamp
    encoded = base64.b64encode(data.encode()).decode()
    return encoded


def send_stk_push(phone, amount, account_reference):
    timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    password = generate_password(timestamp)
    access_token = get_access_token()

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    payload = {
        "BusinessShortCode": MPESA_SHORTCODE,
        "Password": password,
        "Timestamp": timestamp,
        "TransactionType": "CustomerPayBillOnline",
        "Amount": int(amount),
        "PartyA": phone,
        "PartyB": MPESA_SHORTCODE,
        "PhoneNumber": phone,
        "CallBackURL": CALLBACK_URL,
        "AccountReference": account_reference,
        "TransactionDesc": "FlowStack WhatsApp Payment"
    }

    response = requests.post(STK_PUSH_URL, json=payload, headers=headers, timeout=30)
    response.raise_for_status()
    return response.json()


# =========================
# HEALTH CHECK
# =========================

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


# =========================
# WHATSAPP WEBHOOK (TWILIO)
# =========================

@app.route("/webhook/whatsapp", methods=["POST"])
def whatsapp_webhook():
    global order_counter

    incoming_msg = request.form.get("Body", "").strip().lower()
    from_number = request.form.get("From", "").replace("whatsapp:", "")

    # Create order: order 100
    if incoming_msg.startswith("order"):
        try:
            amount = int(incoming_msg.split(" ")[1])
        except:
            return "Usage: order <amount> e.g. order 100"

        order_id = order_counter
        order_counter += 1

        orders[order_id] = {
            "phone": from_number,
            "amount": amount,
            "paid": False
        }

        return f"Order #{order_id} created. Amount KES {amount}. Reply 'pay {order_id}' to pay now."

    # Pay order: pay 1
    if incoming_msg.startswith("pay"):
        try:
            parts = incoming_msg.split(" ")
            order_id = int(parts[1])
        except:
            return "Usage: pay <order_id> e.g. pay 1"

        if order_id not in orders:
            return f"Order #{order_id} not found."

        order = orders[order_id]

        if order["paid"]:
            return f"Order #{order_id} already paid."

        try:
            stk_response = send_stk_push(
                phone=order["phone"],
                amount=order["amount"],
                account_reference=f"ORDER{order_id}"
            )
        except Exception as e:
            return f"Payment error: {str(e)}"

        return (
            f"STK Push sent for KES {order['amount']}.\n"
            f"Enter your M-Pesa PIN to complete payment."
        )

    return "Welcome to FlowStack. Send 'order 100' to create an order."


# =========================
# M-PESA CALLBACK
# =========================

@app.route("/mpesa/callback", methods=["POST"])
def mpesa_callback():
    data = request.json
    print("M-Pesa Callback:", data)

    try:
        stk_callback = data["Body"]["stkCallback"]
        result_code = stk_callback["ResultCode"]
        checkout_id = stk_callback["CheckoutRequestID"]

        if result_code == 0:
            metadata = stk_callback["CallbackMetadata"]["Item"]
            amount = next(item["Value"] for item in metadata if item["Name"] == "Amount")
            phone = next(item["Value"] for item in metadata if item["Name"] == "PhoneNumber")

            # Mark matching order as paid
            for order_id, order in orders.items():
                if order["phone"] == str(phone) and order["amount"] == int(amount):
                    order["paid"] = True
                    print(f"Order #{order_id} marked as PAID")
                    break

    except Exception as e:
        print("Callback parse error:", e)

    return jsonify({"ResultCode": 0, "ResultDesc": "Accepted"})


# =========================
# MAIN
# =========================

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
