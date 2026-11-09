import os
import sys

# Let `import payment_simulator` work when running `pytest` from the
# project root, without needing to `pip install` the package first.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
