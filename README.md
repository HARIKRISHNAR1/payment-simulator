# Payment Processing Simulator

A backend service that simulates how a real payment gateway safely processes
a charge request — even when the network is unreliable and the same request
ends up being sent more than once.

## Table of Contents

- [Overview](#overview)
- [Why This Project Exists](#why-this-project-exists)
- [Key Concepts](#key-concepts)
- [How It Works](#how-it-works)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Getting Started](#getting-started)
- [Usage](#usage)
- [Running Tests](#running-tests)
- [Example Output](#example-output)
- [Design Decisions](#design-decisions)
- [Limitations and Future Improvements](#limitations-and-future-improvements)
- [License](#license)

## Overview

This project implements a small, self-contained payment processing backend
that demonstrates **idempotent request handling** — a core requirement for
any real payment system. It exposes a REST API (built with Flask) and a
core processing engine that can also be run standalone through a demo
script, with a full automated test suite proving its correctness.

## Why This Project Exists

Payment systems have one rule they cannot break: **a customer must never
be charged twice for the same purchase.** In practice this is harder than
it sounds, because:

- Networks are unreliable — a client's request can succeed on the server
  side but the response can get lost before reaching the client.
- When a client doesn't receive a response, the safe and common behavior
  is to retry the exact same request.
- Under load, two retries can even arrive at the server at nearly the same
  instant.

A naive payment API would process every incoming request independently,
meaning any retry becomes a second, duplicate charge. This project exists
to show a correct, tested solution to that problem using patterns real
payment systems (Stripe, PayPal, Google Pay, etc.) actually use.

## Key Concepts

**Idempotency key**
A unique identifier the client generates and attaches to a payment request.
If the server receives a request with a key it has already processed, it
returns the original result instead of charging again. This is the
industry-standard technique for making an operation "idempotent" (safe to
repeat).

**Concurrency-safe locking**
Checking "have I seen this key?" and then "mark it as being processed" must
happen as a single, uninterruptible unit. If two requests for the same key
arrive at the same moment, naive code could let both slip past the check
before either finishes — resulting in two charges. This project uses a
per-key lock so only one request at a time can process a given key.

**Transaction state machine**
Every transaction moves through a strict set of states:

## PENDING -> PROCESSING -> SUCCESS -> FAILED -> (retry) -> PENDING


A transaction can never move backward out of `SUCCESS`, which prevents
bugs like accidentally reopening or re-charging a completed payment.

## How It Works

1. A client sends a `POST /charge` request with an `Idempotency-Key` header
   and a JSON body (`amount`, `payee`).
2. The server acquires a lock scoped to that specific idempotency key.
3. It checks whether a transaction for that key already exists:
   - If it's already `SUCCESS` or currently `PROCESSING`, the server
     returns the existing result and does **not** charge again.
   - If it previously `FAILED`, this is treated as a legitimate retry and
     reprocessed.
   - If it's new, a transaction is created in the `PENDING` state.
4. The transaction moves to `PROCESSING`, and a simulated call to a "bank"
   is made (represented here by a function with a randomized success/
   failure outcome and an artificial delay, standing in for a real payment
   network call).
5. Based on the result, the transaction moves to `SUCCESS` or `FAILED`.
6. The lock is released, and the result is returned to the client.

## Tech Stack

- **Python 3.12**
- **Flask** - lightweight web framework for the HTTP API
- **pytest** - automated testing
- No external database is used; transactions are stored in memory for
  simplicity (see Limitations below).

## Project Structure

payment-simulator/
├── payment_simulator/
│ ├── init.py # package exports
│ ├── models.py # Transaction class and state machine rules
│ ├── processor.py # core idempotency + concurrency logic
│ └── api.py # Flask API exposing the processor over HTTP
├── tests/
│ ├── conftest.py # lets pytest find the package without installing it
│ └── test_processor.py # automated tests
├── demo.py # runnable script demonstrating the core behavior
├── requirements.txt # Python dependencies
├── .gitignore
└── README.md


## Getting Started

### Prerequisites

- Python 3.10 or newer
- pip

### Installation

```bash
git clone https://github.com/<your-username>/payment-simulator.git
cd payment-simulator
pip install -r requirements.txt
```

## Usage

### Option 1: Run the demo script (no server required)

```bash
python demo.py
```

This runs three scripted demonstrations and prints the results:
duplicate-request detection, ten simultaneous requests racing for the same
key, and a failed payment being retried until it succeeds.

### Option 2: Run it as an HTTP API

```bash
python -m payment_simulator.api
```

The server starts on `http://localhost:5000`.

**Check the service is running:**

```bash
curl http://localhost:5000/
```

**Process a payment:**

```bash
curl -X POST http://localhost:5000/charge \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: order-123" \
  -d '{"amount": 500, "payee": "merchant_abc"}'
```

**Send the exact same request again** - you'll get back the same
`transaction_id` and `"duplicate_request": true`, proving the customer
was not charged twice.

**Look up a transaction:**

```bash
curl http://localhost:5000/transactions/order-123
```

## Running Tests

```bash
pytest -v
```

The test suite verifies:

- the same idempotency key never results in two charges
- different idempotency keys are processed independently
- 20 simultaneous requests for the same key still result in exactly one
  charge
- a failed payment can be retried and later succeed
- a completed (`SUCCESS`) transaction cannot be moved to any other state

## Example Output

--- Demo 1: sending the same request twice ---
First call -> state=SUCCESS, transaction_id=b70ffdef-...
Second call -> recognised as a duplicate, same transaction_id=b70ffdef-...

--- Demo 2: firing 10 requests at once with the same key ---
Distinct transaction_ids produced across 10 threads (should be 1): 1
Final state=SUCCESS, attempts=1 (attempts should be 1)

--- Demo 3: a failed payment being retried ---
Attempt 1 -> state=FAILED, failure_reason=bank_declined_or_timeout
Attempt 2 (retry) -> state=SUCCESS, attempts=2


## Design Decisions

**Why a lock per idempotency key instead of one global lock?**
A single global lock would force every payment in the system to wait for
every other payment to finish, even for completely unrelated customers.
Locking per-key means only requests for the *same* transaction are
serialized, while unrelated transactions still process in parallel.

**Why simulate the bank call with random failure instead of always
succeeding?**
Real payment networks are not 100% reliable. Simulating occasional
failure is what makes the retry logic (and the tests for it) meaningful,
instead of only ever exercising the "happy path."

**Why an in-memory store instead of a database?**
This keeps the project easy to run and read without needing to set up
infrastructure. The core logic (locking, idempotency checks, state
transitions) is written so it would translate directly to a database
implementation.

## Limitations and Future Improvements

- Transactions are stored in memory and are lost when the process
  restarts. A production version would persist them in a database
  (e.g., PostgreSQL), with the idempotency key as a unique, indexed
  column.
- There is no expiry on idempotency keys. A real system typically expires
  them after a fixed window (e.g., 24 hours) to bound memory/storage use.
- The "bank" is simulated with a random success/failure outcome rather
  than calling a real payment provider's API.
- No authentication or rate limiting is implemented on the API.
- A possible extension: add a `/refund` endpoint with its own state
  machine, or add exponential backoff with a maximum retry limit.
