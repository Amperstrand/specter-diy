"""
Simple helper functions to get reader and connection
"""
import uscard as sc
from pyb import Pin

reader = None
conn = None


def get_reader():
    global reader
    if reader is not None:
        return reader
    reader = sc.Reader(
        name="Specter card reader",
        ifaceId=2,
        ioPin=Pin.cpu.A2,
        clkPin=Pin.cpu.A4,
        rstPin=Pin.cpu.G10,
        presPin=Pin.cpu.C2,
        pwrPin=Pin.cpu.C5,
    )
    return reader


def get_connection():
    global conn
    if conn is not None:
        return conn
    reader = get_reader()
    conn = reader.createConnection()
    return conn


def encode(data):
    return bytes([len(data)]) + data


# ========================================
# Public Key Utilities
# ========================================

def compress_pubkey(pubkey_bytes: bytes) -> bytes:
    """Compress an uncompressed public key (65 bytes) to compressed format (33 bytes).
    
    Args:
        pubkey_bytes: Either a 33-byte compressed pubkey or 65-byte uncompressed pubkey
    
    Returns:
        33-byte compressed public key (02/03 prefix + x-coordinate)
    
    Raises:
        ValueError: If pubkey length is not 33 or 65 bytes
    """
    if len(pubkey_bytes) == 33:
        # Already compressed - return as-is
        return pubkey_bytes
    
    if len(pubkey_bytes) == 65:
        # Uncompressed format: 04 || x (32 bytes) || y (32 bytes)
        if pubkey_bytes[0] != 0x04:
            raise ValueError("Invalid uncompressed pubkey prefix")
        x = pubkey_bytes[1:33]
        y_last = pubkey_bytes[64]
        # Prefix: 02 if y is even, 03 if y is odd
        prefix = b'\x03' if y_last % 2 else b'\x02'
        return prefix + x
    
    raise ValueError("Invalid pubkey length: " + str(len(pubkey_bytes)) + ", expected 33 or 65")


def derive_fingerprint(pubkey_bytes: bytes) -> bytes:
    """Derive wallet fingerprint from a public key.
    
    Fingerprint = hash160(pubkey)[:4] where hash160 = RIPEMD160(SHA256(data))
    
    Args:
        pubkey_bytes: Public key (compressed or uncompressed)
    
    Returns:
        4-byte fingerprint
    """
    # Ensure pubkey is compressed for consistent fingerprint
    compressed = compress_pubkey(pubkey_bytes)
    sha256_hash = hashlib.sha256(compressed).digest()
    ripemd160 = hashlib.new('ripemd160', sha256_hash).digest()
    return ripemd160[:4]


# ========================================
# BIP32 Path Utilities
# ========================================

def path_to_bytes(path_str: str) -> bytes:
    """Convert a BIP32 derivation path string to bytes.
    
    Args:
        path_str: Derivation path like "m/44h/0h/0h" or "m/44'/0'/0'"
    
    Returns:
        bytes: 4 bytes per level, big-endian, hardened bit = 0x80000000
        
    Examples:
        path_to_bytes("m") -> b''
        path_to_bytes("m/44h/0h/0h") -> bytes with hardened indices
        path_to_bytes("m/44h/0h/0h/0/0") -> bytes with mixed hardened/non-hardened
    """
    path_bytes = b''
    
    # Remove 'm/' prefix if present
    if path_str.startswith('m/'):
        path_str = path_str[2:]
    elif path_str == 'm':
        return b''
    
    for part in path_str.split('/'):
        if not part:
            continue
        # Check for hardened derivation
        hardened = part.endswith('h') or part.endswith("'")
        if hardened:
            part = part[:-1]
        
        index = int(part)
        if hardened:
            index |= 0x80000000
        
        # Big-endian 4 bytes
        path_bytes += index.to_bytes(4, 'big')
    
    return path_bytes


# ========================================
# ISO Exception Handling
# ========================================

def handle_pin_iso_exception(e, pin_attempts_max=5):
    """Handle PIN-related exceptions from JavaCard.
    
    Args:
        e: ISOException or SecureError from applet communication
        pin_attempts_max: Maximum PIN attempts (default 5)
    
    Returns:
        tuple: (attempts_remaining, should_raise, exception_to_raise)
        
        - attempts_remaining: Number of PIN attempts left (0 if bricked)
        - should_raise: True if an exception should be raised
        - exception_to_raise: The exception to raise (or original if unknown)
    
    Status Words (Satochip/SeedKeeper):
        9C0C: Card bricked
        6983: Card bricked (ISO standard)
        63CX: Wrong PIN, X attempts remaining
    
    Error Codes (MemoryCard/SecureApplet):
        0502: Wrong PIN
        0503: Card bricked
    """
    from .applets.applet import ISOException
    from ..core import PinError
    from platform import CriticalErrorWipeImmediately
    
    err_str = str(e).lower()
    
    # MemoryCard/SecureApplet error codes
    if err_str == "0503":  # Bricked
        return (0, True, CriticalErrorWipeImmediately("No more PIN attempts!\nWipe!"))
    
    if err_str == "0502":  # Wrong PIN - attempts unknown from this code
        return (None, True, PinError("Invalid PIN!"))
    
    # Satochip/SeedKeeper ISO status words
    # Card is bricked - no more attempts
    if err_str == "9c0c" or err_str == "6983":
        return (0, True, CriticalErrorWipeImmediately("No more PIN attempts!\nWipe!"))
    
    # Wrong PIN: SW = 63Cx where x = remaining attempts
    if err_str.startswith("63c") and len(err_str) == 4:
        try:
            attempts_left = int(err_str[3], 16)
        except ValueError:
            attempts_left = None
        
        if attempts_left is not None:
            return (
                attempts_left,
                True,
                PinError("Invalid PIN!\n" + str(attempts_left) + " attempts left...")
            )
        return (None, True, PinError("Invalid PIN!"))
    
    # Unknown error - re-raise original exception
    return (None, True, e)
from binascii import hexlify
import hashlib
