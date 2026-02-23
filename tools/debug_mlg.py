import struct
import sys

def debug_mlg_file(file_path):
    with open(file_path, 'rb') as f:
        data = f.read()
    
    print(f"Total file size: {len(data)} bytes\n")
    
    # Parse header with big-endian (version 2 seems right)
    offset = 0
    magic = data[offset:offset+6].decode('utf-8', errors='ignore')
    offset += 6
    
    print(f"Magic: {magic}")
    
    version = struct.unpack_from('>h', data, offset)[0]
    offset += 2
    print(f"Version: {version}")
    
    timestamp = struct.unpack_from('>i', data, offset)[0]
    offset += 4
    print(f"Timestamp: {timestamp}")
    
    info_start = struct.unpack_from('>h', data, offset)[0]
    offset += 2
    print(f"Info data start: {info_start}")
    
    data_begin_header = struct.unpack_from('>i', data, offset)[0]
    offset += 4
    
    record_length = struct.unpack_from('>h', data, offset)[0]
    offset += 2
    print(f"Record length: {record_length}")
    
    num_fields = struct.unpack_from('>h', data, offset)[0]
    offset += 2
    print(f"Number of fields: {num_fields}")
    
    print(f"\nHeader size: 22 bytes")
    print(f"Field definition size for v{version}: {89 if version == 2 else 55} bytes each")
    print(f"Total field section: {num_fields} * {89 if version == 2 else 55} = {num_fields * (89 if version == 2 else 55)} bytes")
    
    # Calculate where data should actually start
    calculated_data_start = 22 + (num_fields * (89 if version == 2 else 55))
    print(f"\nCalculated data start: {calculated_data_start}")
    print(f"Header data_begin value: {data_begin_header} (likely wrong)")
    
    # Use calculated value
    data_begin_index = calculated_data_start
    
    if data_begin_index < len(data):
        print(f"\nAt calculated offset ({data_begin_index}):")
        print(f"Bytes remaining: {len(data) - data_begin_index}")
        print(f"First 40 bytes: {data[data_begin_index:data_begin_index+40].hex(' ')}")
        
        # Try to parse first block with big-endian
        try:
            block_type = struct.unpack_from('>b', data, data_begin_index)[0]
            counter = struct.unpack_from('>B', data, data_begin_index+1)[0]
            timestamp_ms = struct.unpack_from('>H', data, data_begin_index+2)[0]
            
            print(f"\nFirst block (BE):")
            print(f"  Type: {block_type}")
            print(f"  Counter: {counter}")
            print(f"  Timestamp: {timestamp_ms} ms")
            
            # Try little-endian too
            block_type_le = struct.unpack_from('<b', data, data_begin_index)[0]
            timestamp_ms_le = struct.unpack_from('<H', data, data_begin_index+2)[0]
            
            print(f"\nFirst block (LE):")
            print(f"  Type: {block_type_le}")
            print(f"  Timestamp: {timestamp_ms_le} ms")
        except:
            print("Error parsing first block")
    else:
        print(f"\nCalculated data start {data_begin_index} is beyond file size!")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        debug_mlg_file(sys.argv[1])
    else:
        print("Usage: python debug_mlg.py <file.mlg>")
