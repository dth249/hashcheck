"""
Các hàm mật mã cốt lõi: SHA-256 hashing, sinh khóa RSA, ký số, xác minh chữ ký.

Dùng thư viện `cryptography`
"""

import os
import hashlib

from cryptography.hazmat.primitives.asymmetric import rsa, padding, utils as asym_utils
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.exceptions import InvalidSignature

KEYS_DIR = "keys"
PRIVATE_KEY_PATH = os.path.join(KEYS_DIR, "private.pem")
PUBLIC_KEY_PATH = os.path.join(KEYS_DIR, "public.pem")

RSA_KEY_SIZE = 2048


# ---------------------------------------------------------------------------
# SHA-256
# ---------------------------------------------------------------------------

def hash_data(data: bytes) -> bytes:
    """SHA-256 digest của dữ liệu đầu vào (bytes). Trả về digest dạng bytes."""
    return hashlib.sha256(data).digest()


def hash_data_hex(data: bytes) -> str:
    """SHA-256 digest dạng hex string, tiện để log/in ra."""
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# RSA key management
# ---------------------------------------------------------------------------

def generate_keys(force: bool = False):
    """
    Sinh cặp khóa RSA-2048 và lưu vào keys/private.pem, keys/public.pem.
    Nếu khóa đã tồn tại và force=False thì bỏ qua (không sinh lại).
    """
    os.makedirs(KEYS_DIR, exist_ok=True)

    if not force and os.path.exists(PRIVATE_KEY_PATH) and os.path.exists(PUBLIC_KEY_PATH):
        print("Keys already exist, skipping generation. (use force=True to regenerate)")
        return

    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=RSA_KEY_SIZE,
    )
    public_key = private_key.public_key()

    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    with open(PRIVATE_KEY_PATH, "wb") as f:
        f.write(private_pem)
    with open(PUBLIC_KEY_PATH, "wb") as f:
        f.write(public_pem)

    print(f"Generated RSA-{RSA_KEY_SIZE} keypair -> {PRIVATE_KEY_PATH}, {PUBLIC_KEY_PATH}")


def load_private_key():
    with open(PRIVATE_KEY_PATH, "rb") as f:
        return serialization.load_pem_private_key(f.read(), password=None)


def load_public_key():
    with open(PUBLIC_KEY_PATH, "rb") as f:
        return serialization.load_pem_public_key(f.read())


# ---------------------------------------------------------------------------
# Sign / Verify
# ---------------------------------------------------------------------------

def sign_data(private_key, data: bytes) -> bytes:
    """
    Ký số dữ liệu bằng RSA-PSS + SHA-256.
    Thư viện tự hash `data` bên trong — dùng khi không cần lưu digest riêng.
    """
    return private_key.sign(
        data,
        padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()),
            salt_length=padding.PSS.MAX_LENGTH,
        ),
        hashes.SHA256(),
    )


def sign_digest(private_key, digest: bytes) -> bytes:
    """
    Ký RSA-PSS trên digest SHA-256 đã tính sẵn (32 bytes).
    Dùng Prehashed để thư viện KHÔNG hash lại — tránh tính SHA-256 hai lần.
    Khớp chính xác công thức paper: sigma = Sign_sk(h).
    """
    return private_key.sign(
        digest,
        padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()),
            salt_length=padding.PSS.MAX_LENGTH,
        ),
        asym_utils.Prehashed(hashes.SHA256()),
    )


def verify_signature(public_key, data: bytes, signature: bytes) -> bool:
    """
    Xác minh chữ ký — thư viện tự hash `data` bên trong.
    """
    try:
        public_key.verify(
            signature,
            data,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.MAX_LENGTH,
            ),
            hashes.SHA256(),
        )
        return True
    except InvalidSignature:
        return False


def verify_digest(public_key, digest: bytes, signature: bytes) -> bool:
    """
    Xác minh chữ ký trên digest SHA-256 đã tính sẵn.
    Dùng Prehashed — khớp với sign_digest(), không hash lại.
    """
    try:
        public_key.verify(
            signature,
            digest,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.MAX_LENGTH,
            ),
            asym_utils.Prehashed(hashes.SHA256()),
        )
        return True
    except InvalidSignature:
        return False


if __name__ == "__main__":
    # Demo nhanh
    generate_keys()
    priv = load_private_key()
    pub = load_public_key()

    sample = b'{"order_id":"ORD-00000001","price":12.5}'
    digest_hex = hash_data_hex(sample)
    sig = sign_data(priv, sample)
    is_valid = verify_signature(pub, sample, sig)

    print("SHA-256:", digest_hex)
    print("Signature length (bytes):", len(sig))
    print("Verify valid:", is_valid)
