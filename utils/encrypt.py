"""AES 加密：用于学习通登录时加密用户名和密码"""
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
import base64

# 超星固定的 AES key 和 iv
_KEY = b"u2oh6Vu^HWe4_AES"
_IV = b"u2oh6Vu^HWe4_AES"


def aes_encrypt(data: str) -> str:
    """AES-128-CBC 加密，返回 base64 字符串"""
    padder = padding.PKCS7(128).padder()
    padded_data = padder.update(data.encode('utf-8')) + padder.finalize()
    cipher = Cipher(algorithms.AES(_KEY), modes.CBC(_IV), backend=default_backend())
    encryptor = cipher.encryptor()
    encrypted_data = encryptor.update(padded_data) + encryptor.finalize()
    return base64.b64encode(encrypted_data).decode('utf-8')
