from flask import Flask, jsonify
from flask_cors import CORS
import logging

app = Flask(__name__)
CORS(app)  # Allow all origins for dashboard to call

# ----------------------------
# Logging setup
# ----------------------------
logging.basicConfig(level=logging.INFO)

# ----------------------------
# Simulated orders storage
# ----------------------------
orders_list = []  # Replace with DB in prod

# ----------------------------
# Health check
# ----------------------------
@app.route("/health", methods=["GET"])
def health():
    logging.info("Health check called")
    return jsonify({"status": "ok"})

# ----------------------------
# Orders endpoint
# ----------------------------
@app.route("/orders", methods=["GET"])
def orders():
    logging.info("Orders endpoint called")
    return jsonify({"orders": orders_list, "status": "ok"})

# ----------------------------
# Diagnostic endpoint
# ----------------------------
@app.route("/diagnostic", methods=["GET"])
def diagnostic():
    try:
        result = {
            "server_reachable": True,
            "cors_test": "CORS enabled",
            "internal_orders_call": {
                "status_code": 200,
                "json": {"orders": orders_list, "status": "ok"}
            }
        }
        logging.info(f"Diagnostic result: {result}")
        return jsonify(result)
    except Exception as e:
        logging.error(f"Diagnostic error: {e}")
        return jsonify({"error": str(e)}), 500

# ----------------------------
# Run app
# ----------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
