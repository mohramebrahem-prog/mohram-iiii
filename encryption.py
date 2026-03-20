# -*- coding: utf-8 -*-
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import base64

class AESCipher:
    def __init__(self, key: str):
        kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32,
                         salt=b"mhrm_salt_v2", iterations=100000)
        self.fernet = Fernet(base64.urlsafe_b64encode(kdf.derive(key.encode())))

    def encrypt(self, data: str) -> str:
        return self.fernet.encrypt(data.encode()).decode() if data else ""

    def decrypt(self, enc: str) -> str:
        try:
            return self.fernet.decrypt(enc.encode()).decode() if enc else ""
        except Exception:
            return ""
