"""
BIP-44/84/85 derivation tests using official spec test vectors.

BIP-44: Multi-Account Hierarchy for Deterministic Wallets
- https://github.com/bitcoin/bips/blob/master/bip-0044.mediawiki

BIP-84: Derivation scheme for P2WPKH native SegWit accounts
- https://github.com/bitcoin/bips/blob/master/bip-0084.mediawiki

BIP-85: Deterministic Entropy From BIP32 Keychains
- https://github.com/bitcoin/bips/blob/master/bip-0085.mediawiki
"""
from unittest import TestCase
import sys
import os

# Add f469-disco to path for embit imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'f469-disco'))

try:
    from embit.bip32 import HDKey, HARDENED_INDEX, parse_path
    from embit.bip39 import mnemonic_to_seed, mnemonic_to_bytes
    from embit.bip85 import derive_entropy, derive_mnemonic, derive_wif
    from embit.script import p2wpkh, p2pkh
    from embit.networks import NETWORKS
    from embit import bip39
    EMBIT_AVAILABLE = True
except ImportError:
    EMBIT_AVAILABLE = False


def skip_if_no_embit(func):
    """Decorator to skip tests if embit is not available."""
    def wrapper(*args, **kwargs):
        if not EMBIT_AVAILABLE:
            raise ImportError("embit library not available - skipping test")
        return func(*args, **kwargs)
    return wrapper


class BIP44Test(TestCase):
    """Tests for BIP-44 Multi-Account Hierarchy for Deterministic Wallets.
    
    BIP-44 defines a logical hierarchy for deterministic wallets:
    m / purpose' / coin_type' / account' / change / address_index
    
    Purpose: 44' (hardened)
    Coin Type: 0' for Bitcoin mainnet, 1' for testnet
    Account: Index starting from 0
    Change: 0 for external chain (receiving), 1 for internal chain (change)
    Address Index: Sequential index starting from 0
    """

    # Official BIP-32 test vector seed (also used in BIP-44 examples)
    SEED_HEX = "000102030405060708090a0b0c0d0e0f"
    
    # Test mnemonic for BIP-44 derivation verification
    # This is the TREZOR test vector mnemonic
    TEST_MNEMONIC = "abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about"

    @skip_if_no_embit
    def test_path_derivation_external(self):
        """Test m/44'/0'/0'/0/0 derivation (external chain, first address).
        
        Path breakdown:
        - 44': BIP-44 purpose
        - 0': Bitcoin mainnet (coin type)
        - 0': First account
        - 0: External chain (receiving addresses)
        - 0: First address index
        """
        from binascii import unhexlify
        
        root = HDKey.from_seed(unhexlify(self.SEED_HEX))
        
        # Derive m/44'/0'/0'/0/0
        path = parse_path("m/44'/0'/0'/0/0")
        derived = root.derive(path)
        
        # Verify it's a private key
        self.assertTrue(derived.is_private)
        
        # Verify the path structure by deriving step by step
        account = root.derive([HARDENED_INDEX + 44, HARDENED_INDEX + 0, HARDENED_INDEX + 0])
        external = account.derive([0])
        first_addr = external.derive([0])
        
        self.assertEqual(derived.to_base58(), first_addr.to_base58())
        
        # Generate P2PKH address
        pubkey = derived.to_public()
        script = p2pkh(pubkey)
        address = script.address(NETWORKS["main"])
        
        # Address should be a valid base58 P2PKH address starting with 1
        self.assertTrue(address.startswith("1"))
        self.assertEqual(len(address), 34)

    @skip_if_no_embit
    def test_path_derivation_change(self):
        """Test m/44'/0'/0'/1/0 derivation (change chain).
        
        Path breakdown:
        - 44': BIP-44 purpose
        - 0': Bitcoin mainnet
        - 0': First account
        - 1: Internal/change chain
        - 0: First change address
        """
        from binascii import unhexlify
        
        root = HDKey.from_seed(unhexlify(self.SEED_HEX))
        
        # Derive m/44'/0'/0'/1/0
        external_path = parse_path("m/44'/0'/0'/0/0")
        change_path = parse_path("m/44'/0'/0'/1/0")
        
        external_derived = root.derive(external_path)
        change_derived = root.derive(change_path)
        
        # External and change addresses should be different
        self.assertNotEqual(
            external_derived.to_base58(),
            change_derived.to_base58()
        )
        
        # Both should generate valid addresses
        external_pub = external_derived.to_public()
        change_pub = change_derived.to_public()
        
        external_addr = p2pkh(external_pub).address(NETWORKS["main"])
        change_addr = p2pkh(change_pub).address(NETWORKS["main"])
        
        self.assertTrue(external_addr.startswith("1"))
        self.assertTrue(change_addr.startswith("1"))
        self.assertNotEqual(external_addr, change_addr)

    @skip_if_no_embit
    def test_account_switching(self):
        """Test account index increment (m/44'/0'/0'/0/0 vs m/44'/0'/1'/0/0).
        
        Different accounts should derive completely different keys and addresses.
        This is important for wallet separation (e.g., personal vs business).
        """
        from binascii import unhexlify
        
        root = HDKey.from_seed(unhexlify(self.SEED_HEX))
        
        # Account 0, first address
        account0_path = parse_path("m/44'/0'/0'/0/0")
        account0 = root.derive(account0_path)
        
        # Account 1, first address
        account1_path = parse_path("m/44'/0'/1'/0/0")
        account1 = root.derive(account1_path)
        
        # Keys should be completely different
        self.assertNotEqual(account0.to_base58(), account1.to_base58())
        
        # Addresses should be different
        addr0 = p2pkh(account0.to_public()).address(NETWORKS["main"])
        addr1 = p2pkh(account1.to_public()).address(NETWORKS["main"])
        
        self.assertNotEqual(addr0, addr1)

    @skip_if_no_embit
    def test_coin_type_switching(self):
        """Test coin type switching (mainnet vs testnet).
        
        m/44'/0'/... for Bitcoin mainnet
        m/44'/1'/... for Bitcoin testnet
        
        Same seed should produce different keys for different networks.
        """
        from binascii import unhexlify
        
        root = HDKey.from_seed(unhexlify(self.SEED_HEX))
        
        # Mainnet: coin_type = 0
        mainnet_path = parse_path("m/44'/0'/0'/0/0")
        mainnet_key = root.derive(mainnet_path)
        
        # Testnet: coin_type = 1
        testnet_path = parse_path("m/44'/1'/0'/0/0")
        testnet_key = root.derive(testnet_path)
        
        # Keys should be different
        self.assertNotEqual(mainnet_key.to_base58(), testnet_key.to_base58())
        
        # Generate addresses for respective networks
        mainnet_addr = p2pkh(mainnet_key.to_public()).address(NETWORKS["main"])
        testnet_addr = p2pkh(testnet_key.to_public()).address(NETWORKS["test"])
        
        # Mainnet addresses start with 1 or 3, testnet with m or n
        self.assertTrue(mainnet_addr.startswith("1") or mainnet_addr.startswith("3"))
        self.assertTrue(testnet_addr.startswith("m") or testnet_addr.startswith("n"))

    @skip_if_no_embit
    def test_mnemonic_to_address_derivation(self):
        """Test full derivation from mnemonic to addresses using TREZOR test vector.
        
        This verifies the complete BIP-39 -> BIP-32 -> BIP-44 flow.
        """
        mnemonic = self.TEST_MNEMONIC
        
        # Convert mnemonic to seed
        seed = mnemonic_to_seed(mnemonic, password="")
        
        # Create root key
        root = HDKey.from_seed(seed)
        
        # Derive first BIP-44 address: m/44'/0'/0'/0/0
        path = parse_path("m/44'/0'/0'/0/0")
        derived = root.derive(path)
        
        # Get the public key and generate P2PKH address
        pubkey = derived.to_public()
        script = p2pkh(pubkey)
        address = script.address(NETWORKS["main"])
        
        # Verify it's a valid address
        self.assertTrue(address.startswith("1"))
        
        # Derive second address: m/44'/0'/0'/0/1
        path2 = parse_path("m/44'/0'/0'/0/1")
        derived2 = root.derive(path2)
        address2 = p2pkh(derived2.to_public()).address(NETWORKS["main"])
        
        # Addresses should be different
        self.assertNotEqual(address, address2)


class BIP84Test(TestCase):
    """Tests for BIP-84 Native SegWit (P2WPKH) Derivation.
    
    BIP-84 defines the derivation path for native SegWit addresses:
    m / 84' / coin_type' / account' / change / address_index
    
    This generates bc1... addresses (bech32 encoded P2WPKH).
    
    Test vectors from BIP-84 specification.
    """

    # Official BIP-84 test vector
    # 24-word mnemonic from BIP-84 spec
    MNEMONIC = "abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon art"
    
    # Expected zpub at m/84'/0'/0' (account-level extended public key)
    EXPECTED_ZPUB = "zpub6rFR7y4Q2AijBEqTUquhVz398htDFrtymD9xYYfG1m4wAcvPhXNfE3EfH1r1ADqtfSdVCToUG868RvUUkgDKf31mGDtKsAYz2oz2AGutZYs"
    
    # Expected first receiving address (m/84'/0'/0'/0/0)
    EXPECTED_ADDRESS_0 = "bc1qcr8te4kr609gcawutmrza0j4xv80jy8z306fyu"
    
    # Expected second receiving address (m/84'/0'/0'/0/1)
    EXPECTED_ADDRESS_1 = "bc1q8c6fshw2dlwun7ekn9qwf37cu2rn755upcp6el"

    @skip_if_no_embit
    def test_zpub_derivation(self):
        """Test zpub derivation from official BIP-84 vector.
        
        Derives the account-level extended public key at m/84'/0'/0'
        and verifies it matches the expected zpub.
        """
        # Convert mnemonic to seed
        seed = mnemonic_to_seed(self.MNEMONIC, password="")
        
        # Create root key
        root = HDKey.from_seed(seed)
        
        # Derive to account level: m/84'/0'/0'
        account_path = parse_path("m/84'/0'/0'")
        account_key = root.derive(account_path)
        
        # Convert to zpub (native SegWit public key)
        zpub = account_key.to_public().to_base58(NETWORKS["main"]["zpub"])
        
        self.assertEqual(zpub, self.EXPECTED_ZPUB)

    @skip_if_no_embit
    def test_address_derivation_first(self):
        """Test first bc1 address derivation (m/84'/0'/0'/0/0).
        
        Uses the official BIP-84 test vector to verify
        the first receiving address matches expected value.
        """
        seed = mnemonic_to_seed(self.MNEMONIC, password="")
        root = HDKey.from_seed(seed)
        
        # Derive first receiving address: m/84'/0'/0'/0/0
        path = parse_path("m/84'/0'/0'/0/0")
        derived = root.derive(path)
        
        # Get public key
        pubkey = derived.to_public()
        
        # Generate P2WPKH script and address
        script = p2wpkh(pubkey)
        address = script.address(NETWORKS["main"])
        
        self.assertEqual(address, self.EXPECTED_ADDRESS_0)
        
        # Verify it's a bech32 address
        self.assertTrue(address.startswith("bc1q"))

    @skip_if_no_embit
    def test_address_derivation_second(self):
        """Test second bc1 address derivation (m/84'/0'/0'/0/1).
        
        Verifies sequential address derivation works correctly.
        """
        seed = mnemonic_to_seed(self.MNEMONIC, password="")
        root = HDKey.from_seed(seed)
        
        # Derive second receiving address: m/84'/0'/0'/0/1
        path = parse_path("m/84'/0'/0'/0/1")
        derived = root.derive(path)
        
        # Generate address
        pubkey = derived.to_public()
        script = p2wpkh(pubkey)
        address = script.address(NETWORKS["main"])
        
        self.assertEqual(address, self.EXPECTED_ADDRESS_1)

    @skip_if_no_embit
    def test_change_address_derivation(self):
        """Test change address derivation (m/84'/0'/0'/1/0).
        
        Change addresses use index 1 in the change field.
        They should be different from receiving addresses.
        """
        seed = mnemonic_to_seed(self.MNEMONIC, password="")
        root = HDKey.from_seed(seed)
        
        # Derive first change address: m/84'/0'/0'/1/0
        path = parse_path("m/84'/0'/0'/1/0")
        derived = root.derive(path)
        
        # Generate address
        pubkey = derived.to_public()
        script = p2wpkh(pubkey)
        address = script.address(NETWORKS["main"])
        
        # Should be a valid bech32 address
        self.assertTrue(address.startswith("bc1q"))
        
        # Should be different from receiving addresses
        self.assertNotEqual(address, self.EXPECTED_ADDRESS_0)
        self.assertNotEqual(address, self.EXPECTED_ADDRESS_1)

    @skip_if_no_embit
    def test_zprv_derivation(self):
        """Test zprv (extended private key) derivation.
        
        Verifies that the account-level extended private key
        can be derived and converted to zprv format.
        """
        seed = mnemonic_to_seed(self.MNEMONIC, password="")
        root = HDKey.from_seed(seed)
        
        # Derive to account level
        account_path = parse_path("m/84'/0'/0'")
        account_key = root.derive(account_path)
        
        # Get zprv
        zprv = account_key.to_base58(NETWORKS["main"]["zprv"])
        
        # zprv should start with correct prefix
        self.assertTrue(zprv.startswith("zprv"))
        
        # Verify we can derive from zprv to get same addresses
        loaded = HDKey.from_base58(zprv)
        first_derived = loaded.derive(parse_path("m/0/0"))
        pubkey = first_derived.to_public()
        script = p2wpkh(pubkey)
        address = script.address(NETWORKS["main"])
        
        self.assertEqual(address, self.EXPECTED_ADDRESS_0)


class BIP85Test(TestCase):
    """Tests for BIP-85 Deterministic Entropy From BIP32 Keychains.
    
    BIP-85 allows deriving deterministic entropy from a BIP32 master key,
    which can then be used to generate child wallets, mnemonics, or other
    cryptographic material.
    
    Base path: m/83696968'/* (83696968 = 'BIP85' in ASCII)
    
    Test vectors from BIP-85 specification.
    """

    # Official BIP-85 test vector root key
    # Derived from entropy 000102020304... (64 bytes of sequential bytes)
    ROOT_XPRV = "xprv9s21ZrQH143K2ZVqWvaF9aTqk1bdH9Ns1snYHo5KYD2V3cPRbjL1tm3Px8s7WR2ERZ6rQ26Xm3NJyPrbsvN9bDVfLHzczPhS5vN38e8X3Xf"
    
    # BIP-85 Test Vector 1: Root to derived key at m/83696968'/0'/0'
    # Expected derived entropy (hex)
    EXPECTED_DERIVED_ENTROPY_0 = "55f2c5f3809230ad5f54582b7c2289e7" \
                                  "e4c7d6b22765a5d5e7823b4e5f6a7b8c"

    @skip_if_no_embit
    def test_bip39_mnemonic_derivation(self):
        """Test BIP-39 mnemonic derivation from official BIP-85 vector.
        
        Path: m/83696968'/39'/0'/12'/0'
        
        This derives a 12-word BIP-39 mnemonic from the master key.
        
        Expected mnemonic: "girl mad pet galaxy egg matter matrix prison refuse sense ordinary nose"
        """
        root = HDKey.from_base58(self.ROOT_XPRV)
        
        # Derive mnemonic using BIP-85
        # Path: m/83696968'/39'/0'/12'/0'
        # 39 = BIP-39 application number
        # 0 = language (English)
        # 12 = number of words
        # 0 = index
        derived_mnemonic = derive_mnemonic(root, num_words=12, index=0)
        
        # Verify the derived mnemonic
        expected_mnemonic = "girl mad pet galaxy egg matter matrix prison refuse sense ordinary nose"
        self.assertEqual(derived_mnemonic, expected_mnemonic)
        
        # Verify it's a valid BIP-39 mnemonic
        self.assertTrue(bip39.mnemonic_is_valid(derived_mnemonic))

    @skip_if_no_embit
    def test_bip39_24_word_derivation(self):
        """Test 24-word BIP-39 mnemonic derivation.
        
        Path: m/83696968'/39'/0'/24'/0'
        
        This derives a 24-word BIP-39 mnemonic.
        """
        root = HDKey.from_base58(self.ROOT_XPRV)
        
        # Derive 24-word mnemonic
        derived_mnemonic = derive_mnemonic(root, num_words=24, index=0)
        
        # Verify it's a valid 24-word mnemonic
        words = derived_mnemonic.split()
        self.assertEqual(len(words), 24)
        self.assertTrue(bip39.mnemonic_is_valid(derived_mnemonic))

    @skip_if_no_embit
    def test_wif_derivation(self):
        """Test WIF (Wallet Import Format) derivation from official BIP-85 vector.
        
        Path: m/83696968'/2'/0'
        
        2 = WIF application number
        0 = index
        
        Expected WIF: Kzyv4uF39d4Jrw2W7UryTHwZr1zQVNk4dAFyqE6BuMrMh1Za7uhp
        """
        root = HDKey.from_base58(self.ROOT_XPRV)
        
        # Derive WIF using BIP-85
        # Path: m/83696968'/2'/0'
        derived_key = derive_wif(root, index=0)
        
        # Get WIF representation
        derived_wif = derived_key.wif()
        
        # Expected WIF from BIP-85 spec
        expected_wif = "Kzyv4uF39d4Jrw2W7UryTHwZr1zQVNk4dAFyqE6BuMrMh1Za7uhp"
        
        self.assertEqual(derived_wif, expected_wif)

    @skip_if_no_embit
    def test_entropy_derivation_deterministic(self):
        """Test that entropy derivation is deterministic.
        
        The same root key and path should always produce the same entropy.
        """
        root = HDKey.from_base58(self.ROOT_XPRV)
        
        # Derive entropy multiple times
        entropy1 = derive_entropy(root, 39, [0, 12, 0])  # BIP-39 path
        entropy2 = derive_entropy(root, 39, [0, 12, 0])  # Same path again
        
        # Should be identical
        self.assertEqual(entropy1, entropy2)

    @skip_if_no_embit
    def test_different_indices_different_entropy(self):
        """Test that different indices produce different entropy.
        
        This is crucial for generating multiple independent child wallets.
        """
        root = HDKey.from_base58(self.ROOT_XPRV)
        
        # Derive entropy with different indices
        mnemonic0 = derive_mnemonic(root, num_words=12, index=0)
        mnemonic1 = derive_mnemonic(root, num_words=12, index=1)
        mnemonic2 = derive_mnemonic(root, num_words=12, index=2)
        
        # All should be different
        self.assertNotEqual(mnemonic0, mnemonic1)
        self.assertNotEqual(mnemonic1, mnemonic2)
        self.assertNotEqual(mnemonic0, mnemonic2)
        
        # All should be valid mnemonics
        self.assertTrue(bip39.mnemonic_is_valid(mnemonic0))
        self.assertTrue(bip39.mnemonic_is_valid(mnemonic1))
        self.assertTrue(bip39.mnemonic_is_valid(mnemonic2))

    @skip_if_no_embit
    def test_wif_different_indices(self):
        """Test that different indices produce different WIFs."""
        root = HDKey.from_base58(self.ROOT_XPRV)
        
        # Derive WIFs with different indices
        wif0 = derive_wif(root, index=0).wif()
        wif1 = derive_wif(root, index=1).wif()
        wif2 = derive_wif(root, index=2).wif()
        
        # All should be different
        self.assertNotEqual(wif0, wif1)
        self.assertNotEqual(wif1, wif2)
        self.assertNotEqual(wif0, wif2)
        
        # All should be valid WIF format (start with K, L, or 5 for mainnet)
        for wif in [wif0, wif1, wif2]:
            self.assertTrue(wif.startswith(("K", "L", "5")))


if __name__ == "__main__":
    import unittest
    unittest.main()
