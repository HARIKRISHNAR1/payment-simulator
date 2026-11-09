# demo.py
# Run with: python demo.py
#
# This script walks through the main things the processor does, one at a
# time, and prints out what happened so you can see it working without
# needing to start the web server.

import threading

from payment_simulator import PaymentProcessor, DuplicateRequestResult


def demo_duplicate_request():
    print("\n--- Demo 1: sending the same request twice ---")
    processor = PaymentProcessor(failure_rate=0.0)   # failure_rate=0 keeps this demo predictable

    txn1 = processor.charge("order-001", 500, "merchant_abc")   # first time we see this key
    print(f"First call  -> state={txn1.state}, transaction_id={txn1.transaction_id}")

    result2 = processor.charge("order-001", 500, "merchant_abc")   # exact same key sent again
    if isinstance(result2, DuplicateRequestResult):
        # should land here - the processor recognised this as a repeat
        print(f"Second call -> recognised as a duplicate, same transaction_id={result2.transaction.transaction_id}")
    else:
        print(f"Second call -> state={result2.state}, transaction_id={result2.transaction_id}")


def demo_concurrent_requests():
    print("\n--- Demo 2: firing 10 requests at once with the same key ---")
    processor = PaymentProcessor(failure_rate=0.0)   # failure_rate=0 so the result is simple to read
    seen_ids = set()           # will collect every transaction_id we get back
    ids_lock = threading.Lock()   # protects seen_ids since multiple threads write to it

    def worker():
        result = processor.charge("order-002", 1000, "merchant_xyz")
        txn = result.transaction if isinstance(result, DuplicateRequestResult) else result
        with ids_lock:
            seen_ids.add(txn.transaction_id)

    threads = [threading.Thread(target=worker) for _ in range(10)]   # 10 "customers" all trying at once
    for t in threads:
        t.start()
    for t in threads:
        t.join()   # wait here until all 10 have finished

    final_txn = processor.get("order-002")
    print(f"Distinct transaction_ids produced across 10 threads (should be 1): {len(seen_ids)}")
    print(f"Final state={final_txn.state}, attempts={final_txn.attempts} (attempts should be 1)")


def demo_retry_after_failure():
    print("\n--- Demo 3: a failed payment being retried ---")
    processor = PaymentProcessor(failure_rate=1.0)   # failure_rate=1.0 forces the first attempt to fail
    txn = processor.charge("order-003", 250, "merchant_retry")
    print(f"Attempt 1 -> state={txn.state}, failure_reason={txn.failure_reason}")

    processor.failure_rate = 0.0   # now let the next attempt succeed
    txn = processor.charge("order-003", 250, "merchant_retry")
    print(f"Attempt 2 (retry) -> state={txn.state}, attempts={txn.attempts}")


if __name__ == "__main__":
    demo_duplicate_request()
    demo_concurrent_requests()
    demo_retry_after_failure()
