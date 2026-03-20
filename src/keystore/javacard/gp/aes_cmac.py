"""AES-CMAC (NIST SP 800-38B) implementation.

Pure Python using ucryptolib AES-128-ECB. Used by SCP03 for secure messaging MAC.
"""

from ucryptolib import aes as _aes

_AES_BLOCK = 16


def _xor16(a, b):
    return bytes(x ^ y for x, y in zip(a, b))


def _doubled(block):
    """Multiply block by x in GF(2^128) per CMAC spec."""
    overflow = 0
    result = bytearray(16)
    for i in range(15, -1, -1):
        val = (block[i] << 1) | overflow
        result[i] = val & 0xFF
        overflow = (block[i] >> 7) & 1
    if overflow:
        result[15] ^= 0x87
    return bytes(result)


def _aes_ecb_encrypt(key, block):
    c = _aes(key, 1)
    return c.encrypt(block)


def _generate_subkeys(key):
    """Generate CMAC subkeys K1 and K2."""
    l = _aes_ecb_encrypt(key, b'\x00' * 16)
    k1 = _doubled(l)
    k2 = _doubled(k1)
    return k1, k2


def aes_cmac(key, msg):
    """Compute AES-CMAC over msg with given key.

    Returns 16-byte MAC (truncated to 8 bytes by caller for SCP03).
    """
    k1, k2 = _generate_subkeys(key)
    n = (len(msg) + 15) // 16
    if n == 0:
        n = 1

    if len(msg) == 0 or len(msg) % 16 != 0:
        block = msg + b'\x80' + b'\x00' * (15 - (len(msg) % 16))
        block = _xor16(block, k2)
    else:
        block = _xor16(msg[-16:], k1)

    x = b'\x00' * 16
    if n > 1:
        for i in range(n - 1):
            y = _xor16(x, msg[i * 16:(i + 1) * 16])
            x = _aes_ecb_encrypt(key, y)
        x = _xor16(x, block)
    else:
        x = _xor16(x, block)

    return _aes_ecb_encrypt(key, x)
