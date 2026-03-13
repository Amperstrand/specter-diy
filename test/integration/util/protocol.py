"""
Command Protocol Mapper for HIL Testing.

Translates SimController's dual-channel protocol (USB + GUI) into
TestMode's single-channel protocol (TEST_* commands over UART).

SimController Protocol:
- USB channel: Binary commands like "sign <psbt>", "xpub <path>", etc.
- GUI channel: JSON-serialized values (True, False, numbers, strings)

TestMode Protocol:
- Single UART channel with text commands: TEST_SIGN:, TEST_XPUB:, TEST_UI_SET:, etc.
- Responses: "OK:<data>" or "ERROR:<message>"
"""

from typing import Union, Optional


# ============================================================================
# MAPPING TABLE: USB/GUI commands → TestMode commands
# ============================================================================

# USB command prefixes and their TestMode equivalents
# Format: (usb_prefix, testmode_prefix, requires_arg)
# Note: "sign" is handled specially due to PSBT-to-sighash conversion requirement
USB_COMMAND_MAP = {
    # Key management
    "xpub": ("TEST_XPUB:", True),       # xpub m/44h/1h/0h → TEST_XPUB:m/44h/1h/0h
    "fingerprint": ("TEST_STATUS", False),  # fingerprint → TEST_STATUS (fingerprint in response)
    
    # Wallet management - limited support in TestMode
    "addwallet": (None, True),          # Not directly supported
    "bitcoin:": (None, True),           # Address lookup not directly supported
}

# GUI command types and their TestMode equivalents
# These are Python values sent via GUI channel
GUI_COMMAND_MAP = {
    # Boolean confirmations → TEST_UI_SET with confirm/cancel
    True: "TEST_UI_SET:confirm",
    False: "TEST_UI_SET:cancel",
    
    # None is used for "no action needed" or screen advance
    None: "TEST_UI_SET:continue",
    
    # String and numeric values passed through
    # Handled dynamically in map_gui_command()
}


class CommandMapperError(Exception):
    """Raised when a command cannot be mapped."""
    pass


class CommandMapper:
    """
    Maps SimController dual-channel commands to TestMode single-channel commands.
    
    SimController uses two channels:
    1. USB: Binary commands (e.g., b"sign <psbt>")
    2. GUI: JSON values (e.g., True, False, "1234", 1)
    
    TestMode uses single UART channel:
    - TEST_* commands with text arguments
    - Responses in "OK:data" or "ERROR:message" format
    """
    
    def __init__(self):
        """Initialize the command mapper."""
        self._usb_map = USB_COMMAND_MAP
        self._gui_map = GUI_COMMAND_MAP
    
    def map_usb_command(self, data: bytes) -> str:
        """
        Convert USB binary command to TEST_* string command.
        
        Args:
            data: USB command bytes (e.g., b"xpub m/44h/1h/0h")
            
        Returns:
            TestMode command string (e.g., "TEST_XPUB:m/44h/1h/0h")
            
        Raises:
            CommandMapperError: If command cannot be mapped
            
        Examples:
            >>> mapper = CommandMapper()
            >>> mapper.map_usb_command(b"xpub m/44h/1h/0h")
            'TEST_XPUB:m/44h/1h/0h'
            >>> mapper.map_usb_command(b"fingerprint")
            'TEST_STATUS'
        """
        if isinstance(data, bytes):
            cmd_str = data.decode('utf-8', errors='replace').strip()
        else:
            cmd_str = str(data).strip()
        
        # Remove trailing \r\n if present
        cmd_str = cmd_str.rstrip('\r\n')
        
        # Special case: "sign" command needs PSBT-to-sighash conversion
        # The USB protocol sends PSBT base64, but TestMode expects hex sighash
        if cmd_str.startswith("sign "):
            # Extract PSBT data
            psbt_data = cmd_str[5:].strip()
            if not psbt_data:
                raise CommandMapperError(
                    "USB 'sign' command requires PSBT data"
                )
            # TestMode TEST_SIGN expects hex-encoded 32-byte sighash, not PSBT
            # PSBT-to-sighash conversion requires parsing the PSBT structure
            raise CommandMapperError(
                f"USB 'sign' command requires PSBT-to-sighash conversion. "
                f"TestMode expects TEST_SIGN:<hex_sighash> (32 bytes hex). "
                f"Received PSBT: {psbt_data[:30]}..."
            )
        
        # Check each mapped prefix
        for prefix, (testmode_prefix, requires_arg) in self._usb_map.items():
            if cmd_str.startswith(prefix):
                if testmode_prefix is None:
                    raise CommandMapperError(
                        f"USB command '{prefix}' is not supported in TestMode. "
                        f"Original command: {cmd_str[:50]}..."
                    )
                
                if requires_arg:
                    # Extract argument after prefix
                    arg = cmd_str[len(prefix):].strip()
                    if not arg:
                        raise CommandMapperError(
                            f"USB command '{prefix}' requires an argument"
                        )
                    return f"{testmode_prefix}{arg}"
                else:
                    # No argument needed
                    return testmode_prefix
        # Unknown command
        raise CommandMapperError(
            f"Unknown USB command: {cmd_str[:50]}{'...' if len(cmd_str) > 50 else ''}"
        )
    
    def map_gui_command(self, command: Union[bool, int, str, None]) -> str:
        """
        Convert GUI JSON command to TEST_UI_* string command.
        
        Args:
            command: GUI value (True, False, int, str, or None)
            
        Returns:
            TestMode UI command string (e.g., "TEST_UI_SET:confirm")
            
        Raises:
            CommandMapperError: If command cannot be mapped
            
        Examples:
            >>> mapper = CommandMapper()
            >>> mapper.map_gui_command(True)
            'TEST_UI_SET:confirm'
            >>> mapper.map_gui_command(False)
            'TEST_UI_SET:cancel'
            >>> mapper.map_gui_command("1234")
            'TEST_UI_PIN:1234'
        """
        # Check explicit mappings first (only for bool and None types in map)
        if command is True or command is False or command is None:
            return self._gui_map[command]
        
        # Handle PIN entry (string of digits)
        if isinstance(command, str):
            if command.isdigit():
                return f"TEST_UI_PIN:{command}"
            # Generic string value
            return f"TEST_UI_SET:{command}"
        
        # Handle numeric values
        if isinstance(command, int):
            return f"TEST_UI_SET:{command}"
        
        # Handle float values
        if isinstance(command, float):
            return f"TEST_UI_SET:{command}"
        
        # Unknown type
        raise CommandMapperError(
            f"Cannot map GUI command of type {type(command).__name__}: {command!r}"
        )
    
    def parse_response(self, response: str) -> bytes:
        """
        Parse TestMode response into format tests expect.
        
        TestMode responses:
        - "OK:<data>" → success with data
        - "ERROR:<message>" → error with message
        
        Tests expect:
        - bytes response (e.g., b"tpub..." or b"error: User cancelled")
        
        Args:
            response: TestMode response string
            
        Returns:
            bytes in format expected by tests
            
        Examples:
            >>> mapper = CommandMapper()
            >>> mapper.parse_response("OK:tpubDC5FSnBiZDMm...")
            b'tpubDC5FSnBiZDMm...'
            >>> mapper.parse_response("ERROR:User cancelled")
            b'error: User cancelled'
        """
        if not response:
            return b""
        
        response = response.strip()
        
        if response.startswith("OK:"):
            # Success - return data after "OK:"
            data = response[3:]
            return data.encode('utf-8')
        
        elif response.startswith("ERROR:"):
            # Error - convert to test-expected format
            message = response[6:]
            return f"error: {message}".encode('utf-8')
        
        else:
            # Unknown format - return as-is
            return response.encode('utf-8')
    
    def is_command_supported(self, usb_data: bytes) -> bool:
        """
        Check if a USB command is supported in TestMode.
        
        Args:
            usb_data: USB command bytes
            
        Returns:
            True if command can be mapped, False otherwise
        """
        try:
            self.map_usb_command(usb_data)
            return True
        except CommandMapperError:
            return False
    
    def get_supported_usb_commands(self) -> list[str]:
        """
        Get list of supported USB command prefixes.
        
        Returns:
            List of USB command prefixes that can be mapped
        """
        return [
            prefix for prefix, (testmode, _) in self._usb_map.items() 
            if testmode is not None
        ]
    
    def get_supported_testmode_commands(self) -> list[str]:
        """
        Get list of TestMode commands this mapper can generate.
        
        Returns:
            List of TEST_* command prefixes
        """
        commands = set()
        for testmode_prefix, _ in self._usb_map.values():
            if testmode_prefix:
                # Extract base command (e.g., "TEST_XPUB" from "TEST_XPUB:")
                base = testmode_prefix.rstrip(':')
                commands.add(base)
        
        # Add GUI commands
        commands.add("TEST_UI_SET")
        commands.add("TEST_UI_PIN")
        
        return sorted(commands)


# ============================================================================
# Convenience functions
# ============================================================================

def map_query(usb_data: bytes, gui_commands: Optional[list[Union[bool, int, str, None]]] = None) -> list[str]:
    """
    Map a complete SimController.query() call to TestMode commands.
    
    Args:
        usb_data: USB command bytes
        gui_commands: List of GUI commands (optional)
        
    Returns:
        List of TestMode commands to send in sequence
        
    Raises:
        CommandMapperError: If any command cannot be mapped
    """
    mapper = CommandMapper()
    commands = []
    
    # Map USB command
    commands.append(mapper.map_usb_command(usb_data))
    
    # Map GUI commands
    if gui_commands:
        for gui_cmd in gui_commands:
            commands.append(mapper.map_gui_command(gui_cmd))
    
    return commands
