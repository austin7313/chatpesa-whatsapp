from flask import Flask, request, Response
import os

app = Flask(__name__)

@app.route("/")
def home():
    return "OK"

@app.route("/webhook/whatsapp", methods=["POST"])
def whatsapp_webhook():
    try:
        body = request.form.get("Body", "")
        from_number = request.form.get("From", "")

        print("📩 Incoming WhatsApp")
        print("From:", from_number)
        print("Body:", body)

        return Response(
            """<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Message>
✅ WhatsApp webhook is WORKING.
You said: {msg}
  </Message>
</Response>
""".format(msg=body),
            mimetype="application/xml"
        )

    except Exception as e:
        print("❌ FATAL ERROR:", e)
        return Response(
            """<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Message>
❌ Hard failure inside webhook
  </Message>
</Response>
""",
            mimetype="application/xml"
        )

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    print("🚀 Starting on port", port)
    app.run(host="0.0.0.0", port=port)
