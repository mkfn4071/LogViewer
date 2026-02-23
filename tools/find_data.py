import struct
import sys

def find_data_blocks(file_path):
    with open(file_path, 'rb') as f:
        data = f.read()
    
    print(f"Total file size: {len(data)} bytes\n")
    
    # Look for possible data block patterns
    # Data blocks start with type (0 or 1), counter, timestamp
    # Let's search for sequences that look like data blocks
    
    print("Searching for potential data block signatures...")
    print("(Looking for byte 0x00 or 0x01 followed by reasonable patterns)\n")
    
    candidates = []
    for i in range(28000, len(data) - 1000, 100):
        byte = data[i]
        if byte == 0 or byte == 1:
            # Check if next bytes look reasonable
            try:
                counter = data[i+1]
                timestamp = struct.unpack_from('>H', data, i+2)[0]
                
                # Timestamps should be relatively small (milliseconds within session)
                if counter < 255 and timestamp < 65535:
                    candidates.append((i, byte, counter, timestamp))
            except:
                pass
    
    print(f"Found {len(candidates)} potential block starts:")
    for i, (offset, block_type, counter, ts) in enumerate(candidates[:20]):
        hex_preview = data[offset:offset+20].hex(' ')
        print(f"  {offset}: type={block_type}, counter={counter}, ts={ts}ms | {hex_preview}")
    
    if candidates:
        print(f"\nMost likely data start: {candidates[0][0]}")
        return candidates[0][0]
    
    return None

if __name__ == "__main__":
    if len(sys.argv) > 1:
        find_data_blocks(sys.argv[1])
    else:
        print("Usage: python find_data.py <file.mlg>")
