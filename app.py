"""
Demo end-to-end pipeline cho 1 đơn hàng đơn lẻ, để minh họa

Quy trình:
  Order -> Canonicalization -> SHA-256 -> RSA Sign -> Store -> Verify
"""

import json
import base64

from canonicalization import canonicalize
from crypto_utils import generate_keys, load_private_key, load_public_key, sign_data, verify_signature, hash_data_hex


def demo_single_order():
    print("=" * 60)
    print("IntegriChain - End-to-End Demo (single order)")
    print("=" * 60)

    generate_keys()
    private_key = load_private_key()
    public_key = load_public_key()

    order = {
        "order_id": "ORD-DEMO-0001",
        "customer_id": "CUST-DEMO01",
        "product": "Wireless Mouse",
        "quantity": 2,
        "price": 25.50,
        "discount": 0.1,
        "total": 45.9011,
        "address": "123 Demo Street, Hanoi  ",
        "payment": "credit_card",
        "created_at": "2026-06-30T12:00:00Z",
    }

    print("\n[1] Original order:")
    print(json.dumps(order, indent=2, ensure_ascii=False))

    print("\n[2] Canonicalization:")
    canon_bytes = canonicalize(order)
    print(canon_bytes.decode("utf-8"))

    print("\n[3] SHA-256 hash:")
    digest_hex = hash_data_hex(canon_bytes)
    print(digest_hex)

    print("\n[4] RSA Sign:")
    signature = sign_data(private_key, canon_bytes)
    sig_b64 = base64.b64encode(signature).decode("ascii")
    print(f"Signature (base64, truncated): {sig_b64[:60]}...")
    print(f"Signature length: {len(signature)} bytes")

    print("\n[5] Store (simulated): order + signature would be persisted here.")

    print("\n[6] Verify:")
    is_valid = verify_signature(public_key, canon_bytes, signature)
    print(f"Signature valid: {is_valid}")

    print("\n[6b] Tamper test (modify order after signing, verify should fail):")
    tampered_order = dict(order)
    tampered_order["price"] = 999.99
    tampered_bytes = canonicalize(tampered_order)
    is_valid_tampered = verify_signature(public_key, tampered_bytes, signature)
    print(f"Tampered data + original signature valid: {is_valid_tampered} (expected: False)")

    print("\n" + "=" * 60)
    print("Demo complete.")


if __name__ == "__main__":
    demo_single_order()
