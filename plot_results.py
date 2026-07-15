"""
Đọc results/benchmark.csv và sinh biểu đồ phục vụ báo cáo:
  - results/signing_latency.png    (histogram)
  - results/verification_latency.png (histogram)
  - results/throughput.png          (bar chart so sánh các bước)
"""

import os
import csv
import matplotlib
matplotlib.use("Agg")  # không cần GUI, chỉ xuất file ảnh
import matplotlib.pyplot as plt

RESULTS_DIR = "results"
CSV_PATH = os.path.join(RESULTS_DIR, "benchmark.csv")


def load_csv():
    canon, sign, verify = [], [], []
    with open(CSV_PATH, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            canon.append(float(row["canonicalization_ms"]))
            sign.append(float(row["signing_ms"]))
            verify.append(float(row["verification_ms"]))
    return canon, sign, verify


def plot_histogram(data, title, xlabel, filename, color="#fe2c55"):
    plt.figure(figsize=(8, 5))
    plt.hist(data, bins=60, color=color, edgecolor="black", alpha=0.8)
    plt.title(title)
    plt.xlabel(xlabel)
    plt.ylabel("Frequency")
    plt.tight_layout()
    out_path = os.path.join(RESULTS_DIR, filename)
    plt.savefig(out_path, dpi=150)
    plt.close()
    print(f"Saved {out_path}")


def plot_throughput_bar(canon, sign, verify):
    import statistics

    avg_canon = statistics.mean(canon)
    avg_sign = statistics.mean(sign)
    avg_verify = statistics.mean(verify)

    labels = ["Canonicalization", "Signing", "Verification"]
    values = [avg_canon, avg_sign, avg_verify]

    plt.figure(figsize=(7, 5))
    bars = plt.bar(labels, values, color=["#444444", "#fe2c55", "#0f0f0f"])
    plt.ylabel("Average Latency (ms)")
    plt.title("Average Latency by Pipeline Stage")

    for bar, value in zip(bars, values):
        plt.text(bar.get_x() + bar.get_width() / 2, value, f"{value:.2f}ms",
                  ha="center", va="bottom")

    plt.tight_layout()
    out_path = os.path.join(RESULTS_DIR, "throughput.png")
    plt.savefig(out_path, dpi=150)
    plt.close()
    print(f"Saved {out_path}")


def main():
    if not os.path.exists(CSV_PATH):
        raise FileNotFoundError(f"{CSV_PATH} not found. Run benchmark.py first.")

    canon, sign, verify = load_csv()

    plot_histogram(sign, "Signing Latency Distribution (RSA-2048 + PSS)", "Latency (ms)", "signing_latency.png")
    plot_histogram(verify, "Verification Latency Distribution", "Latency (ms)", "verification_latency.png")
    plot_throughput_bar(canon, sign, verify)


if __name__ == "__main__":
    main()
