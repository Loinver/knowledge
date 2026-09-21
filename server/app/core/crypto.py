"""凭据加密（H-20）。

开发态用 base64 + XOR 做可逆编码（无网络装 cryptography）。
M2 后期装 cryptography 后替换为 AES-GCM，密钥来自环境变量。
凭据密文落库，解密只在后端，浏览器永不接触明文。
"""

from __future__ import annotations

import base64
import hashlib

from app.core.config import get_settings


def _derive_key() -> bytes:
    """从配置派生固定密钥（开发态）。生产用 KMS。"""
    raw = get_settings().crypto_key.encode()
    return hashlib.sha256(raw).digest()


def encrypt(plaintext: str) -> str:
    """加密凭据。开发态用 XOR + base64，可逆但不安全。"""
    key = _derive_key()
    data = plaintext.encode()
    cipher = bytes(b ^ key[i % len(key)] for i, b in enumerate(data))
    return base64.b64encode(cipher).decode()


def decrypt(ciphertext: str) -> str:
    """解密凭据。只在后端调用。"""
    key = _derive_key()
    cipher = base64.b64decode(ciphertext)
    data = bytes(b ^ key[i % len(key)] for i, b in enumerate(cipher))
    return data.decode()


def mask_credential(params: dict) -> dict:
    """脱敏：返回给浏览器的可展示配置，凭据字段遮蔽。"""
    masked = {}
    for k, v in params.items():
        if k.lower() in ("password", "pwd", "credential", "secret", "token"):
            masked[k] = "***"
        else:
            masked[k] = v
    return masked
