"""

Đo và so sánh phân bố latency VERIFY giữa 2 nhóm: đơn hàng hợp lệ (valid)
và đơn hàng bị chỉnh sửa (tampered). Phục vụ trực tiếp:
  - Table 4: thống kê mean / variance / std cho cả 2 nhóm
  - Figure 2: histogram chồng 2 phân bố, có vẽ đường mean

Output:
    results/tamper_latency_raw.csv       (mỗi dòng: group, latency_ms)
    results/tamper_latency_summary.txt   (Table 4: mean/variance/std)
    results/figure2_valid_vs_tampered.png
"""

import json
import os
import csv
import gc
import time
import base64
import random
import statistics

from canonicalization import canonicalize
from crypto_utils import load_public_key, verify_signature, hash_data

ORDERS_PATH = os.path.join("dataset", "orders.json")
SIGNATURES_PATH = os.path.join("dataset", "signatures.json")
RESULTS_DIR = "results"

GROUP_SIZE = 10_000          # khớp "10,000 orders per group" trong Table 4
WARMUP_ITERS = 500           # số vòng chạy nháp bỏ đi trước khi đo, để ổn định cache/interpreter
RANDOM_SEED = 42              # cố định seed để kết quả tamper có thể tái lập


def load_data():
    if not os.path.exists(SIGNATURES_PATH):
        raise FileNotFoundError(
            f"{SIGNATURES_PATH} not found. Run sign.py first to generate signatures."
        )
    with open(ORDERS_PATH, "r", encoding="utf-8") as f:
        orders = json.load(f)
    with open(SIGNATURES_PATH, "r", encoding="utf-8") as f:
        signatures = json.load(f)
    sig_by_id = {s["order_id"]: s for s in signatures}
    return orders, sig_by_id


def tamper_order(order: dict, rng: random.Random) -> dict:
    """
    Chỉnh sửa 1 trường dữ liệu, theo đúng mô tả Section 4.4 của paper:
    "altering either a price digit or an address character".
    Xử lý đúng cả 3 loại order (small/medium/large).
    Trả về BẢN SAO đã tamper — không sửa order gốc.
    """
    tampered = dict(order)

    # Xác định field "price-like" và "address-like" theo loại order
    # small  : có "price", không có "address"
    # medium : có "price" và "address"
    # large  : có "subtotal", có "shipping_address" (nested dict)

    has_price   = "price"   in order
    has_address = "address" in order
    has_subtotal        = "subtotal"         in order
    has_shipping        = "shipping_address" in order

    coin = rng.random() < 0.5

    if coin and has_price:
        # Tamper price (small / medium)
        tampered["price"] = round(order["price"] + 0.01, 2)
    elif coin and has_subtotal:
        # Tamper subtotal (large)
        tampered["subtotal"] = round(order["subtotal"] + 0.01, 2)
    elif has_address:
        # Tamper address string (medium)
        addr = order["address"]
        tampered["address"] = ("X" if addr[0] != "X" else "Y") + addr[1:]
    elif has_shipping:
        # Tamper shipping_address.street (large)
        addr = order["shipping_address"]["street"]
        tampered["shipping_address"] = dict(order["shipping_address"])
        tampered["shipping_address"]["street"] = (
            ("X" if addr[0] != "X" else "Y") + addr[1:]
        )
    else:
        # Fallback: tamper customer_id (small không có address)
        tampered["customer_id"] = order["customer_id"] + "X"

    return tampered


def measure_verify_latency(order: dict, signature: bytes, public_key) -> float:
    """
    Đo latency của ĐÚNG 2 bước: hash_data() + verify_signature(), vô điều
    kiện, không short-circuit. Trả về latency tính bằng mili-giây.
    """
    data_bytes = canonicalize(order)
    t0 = time.perf_counter()
    digest = hash_data(data_bytes)
    verify_signature(public_key, digest, signature)
    t1 = time.perf_counter()
    return (t1 - t0) * 1000.0


def run_group(label, orders, sig_by_id, public_key, tamper: bool, rng: random.Random):
    """Đo latency cho 1 nhóm (valid hoặc tampered), trả về list latency (ms)."""
    latencies = []

    # --- Warm-up: chạy vài trăm lần bỏ kết quả, ổn định cache/branch predictor ---
    for order in orders[:WARMUP_ITERS]:
        record = sig_by_id[order["order_id"]]
        signature = base64.b64decode(record["signature_b64"])
        target_order = tamper_order(order, rng) if tamper else order
        measure_verify_latency(target_order, signature, public_key)

    # --- Đo thật, tắt garbage collector để tránh nhiễu do GC pause ngẫu nhiên ---
    gc.disable()
    try:
        for order in orders:
            record = sig_by_id[order["order_id"]]
            signature = base64.b64decode(record["signature_b64"])
            # QUAN TRỌNG: chữ ký luôn là chữ ký GỐC (ký trên dữ liệu chưa
            # tamper) — đúng kịch bản tấn công thật: kẻ tấn công sửa dữ liệu
            # trong database nhưng không có private key để ký lại.
            target_order = tamper_order(order, rng) if tamper else order
            latency = measure_verify_latency(target_order, signature, public_key)
            latencies.append(latency)
    finally:
        gc.enable()

    return latencies


def compute_stats(latencies):
    """Mean / population variance / population std, tương đương numpy.mean/var/std
    (numpy mặc định ddof=0 -> population variance, khớp cách tính ở đây)."""
    mean = statistics.mean(latencies)
    variance = statistics.pvariance(latencies)   # ddof=0, khớp numpy.var mặc định
    stdev = statistics.pstdev(latencies)          # ddof=0, khớp numpy.std mặc định
    return {
        "mean": mean,
        "variance": variance,
        "stdev": stdev,
        "min": min(latencies),
        "max": max(latencies),
        "median": statistics.median(latencies),
        "n": len(latencies),
    }


def plot_figure2(valid_latencies, tampered_latencies, valid_stats, tampered_stats):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.figure(figsize=(9, 5.5))
    bins = 60
    plt.hist(valid_latencies, bins=bins, alpha=0.55, label="Valid orders",
              color="#0f0f0f", edgecolor="black")
    plt.hist(tampered_latencies, bins=bins, alpha=0.55, label="Tampered orders",
              color="#fe2c55", edgecolor="black")

    plt.axvline(valid_stats["mean"], color="#0f0f0f", linestyle="--", linewidth=1.5,
                label=f"Valid mean = {valid_stats['mean']:.4f} ms")
    plt.axvline(tampered_stats["mean"], color="#fe2c55", linestyle="--", linewidth=1.5,
                label=f"Tampered mean = {tampered_stats['mean']:.4f} ms")

    plt.xlabel("Verification Latency (ms)")
    plt.ylabel("Frequency")
    plt.title("Verification Latency Distribution: Valid vs. Tampered Orders")
    plt.legend()
    plt.tight_layout()

    out_path = os.path.join(RESULTS_DIR, "figure2_valid_vs_tampered.png")
    plt.savefig(out_path, dpi=150)
    plt.close()
    print(f"Saved {out_path}")


def main():
    os.makedirs(RESULTS_DIR, exist_ok=True)
    rng = random.Random(RANDOM_SEED)

    public_key = load_public_key()
    orders, sig_by_id = load_data()

    if len(orders) < GROUP_SIZE * 2:
        raise ValueError(
            f"Cần ít nhất {GROUP_SIZE * 2:,} orders trong dataset để tách 2 nhóm "
            f"không trùng nhau (hiện có {len(orders):,}). Chạy lại dataset_generator.py."
        )

    # Nhóm valid và nhóm tampered dùng 2 tập order KHÔNG trùng nhau,
    # tránh đo trùng lặp 1 order ở cả 2 vai trò.
    valid_orders = orders[:GROUP_SIZE]
    tampered_source_orders = orders[GROUP_SIZE:GROUP_SIZE * 2]

    print(f"Measuring {GROUP_SIZE:,} valid orders...")
    valid_latencies = run_group("valid", valid_orders, sig_by_id, public_key,
                                 tamper=False, rng=rng)

    print(f"Measuring {GROUP_SIZE:,} tampered orders...")
    tampered_latencies = run_group("tampered", tampered_source_orders, sig_by_id,
                                    public_key, tamper=True, rng=rng)

    valid_stats = compute_stats(valid_latencies)
    tampered_stats = compute_stats(tampered_latencies)

    # --- Ghi CSV thô (dùng lại được cho phân tích khác nếu cần) ---
    raw_csv_path = os.path.join(RESULTS_DIR, "tamper_latency_raw.csv")
    with open(raw_csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["group", "latency_ms"])
        for v in valid_latencies:
            writer.writerow(["valid", f"{v:.6f}"])
        for v in tampered_latencies:
            writer.writerow(["tampered", f"{v:.6f}"])

    # --- Ghi bảng tóm tắt (Table 4) ---
    summary_path = os.path.join(RESULTS_DIR, "tamper_latency_summary.txt")
    lines = []
    lines.append("Table 4. Verification-latency distribution statistics "
                  f"({GROUP_SIZE:,} orders per group)")
    lines.append("-" * 70)
    lines.append(f"{'Group':<18}{'Mean (ms)':<14}{'Variance (ms^2)':<18}{'Std. dev (ms)':<14}")
    lines.append(f"{'Valid orders':<18}{valid_stats['mean']:<14.4f}"
                  f"{valid_stats['variance']:<18.6f}{valid_stats['stdev']:<14.4f}")
    lines.append(f"{'Tampered orders':<18}{tampered_stats['mean']:<14.4f}"
                  f"{tampered_stats['variance']:<18.6f}{tampered_stats['stdev']:<14.4f}")
    lines.append("")
    lines.append("Chi tiết đầy đủ (min/median/max):")
    for label, stats in (("Valid", valid_stats), ("Tampered", tampered_stats)):
        lines.append(f"  {label:<10} n={stats['n']:,}  min={stats['min']:.4f}ms  "
                      f"median={stats['median']:.4f}ms  max={stats['max']:.4f}ms")
    lines.append("")
    lines.append("Ghi chú phương pháp: latency đo trên hash_data()+verify_signature() "
                  "vô điều kiện (không short-circuit ở bước so khớp hash), khớp cách đo "
                  "'Verification' trong Table 1 -> hai bảng phải cùng bậc độ lớn.")

    summary_text = "\n".join(lines)
    with open(summary_path, "w", encoding="utf-8") as f:
        f.write(summary_text)

    print()
    print(summary_text)
    print()
    print(f"Raw CSV written to    : {raw_csv_path}")
    print(f"Summary written to    : {summary_path}")

    plot_figure2(valid_latencies, tampered_latencies, valid_stats, tampered_stats)


if __name__ == "__main__":
    main()
