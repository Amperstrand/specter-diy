"""Pure Python 3DES (Triple DES / DES-EDE3) implementation.

Required for SCP02 secure messaging. MicroPython on STM32F469 has no
built-in DES/3DES support — only AES via ucryptolib.
"""


def _des_encrypt_block(key, block):
    """DES single-block encryption using a simplified implementation.

    This is a reference DES implementation for 64-bit blocks with
    56-bit keys. Used internally by 3DES.
    """
    return _des(key, block, _ENCRYPT)


def _des_decrypt_block(key, block):
    """DES single-block decryption."""
    return _des(key, block, _DECRYPT)


def des3_ecb_encrypt(key, block):
    """3DES-ECB encryption (DES-EDE3).

    key: 16 bytes (2-key 3DES, K1||K2, K3=K1)
    block: 8 bytes
    Returns: 8 bytes
    """
    k1 = key[:8]
    k2 = key[8:16]
    return _des_encrypt_block(k1, _des_decrypt_block(k2, _des_encrypt_block(k1, block)))


def des3_ecb_decrypt(key, block):
    """3DES-ECB decryption (DES-EDE3).

    key: 16 bytes (2-key 3DES, K1||K2, K3=K1)
    block: 8 bytes
    Returns: 8 bytes
    """
    k1 = key[:8]
    k2 = key[8:16]
    return _des_decrypt_block(k1, _des_encrypt_block(k2, _des_decrypt_block(k1, block)))


def des3_cbc_encrypt_raw(key, iv, data):
    """3DES-CBC encryption without padding.

    key: 16 bytes (2-key 3DES)
    iv: 8 bytes (initialization vector)
    data: bytes (must be multiple of 8)
    Returns: ciphertext bytes (same length as data)
    """
    if len(data) % 8 != 0:
        raise ValueError("Data length must be multiple of 8")
    result = b""
    prev = iv
    for i in range(0, len(data), 8):
        block = bytes(a ^ b for a, b in zip(data[i:i + 8], prev))
        enc = des3_ecb_encrypt(key, block)
        result += enc
        prev = enc
    return result


def des3_cbc_decrypt_raw(key, iv, data):
    """3DES-CBC decryption without padding.

    key: 16 bytes (2-key 3DES)
    iv: 8 bytes (initialization vector)
    data: ciphertext bytes (must be multiple of 8)
    Returns: plaintext bytes (same length as data)
    """
    if len(data) % 8 != 0:
        raise ValueError("Data length must be multiple of 8")
    result = b""
    prev = iv
    for i in range(0, len(data), 8):
        block = data[i:i + 8]
        dec = des3_ecb_decrypt(key, block)
        result += bytes(a ^ b for a, b in zip(dec, prev))
        prev = block
    return result


def des_cbc_encrypt_raw(key, iv, data):
    """Single-DES-CBC encryption without padding.

    key: 8 bytes (single DES)
    iv: 8 bytes
    data: bytes (must be multiple of 8)
    Returns: ciphertext bytes
    """
    if len(data) % 8 != 0:
        raise ValueError("Data length must be multiple of 8")
    result = b""
    prev = iv
    for i in range(0, len(data), 8):
        block = bytes(a ^ b for a, b in zip(data[i:i + 8], prev))
        enc = _des_encrypt_block(key, block)
        result += enc
        prev = enc
    return result


def des3_cbc_encrypt(key, iv, data):
    """3DES-CBC encryption with ISO 7816-4 padding.

    key: 16 bytes (2-key 3DES)
    iv: 8 bytes (initialization vector)
    data: bytes to encrypt
    Returns: ciphertext bytes
    """
    padded = data + b'\x80'
    if len(padded) % 8 != 0:
        padded += b'\x00' * (8 - (len(padded) % 8))

    result = b""
    prev = iv
    for i in range(0, len(padded), 8):
        block = bytes(a ^ b for a, b in zip(padded[i:i + 8], prev))
        enc = des3_ecb_encrypt(key, block)
        result += enc
        prev = enc
    return result


def des3_cbc_decrypt(key, iv, data):
    """3DES-CBC decryption with ISO 7816-4 padding removal.

    key: 16 bytes (2-key 3DES)
    iv: 8 bytes
    data: ciphertext bytes (must be multiple of 8)
    Returns: plaintext bytes
    """
    if len(data) % 8 != 0:
        raise ValueError("Ciphertext length must be multiple of 8")

    result = b""
    prev = iv
    for i in range(0, len(data), 8):
        block = data[i:i + 8]
        dec = des3_ecb_decrypt(key, block)
        result += bytes(a ^ b for a, b in zip(dec, prev))
        prev = block

    pad_len = result[-1]
    if pad_len < 1 or pad_len > 8:
        raise ValueError("Invalid padding")
    if result[-pad_len:] != b'\x80' + b'\x00' * (pad_len - 1):
        raise ValueError("Invalid padding")
    return result[:-pad_len]


def des_cbc_mac(key, iv, data):
    """DES-CBC-MAC (ISO 9797-1 MAC algorithm 1).

    Computes MAC over data using 3DES-CBC. The final CBC block
    is the 8-byte MAC. For full 3DES MAC (algorithm 3), the last
    block uses single DES decrypt.

    key: 16 bytes (2-key 3DES)
    iv: 8 bytes (typically all zeros for first computation)
    data: bytes to MAC
    Returns: 8-byte MAC
    """
    padded = data
    if len(padded) % 8 != 0:
        padded += b'\x00' * (8 - (len(padded) % 8))

    prev = iv
    for i in range(0, len(padded), 8):
        block = bytes(a ^ b for a, b in zip(padded[i:i + 8], prev))
        prev = des3_ecb_encrypt(key, block)

    return prev


def des_cbc_mac_full(key, iv, data):
    """Full DES-CBC-MAC (ISO 9797-1 MAC algorithm 3).

    Uses 3DES for all blocks except the last, which uses single DES.
    Produces an 8-byte MAC.

    key: 16 bytes (2-key 3DES)
    iv: 8 bytes
    data: bytes to MAC
    Returns: 8-byte MAC
    """
    padded = data
    if len(padded) % 8 != 0:
        padded += b'\x00' * (8 - (len(padded) % 8))

    k1 = key[:8]
    k2 = key[8:16]
    prev = iv
    n = len(padded) // 8

    for i in range(n):
        block = bytes(a ^ b for a, b in zip(padded[i * 8:(i + 1) * 8], prev))
        if i < n - 1:
            prev = des3_ecb_encrypt(key, block)
        else:
            prev = _des_decrypt_block(k1, des3_ecb_encrypt(key, block))

    return prev


# ---- DES implementation (FIPS 46-3) ----

_ENCRYPT = 0
_DECRYPT = 1

_IP = [58, 50, 42, 34, 26, 18, 10, 2,
       60, 52, 44, 36, 28, 20, 12, 4,
       62, 54, 46, 38, 30, 22, 14, 6,
       64, 56, 48, 40, 32, 24, 16, 8,
       57, 49, 41, 33, 25, 17, 9, 1,
       59, 51, 43, 35, 27, 19, 11, 3,
       61, 53, 45, 37, 29, 21, 13, 5,
       63, 55, 47, 39, 31, 23, 15, 7]

_FP = [16, 7, 20, 21, 29, 12, 28, 17,
       1, 15, 23, 26, 5, 18, 31, 10,
       2, 8, 24, 14, 32, 27, 3, 9,
       19, 13, 30, 6, 22, 11, 4, 25]

_E = [32, 1, 2, 3, 4, 5,
      4, 5, 6, 7, 8, 9,
      8, 9, 10, 11, 12, 13,
      12, 13, 14, 15, 16, 17,
      16, 17, 18, 19, 20, 21,
      20, 21, 22, 23, 24, 25,
      24, 25, 26, 27, 28, 29,
      28, 29, 30, 31, 32, 1]

_P = [16, 7, 20, 21, 29, 12, 28, 17,
      1, 15, 23, 26, 5, 18, 31, 10,
      2, 8, 24, 14, 32, 27, 3, 9,
      19, 13, 30, 6, 22, 11, 4, 25]

_PC1 = [
    57, 49, 41, 33, 25, 17,  9,
     1, 58, 50, 42, 34, 26, 18,
    10,  2, 59, 51, 43, 35, 27,
    19, 11,  3, 60, 52, 44, 36,
    63, 55, 47, 39, 31, 23, 15,
     7, 62, 54, 46, 38, 30, 22,
    14,  6, 61, 53, 45, 37, 29,
    21, 13,  5, 28, 20, 12,  4,
]

_PC2 = [
    14, 17, 11, 24,  1,  5,
     3, 28, 15,  6, 21, 10,
    23, 19, 12,  4, 26,  8,
    16,  7, 27, 20, 13,  2,
    41, 52, 31, 37, 47, 55,
    30, 40, 51, 45, 33, 48,
    44, 49, 39, 56, 34, 53,
    46, 42, 50, 36, 29, 32,
]

_IP_INV = [
    40, 8, 48, 16, 56, 24, 64, 32,
    39,  7, 47, 15, 55, 23, 63, 31,
    38,  6, 46, 14, 54, 22, 62, 30,
    37,  5, 45, 13, 53, 21, 61, 29,
    36,  4, 44, 12, 52, 20, 60, 28,
    35, 3, 43, 11, 51, 19, 59, 27,
    34,  2, 42, 10, 50, 18, 58, 26,
    33, 1, 41, 9, 49, 17, 57, 25,
]

_SBOX1 = [
    14, 4, 13, 1, 2, 15, 11, 8, 3, 10, 6, 12, 5, 9, 0, 7,
    0, 15, 7, 4, 14, 2, 13, 1, 10, 6, 12, 11, 9, 5, 3, 8,
    4, 1, 14, 8, 13, 6, 2, 11, 15, 12, 9, 7, 3, 10, 5, 0,
    15, 12, 8, 2, 4, 9, 1, 7, 5, 11, 3, 14, 10, 0, 6, 13,
]

_SBOX2 = [
    15, 1, 8, 14, 6, 11, 3, 4, 9, 7, 2, 13, 12, 0, 5, 10,
    3, 13, 4, 7, 15, 2, 8, 14, 12, 0, 1, 10, 6, 9, 11, 5,
    0, 14, 7, 11, 10, 4, 13, 1, 5, 8, 12, 6, 9, 3, 2, 15,
    13, 8, 10, 1, 3, 15, 4, 2, 11, 6, 7, 12, 0, 5, 14, 9,
]

_SBOX3 = [
    10, 0, 9, 14, 6, 3, 15, 5, 1, 13, 12, 7, 11, 4, 2, 8,
    13, 7, 0, 9, 3, 4, 6, 10, 2, 8, 5, 14, 12, 11, 15, 1,
    13, 6, 4, 9, 8, 15, 3, 0, 11, 1, 2, 12, 5, 10, 14, 7,
    1, 10, 13, 0, 6, 9, 8, 7, 4, 15, 14, 3, 11, 5, 2, 12,
]

_SBOX4 = [
    7, 13, 14, 3, 0, 6, 9, 10, 1, 2, 8, 5, 11, 12, 4, 15,
    13, 8, 11, 5, 6, 15, 0, 3, 4, 7, 2, 12, 1, 10, 14, 9,
    10, 6, 9, 0, 12, 11, 7, 13, 15, 1, 3, 14, 5, 2, 8, 4,
    3, 15, 0, 6, 10, 1, 13, 8, 9, 4, 5, 11, 12, 7, 2, 14,
]

_SBOX5 = [
    2, 12, 4, 1, 7, 10, 11, 6, 8, 5, 3, 15, 13, 0, 14, 9,
    14, 11, 2, 12, 4, 7, 13, 1, 5, 0, 15, 10, 3, 9, 8, 6,
    4, 2, 1, 11, 10, 13, 7, 8, 15, 9, 12, 5, 6, 3, 0, 14,
    11, 8, 12, 7, 1, 14, 2, 13, 6, 15, 0, 9, 10, 4, 5, 3,
]

_SBOX6 = [
    12, 1, 10, 15, 9, 2, 6, 8, 0, 13, 3, 4, 14, 7, 5, 11,
    10, 15, 4, 2, 7, 12, 9, 5, 6, 1, 13, 14, 0, 11, 3, 8,
    9, 14, 15, 5, 2, 8, 12, 3, 7, 0, 4, 10, 1, 13, 11, 6,
    4, 3, 2, 12, 9, 5, 15, 10, 11, 14, 1, 7, 6, 0, 8, 13,
]

_SBOX7 = [
    4, 11, 2, 14, 15, 0, 8, 13, 3, 12, 9, 7, 5, 10, 6, 1,
    13, 0, 11, 7, 4, 9, 1, 10, 14, 3, 5, 12, 2, 15, 8, 6,
    1, 4, 11, 13, 12, 3, 7, 14, 10, 15, 6, 8, 0, 5, 9, 2,
    6, 11, 13, 8, 1, 4, 10, 7, 9, 5, 0, 15, 14, 2, 3, 12,
]

_SBOX8 = [
    13, 2, 8, 4, 6, 15, 11, 1, 10, 9, 3, 14, 5, 0, 12, 7,
    1, 15, 13, 8, 10, 3, 7, 4, 12, 5, 6, 11, 0, 14, 9, 2,
    7, 11, 4, 1, 9, 12, 14, 2, 0, 6, 10, 13, 15, 3, 5, 8,
    2, 1, 14, 7, 4, 10, 8, 13, 15, 12, 9, 0, 3, 5, 6, 11,
]

_SBOXES = [_SBOX1, _SBOX2, _SBOX3, _SBOX4, _SBOX5, _SBOX6, _SBOX7, _SBOX8]

_SHIFTS = [1, 1, 2, 2, 2, 2, 2, 2, 1, 2, 2, 2, 2, 2, 2, 1]


def _bytes_to_bits(data):
    bits = []
    for byte in data:
        for i in range(7, -1, -1):
            bits.append((byte >> i) & 1)
    return bits


def _bits_to_bytes(bits):
    result = bytearray()
    for i in range(0, len(bits), 8):
        byte = 0
        for j in range(8):
            byte = (byte << 1) | bits[i + j]
        result.append(byte)
    return bytes(result)


def _permute(block, table, n):
    return [block[table[i] - 1] for i in range(n)]


def _left_shift(bits, n):
    return bits[n:] + bits[:n]


def _xor_bits(a, b):
    return [x ^ y for x, y in zip(a, b)]


def _key_schedule(key_bytes):
    keys = []
    key_bits = _bytes_to_bits(key_bytes)
    perm = _permute(key_bits, _PC1, 56)
    C = perm[:28]
    D = perm[28:]

    for i in range(16):
        C = _left_shift(C, _SHIFTS[i])
        D = _left_shift(D, _SHIFTS[i])

        combined = C + D
        round_key = _permute(combined, _PC2, 48)
        keys.append(round_key)
    return keys


def _f(R, K):
    expanded = _permute(R, _E, 48)
    xored = _xor_bits(expanded, K)

    sbox_out = []
    for i in range(8):
        b = xored[i * 6:(i + 1) * 6]
        row = (b[0] << 1) | b[5]
        col = (b[1] << 3) | (b[2] << 2) | (b[3] << 1) | b[4]
        val = _SBOXES[i][row * 16 + col]
        sbox_out.append((val >> 3) & 1)
        sbox_out.append((val >> 2) & 1)
        sbox_out.append((val >> 1) & 1)
        sbox_out.append(val & 1)

    return _permute(sbox_out, _P, 32)


def _des(key_bytes, block_bytes, mode):
    round_keys = _key_schedule(key_bytes)

    block = _permute(_bytes_to_bits(block_bytes), _IP, 64)
    left = block[:32]
    right = block[32:]

    for i in range(16):
        if mode == _ENCRYPT:
            ki = i
        else:
            ki = 15 - i
        temp = right
        right = _xor_bits(left, _f(right, round_keys[ki]))
        left = temp

    combined = right + left
    result = _permute(combined, _IP_INV, 64)
    return _bits_to_bytes(result)
