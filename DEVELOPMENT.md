# Development Guide

Development documentation for MLG Log Viewer contributors.

## Project Overview

MLG Log Viewer is a Python application for viewing and analyzing TunerStudio MS MegaSquirt `.mlg` (MegaLogViewer) binary log files. The application provides:

- Binary format parsing for MLVLG files
- Native tkinter GUI with data grid, visualization, and statistics
- CSV export functionality
- Column sorting and pagination for large datasets

## Architecture

### Class Structure

```
mlg_log_viewer.py (753 lines)
├── MLGParser (lines 23-175)
│   ├── Binary file parsing
│   ├── MLVLG format handling (big-endian)
│   └── Field type mapping (U08-F32)
├── LogData (lines 178-225)
│   ├── Data model
│   ├── Statistics calculation
│   └── Channel access methods
└── LogViewerApp (lines 228-730)
    ├── GUI application (tkinter)
    ├── Three-tab interface
    ├── Pagination (1000 records/page)
    ├── Column sorting
    └── CSV export
```

### Key Components

**MLGParser**:
- `parse_header()` - Reads 22-byte MLVLG header
- `parse_field_definition()` - Extracts field metadata (55 bytes v1, 89 bytes v2)
- `parse_data_blocks()` - Decodes binary data records
- Field types: U08, S08, U16, S16, U32, S32, S64, F32

**LogData**:
- `get_channel_names()` - List all available channels
- `get_channel_data(name)` - Retrieve values for a channel
- `get_statistics(name)` - Calculate min/max/mean/std
- `get_field_info(name)` - Get units, scale, transform

**LogViewerApp**:
- Menu and toolbar
- Data Grid tab with sorting and pagination
- Visualization tab with matplotlib plots
- Summary tab with file metadata

### File Structure

```
LogViewer/
├── mlg_log_viewer.py       # Main application (production)
├── test_mlg_viewer.py      # Automated unit tests
├── README.md               # User documentation
├── TESTING.md              # Manual testing guide
├── DEVELOPMENT.md          # This file
├── requirements.txt        # Python dependencies
├── .gitignore              # Git exclusions
├── tools/                  # Development utilities
│   ├── debug_mlg.py        # Binary format inspector
│   ├── find_data.py        # Data block locator
│   ├── find_xml_end.py     # XML boundary scanner
│   └── manual_test_parser.py  # Manual parse testing
└── .copilot-tracking/      # RPI agent artifacts (not in git)
```

## Development Setup

### Prerequisites

- **Python**: 3.7 or higher
- **Operating System**: Windows, macOS, or Linux

### Installation

1. Clone repository or extract files
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Verify matplotlib installation:

```bash
python -c "import matplotlib; print('OK')"
```

### Running the Application

**GUI Mode** (default):

```bash
python mlg_log_viewer.py
```

**With File Argument**:

```bash
python mlg_log_viewer.py path/to/logfile.mlg
```

**Expected Result**: Window opens showing log viewer interface.

## Testing

### Automated Unit Tests

Run comprehensive test suite covering parser and data model:

```bash
python -m unittest test_mlg_viewer.py
```

**Auto-discovery** (finds all test_*.py files):

```bash
python -m unittest discover
```

**Specific test class**:

```bash
python -m unittest test_mlg_viewer.TestMLGParser
```

**Single test method**:

```bash
python -m unittest test_mlg_viewer.TestMLGParser.test_parse_header_valid_file
```

**Expected Output**:

```
...............
----------------------------------------------------------------------
Ran 15 tests in 0.025s

OK
```

### Test Coverage

The test suite covers:

- ✅ MLGParser: Header parsing, field definitions, data blocks, byte order
- ✅ Error handling: Invalid formats, truncated files
- ✅ LogData: Channel access, statistics, metadata
- ✅ Integration: Full parse workflow
- ✅ Edge cases: Empty data, boundary conditions

### Manual Testing

For manual exploratory testing and debugging, see [TESTING.md](TESTING.md).

## Debugging Tools

The `tools/` directory contains utilities for analyzing .mlg file structure during development.

### debug_mlg.py

Inspects binary file structure and validates header parsing.

**Usage**:

```bash
python tools/debug_mlg.py MyCar/DataLogs/2025-11-02_15.10.56.mlg
```

**Output**:
- File size
- Header fields (magic, version, timestamp, field count)
- Data start offset calculation
- First data block preview

**Use Cases**:
- Verify file format version
- Diagnose parsing offset issues
- Compare header vs. calculated data start

### find_data.py

Searches for data block signatures when data start offset is unclear.

**Usage**:

```bash
python tools/find_data.py MyCar/DataLogs/2025-11-02_15.10.56.mlg
```

**Output**:
- Potential data block start offsets
- Block type, counter, and timestamp preview
- Hex dump of candidate locations

**Use Cases**:
- Locate data blocks in malformed files
- Debug data offset calculation issues

### find_xml_end.py

Locates XML boundaries and data block transitions.

**Usage**:

```bash
python tools/find_xml_end.py MyCar/DataLogs/2025-11-02_15.10.56.mlg
```

**Output**:
- XML end tags and offsets
- Binary data start after XML
- File structure analysis

**Use Cases**:
- Understand file format variations
- Debug XML/binary boundary parsing

### manual_test_parser.py

Quick manual validation of parser functionality.

**Usage**:

```bash
python tools/manual_test_parser.py MyCar/DataLogs/2025-11-02_15.10.56.mlg
```

**Output**:
- File metadata (timestamp, version, field count)
- First 20 channels
- Sample statistics (RPM, MAP, TPS, AFR)
- First 5 records

**Use Cases**:
- Quick sanity check after parser changes
- Verify specific .mlg files are readable
- Compare multiple log files

## Code Style

### Conventions

Follow PEP 8 style guidelines:

- **Indentation**: 4 spaces (no tabs)
- **Line length**: 100 characters maximum (docstrings and comments)
- **Naming**:
  - Classes: `PascalCase` (e.g., `MLGParser`, `LogData`)
  - Functions/methods: `snake_case` (e.g., `parse_header()`, `get_channel_data()`)
  - Constants: `UPPER_SNAKE_CASE` (e.g., `PAGE_SIZE`, `MAX_RECORDS`)
  - Private methods: `_leading_underscore` (e.g., `_sort_column`)

### Type Hints

Add type hints to new methods:

```python
def parse_header(self) -> Dict[str, Any]:
    """Parse MLG file header."""
    ...

def get_channel_names(self) -> List[str]:
    """Return list of channel names."""
    ...
```

### Docstrings

Use docstring format for public methods:

```python
def method_name(self, param: type) -> return_type:
    """
    Brief description on one line.
    
    Longer explanation if needed. Describe parameters,
    return values, and any exceptions raised.
    
    Args:
        param: Description of parameter
    
    Returns:
        Description of return value
    
    Raises:
        ValueError: When input is invalid
    """
```

## Adding Features

### Workflow

1. **Research**: Understand requirements and existing patterns
2. **Design**: Plan changes without breaking existing functionality
3. **Test**: Write unit tests first (TDD approach)
4. **Implement**: Make code changes
5. **Validate**: Run tests and manual verification
6. **Document**: Update README.md or DEVELOPMENT.md

### Adding Parser Support

To add support for new field types:

1. Update `FIELD_TYPES` dictionary in `MLGParser` class
2. Add struct format and byte size
3. Update `parse_field_definition()` if needed
4. Add test case in `test_mlg_viewer.py`

### Adding GUI Features

To add new GUI functionality:

1. Locate appropriate class method in `LogViewerApp`
2. Follow existing patterns (menu → toolbar → handler)
3. Update `create_menu()`, `create_toolbar()`, or tab methods
4. Test with multiple file sizes

### Adding Statistics

To add new statistical calculations:

1. Extend `get_statistics()` in `LogData` class
2. Use numpy if available, fallback to pure Python
3. Add test case with known values
4. Update Summary tab if displaying in GUI

## Common Issues

### Import Errors

**Problem**: `ModuleNotFoundError: No module named 'matplotlib'`

**Solution**:

```bash
pip install matplotlib
```

### Parser Failures

**Problem**: `ValueError: Invalid file format`

**Solution**:
- Verify file is valid .mlg from TunerStudio MS
- Use `tools/debug_mlg.py` to inspect header
- Check file not corrupted or truncated

### Test Failures

**Problem**: Unit tests failing after code changes

**Solution**:
1. Run specific failing test: `python -m unittest test_mlg_viewer.TestMLGParser.test_name`
2. Read assertion error message
3. Use debug print statements in test
4. Verify mock data matches expected format

### GUI Not Responding

**Problem**: Application hangs during file load

**Solution**:
- Check file size (large files take time)
- Verify file within MAX_RECORDS limit (100,000)
- Use file size validation in `open_file()` method
- Monitor memory usage

## Performance Optimization

### Large Files

- Current limit: 100,000 records (MAX_RECORDS)
- Pagination: 1000 records per page (PAGE_SIZE)
- Memory: Files loaded entirely into memory

### Tuning Constants

Modify class constants to adjust behavior:

```python
class MLGParser:
    MAX_RECORDS = 100000  # Parser record limit

class LogViewerApp:
    PAGE_SIZE = 1000      # Records per page
    MAX_FILE_SIZE_MB = 500  # File size warning threshold
```

## Contributing

### Before Committing

1. Run unit tests: `python -m unittest discover`
2. Verify application launches: `python mlg_log_viewer.py`
3. Test with sample .mlg file
4. Check for syntax errors: `python -m py_compile mlg_log_viewer.py`

### Commit Messages

Follow Conventional Commits format:

```
feat: add new feature description
fix: resolve specific bug
test: add unit tests for feature
docs: update documentation
refactor: restructure code without behavior change
```

See [commit-message.instructions.md](c:\Users\mkfn4\.vscode-insiders\extensions\ise-hve-essentials.hve-core-3.0.2\.github\instructions\hve-core\commit-message.instructions.md) for details.

## Resources

- **Python unittest**: https://docs.python.org/3/library/unittest.html
- **matplotlib**: https://matplotlib.org/stable/api/index.html
- **tkinter**: https://docs.python.org/3/library/tkinter.html
- **TunerStudio MS**: Refer to official documentation for .mlg format specifications

## Questions and Support

For issues related to:
- **Parser logic**: Check `tools/debug_mlg.py` output, review MLVLG format
- **GUI behavior**: Test with minimal data, check tkinter event loop
- **Test failures**: Run specific test, add debug output, verify mock data
- **Performance**: Profile with large files, check memory usage, adjust constants
