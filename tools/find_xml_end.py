import sys

def find_xml_end(file_path):
    with open(file_path, 'rb') as f:
        data = f.read()
    
    print(f"Total file size: {len(data)} bytes\n")
    
    # Look for XML closing tags
    xml_start = data.find(b'<', 28680)
    xml_end_patterns = [b'</MegaTune>', b'</msq>', b'</constants>']
    
    print(f"XML appears to start at: {xml_start}")
    
    for pattern in xml_end_patterns:
        pos = data.find(pattern)
        if pos != -1:
            print(f"Found {pattern.decode()} at offset: {pos}")
            # Show what comes after
            after_xml = pos + len(pattern)
            print(f"\n100 bytes after XML end ({after_xml}):")
            print(data[after_xml:after_xml+100].hex(' '))
            
            # Try a few offsets to find binary data start
            for test_offset in range(after_xml, after_xml + 100):
                byte = data[test_offset]
                if byte == 0 or byte == 1:
                    print(f"\nPotential data block at {test_offset}:")
                    print(f"  Bytes: {data[test_offset:test_offset+20].hex(' ')}")
            break
    
    # Also check file structure
    print(f"\nLast 100 bytes of file:")
    print(data[-100:].hex(' '))

if __name__ == "__main__":
    if len(sys.argv) > 1:
        find_xml_end(sys.argv[1])
    else:
        print("Usage: python find_xml_end.py <file.mlg>")
