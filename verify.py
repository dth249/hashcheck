"""
Xác minh toàn bộ chữ ký trong dataset/signatures.json khớp với dataset/orders.json.
"""

import json
import os
import base64

from canonicalization import canonicalize
from crypto_utils import load_public_key, verify_digest, hash_data

ORDERS_PATH = os.path.join("dataset", "orders.json")
SIGNATURES_PATH = os.path.join("dataset", "signatures.json")


def main():
    if not os.path.exists(SIGNATURES_PATH):
        raise FileNotFoundError(
            f"{SIGNATURES_PATH} not found. Run sign.py first."
        )

    public_key = load_public_key()

    with open(ORDERS_PATH, "r", encoding="utf-8") as f:
        orders = json.load(f)
    with open(SIGNATURES_PATH, "r", encoding="utf-8") as f:
        signatures = json.load(f)

    sig_by_order_id = {s["order_id"]: s for s in signatures}

    total = len(orders)
    valid_count = 0
    invalid_orders = []

    print(f"Verifying {total:,} orders...")

    for order in orders:
        record = sig_by_order_id.get(order["order_id"])
        if record is None:
            invalid_orders.append((order["order_id"], "missing_signature"))
            continue

        canon_bytes = canonicalize(order)
        digest = hash_data(canon_bytes)       # SHA-256, 32 bytes

        if digest.hex() != record["sha256"]:
            invalid_orders.append((order["order_id"], "hash_mismatch"))
            continue

        signature = base64.b64decode(record["signature_b64"])
        is_valid = verify_digest(public_key, digest, signature)  # Prehashed, không hash lại

        if is_valid:
            valid_count += 1
        else:
            invalid_orders.append((order["order_id"], "invalid_signature"))

    print(f"\nValid:   {valid_count:,} / {total:,}")
    print(f"Invalid: {len(invalid_orders):,} / {total:,}")

    if invalid_orders:
        print("\nSample of invalid records (max 10 shown):")
        for order_id, reason in invalid_orders[:10]:
            print(f"  - {order_id}: {reason}")


if __name__ == "__main__":
    main()
