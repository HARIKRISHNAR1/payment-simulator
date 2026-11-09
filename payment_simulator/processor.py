# processor.py
# This is where the actual payment handling logic lives.
#
# The two things this is built to get right:
#   1. If the same idempotency_key shows up twice, don't charge twice.
#   2. If two requests for the same key show up AT THE SAME TIME
#      (e.g. the app sent the request twice because of a glitch),
#      still only charge once.

import random        # used to randomly simulate the bank call failing sometimes
import threading      # gives us Lock, which we use to stop two requests racing each other
import time            # used to fake a small network delay when "calling the bank"

from .models import Transaction, TransactionState   # the Transaction class we wrote in models.py


class DuplicateRequestResult:
    # When charge() notices it has already seen this idempotency_key before,
    # it wraps the existing transaction in this class instead of processing again.
    # That way the caller can tell the difference between "fresh charge" and "already done this".
    def __init__(self, transaction: Transaction):
        self.transaction = transaction
        self.was_duplicate = True


class PaymentProcessor:
    def __init__(self, failure_rate: float = 0.3):
        # Normally this would be a real database table. Here it's just a
        # plain dictionary living in memory, keyed by idempotency_key.
        self._transactions: dict[str, Transaction] = {}

        # We need one lock PER idempotency_key, not one lock for everything,
        # otherwise two completely different customers paying at the same time
        # would have to wait for each other for no reason.
        self._locks: dict[str, threading.Lock] = {}
        self._locks_guard = threading.Lock()  # protects the _locks dictionary itself from being edited by two threads at once

        self.failure_rate = failure_rate  # chance the fake "bank" call fails, so we can test retries

    def _get_lock(self, idempotency_key: str) -> threading.Lock:
        # Returns the lock for this specific key, creating it if it doesn't exist yet.
        with self._locks_guard:                      # only one thread can be in here at a time
            if idempotency_key not in self._locks:    # if we've never seen this key before
                self._locks[idempotency_key] = threading.Lock()  # make a brand new lock for it
            return self._locks[idempotency_key]        # hand back the lock (existing or new)

    def charge(self, idempotency_key: str, amount: float, payee: str):
        # Main entry point. Safe to call this more than once with the same
        # idempotency_key - only the first successful call actually charges.
        lock = self._get_lock(idempotency_key)   # grab the lock that belongs to this key

        with lock:   # everything below only runs for ONE caller at a time, per key
            existing = self._transactions.get(idempotency_key)   # look up any earlier attempt

            if existing and existing.state in (TransactionState.SUCCESS, TransactionState.PROCESSING):
                # we've already handled this (or are handling it right now in another thread
                # that briefly released the lock) - don't touch the bank again
                return DuplicateRequestResult(existing)

            if existing and existing.state == TransactionState.FAILED:
                # a previous attempt failed, so this is a legitimate retry, not a duplicate
                txn = existing
                txn.move_to(TransactionState.PENDING)   # reset it back to PENDING before trying again
            else:
                # first time we've ever seen this key - make a brand new transaction
                txn = Transaction(idempotency_key=idempotency_key, amount=amount, payee=payee)
                self._transactions[idempotency_key] = txn   # store it so future calls can find it

            txn.attempts += 1                              # count this as one more attempt
            txn.move_to(TransactionState.PROCESSING)        # mark it as being worked on right now

            self._call_bank(txn)    # this will flip the state to SUCCESS or FAILED
            return txn

    def _call_bank(self, txn: Transaction):
        # Stands in for calling a real bank/payment network. Real systems
        # depend on a slower, sometimes-unreliable external service like
        # this, so we simulate that on purpose rather than pretending
        # everything always works.
        time.sleep(0.01)   # tiny fake delay, like a real network call would have

        if random.random() < self.failure_rate:   # roll the dice to decide if this "call" fails
            txn.failure_reason = "bank_declined_or_timeout"
            txn.move_to(TransactionState.FAILED)
        else:
            txn.move_to(TransactionState.SUCCESS)

    def get(self, idempotency_key: str) -> Transaction | None:
        # Simple lookup, used by the API and by the demo script to check results.
        return self._transactions.get(idempotency_key)
