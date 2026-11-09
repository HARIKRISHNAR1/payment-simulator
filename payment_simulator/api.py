# api.py
# Wraps the PaymentProcessor in a small Flask app so it behaves like a
# real HTTP service instead of just a Python script you run locally.
#
# Start it with:  python -m payment_simulator.api
#
# Then from another terminal:
#   curl -X POST http://localhost:5000/charge \
#     -H "Content-Type: application/json" \
#     -H "Idempotency-Key: order-123" \
#     -d '{"amount": 500, "payee": "merchant_abc"}'
#
# Running that exact command a second time returns the same transaction_id,
# which proves the customer wasn't charged twice.

# Flask gives us routes, jsonify turns dicts into JSON responses
from flask import Flask, jsonify, request

from .processor import PaymentProcessor, DuplicateRequestResult

app = Flask(__name__)                        # the Flask application object
# one processor shared by all requests to this app
processor = PaymentProcessor(failure_rate=0.3)


@app.route("/", methods=["GET"])
def index():
    # friendly landing message - lists the real endpoints so it's obvious
    # the service is running and where to send real requests
    return jsonify({
        "service": "payment-simulator",
        "status": "running",
        "endpoints": {
            "POST /charge": "process a payment (needs an Idempotency-Key header)",
            "GET /transactions/<idempotency_key>": "look up a transaction",
        },
    })


# this function runs whenever someone POSTs to /charge
@app.route("/charge", methods=["POST"])
def charge():
    # read the key from the request headers
    idempotency_key = request.headers.get("Idempotency-Key")
    if not idempotency_key:
        # without a key we can't protect against duplicate charges, so we refuse the request
        return jsonify({"error": "Idempotency-Key header is required"}), 400

    body = request.get_json(force=True)   # parse the JSON body the client sent
    amount = body.get("amount")
    payee = body.get("payee")
    if amount is None or payee is None:
        return jsonify({"error": "amount and payee are required"}), 400

    # hand off to the real logic
    result = processor.charge(idempotency_key, amount, payee)

    if isinstance(result, DuplicateRequestResult):
        # this was a repeat of a request we already handled
        txn = result.transaction
        return jsonify({
            "transaction_id": txn.transaction_id,
            "state": txn.state,
            "duplicate_request": True,
        })

    # this was a fresh charge attempt
    txn = result
    # 402 = "payment required/failed"
    status_code = 200 if txn.state == "SUCCESS" else 402
    return jsonify({
        "transaction_id": txn.transaction_id,
        "state": txn.state,
        "attempts": txn.attempts,
        "failure_reason": txn.failure_reason,
        "duplicate_request": False,
    }), status_code


# lets you look up a transaction by its key
@app.route("/transactions/<idempotency_key>", methods=["GET"])
def get_transaction(idempotency_key):
    txn = processor.get(idempotency_key)
    if not txn:
        return jsonify({"error": "not found"}), 404
    return jsonify({
        "transaction_id": txn.transaction_id,
        "state": txn.state,
        "attempts": txn.attempts,
        "amount": txn.amount,
        "payee": txn.payee,
    })


if __name__ == "__main__":
    # debug=True auto-reloads the server when you edit the code - handy while building
    app.run(debug=True)
