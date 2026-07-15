"""
Ký số toàn bộ dataset orders.json bằng RSA, lưu kết quả ra dataset/signatures.json.
"""

import json
import os
import base64

from canonicalization import canonicalize
from crypto_utils import generate_keys, load_private_key, sign_digest, hash_data

ORDERS_PATH = os.path.join("dataset", "orders.json")
SIGNATURES_PATH = os.path.join("dataset", "signatures.json")


def main():
    generate_keys()  # no-op nếu đã có khóa
    private_key = load_private_key()

    if not os.path.exists(ORDERS_PATH):
        raise FileNotFoundError(
            f"{ORDERS_PATH} not found. Run dataset_generator.py first."
        )

    with open(ORDERS_PATH, "r", encoding="utf-8") as f:
        orders = json.load(f)

    print(f"Signing {len(orders):,} orders...")

    signed_records = []
    for order in orders:
        canon_bytes = canonicalize(order)         # jcs.canonicalize → bytes
        digest = hash_data(canon_bytes)            # SHA-256, 32 bytes
        signature = sign_digest(private_key, digest)  # ký trên digest, không hash lại

        signed_records.append({
            "order_id": order["order_id"],
            "sha256": digest.hex(),
            "signature_b64": base64.b64encode(signature).decode("ascii"),
        })

    with open(SIGNATURES_PATH, "w", encoding="utf-8") as f:
        json.dump(signed_records, f, indent=2)

    print(f"Done. Wrote {len(signed_records):,} signatures to {SIGNATURES_PATH}")


if __name__ == "__main__":
    main()
