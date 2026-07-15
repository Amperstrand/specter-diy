"""
Smartcard Keystore Mixin

Provides common structured test output functionality for smartcard-based keystores.
This includes SeedKeeper, MemoryCard/Satochip, and any future smartcard implementations.
"""

from helpers import (
    test_output, test_output_atr, test_output_card_type,
    test_output_pin_state, test_output_pin_result,
    test_output_mnemonic_loaded, test_output_error,
    test_output_secure_channel,
)


class SmartcardTestMixin:
    """
    Mixin class providing structured test output for smartcard keystores.
    
    Usage:
        class MySmartcardKeystore(SmartcardTestMixin, RAMKeyStore):
            def is_available(cls):
                # ... card detection logic ...
                self._output_card_probe_result(True, atr_bytes, card_type='MyCard')
    """
    
    # Card type name - override in subclass
    CARD_TYPE = "Unknown"
    
    def _output_atr(self, atr_bytes):
        """Output ATR in structured format"""
        test_output_atr(atr_bytes)
        # Also keep BootTrace for backward compatibility
        print(f'[BootTrace][{self.CARD_TYPE}] ATR:', ' '.join('%02X' % b for b in atr_bytes))
    
    def _output_card_probe_result(self, available, atr_bytes=None, reason=None):
        """Output card probe result"""
        if available:
            test_output('probe_result', {'available': True, 'card_type': self.CARD_TYPE})
            print(f'[BootTrace][{self.CARD_TYPE}] is_available = True')
            if atr_bytes:
                self._output_atr(atr_bytes)
        else:
            data = {'available': False}
            if reason:
                data['reason'] = reason
            test_output('probe_result', data)
            if reason:
                print(f'[BootTrace][{self.CARD_TYPE}] is_available = False: {reason}')
    
    def _output_card_detected(self, applet_name=None, aid=None):
        """Output card detection event"""
        test_output_card_type(self.CARD_TYPE, applet_name=applet_name, aid=aid)
        print(f'[BootTrace][{self.CARD_TYPE}] Card detected')
    
    def _output_protocol(self, protocol):
        """Output protocol used (T=0 or T=1)"""
        protocol_name = 'T=1' if 'T1' in str(protocol) or 't1' in str(protocol).lower() else 'T=0'
        test_output('protocol', {'protocol': protocol_name})
        print(f'[BootTrace][{self.CARD_TYPE}] Protocol: {protocol_name}')
    
    def _output_pin_state(self, attempts_remaining=None, attempts_max=None, is_locked=None):
        """Output PIN state"""
        test_output_pin_state(
            attempts_remaining=attempts_remaining,
            attempts_max=attempts_max,
            is_locked=is_locked
        )
        if attempts_remaining is not None:
            print(f'[BootTrace][{self.CARD_TYPE}] PIN attempts remaining:', attempts_remaining)
    
    def _output_pin_success(self):
        """Output successful PIN verification"""
        test_output_pin_result(True)
        print(f'[BootTrace][{self.CARD_TYPE}] PIN verified successfully')
    
    def _output_pin_failure(self, error_message, attempts_left=None):
        """Output failed PIN verification"""
        data = {'error': error_message}
        if attempts_left is not None:
            data['attempts_left'] = attempts_left
        test_output_pin_result(False, error_message)
        print(f'[BootTrace][{self.CARD_TYPE}] PIN failed:', error_message)
    
    def _output_pin_bricked(self):
        """Output card bricked (no more PIN attempts)"""
        test_output_pin_result(False, "Card bricked - no more attempts")
        print(f'[BootTrace][{self.CARD_TYPE}] Card bricked - no more PIN attempts')
    
    def _output_secure_channel_success(self, card_pubkey=None):
        """Output secure channel established"""
        test_output_secure_channel(True, card_pubkey=card_pubkey)
        print(f'[BootTrace][{self.CARD_TYPE}] Secure channel established')
    
    def _output_secure_channel_failure(self, error):
        """Output secure channel failure"""
        test_output_secure_channel(False, error=error)
        print(f'[BootTrace][{self.CARD_TYPE}] Secure channel failed:', error)
    
    def _output_mnemonic_loaded(self, fingerprint=None, secret_id=None, label=None):
        """Output mnemonic loaded successfully"""
        test_output_mnemonic_loaded(
            fingerprint=fingerprint.hex() if isinstance(fingerprint, bytes) else fingerprint,
            secret_id=secret_id,
            label=label
        )
        print(f'[BootTrace][{self.CARD_TYPE}] Mnemonic loaded successfully')
    
    def _output_mnemonic_load_failure(self, error):
        """Output mnemonic load failure"""
        test_output_error('mnemonic_load', error)
        print(f'[BootTrace][{self.CARD_TYPE}] Mnemonic load failed:', error)
    
    def _output_error(self, stage, error):
        """Output generic error"""
        test_output_error(stage, str(error))
        print(f'[BootTrace][{self.CARD_TYPE}] Error in {stage}:', error)
    
    def _output_probe_start(self):
        """Output probe start"""
        test_output('probe_start', {'keystore': self.CARD_TYPE})
        print(f'[BootTrace][{self.CARD_TYPE}] is_available() called')
    
    def _output_probe_failure(self, error):
        """Output probe failure"""
        test_output_error('probe', str(error))
        print(f'[BootTrace][{self.CARD_TYPE}] Probe failed:', error)
    
    def _output_connect_success(self, protocol=None):
        """Output successful connection"""
        if protocol:
            self._output_protocol(protocol)
        print(f'[BootTrace][{self.CARD_TYPE}] Connected')
    
    def _output_connect_failure(self, error):
        """Output connection failure"""
        test_output_error('connect', str(error))
        print(f'[BootTrace][{self.CARD_TYPE}] Connect failed:', type(error).__name__, error)
    
    def _output_applet_select_success(self):
        """Output successful applet selection"""
        test_output('applet_selected', {'applet': self.CARD_TYPE})
        print(f'[BootTrace][{self.CARD_TYPE}] Applet selected')
    
    def _output_applet_select_failure(self, error):
        """Output applet selection failure"""
        test_output_error('applet_select', str(error))
        print(f'[BootTrace][{self.CARD_TYPE}] Applet select failed:', type(error).__name__, error)


# Card type constants for consistency
CARD_TYPE_SEEDKEEPER = "SeedKeeper"
CARD_TYPE_MEMORYCARD = "MemoryCard"
CARD_TYPE_SATOCHIP = "Satochip"
