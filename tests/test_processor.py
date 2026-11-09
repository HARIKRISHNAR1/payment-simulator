# test_processor.py
# Run with: pytest -v
#
# These are automated checks that prove the processor behaves correctly.
# If anyone (or future-you) changes the code later and breaks one of
# these guarantees, these tests will fail and catch the mistake.

import threading

import pytest

from payment_simulator import PaymentProcessor, DuplicateRequestResult, TransactionState


def test_duplicate_idempotency_key_is_not_charged_twice():
    processor = PaymentProcessor(failure_rate=0.0)   # no randomness, so the test is predictable

    first = processor.charge("key-1", 100, "merchant_a")    # first charge, should succeed
    second = processor.charge("key-1", 100, "merchant_a")   # same key again - should be caught as a duplicate

    assert isinstance(second, DuplicateRequestResult)                       # must be flagged as duplicate
    assert second.transaction.transaction_id == first.transaction_id        # and point at the same transaction


def test_different_keys_are_charged_separately():
    processor = PaymentProcessor(failure_rate=0.0)

    txn_a = processor.charge("key-a", 100, "merchant_a")   # two different keys...
    txn_b = processor.charge("key-b", 100, "merchant_b")

    assert txn_a.transaction_id != txn_b.transaction_id    # ...should be two different transactions


def test_concurrent_requests_same_key_only_charge_once():
    processor = PaymentProcessor(failure_rate=0.0)
    results = []
    results_lock = threading.Lock()

    def worker():
        result = processor.charge("key-concurrent", 500, "merchant_c")
        with results_lock:               # avoid two threads appending to the list at the same instant
            results.append(result)

    threads = [threading.Thread(target=worker) for _ in range(20)]   # simulate 20 requests at once
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    fresh_charges = [r for r in results if not isinstance(r, DuplicateRequestResult)]
    assert len(fresh_charges) == 1   # out of 20 near-simultaneous calls, only one should be a real charge


def test_failed_payment_can_be_retried_and_succeed():
    processor = PaymentProcessor(failure_rate=1.0)   # force the first attempt to fail
    txn = processor.charge("key-retry", 100, "merchant_d")
    assert txn.state == TransactionState.FAILED

    processor.failure_rate = 0.0   # now let it succeed
    txn = processor.charge("key-retry", 100, "merchant_d")
    assert txn.state == TransactionState.SUCCESS
    assert txn.attempts == 2   # one failed attempt + one successful attempt


def test_illegal_state_transition_raises_error():
    processor = PaymentProcessor(failure_rate=0.0)
    txn = processor.charge("key-illegal", 100, "merchant_e")
    assert txn.state == TransactionState.SUCCESS

    with pytest.raises(ValueError):          # SUCCESS is a final state, so this move should be rejected
        txn.move_to(TransactionState.PENDING)
