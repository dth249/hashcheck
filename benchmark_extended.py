"""
Benchmark mở rộng — so sánh 2 phương thức ký trên 3 nhóm kích thước đơn hàng.

Biến số duy nhất: bước canonicalization (bước canon)
  direct — json.dumps thô, không sort key, không chuẩn hóa → hash+sign
  jcs    — jcs.canonicalize() theo RFC 8785              → hash+sign

Cả 2 phương thức có hash+sign giống hệt nhau (sign_data, SHA-256 internal).
Bước canon được đo riêng để cô lập overhead của canonicalization.

Dataset: dataset/orders.json (100k orders, _size_group: small/medium/large)

Output:
  results/extended_raw.csv     — per-order latency
  results/extended_summary.csv — mean/std per (method × size_group)
  results/extended_log.txt     — log đầy đủ
"""

import csv
import json
import os
import platform
import statistics
import time
from datetime import datetime

import jcs

from canonicalization import canonicalize as jcs_nfc_canonicalize
from crypto_utils import (
    generate_keys,
    load_private_key,
    load_public_key,
    sign_data,
    verify_signature,
)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
DATASET_PATH     = os.path.join("dataset", "orders.json")
RESULTS_DIR      = "results"
RAW_CSV_PATH     = os.path.join(RESULTS_DIR, "extended_raw.csv")
SUMMARY_CSV_PATH = os.path.join(RESULTS_DIR, "extended_summary.csv")
LOG_PATH         = os.path.join(RESULTS_DIR, "extended_log.txt")

METHODS     = ["direct", "jcs"]
SIZE_GROUPS = ["small", "medium", "large"]


# ---------------------------------------------------------------------------
# 2 phương thức — phân hóa tại bước canon
# ---------------------------------------------------------------------------

def run_direct(order: dict, private_key, public_key) -> dict:
    """
    Direct JSON signing:
      Bước canon: json.dumps thô — không sort key, không chuẩn hóa.
      Bước sign:  sign_data() — SHA-256 (internal) + RSA PKCS#1 v1.5.
    Không deterministic giữa các hệ thống khác nhau.
    """
    t0 = time.perf_counter()
    data = json.dumps(order, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    t1 = time.perf_counter()

    t2 = time.perf_counter()
    sig = sign_data(private_key, data)
    t3 = time.perf_counter()

    t4 = time.perf_counter()
    verify_signature(public_key, data, sig)
    t5 = time.perf_counter()

    return {
        "payload_bytes": len(data),
        "canon_sec":  t1 - t0,
        "sign_sec":   t3 - t2,
        "verify_sec": t5 - t4,
    }


def run_jcs(order: dict, private_key, public_key) -> dict:
    """
    JCS + NFC signing (IntelliHash pipeline):
      Bước canon: NFC normalization → jcs.canonicalize() RFC 8785.
        - NFC: đưa tất cả chuỗi về dạng NFC trước (phần mở rộng so với JCS gốc).
        - JCS: sort key, ECMAScript number format (RFC 8785).
      Bước sign: sign_data() — SHA-256 (internal) + RSA PKCS#1 v1.5.
    Deterministic và nhất quán với dữ liệu NFC/NFD hỗn hợp.
    """
    t0 = time.perf_counter()
    canon = jcs_nfc_canonicalize(order)   # NFC + JCS
    t1 = time.perf_counter()

    t2 = time.perf_counter()
    sig = sign_data(private_key, canon)
    t3 = time.perf_counter()

    t4 = time.perf_counter()
    verify_signature(public_key, canon, sig)
    t5 = time.perf_counter()

    return {
        "payload_bytes": len(canon),
        "canon_sec":  t1 - t0,
        "sign_sec":   t3 - t2,
        "verify_sec": t5 - t4,
    }


METHOD_FN = {
    "direct": run_direct,
    "jcs":    run_jcs,
}


# ---------------------------------------------------------------------------
# Stats helper
# ---------------------------------------------------------------------------

def stats_ms(values_sec: list) -> dict:
    ms = [v * 1000 for v in values_sec]
    return {
        "avg":    statistics.mean(ms),
        "std":    statistics.stdev(ms) if len(ms) > 1 else 0.0,
        "median": statistics.median(ms),
        "min":    min(ms),
        "max":    max(ms),
    }


# ---------------------------------------------------------------------------
# Machine info
# ---------------------------------------------------------------------------

def get_machine_info() -> dict:
    import importlib.metadata
    cpu = platform.processor() or "unknown"
    try:
        if platform.system() == "Windows":
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"HARDWARE\DESCRIPTION\System\CentralProcessor\0",
            )
            cpu = winreg.QueryValueEx(key, "ProcessorNameString")[0].strip()
            winreg.CloseKey(key)
    except Exception:
        pass

    ram = "unknown"
    try:
        import ctypes
        if platform.system() == "Windows":
            class MEM(ctypes.Structure):
                _fields_ = [
                    ("dwLength",     ctypes.c_ulong),
                    ("dwMemLoad",    ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    *[(f"_r{i}", ctypes.c_ulonglong) for i in range(6)],
                ]
            m = MEM(); m.dwLength = ctypes.sizeof(m)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
            ram = f"{m.ullTotalPhys / (1024**3):.1f} GB"
    except Exception:
        pass

    try:    crypto_ver = importlib.metadata.version("cryptography")
    except Exception: crypto_ver = "unknown"
    try:    jcs_ver = importlib.metadata.version("jcs")
    except Exception: jcs_ver = "unknown"

    return {
        "os":            f"{platform.system()} {platform.release()}",
        "cpu":           cpu,
        "logical_cores": os.cpu_count(),
        "ram":           ram,
        "python":        platform.python_version(),
        "cryptography":  crypto_ver,
        "jcs":           jcs_ver,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    os.makedirs(RESULTS_DIR, exist_ok=True)
    generate_keys()
    private_key = load_private_key()
    public_key  = load_public_key()

    if not os.path.exists(DATASET_PATH):
        raise FileNotFoundError(
            f"{DATASET_PATH} not found. Run dataset_generator.py first."
        )

    print(f"Loading {DATASET_PATH}...")
    with open(DATASET_PATH, "r", encoding="utf-8") as f:
        all_orders = json.load(f)

    grouped: dict[str, list] = {g: [] for g in SIZE_GROUPS}
    for o in all_orders:
        g = o.get("_size_group", "medium")
        if g in grouped:
            grouped[g].append(o)

    print("Dataset breakdown:")
    for g, lst in grouped.items():
        print(f"  {g:<8}: {len(lst):,} orders")
    print()

    machine_info = get_machine_info()
    timestamp    = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    all_raw_rows  = []
    summary_rows  = []
    log_lines     = []

    log_lines.append("=" * 72)
    log_lines.append("IntelliHash Extended Benchmark — 2 Methods × 3 Size Groups")
    log_lines.append("=" * 72)
    log_lines.append(f"Timestamp : {timestamp}")
    log_lines.append("")
    log_lines.append("Machine Info")
    log_lines.append("-" * 72)
    for k, v in machine_info.items():
        log_lines.append(f"  {k:<18}: {v}")
    log_lines.append("")
    log_lines.append("Dataset breakdown")
    log_lines.append("-" * 72)
    for g in SIZE_GROUPS:
        log_lines.append(f"  {g:<8}: {len(grouped[g]):,} orders")
    log_lines.append("")

    for size_group in SIZE_GROUPS:
        orders = grouped[size_group]
        if not orders:
            print(f"[{size_group}] No orders found, skipping.")
            continue

        log_lines.append(f"Size group: {size_group}  ({len(orders):,} orders)")
        log_lines.append("-" * 60)

        for method in METHODS:
            run_fn = METHOD_FN[method]
            print(f"  [{size_group:<6}] [{method:<6}]", end="", flush=True)

            t_wall_start = time.perf_counter()
            rows = [run_fn(o, private_key, public_key) for o in orders]
            t_wall = time.perf_counter() - t_wall_start
            print(f" {len(rows):,} orders done ({t_wall:.1f}s)")

            avg_bytes    = statistics.mean(r["payload_bytes"] for r in rows)
            canon_stats  = stats_ms([r["canon_sec"]  for r in rows])
            sign_stats   = stats_ms([r["sign_sec"]   for r in rows])
            verify_stats = stats_ms([r["verify_sec"] for r in rows])
            throughput   = len(rows) / sum(r["sign_sec"] for r in rows)

            for r in rows:
                all_raw_rows.append({
                    "method":        method,
                    "size_group":    size_group,
                    "payload_bytes": r["payload_bytes"],
                    "canon_ms":      round(r["canon_sec"]  * 1000, 4),
                    "sign_ms":       round(r["sign_sec"]   * 1000, 4),
                    "verify_ms":     round(r["verify_sec"] * 1000, 4),
                    "total_ms":      round((r["canon_sec"] + r["sign_sec"] + r["verify_sec"]) * 1000, 4),
                })

            summary_rows.append({
                "method":            method,
                "size_group":        size_group,
                "n_orders":          len(rows),
                "avg_payload_bytes": round(avg_bytes, 1),
                "canon_avg_ms":      round(canon_stats["avg"],  4),
                "canon_std_ms":      round(canon_stats["std"],  4),
                "sign_avg_ms":       round(sign_stats["avg"],   4),
                "sign_std_ms":       round(sign_stats["std"],   4),
                "verify_avg_ms":     round(verify_stats["avg"], 4),
                "verify_std_ms":     round(verify_stats["std"], 4),
                "throughput_sign":   round(throughput,          2),
            })

            log_lines.append(f"  method: {method}")
            log_lines.append(f"    avg_payload = {avg_bytes:.0f} bytes")
            log_lines.append(f"    canon  avg={canon_stats['avg']:.4f}ms  std={canon_stats['std']:.4f}ms")
            log_lines.append(f"    sign   avg={sign_stats['avg']:.4f}ms  std={sign_stats['std']:.4f}ms")
            log_lines.append(f"    verify avg={verify_stats['avg']:.4f}ms  std={verify_stats['std']:.4f}ms")
            log_lines.append(f"    throughput (sign): {throughput:.0f} orders/sec")
            log_lines.append("")

        log_lines.append("")

    # --- Write CSVs ---
    raw_fields = ["method", "size_group", "payload_bytes",
                  "canon_ms", "sign_ms", "verify_ms", "total_ms"]
    with open(RAW_CSV_PATH, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=raw_fields)
        w.writeheader(); w.writerows(all_raw_rows)

    sum_fields = ["method", "size_group", "n_orders", "avg_payload_bytes",
                  "canon_avg_ms", "canon_std_ms",
                  "sign_avg_ms",  "sign_std_ms",
                  "verify_avg_ms","verify_std_ms",
                  "throughput_sign"]
    with open(SUMMARY_CSV_PATH, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=sum_fields)
        w.writeheader(); w.writerows(summary_rows)

    log_text = "\n".join(log_lines)
    with open(LOG_PATH, "w", encoding="utf-8") as f:
        f.write(log_text)

    print()
    print(log_text)
    print(f"\nRaw CSV   : {RAW_CSV_PATH}")
    print(f"Summary   : {SUMMARY_CSV_PATH}")
    print(f"Log       : {LOG_PATH}")


if __name__ == "__main__":
    main()
