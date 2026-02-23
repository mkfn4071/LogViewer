# MLG Log Viewer

A Python-based log viewer application for TunerStudio MS MegaSquirt `.mlg` (MegaLogViewer) files. This tool provides a native tkinter GUI for viewing, analyzing, and exporting ECU data logs.

## Features

- **Binary Format Parsing**: Native support for MLVLG (MegaLogViewer) binary format
- **Data Grid View**: Browse log data in structured table format with pagination (1000 records per page)
- **Column Sorting**: Click column headers to sort data (ascending/descending with visual indicators)
- **Visualization**: Interactive matplotlib charts for analyzing individual channels
- **Statistics**: Automatic calculation of min/max/mean/std for all channels
- **CSV Export**: Export log data to CSV format for external analysis
- **File Size Protection**: Warns before loading files >500 MB to prevent memory issues
- **Resource Management**: Proper cleanup of matplotlib figures to prevent memory leaks

## Requirements

- Python 3.7 or higher
- matplotlib

### Installation

1. Ensure Python 3.7+ is installed on your system
2. Install required dependencies:

```bash
pip install matplotlib
```

3. Run the application:

```bash
python mlg_log_viewer.py
```

## Usage

### Opening Log Files

**Via GUI:**
1. Launch the application
2. Click **File → Open** (or use Ctrl+O)
3. Navigate to your log files (typically in `MyCar/DataLogs/`)
4. Select an `.mlg` file and click **Open**

**Via Command Line:**

```bash
python mlg_log_viewer.py path/to/logfile.mlg
```

### Viewing Data

**Data Grid Tab:**
- Browse tables showing all logged channels
- Click column headers to sort data (toggle ascending/descending)
- Use pagination controls to navigate large datasets:
  - **First/Last**: Jump to beginning/end
  - **Previous/Next**: Move one page at a time
  - **Go to Page**: Enter specific page number
- Current page and total pages displayed at bottom

**Visualization Tab:**
- Select a channel from the dropdown menu
- Click **Plot Channel** to display line chart
- Use matplotlib toolbar for:
  - Pan and zoom
  - Save plot to image file
  - Configure plot settings
- Statistics (min/max/mean/std) displayed below plot

**Summary Tab:**
- Overview of log file metadata:
  - Filename and path
  - Total records count
  - Number of channels
  - Complete channel list

### Exporting Data

1. Open a log file
2. Click **File → Export CSV** (or use Ctrl+E)
3. Choose save location and filename
4. CSV file created with headers and all records

### Keyboard Shortcuts

- **Ctrl+O**: Open log file
- **Ctrl+E**: Export to CSV
- **Ctrl+Q**: Quit application

## File Format

The application reads TunerStudio MS `.mlg` files in MLVLG binary format:

- **Header**: Magic string "MLVLG", format version, timestamp
- **Field Definitions**: Channel metadata (name, units, data type, scale/transform)
- **Data Blocks**: Binary data records in big-endian byte order

Supported data types:
- U08, S08: Unsigned/signed 8-bit integers
- U16, S16: Unsigned/signed 16-bit integers
- U32, S32: Unsigned/signed 32-bit integers
- F32: 32-bit floating point

## Performance Considerations

- Files are loaded entirely into memory for fast access
- Pagination limits displayed records to 1000 per page
- Maximum record limit: 100,000 (configurable in code)
- Files >500 MB trigger confirmation dialog before loading

## Troubleshooting

### "Failed to load file: Invalid file format"
- Verify file is a valid `.mlg` file from TunerStudio MS
- Check file is not corrupted or truncated
- Ensure file starts with "MLVLG" magic string

### "File Access Error: Could not access file"
- Check file permissions
- Ensure file is not locked by another application
- Verify file path exists

### Application Hangs During Load
- Large files may take time to parse
- Monitor memory usage (Task Manager/Activity Monitor)
- Consider splitting large logs into smaller files

### Memory Usage Issues
- Close other applications to free memory
- Reduce MAX_RECORDS constant in code
- Export specific time ranges to CSV for analysis

### Plot Display Issues
- Ensure matplotlib is installed correctly
- Try updating matplotlib: `pip install --upgrade matplotlib`
- Check for Qt/Tk backend conflicts

## Architecture

### MLGParser Class
Handles binary file parsing:
- `parse_header()`: Reads file header and metadata
- `parse_field_definition()`: Extracts channel definitions
- `parse_data_blocks()`: Reads and decodes binary data records

### LogData Class
Data model for parsed logs:
- Stores channels as dictionary of name→values
- Provides statistical analysis methods
- Handles data transformations (scale/offset)

### LogViewerApp Class
Main GUI application:
- Menu and toolbar creation
- Three-tab notebook interface
- Data grid with pagination and sorting
- matplotlib chart integration
- File operations (open/export)

## Development

### Modifying Constants

Key configuration values in `LogViewerApp` class:

```python
PAGE_SIZE = 1000              # Records per page
MAX_RECORDS = 100000          # Maximum records to load
MAX_FILE_SIZE_MB = 500        # File size warning threshold
WINDOW_WIDTH = 1200           # Initial window width
WINDOW_HEIGHT = 800           # Initial window height
```

### Adding New Features

- Parser modifications: Edit `MLGParser` class
- Data processing: Update `LogData` class
- UI changes: Modify `LogViewerApp` class methods
- New visualizations: Extend `plot_selected_channel()` method

## License

This project is provided as-is for use with TunerStudio MS MegaSquirt data logs.

## Support

For issues related to:
- **File Format**: Consult TunerStudio MS documentation
- **Python/Dependencies**: Check Python and matplotlib documentation
- **Application Bugs**: Review error messages in dialogs and console output
