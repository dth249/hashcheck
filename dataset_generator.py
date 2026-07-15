"""
Sinh dataset đơn hàng giả lập (synthetic orders) phục vụ benchmark.

Sinh 100,000 đơn hàng gộp vào 1 file orders.json, phân 3 nhóm kích thước:
  small  (30k) — 5 fields,  ~200–300 bytes canonical
  medium (40k) — 10 fields, ~500–700 bytes canonical  (giống dataset cũ)
  large  (30k) — 15+ fields với nested product_list và địa chỉ lồng nhau, ~1,200–2,000 bytes

Mỗi order có field "_size_group" để benchmark_extended.py phân nhóm khi đo.
Output: dataset/orders.json
"""

import json
import random
import string
import os
from datetime import datetime, timedelta

DATASET_DIR = "dataset"
OUTPUT_PATH = os.path.join(DATASET_DIR, "orders.json")

# 100k orders tổng, phân 3 nhóm kích thước đơn hàng (nằm trong cùng 1 file)
GROUP_COUNTS = {
    "small":  30_000,   # ~200 bytes/order
    "medium": 40_000,   # ~600 bytes/order
    "large":  30_000,   # ~1,500 bytes/order
}

PRODUCTS = [
    "Wireless Mouse", "Mechanical Keyboard", "USB-C Cable", "Laptop Stand",
    "Bluetooth Speaker", "Monitor 24in", "Webcam HD", "External SSD 1TB",
    "Phone Case", "Desk Lamp", "Power Bank 20000mAh", "Noise Cancelling Headset",
]
PAYMENT_METHODS = ["credit_card", "paypal", "bank_transfer", "cod", "e_wallet"]
CITIES          = ["Hanoi", "Ho Chi Minh City", "Da Nang", "Hue", "Can Tho", "Hai Phong"]
DISTRICTS       = ["Ba Dinh", "Hoan Kiem", "Cau Giay", "Dong Da", "Hai Ba Trung", "Thanh Xuan"]
STATUS_LIST     = ["pending", "confirmed", "shipped", "delivered", "cancelled"]
NOTES_POOL      = [
    "Please leave at front door.", "Fragile items, handle with care.",
    "Call before delivery.", "No contact delivery preferred.",
    "Gift wrap requested.", "Deliver between 9am–5pm only.",
    "Second floor, no elevator.", "Ring the doorbell twice.",
]


def rstr(length: int = 8) -> str:
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=length))


def rdate() -> str:
    start = datetime(2024, 1, 1)
    return (start + timedelta(days=random.randint(0, 730),
                              seconds=random.randint(0, 86399))
            ).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Small order: 5 fields, no nesting
# ---------------------------------------------------------------------------
def generate_small(order_index: int) -> dict:
    price = round(random.uniform(5.0, 500.0), 2)
    return {
        "_size_group": "small",
        "order_id":    f"ORD-{order_index:08d}",
        "customer_id": f"CUST-{rstr(6)}",
        "product":     random.choice(PRODUCTS),
        "price":       price,
        "created_at":  rdate(),
    }


# ---------------------------------------------------------------------------
# Medium order: 10 fields, flat structure (dataset cũ)
# ---------------------------------------------------------------------------
def generate_medium(order_index: int) -> dict:
    quantity = random.randint(1, 10)
    price    = round(random.uniform(5.0, 500.0), 2)
    discount = round(random.uniform(0, 0.3), 2)
    return {
        "_size_group": "medium",
        "order_id":    f"ORD-{order_index:08d}",
        "customer_id": f"CUST-{rstr(6)}",
        "product":     random.choice(PRODUCTS),
        "quantity":    quantity,
        "price":       price,
        "discount":    discount,
        "total":       round(price * quantity * (1 - discount), 2),
        "address":     f"{random.randint(1, 999)} {rstr(5)} Street, {random.choice(CITIES)}",
        "payment":     random.choice(PAYMENT_METHODS),
        "created_at":  rdate(),
    }


# ---------------------------------------------------------------------------
# Large order: 15+ fields, nested product_list + nested address object
# ---------------------------------------------------------------------------
def generate_product_item() -> dict:
    qty        = random.randint(1, 5)
    unit_price = round(random.uniform(5.0, 300.0), 2)
    return {
        "name":       random.choice(PRODUCTS),
        "quantity":   qty,
        "unit_price": unit_price,
        "subtotal":   round(qty * unit_price, 2),
    }


def generate_large(order_index: int) -> dict:
    num_products = random.randint(3, 5)
    product_list = [generate_product_item() for _ in range(num_products)]
    total        = round(sum(p["subtotal"] for p in product_list), 2)
    discount     = round(random.uniform(0, 0.2), 2)
    final_total  = round(total * (1 - discount), 2)

    return {
        "_size_group": "large",
        "order_id":    f"ORD-{order_index:08d}",
        "customer_id": f"CUST-{rstr(6)}",
        "product_list": product_list,
        "item_count":  num_products,
        "subtotal":    total,
        "discount":    discount,
        "total":       final_total,
        "currency":    "USD",
        "payment":     random.choice(PAYMENT_METHODS),
        "status":      random.choice(STATUS_LIST),
        "shipping_address": {
            "street":   f"{random.randint(1, 999)} {rstr(5)} Street",
            "district": random.choice(DISTRICTS),
            "city":     random.choice(CITIES),
            "zip_code": str(random.randint(10000, 99999)),
            "country":  "VN",
        },
        "billing_address": {
            "street":   f"{random.randint(1, 999)} {rstr(5)} Avenue",
            "district": random.choice(DISTRICTS),
            "city":     random.choice(CITIES),
            "zip_code": str(random.randint(10000, 99999)),
            "country":  "VN",
        },
        "notes":       random.choice(NOTES_POOL),
        "created_at":  rdate(),
        "updated_at":  rdate(),
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    os.makedirs(DATASET_DIR, exist_ok=True)

    generators = {
        "small":  generate_small,
        "medium": generate_medium,
        "large":  generate_large,
    }

    orders = []
    order_index = 1
    for group, count in GROUP_COUNTS.items():
        print(f"  Generating {count:,} {group} orders...")
        gen = generators[group]
        for _ in range(count):
            orders.append(gen(order_index))
            order_index += 1

    # Shuffle để các nhóm trộn lẫn trong file (realistic hơn)
    random.shuffle(orders)

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(orders, f, ensure_ascii=False, indent=2)

    size_mb = os.path.getsize(OUTPUT_PATH) / (1024 * 1024)
    total = sum(GROUP_COUNTS.values())
    print(f"\nDone. {total:,} orders -> {OUTPUT_PATH} ({size_mb:.2f} MB)")
    for g, c in GROUP_COUNTS.items():
        print(f"  {g:<8}: {c:,} orders")


if __name__ == "__main__":
    main()
