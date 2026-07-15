"""
Sinh biểu đồ từ kết quả benchmark_extended.py (2 methods × 3 size groups).

Input : results/extended_summary.csv
Output:
  results/fig_canon_by_size.png     — Canon latency vs order size (chứng minh O(|o|))
  results/fig_method_comparison.png — Grouped bar: canon/sign/verify per method
  results/fig_throughput.png        — Throughput comparison
"""

import csv
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

RESULTS_DIR = "results"
SUMMARY_CSV = os.path.join(RESULTS_DIR, "extended_summary.csv")

METHODS     = ["direct", "jcs"]
SIZE_GROUPS = ["small", "medium", "large"]

METHOD_COLORS = {
    "direct": "#6c757d",
    "jcs":    "#dc3545",
}
METHOD_LABELS = {
    "direct": "Direct JSON Signing",
    "jcs":    "JCS + NFC / IntelliHash (RFC 8785 + NFC)",
}
SIZE_LABELS = {
    "small":  "Small\n(~5 fields)",
    "medium": "Medium\n(~10 fields)",
    "large":  "Large\n(nested list)",
}


def load_summary() -> dict:
    data = {}
    with open(SUMMARY_CSV, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            key = (row["method"], row["size_group"])
            data[key] = {
                k: float(v) if k not in ("method", "size_group") else v
                for k, v in row.items()
            }
    return data


# ---------------------------------------------------------------------------
# Figure A: Canon latency vs order size — chứng minh O(|o|)
# ---------------------------------------------------------------------------
def plot_canon_by_size(data: dict):
    fig, ax = plt.subplots(figsize=(9, 5))

    for method in METHODS:
        x_labels, y_vals, err_vals = [], [], []
        for sg in SIZE_GROUPS:
            key = (method, sg)
            if key not in data:
                continue
            avg_b = data[key]["avg_payload_bytes"]
            x_labels.append(f"{SIZE_LABELS[sg]}\n~{avg_b:.0f} B")
            y_vals.append(data[key]["canon_avg_ms"])
            err_vals.append(data[key]["canon_std_ms"])

        ax.errorbar(
            x_labels, y_vals, yerr=err_vals,
            marker="o", linewidth=2.2, markersize=8, capsize=6,
            color=METHOD_COLORS[method],
            label=METHOD_LABELS[method],
        )

    ax.set_xlabel("Order Size Group (average canonical payload size)", fontsize=12)
    ax.set_ylabel("Canonicalization Latency (ms)", fontsize=12)
    ax.set_title(
        "Canonicalization Latency vs. Order Size\n"
        "(Validates O(|o|) linear complexity — Section 2.2)",
        fontsize=13, fontweight="bold",
    )
    ax.legend(fontsize=11)
    ax.grid(axis="y", linestyle="--", alpha=0.5)
    ax.set_ylim(bottom=0)

    plt.tight_layout()
    out = os.path.join(RESULTS_DIR, "fig_canon_by_size.png")
    plt.savefig(out, dpi=200)
    plt.close()
    print(f"Saved: {out}")


# ---------------------------------------------------------------------------
# Figure B: Grouped bar — canon / sign / verify per method (medium group)
# ---------------------------------------------------------------------------
def plot_method_comparison(data: dict, target_size: str = "medium"):
    stages = [
        ("canon_avg_ms",  "canon_std_ms",  "Canonicalization"),
        ("sign_avg_ms",   "sign_std_ms",   "SHA-256 + RSA Sign"),
        ("verify_avg_ms", "verify_std_ms", "Verification"),
    ]

    x = np.arange(len(METHODS))
    bar_width = 0.22
    n_stages  = len(stages)
    offsets   = np.linspace(-(n_stages - 1) / 2, (n_stages - 1) / 2, n_stages) * bar_width
    stage_colors = ["#adb5bd", "#0d6efd", "#28a745"]

    fig, ax = plt.subplots(figsize=(9, 6))

    for i, (avg_key, std_key, stage_label) in enumerate(stages):
        avgs = [data.get((m, target_size), {}).get(avg_key, 0) for m in METHODS]
        stds = [data.get((m, target_size), {}).get(std_key, 0) for m in METHODS]

        bars = ax.bar(
            x + offsets[i], avgs, bar_width,
            yerr=stds, capsize=4,
            color=stage_colors[i], alpha=0.85,
            label=stage_label,
            error_kw={"elinewidth": 1.2},
        )
        for bar, avg, std in zip(bars, avgs, stds):
            if avg >= 0.0001:
                ax.text(
                    bar.get_x() + bar.get_width() / 2,
                    bar.get_height() + std * 0.2 + 0.003,
                    f"{avg:.3f}",
                    ha="center", va="bottom", fontsize=9,
                )

    ax.set_xticks(x)
    ax.set_xticklabels([METHOD_LABELS[m] for m in METHODS], fontsize=11)
    ax.set_ylabel("Average Latency (ms)", fontsize=12)
    n = data.get(("jcs", target_size), {}).get("n_orders", 0)
    ax.set_title(
        f"Per-Stage Latency: Direct JSON Signing vs JCS/IntelliHash\n"
        f"(Medium-size orders, n={n:.0f})",
        fontsize=13, fontweight="bold",
    )
    ax.legend(fontsize=11)
    ax.grid(axis="y", linestyle="--", alpha=0.4)
    ax.set_ylim(bottom=0)

    plt.tight_layout()
    out = os.path.join(RESULTS_DIR, "fig_method_comparison.png")
    plt.savefig(out, dpi=200)
    plt.close()
    print(f"Saved: {out}")


# ---------------------------------------------------------------------------
# Figure C: Throughput — orders/sec per method × size group
# ---------------------------------------------------------------------------
def plot_throughput(data: dict):
    x = np.arange(len(SIZE_GROUPS))
    bar_width = 0.3
    offsets = [-bar_width / 2, bar_width / 2]

    fig, ax = plt.subplots(figsize=(9, 5))

    for i, method in enumerate(METHODS):
        throughputs = [
            data.get((method, sg), {}).get("throughput_sign", 0)
            for sg in SIZE_GROUPS
        ]
        bars = ax.bar(
            x + offsets[i], throughputs, bar_width,
            color=METHOD_COLORS[method], alpha=0.85,
            label=METHOD_LABELS[method],
        )
        for bar, tp in zip(bars, throughputs):
            if tp > 0:
                ax.text(
                    bar.get_x() + bar.get_width() / 2,
                    bar.get_height() + 3,
                    f"{tp:.0f}",
                    ha="center", va="bottom", fontsize=9,
                )

    ax.set_xticks(x)
    ax.set_xticklabels([SIZE_LABELS[sg] for sg in SIZE_GROUPS], fontsize=11)
    ax.set_xlabel("Order Size Group", fontsize=12)
    ax.set_ylabel("Signing Throughput (orders/sec)", fontsize=12)
    ax.set_title(
        "Signing Throughput: Direct JSON Signing vs JCS/IntelliHash",
        fontsize=13, fontweight="bold",
    )
    ax.legend(fontsize=11)
    ax.grid(axis="y", linestyle="--", alpha=0.4)
    ax.set_ylim(bottom=0)

    plt.tight_layout()
    out = os.path.join(RESULTS_DIR, "fig_throughput.png")
    plt.savefig(out, dpi=200)
    plt.close()
    print(f"Saved: {out}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main():
    if not os.path.exists(SUMMARY_CSV):
        raise FileNotFoundError(
            f"{SUMMARY_CSV} not found. Run benchmark_extended.py first."
        )

    data = load_summary()
    plot_canon_by_size(data)
    plot_method_comparison(data, target_size="medium")
    plot_throughput(data)
    print("Done.")


if __name__ == "__main__":
    main()
