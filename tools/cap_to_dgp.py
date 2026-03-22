#!/usr/bin/env python3
"""Convert JavaCard CAP file to DGP format for Specter-DIY.

DGP format is the CAP components concatenated in GlobalPlatform order,
excluding Descriptor.cap which is optional.

Usage:
    python cap_to_dgp.py input.cap output.dgp
"""

import sys
import zipfile
import hashlib

# GP component order (tags 1-9, excluding Descriptor which is tag 10)
# See GlobalPlatform Card Specification v2.3
COMPONENT_ORDER = [
    "Header.cap",      # tag 1
    "Directory.cap",   # tag 2
    "Applet.cap",      # tag 3
    "Import.cap",      # tag 4
    "ConstantPool.cap", # tag 5
    "Class.cap",       # tag 6
    "Method.cap",      # tag 7
    "StaticField.cap", # tag 8
    "RefLocation.cap", # tag 9
    # Descriptor.cap (tag 10) - excluded
]

def find_component_path(zf, component_name):
    """Find the path to a component in the CAP zip."""
    for name in zf.namelist():
        if name.endswith(component_name):
            return name
    return None

def cap_to_dgp(cap_path, dgp_path):
    """Convert CAP file to DGP format."""
    print(f"Converting {cap_path} to DGP format...")
    
    with zipfile.ZipFile(cap_path, 'r') as zf:
        components = []
        total_size = 0
        
        for comp_name in COMPONENT_ORDER:
            path = find_component_path(zf, comp_name)
            if path is None:
                print(f"  WARNING: {comp_name} not found in CAP")
                continue
            
            data = zf.read(path)
            components.append(data)
            total_size += len(data)
            print(f"  {comp_name}: {len(data)} bytes")
        
        # Check for Descriptor.cap (optional, excluded from DGP)
        desc_path = find_component_path(zf, "Descriptor.cap")
        if desc_path:
            desc_data = zf.read(desc_path)
            print(f"  Descriptor.cap: {len(desc_data)} bytes (excluded from DGP)")
        
        # Concatenate all components
        dgp_data = b''.join(components)
        
        # Calculate SHA256
        sha256 = hashlib.sha256(dgp_data).hexdigest()
        
        print(f"\nDGP size: {len(dgp_data)} bytes")
        print(f"SHA256: {sha256}")
        
        # Write DGP file
        with open(dgp_path, 'wb') as f:
            f.write(dgp_data)
        
        print(f"Written to {dgp_path}")
        
        # Extract package AID from Header for reference
        if len(dgp_data) >= 10 and dgp_data[0] == 0x01:
            # Header tag is 0x01
            # Magic at offset 3-4 is 0xDE 0xCA
            if dgp_data[3:5] == b'\xDE\xCA':
                flags = dgp_data[7]
                if flags & 0x01:
                    aid_len_offset = 12
                else:
                    aid_len_offset = 8
                
                aid_len = dgp_data[aid_len_offset]
                aid = dgp_data[aid_len_offset + 1:aid_len_offset + 1 + aid_len]
                print(f"Package AID: {aid.hex()} ({aid_len} bytes)")
        
        return sha256

def main():
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} input.cap output.dgp")
        sys.exit(1)
    
    cap_path = sys.argv[1]
    dgp_path = sys.argv[2]
    
    cap_to_dgp(cap_path, dgp_path)

if __name__ == "__main__":
    main()
