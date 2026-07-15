"""
Chuẩn hóa JSON (Canonical JSON) trước khi hash/sign.

Pipeline 2 bước — mở rộng so với JCS gốc (RFC 8785):

  Bước 1 — NFC normalization (mở rộng của IntelliHash):
    RFC 8785 thừa nhận không xử lý Unicode normalization (Section 3.2.2.2):
    "The escaping rules do not include normalization of Unicode".
    Input có chuỗi dạng NFD hoặc hỗn hợp sẽ tạo ra byte sequence khác nhau
    dù về mặt con người đọc là cùng 1 nội dung → hash khác nhau → verify fail.
    IntelliHash thêm bước đưa tất cả chuỗi về NFC trước khi đưa vào JCS.

  Bước 2 — JCS canonicalization (RFC 8785):
    Sort key theo thứ tự Unicode code point, serialize số theo ECMAScript
    IEEE 754 double precision, escape string theo RFC 8259.

Tham chiếu:
  - RFC 8785: https://www.rfc-editor.org/info/rfc8785
  - Unicode NFC: https://unicode.org/reports/tr15/
"""

import unicodedata
import jcs


# ---------------------------------------------------------------------------
# NFC pre-processing (bước mở rộng — JCS gốc không có)
# ---------------------------------------------------------------------------

def _nfc_value(value):
    """
    Đệ quy đưa tất cả chuỗi trong cấu trúc JSON về dạng NFC.
    Các kiểu không phải str (int, float, bool, None) giữ nguyên.
    """
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if isinstance(value, dict):
        return {_nfc_value(k): _nfc_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_nfc_value(item) for item in value]
    return value


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def canonicalize(data: dict) -> bytes:
    """
    Chuẩn hóa JSON 2 bước:
      1. Đưa tất cả chuỗi về NFC (IntelliHash extension).
      2. JCS canonicalize theo RFC 8785.

    Trả về bytes UTF-8 deterministic, sẵn sàng để hash/sign.
    """
    nfc_data = _nfc_value(data)
    return jcs.canonicalize(nfc_data)


# ---------------------------------------------------------------------------
# Demo / smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Test 1: key ordering
    sample_a = {"b": 2, "a": 1, "c": {"y": 2, "x": 1}}
    sample_b = {"a": 1, "c": {"x": 1, "y": 2}, "b": 2}
    out_a = canonicalize(sample_a)
    out_b = canonicalize(sample_b)
    print("=== Test 1: key ordering ===")
    print("Canonical A:", out_a)
    print("Canonical B:", out_b)
    print("Match (expected True):", out_a == out_b)
    print()

    # Test 2: NFC normalization
    # "café" có thể encode theo 2 cách:
    #   NFC: U+0063 U+0061 U+0066 U+00E9           (é = 1 code point)
    #   NFD: U+0063 U+0061 U+0066 U+0065 U+0301    (e + combining accent = 2 code points)
    nfc_str = unicodedata.normalize("NFC", "caf\u00e9")   # é composed
    nfd_str = unicodedata.normalize("NFD", "cafe\u0301")  # e + combining
    print("=== Test 2: NFC normalization ===")
    print("NFC input:", repr(nfc_str), "len:", len(nfc_str))
    print("NFD input:", repr(nfd_str), "len:", len(nfd_str))
    out_nfc = canonicalize({"name": nfc_str})
    out_nfd = canonicalize({"name": nfd_str})
    print("Canonical (NFC input):", out_nfc)
    print("Canonical (NFD input):", out_nfd)
    print("Match after NFC pre-processing (expected True):", out_nfc == out_nfd)
