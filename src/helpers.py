from embit import bip39, compact
import hashlib
import hmac
from ucryptolib import aes
from io import BytesIO
import rng
import platform
from binascii import b2a_base64, a2b_base64
from embit.liquid.networks import NETWORKS
import utime

AES_BLOCK = 16
IV_SIZE = 16
AES_CBC = 2

def is_liquid(network):
    if isinstance(network, str):
        network = NETWORKS[network]
    return ("blech32" in network)

def gen_mnemonic(num_words: int) -> str:
    """Generates a mnemonic with num_words"""
    if num_words < 12 or num_words > 24 or num_words % 3 != 0:
        raise RuntimeError("Invalid word count")
    return bip39.mnemonic_from_bytes(rng.get_random_bytes(num_words * 4 // 3))

def fix_mnemonic(phrase):
    """Fixes checksum of invalid mnemonic"""
    entropy = bip39.mnemonic_to_bytes(phrase, ignore_checksum=True)
    return bip39.mnemonic_from_bytes(entropy)


def tagged_hash(tag: str, data: bytes) -> bytes:
    """BIP-Schnorr tag-specific key derivation"""
    hashtag = hashlib.sha256(tag.encode()).digest()
    return hashlib.sha256(hashtag + hashtag + data).digest()


def encrypt(plain: bytes, key: bytes) -> bytes:
    """Encrypt data with bit padding (0x80...)"""
    iv = rng.get_random_bytes(IV_SIZE)
    crypto = aes(key, AES_CBC, iv)
    # encrypted data should be mod 16 (blocksize)
    # add padding
    plain += b"\x80"
    if len(plain) % AES_BLOCK != 0:
        # fill with zeroes
        plain += b"\x00" * (AES_BLOCK - (len(plain) % AES_BLOCK))
    return iv + crypto.encrypt(plain)


def decrypt(ct: bytes, key: bytes) -> bytes:
    """Decrypt data and remove AES_CBC 80... padding"""
    iv = ct[:IV_SIZE]
    ct = ct[IV_SIZE:]
    # 2 - MODE_CBC
    crypto = aes(key, AES_CBC, iv)
    plain = crypto.decrypt(ct)
    # remove padding:
    # split
    arr = plain.split(b"\x80")
    # remove last element and check it's all zeroes
    last = arr.pop()
    if last != b"\x00" * len(last):
        raise Exception("Invalid padding")
    # join all but last
    return b"\x80".join(arr)


def aead_encrypt(key: bytes, adata: bytes = b"", plaintext: bytes = b"") -> bytes:
    """
    Encrypts and authenticates with associated data using key k.
    output format: <compact-len:associated data><iv><ct><hmac>
    """
    aes_key = tagged_hash("aes", key)
    hmac_key = tagged_hash("hmac", key)
    data = compact.to_bytes(len(adata)) + adata
    # if there is not ct - just add hmac
    if len(plaintext) > 0:
        data += encrypt(plaintext, aes_key)
    mac = hmac.new(hmac_key, data, digestmod="sha256").digest()
    return data + mac


def aead_decrypt(ciphertext: bytes, key: bytes) -> tuple:
    """
    Verifies MAC and decrypts ciphertext with associated data.
    Inverse to aead_encrypt
    Returns a tuple adata, plaintext
    """
    mac = ciphertext[-32:]
    ct = ciphertext[:-32]

    aes_key = tagged_hash("aes", key)
    hmac_key = tagged_hash("hmac", key)
    if mac != hmac.new(hmac_key, ct, digestmod="sha256").digest():
        raise Exception("Invalid HMAC")
    b = BytesIO(ct)
    l = compact.read_from(b)
    adata = b.read(l)
    if len(adata) != l:
        raise Exception("Invalid length")
    ct = b.read()
    if len(ct) == 0:
        return adata, b""
    return adata, decrypt(ct, aes_key)


def load_apps(module="apps", whitelist=None, blacklist=None):
    mod = __import__(module)
    mods = mod.__all__
    apps = []
    if blacklist is not None:
        mods = [mod for mod in mods if mod not in blacklist]
    if whitelist is not None:
        mods = [mod for mod in mods if mod in whitelist]
    for modname in mods:
        appmod = __import__("%s.%s" % (module, modname))
        mod = getattr(appmod, modname)
        if hasattr(mod, "App"):
            app = mod.App(platform.fpath("/qspi/%s" % modname))
            apps.append(app)
        else:
            print("Failed loading app:", modname)
    return apps

def a2b_base64_stream(sin, sout):
    l = 0
    while True:
        chunk = sin.read(64).strip() # 16 chunks 4 chars each
        if len(chunk) == 0:
            break
        l += sout.write(a2b_base64(chunk))
    return l

def b2a_base64_stream(sin, sout):
    l = 0
    while True:
        chunk = sin.read(48) # 16 chunks 3 bytes each
        if len(chunk) == 0:
            break
        l += sout.write(b2a_base64(chunk).strip())
    return l

def read_until(s, chars=b"\n\r", max_len=100, return_on_max_len=False):
    """Reads from stream until one of the chars"""
    res = b""
    chunk = b""
    while True:
        chunk = s.read(1)
        if len(chunk) == 0:
            return res, None
        if chunk in chars:
            return res, chunk
        res += chunk
        if len(res) > max_len:
            return res if return_on_max_len else None, None

def seek_to(s, chars=b"\n"):
    """Seeks stream to one of the chars"""
    off = 0
    chunk = b""
    while True:
        chunk = s.read(1)
        off += len(chunk)
        if len(chunk) == 0:
            return off, None
        if chunk in chars:
            return off, chunk

def read_write(fin, fout, chunk_size=32):
    chunk = fin.read(chunk_size)
    total = fout.write(chunk)
    while len(chunk) > 0:
        chunk = fin.read(chunk_size)
        total += fout.write(chunk)
    return total

# The conv_time() function converts a timestamp measured in seconds from 1970-01-01 00:00:00 UTC to
# humand-readable parameters (year, month, day, hour, minute, second, second, weekday, yeardate) in UTC.
# "Time Epoch: Unix port uses standard for POSIX systems epoch of 1970-01-01 00:00:00 UTC.
# However, embedded ports use epoch of 2000-01-01 00:00:00 UTC."
# (Source: https://micropython.readthedocs.io/en/latest/library/utime.html)
# Simulator MicroPython case:
#   utime.mktime() does not exist. utime.localtime() gives result with both timezone offset and DST offset.
#   To remove the timezone offset, we calculate the offset of EPOCH ZERO timestamp (1970-01-01 00:00:00 UTC),
#   substract it from the timestamp, and recall utime.localtime() again.
#   To remove the DST offset, we usually only need to check the dst_offset in the result (in hours), subtract it
#   and call utime.localtime() again. However, in one case (DST start on March) when the local clocks jump forward,
#   there is an hour when we don't need to apply the shift - and we correct it manually.
# Embedded MicroPython case:
#   utime.gmtime() and utime.localtime() are the same function (in some implementation only utime.localtime()
#   exists, but does not add timezone/dst offsets). However, timestamp zero is not 1970-01-01 00:00:00 UTC,
#   but 2000-01-01 00:00:00 UTC. Therefore we reduce the fixed difference from the timestamp before execution.
if platform.simulator:
    def conv_time(t):
        y, m, d, hh, mm, ss, *_ = utime.localtime(0)
        tz_offset = hh * 3600 + mm * 60 + ss
        if (y, m) == (1970, 1):
            tz_offset += 86400 * (d - 1)
        elif (y, m) == (1969, 12):
            tz_offset -= 86400 * (32 - d)
        else:
            raise ValueError("Failed to calculate simulator timezone offset")
        adjusted_t = t - tz_offset
        dst_offset = utime.localtime(adjusted_t)[8]
        adjusted_t -= dst_offset * 3600
        new_localtime = utime.localtime(adjusted_t)
        if new_localtime[8] == 0 and dst_offset == 1 and new_localtime[3] == 1:
            return (new_localtime[:3] + (2,) + new_localtime[4:])[:8]
        return new_localtime[:8]
    conv_time(0) # Check that the function is working
else:
    _UNIX_EPOCH_OFFSET = 946684800
    _conv_time = utime.gmtime if hasattr(utime, "gmtime") else utime.localtime
    def conv_time(t):
        return _conv_time(t - _UNIX_EPOCH_OFFSET)



# =============================================================================
# Structured Test Output
# =============================================================================

import json

# Test mode flag - set to True for test builds
TEST_MODE = False

# Test card whitelist - only used when TEST_MODE is True
# Format: { 'card_atr_hex': { 'pin': '1234', 'description': 'Test card #1' } }
TEST_CARDS = {}

def test_output(event, data=None):
    """
    Output structured test event for automated testing.
    Format: [TEST] <json>
    
    Args:
        event: Event name (e.g., 'card_detected', 'pin_verify', 'mnemonic_loaded')
        data: Optional dict with event details
    """
    if data is None:
        data = {}
    data['event'] = event
    try:
        print('[TEST] ' + json.dumps(data))
    except:
        # Fallback if json fails
        print('[TEST] event=' + event)

def test_output_atr(atr_bytes):
    """Output ATR in structured format"""
    atr_hex = ' '.join('%02X' % b for b in atr_bytes)
    test_output('atr', {'atr_hex': atr_hex, 'atr_raw': atr_bytes.hex()})

def test_output_card_type(card_type, applet_name=None, aid=None):
    """Output detected card type"""
    data = {'card_type': card_type}
    if applet_name:
        data['applet'] = applet_name
    if aid:
        data['aid'] = aid.hex() if isinstance(aid, bytes) else aid
    test_output('card_detected', data)

def test_output_pin_state(attempts_remaining=None, attempts_max=None, is_locked=None):
    """Output PIN state"""
    data = {}
    if attempts_remaining is not None:
        data['attempts_remaining'] = attempts_remaining
    if attempts_max is not None:
        data['attempts_max'] = attempts_max
    if is_locked is not None:
        data['is_locked'] = is_locked
    test_output('pin_state', data)

def test_output_pin_result(success, error=None):
    """Output PIN verification result"""
    data = {'success': success}
    if error:
        data['error'] = error
    test_output('pin_result', data)

def test_output_mnemonic_loaded(fingerprint=None, secret_id=None, label=None):
    """Output mnemonic load result"""
    data = {'loaded': True}
    if fingerprint:
        data['fingerprint'] = fingerprint
    if secret_id is not None:
        data['secret_id'] = secret_id
    if label:
        data['label'] = label
    test_output('mnemonic_loaded', data)

def test_output_error(stage, message):
    """Output error during testing"""
    test_output('error', {'stage': stage, 'message': message})

def test_output_keystore_selected(keystore_name):
    """Output when keystore is selected"""
    test_output('keystore_selected', {'keystore': keystore_name})

def test_output_secure_channel(established, card_pubkey=None):
    """Output secure channel status"""
    data = {'established': established}
    if card_pubkey:
        data['card_pubkey'] = card_pubkey.hex() if isinstance(card_pubkey, bytes) else card_pubkey
    test_output('secure_channel', data)
