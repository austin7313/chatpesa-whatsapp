from flask import Flask, request, jsonify
from datetime import datetime

app = Flask(__name__)

# Simulated in-memory orders (replace with your DB)
ORDERS_DB = {}

# Sample order creation for reference
# ORDERS_DB["ORD9219"] = {
#     "id": "ORD9219",
#     "customer_name": "Wyckyaustin",
#     "customer_phone": "0722xxxxxx",
#     "items": "Custom Order",
#     "amount": 1000,
#     "status": "AWAITING_PAYMENT",
#     "created_at": datetime.utcnow().isoformat()
# }

@app.route("/mpesa/callback", methods=["POST"])
def mpesa_callback():
    """
    Receive payment confirmation from M-Pesa Daraja (production)
    """
    try:
        data = request.json
        print(f"📤 M-Pesa Callback Received: {data}")

        # Extract relevant fields (adjust according to your Daraja setup)
        trans_id = data.get("TransactionID")
        amount = float(data.get("Amount", 0))
        order_id = data.get("BillRefNumber")  # your Order ID
        first_name = data.get("FirstName", "")
        middle_name = data.get("MiddleName", "")
        last_name = data.get("LastName", "")

        customer_name = " ".join([first_name, middle_name, last_name]).strip()

        # Validate order exists
        order = ORDERS_DB.get(order_id)
        if not order:
            print(f"❌ Unknown order: {order_id}")
            return jsonify({"status": "error", "message": "Order not found"}), 404

        # Validate amount
        if amount != order["amount"]:
            print(f"❌ Amount mismatch: {amount} != {order['amount']}")
            return jsonify({"status": "error", "message": "Amount mismatch"}), 400

        # Update order
        order["status"] = "PAID"
        order["customer_name"] = customer_name
        order["paid_at"] = datetime.utcnow().isoformat()
        order["transaction_id"] = trans_id

        print(f"✅ Order {order_id} marked PAID, customer: {customer_name}")

        # Return 200 to M-Pesa (always!)
        return jsonify({"status": "success"}), 200

    except Exception as e:
        print(f"❌ Callback processing error: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500
