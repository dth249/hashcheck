"""
Đo latency và throughput THẬT của các bước: canonicalization, SHA-256, RSA sign, RSA verify.

Output:
  - results/benchmark.csv   (per-order latency, raw data)
  - results/benchmark.txt   (log tổng hợp: machine info, average, median, throughput...)
"""

import json
import os
import csv
import time
import platform
import statistics
import sys
from datetime import datetime

from canonicalization import canonicalize
from crypto_utils import (
    generate_keys, load_private_key, load_public_key,
    hash_data, sign_digest, verify_digest,
)

ORDERS_PATH = os.path.join("dataset", "orders.json")
RESULTS_DIR = "results"
CSV_PATH = os.path.join(RESULTS_DIR, "benchmark.csv")
LOG_PATH = os.path.join(RESULTS_DIR, "benchmark.txt")

# Số lượng orders dùng cho benchmark. 
BENCHMARK_SAMPLE_SIZE = int(os.environ.get("BENCHMARK_SAMPLE_SIZE", "100000"))


def get_machine_info() -> dict:
    """Thu thập thông tin phần cứng đầy đủ để ghi vào benchmark log."""
    import importlib.metadata

    # --- Tên CPU thương mại ---
    cpu_brand = platform.processor() or "unknown"
    try:
        if platform.system() == "Windows":
            import winreg
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                 r"HARDWARE\DESCRIPTION\System\CentralProcessor\0")
            cpu_brand = winreg.QueryValueEx(key, "ProcessorNameString")[0].strip()
            winreg.CloseKey(key)
        elif platform.system() == "Linux":
            with open("/proc/cpuinfo") as f:
                for line in f:
                    if line.startswith("model name"):
                        cpu_brand = line.split(":", 1)[1].strip()
                        break
        elif platform.system() == "Darwin":
            import subprocess
            result = subprocess.run(
                ["sysctl", "-n", "machdep.cpu.brand_string"],
                capture_output=True, text=True
            )
            if result.returncode == 0:
                cpu_brand = result.stdout.strip()
    except Exception:
        pass

    # --- RAM tổng vật lý ---
    ram_info = "unknown"
    try:
        import ctypes
        if platform.system() == "Windows":
            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength",                ctypes.c_ulong),
                    ("dwMemoryLoad",            ctypes.c_ulong),
                    ("ullTotalPhys",            ctypes.c_ulonglong),
                    ("ullAvailPhys",            ctypes.c_ulonglong),
                    ("ullTotalPageFile",        ctypes.c_ulonglong),
                    ("ullAvailPageFile",        ctypes.c_ulonglong),
                    ("ullTotalVirtual",         ctypes.c_ulonglong),
                    ("ullAvailVirtual",         ctypes.c_ulonglong),
                    ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]
            stat = MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(stat)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
            ram_info = f"{stat.ullTotalPhys / (1024**3):.1f} GB"
        elif platform.system() == "Linux":
            with open("/proc/meminfo") as f:
                for line in f:
                    if line.startswith("MemTotal:"):
                        kb = int(line.split()[1])
                        ram_info = f"{kb / 1024 / 1024:.1f} GB"
                        break
        elif platform.system() == "Darwin":
            import subprocess
            result = subprocess.run(["sysctl", "-n", "hw.memsize"],
                                    capture_output=True, text=True)
            if result.returncode == 0:
                ram_info = f"{int(result.stdout.strip()) / (1024**3):.1f} GB"
    except Exception:
        pass

    # --- Phiên bản thư viện cryptography ---
    try:
        crypto_version = importlib.metadata.version("cryptography")
    except Exception:
        crypto_version = "unknown"

    return {
        "os": f"{platform.system()} {platform.release()} ({platform.version()})",
        "cpu_brand": cpu_brand,
        "cpu_logical_cores": os.cpu_count(),
        "ram_total": ram_info,
        "python_version": platform.python_version(),
        "cryptography_lib": f"cryptography=={crypto_version}",
    }


def stats_ms(values_sec):
    """Convert list of seconds -> dict of stats in milliseconds."""
    values_ms = [v * 1000 for v in values_sec]
    return {
        "avg": statistics.mean(values_ms),
        "median": statistics.median(values_ms),
        "min": min(values_ms),
        "max": max(values_ms),
        "stdev": statistics.stdev(values_ms) if len(values_ms) > 1 else 0.0,
    }


def main():
    os.makedirs(RESULTS_DIR, exist_ok=True)

    generate_keys()  # no-op nếu đã có khóa
    private_key = load_private_key()
    public_key = load_public_key()

    if not os.path.exists(ORDERS_PATH):
        raise FileNotFoundError(
            f"{ORDERS_PATH} not found. Run dataset_generator.py first."
        )

    with open(ORDERS_PATH, "r", encoding="utf-8") as f:
        orders = json.load(f)

    if BENCHMARK_SAMPLE_SIZE < len(orders):
        orders = orders[:BENCHMARK_SAMPLE_SIZE]

    n = len(orders)
    print(f"Running benchmark on {n:,} orders...")
    print("(Set BENCHMARK_SAMPLE_SIZE env var to change sample size, e.g. for a quick test run)")

    canon_latencies = []
    sign_latencies = []
    verify_latencies = []

    csv_rows = []

    overall_start = time.perf_counter()

    for i, order in enumerate(orders, start=1):
        # --- Canonicalization ---
        t0 = time.perf_counter()
        canon_bytes = canonicalize(order)
        t1 = time.perf_counter()
        canon_latencies.append(t1 - t0)

        # --- SHA-256 + Sign (1 bucket, khớp Table 1) ---
        t0 = time.perf_counter()
        digest = hash_data(canon_bytes)          # SHA-256 → 32 bytes
        signature = sign_digest(private_key, digest)  # ký trên digest (Prehashed)
        t1 = time.perf_counter()
        sign_latencies.append(t1 - t0)

        # --- Verify (hash lại 1 lần — bắt buộc theo Algorithm 3) ---
        t0 = time.perf_counter()
        digest_v = hash_data(canon_bytes)
        verify_digest(public_key, digest_v, signature)
        t1 = time.perf_counter()
        verify_latencies.append(t1 - t0)

        csv_rows.append({
            "order_id": order["order_id"],
            "canonicalization_ms": round(canon_latencies[-1] * 1000, 4),
            "signing_ms":          round(sign_latencies[-1]  * 1000, 4),
            "verification_ms":     round(verify_latencies[-1] * 1000, 4),
        })

        if i % 10000 == 0 or i == n:
            elapsed = time.perf_counter() - overall_start
            print(f"  {i:,}/{n:,} processed ({elapsed:.1f}s elapsed)")

    overall_end = time.perf_counter()
    total_wall_time = overall_end - overall_start

    # --- Write CSV ---
    with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["order_id", "canonicalization_ms", "signing_ms", "verification_ms"])
        writer.writeheader()
        writer.writerows(csv_rows)

    # --- Compute stats ---
    canon_stats = stats_ms(canon_latencies)
    sign_stats = stats_ms(sign_latencies)
    verify_stats = stats_ms(verify_latencies)

    # Throughput based on signing step (the bottleneck operation), single-threaded
    sign_throughput = n / sum(sign_latencies)
    verify_throughput = n / sum(verify_latencies)
    end_to_end_throughput = n / total_wall_time  # canon + sign + verify combined

    machine_info = get_machine_info()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # --- Write log ---
    log_lines = []
    log_lines.append("=" * 60)
    log_lines.append("IntegriChain Benchmark Log")
    log_lines.append("=" * 60)
    log_lines.append(f"Timestamp: {timestamp}")
    log_lines.append("")
    log_lines.append("Machine Info")
    log_lines.append("-" * 60)
    for k, v in machine_info.items():
        log_lines.append(f"{k:20s}: {v}")
    log_lines.append("")
    log_lines.append("Dataset")
    log_lines.append("-" * 60)
    log_lines.append(f"{'Orders benchmarked':20s}: {n:,}")
    log_lines.append(f"{'Total wall time':20s}: {total_wall_time:.2f} s")
    log_lines.append("")
    log_lines.append("Canonicalization Latency (ms)")
    log_lines.append("-" * 60)
    for k, v in canon_stats.items():
        log_lines.append(f"{k:10s}: {v:.4f}")
    log_lines.append("")
    log_lines.append("Signing Latency (ms) [RSA-2048 + PKCS#1 v1.5, SHA-256]")
    log_lines.append("-" * 60)
    for k, v in sign_stats.items():
        log_lines.append(f"{k:10s}: {v:.4f}")
    log_lines.append("")
    log_lines.append("Verification Latency (ms)")
    log_lines.append("-" * 60)
    for k, v in verify_stats.items():
        log_lines.append(f"{k:10s}: {v:.4f}")
    log_lines.append("")
    log_lines.append("Throughput (single-threaded, in-process)")
    log_lines.append("-" * 60)
    log_lines.append(f"{'Signing':25s}: {sign_throughput:.2f} orders/sec")
    log_lines.append(f"{'Verification':25s}: {verify_throughput:.2f} orders/sec")
    log_lines.append(f"{'End-to-end pipeline':25s}: {end_to_end_throughput:.2f} orders/sec")
    log_lines.append("")

    log_lines.append("=" * 60)

    log_text = "\n".join(log_lines)

    with open(LOG_PATH, "w", encoding="utf-8") as f:
        f.write(log_text)

    print()
    print(log_text)
    print()
    print(f"CSV written to: {CSV_PATH}")
    print(f"Log written to: {LOG_PATH}")


if __name__ == "__main__":
    main()
