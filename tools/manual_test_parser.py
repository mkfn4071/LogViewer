import sys
sys.path.insert(0, '.')

from mlg_log_viewer import MLGParser, LogData

def test_parser(file_path):
    print(f"Testing {file_path}\n")
    print("=" * 70)
    
    parser = MLGParser(file_path)
    result = parser.parse()
    log_data = LogData(result)
    
    print(f"File: {log_data.filename}")
    print(f"Timestamp: {log_data.file_timestamp}")
    print(f"Format Version: {log_data.format_version}")
    print(f"Fields: {log_data.field_count}")
    print(f"Records: {log_data.record_count}")
    
    print(f"\nFirst 20 channels:")
    for i, name in enumerate(log_data.get_channel_names()[:20]):
        info = log_data.get_field_info(name)
        print(f"  {i+1}. {name:20s} ({info['units']})")
    
    # Show statistics for a few interesting channels
    test_channels = ['RPM', 'MAP', 'TPS', 'AFR', 'Boost psi']
    print(f"\nSample statistics:")
    for ch in test_channels:
        if ch in log_data.get_channel_names():
            stats = log_data.get_statistics(ch)
            info = log_data.get_field_info(ch)
            print(f"  {ch:15s}: min={stats['min']:8.2f}  max={stats['max']:8.2f}  mean={stats['mean']:8.2f}  ({info['units']})")
    
    # Show first 5 records
    if log_data.record_count > 0:
        print(f"\nFirst 5 records sample (first 10 fields):")
        for i in range(min(5, log_data.record_count)):
            rec = log_data.records[i]
            values = []
            for name in list(rec.keys())[:10]:
                values.append(f"{rec[name]:.1f}")
            print(f"  Record {i+1}: {', '.join(values)}")
    
    print("=" * 70)
    print()

if __name__ == "__main__":
    if len(sys.argv) > 1:
        for file_path in sys.argv[1:]:
            test_parser(file_path)
    else:
        # Test multiple files
        files = [
            "MyCar\\DataLogs\\2025-11-02_15.10.56.mlg",
            "MyCar\\DataLogs\\2025-11-02_21.45.31.mlg"
        ]
        for f in files:
            test_parser(f)
