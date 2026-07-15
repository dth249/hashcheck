# HashCheck

Bộ công cụ Python tái tạo phần Experimental Evaluation trong paper IntegriChain.
Sinh dataset thật, đo latency/throughput thật bằng benchmark in-process (không qua HTTP),
và xuất log/CSV/biểu đồ làm bằng chứng cho các con số trong paper.

## Cấu trúc

```
IntegriChain/
├── dataset_generator.py     # Sinh 100,000 đơn hàng giả lập
├── canonicalization.py      # Chuẩn hóa JSON (sort keys, no whitespace)
├── crypto_utils.py          # SHA-256 + RSA-2048 (sign/verify), quản lý khóa
├── sign.py                  # Ký toàn bộ dataset
├── verify.py                # Xác minh toàn bộ chữ ký đã ký
├── benchmark.py             # Đo latency + throughput thật
├── plot_results.py          # Vẽ biểu đồ từ benchmark.csv
├── app.py                   # Demo end-to-end 1 đơn hàng
├── requirements.txt
│
├── dataset/                 # orders.json, signatures.json (sinh ra khi chạy)
├── keys/                    # private.pem, public.pem (sinh ra khi chạy)
└── results/                 # benchmark.csv, benchmark.txt, *.png (sinh ra khi chạy)
```

## Cài đặt
Yêu cầu Python 3.9+. Tải Python tại đây: [python-manager-26.2.msix](https://www.python.org/ftp/python/pymanager/python-manager-26.2.msix)

```bash
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
```


## Quy trình chạy (đúng thứ tự)

### 1. Sinh dataset

```bash
python dataset_generator.py
```

Tạo `dataset/orders.json` với 100,000 đơn hàng giả lập (random, không phải dữ liệu thật).

### 2. (Tùy chọn) Demo end-to-end cho 1 đơn hàng

```bash
python app.py
```

Minh họa trực quan pipeline: Order → Canonicalize → SHA-256 → Sign → Store → Verify,
kèm test "tamper" (sửa dữ liệu sau khi ký, verify phải fail) để chứng minh tính toàn vẹn.

### 3. Chạy benchmark chính

```bash
python benchmark.py
```

Mặc định chạy trên toàn bộ 100,000 orders — **sẽ mất vài phút**. Để test nhanh trước, giới hạn sample size:

```bash
BENCHMARK_SAMPLE_SIZE=1000 python benchmark.py     # Linux/Mac
set BENCHMARK_SAMPLE_SIZE=1000 && python benchmark.py   # Windows cmd
```

Output:
- `results/benchmark.csv` — latency từng order (canonicalization, signing, verification)
- `results/benchmark.txt` — log tổng hợp: machine info, average/median/min/max/stdev, throughput

### 4. Vẽ biểu đồ

```bash
python plot_results.py
```

Tạo `results/signing_latency.png`, `results/verification_latency.png`, `results/throughput.png`.

### 5. (Tùy chọn) Ký + verify toàn bộ dataset

```bash
python sign.py
python verify.py
```

Mô phỏng full integrity verification trên toàn bộ dataset (không phải benchmark, chỉ để chứng minh hệ thống hoạt động đúng ở quy mô lớn).

## Lưu ý

**Benchmark này đo gì:** thời gian thực thi thuần (in-process) của canonicalization, RSA
signing, và RSA verification — gọi hàm trực tiếp trong cùng một process. Đây là benchmark cấp thuật toán, trả lời câu hỏi "cơ chế mật mã này nhanh đến mức nào về mặt tính toán".

**Benchmark này KHÔNG đo:** hiệu năng API/web server (request/response qua HTTP), tải đồng thời nhiều user, độ trễ mạng. Nếu muốn báo cáo throughput ở cấp hệ thống/API thật (ví dụ
Next.js server xử lý bao nhiêu request/giây), cần một bộ load test riêng (vd: k6, Artillery,
Locust) — đó là một con số khác và phải được gọi tên rõ ràng là "system-level throughput",
không lẫn với "signing latency".
