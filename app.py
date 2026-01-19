from flask import Flask, jsonify, request
from flask_cors import CORS
import logging
import requests

app = Flask(__name__)
CORS(app)  # Allow all origins for testing

# ----------------------------
# Logging setup
# ----------------------------
logging.basicConfig(level=logging.INFO)

# ----------------------------
# Backend test endpoints
# ----------------------------
@app.route("/health", methods=["GET"])
def health():
    logging.info("Health check called")
    return jsonify({"status": "ok"})

@app.route("/orders", methods=["GET"])
def orders():
    logging.info("Orders endpoint called")
    # Simulate empty orders for now
    orders_list = []
    return jsonify({"orders": orders_list, "status": "ok"})

# ----------------------------
# Diagnostic endpoint for debugging dashboard connection
# ----------------------------
@app.route("/diagnostic", methods=["GET"])
def diagnostic():
    result = {}
    try:
        # Test if server is reachable
        result['server_reachable'] = True

        # Test CORS
        result['cors_test'] = "CORS enabled"

        # Test if /orders endpoint works internally
        r = requests.get(request.url_root + "orders")
        result['internal_orders_call'] = {
            "status_code": r.status_code,
            "json": r.json()
        }
    except Exception as e:
        result['error'] = str(e)
    
    logging.info(f"Diagnostic result: {result}")
    return jsonify(result)

# ----------------------------
# Run app
# ----------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
