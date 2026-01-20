from flask import Flask, request, jsonify
from datetime import datetime
import pytz

app = Flask(__name__)

# In-memory orders storage (replace with DB in production)
orders = []

# Nairobi timezone
EAT = pytz.timezone("Africa/Nairobi")


# Utility: normalize phone numbers
def normalize_phone(p):
    if not p:
        return None
    p = str(p)
    if p.startswith("+254"):
        return "0" + p[4:]
    if p.startswith("254"):
        return "0" + p[3:]
    return p


# Health check
@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200


# Create new order (WhatsApp webhook simulation)
@app.route("/webhook/whatsapp", methods=["POST"])
def whatsapp_webhook():
    data = request.json
    from_number = data.get("From")
    incoming_msg = data.get("Body", "").strip()

    if not from_number or not incoming_msg:
        return jsonify({"error": "Missing fields"}), 400

    # Generate receipt / order id
    receipt_number = f"RCP{len(orders)+1:04d}"

    order = {
        "id": receipt_number,
        "customer_phone": from_number,
        "items": f"Order from WhatsApp: {incoming_msg}",
        "raw_message": incoming_msg,
        "amount": 0,
        "status": "awaiting_payment",
        "receipt_number": receipt_number,
        "mpesa_receipt": None,
        "payer_name": None,  # NEW FIELD
        "created_at": datetime.now(EAT).isoformat()
    }

    orders.append(order)
    return jsonify({"status": "ok", "order": order}), 200


# STK callback (Safaricom M-Pesa)
@app.route("/webhook/stk", methods=["POST"])
def stk_callback():
    callback_data = request.json or {}

    # Extract metadata safely
    meta_items = callback_data.get("CallbackMetadata", {}).get("Item", [])
    meta = {}
    for item in meta_items:
        name = item.get("Name")
        value = item.get("Value")
        if name:
            meta[name] = value

    receipt = meta.get("MpesaReceiptNumber")
    phone = meta.get("PhoneNumber")
    amount = meta.get("Amount", 0)

    # Extract payer name
    first = str(meta.get("FirstName", "") or "").strip()
    middle = str(meta.get("MiddleName", "") or "").strip()
    last = str(meta.get("LastName", "") or "").strip()
    payer_name = " ".join([first, middle, last]).strip() or None

    # Normalize phone for matching
    callback_phone = normalize_phone(phone)

    # Match oldest awaiting_payment order for this phone (FIFO)
    matched_order = None
    for order in orders:
        if order["status"] != "awaiting_payment":
            continue
        order_phone = normalize_phone(order["customer_phone"].replace("whatsapp:", ""))
        if order_phone == callback_phone:
            matched_order = order
            break

    if matched_order:
        matched_order["status"] = "paid"
        matched_order["mpesa_receipt"] = receipt
        matched_order["payer_name"] = payer_name
        matched_order["amount"] = amount
        print(f"✅ Payment matched: {matched_order['id']} | {payer_name} | {amount}")
    else:
        print(f"⚠️ Callback received but no matching order for {callback_phone}")

    # Respond to Safaricom
    return jsonify({"ResultCode": 0, "ResultDesc": "Accepted"}), 200


# Fetch all orders (Dashboard)
@app.route("/orders", methods=["GET"])
def get_orders():
    return jsonify({"status": "ok", "orders": orders}), 200


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
