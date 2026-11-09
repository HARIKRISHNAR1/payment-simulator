# models.py
# This file holds the Transaction class and the rules for how a transaction
# is allowed to change state over time.

import time          # used to timestamp when a transaction was created
import uuid           # used to generate a unique id for every transaction
from dataclasses import dataclass, field   # dataclass makes writing simple data holder classes shorter


class TransactionState:
    # Just a group of string constants so we don't have typos like "SUCESS"
    # scattered around the code. Using the class like an enum.
    PENDING = "PENDING"        # transaction has been created but not sent to the bank yet
    PROCESSING = "PROCESSING"  # we are currently "talking" to the bank
    SUCCESS = "SUCCESS"        # bank confirmed the charge went through
    FAILED = "FAILED"          # bank declined it, or the call timed out


# This dictionary says which state can move to which other state.
# For example PENDING can only become PROCESSING - it can't jump straight to SUCCESS.
ALLOWED_TRANSITIONS = {
    TransactionState.PENDING: [TransactionState.PROCESSING],
    TransactionState.PROCESSING: [TransactionState.SUCCESS, TransactionState.FAILED],
    TransactionState.SUCCESS: [],  # once a payment succeeds, nothing can change it, so this is empty
    TransactionState.FAILED: [TransactionState.PENDING],  # a failed payment can be tried again
}


@dataclass  # @dataclass auto-generates the __init__ method for us based on the fields below
class Transaction:
    idempotency_key: str      # the unique id the CLIENT sends us so we can recognise repeat requests
    amount: float              # how much money this transaction is for
    payee: str                 # who is receiving the money
    state: str = TransactionState.PENDING   # every new transaction starts as PENDING
    transaction_id: str = field(default_factory=lambda: str(uuid.uuid4()))  # our own internal unique id
    created_at: float = field(default_factory=time.time)  # unix timestamp of when this object was made
    attempts: int = 0          # how many times we've tried to process this transaction
    failure_reason: str | None = None  # why it failed, if it did - None means it hasn't failed (yet)

    def can_move_to(self, new_state: str) -> bool:
        # looks up the ALLOWED_TRANSITIONS table to see if this move is legal
        return new_state in ALLOWED_TRANSITIONS[self.state]

    def move_to(self, new_state: str):
        # this is the ONLY place that should ever change self.state directly
        if not self.can_move_to(new_state):
            # if someone tries an illegal move (like SUCCESS -> PENDING) we stop them here
            raise ValueError(f"Illegal state change: cannot go from {self.state} to {new_state}")
        self.state = new_state
