"""
TunerStudio MS MegaSquirt Log Viewer

A Python application for viewing and analyzing .mlg binary log files
created by TunerStudio MS. Provides parsing, visualization, and export
capabilities using a native tkinter UI.

Author: Generated for MyCar Log Analysis
Date: February 22, 2026
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import struct
from datetime import datetime
import csv
import json
import xml.etree.ElementTree as ET
from typing import List, Dict, Any, Tuple, Optional
import os
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk


class MSQParser:
    """
    Parser for TunerStudio MS .msq tune files.
    
    Reads XML-formatted MegaSquirt tune files and extracts
    constants and pcVariables with their metadata.
    """
    
    # XML namespace used in MSQ files
    NAMESPACE = {'msq': 'http://www.msefi.com/:msq'}
    
    def __init__(self, file_path: str) -> None:
        """Initialize parser with file path."""
        self.file_path = file_path
        self.tree: Optional[ET.ElementTree] = None
        self.root: Optional[ET.Element] = None
    
    def parse(self) -> Dict[str, Any]:
        """Parse MSQ file and return structured data."""
        self.tree = ET.parse(self.file_path)
        self.root = self.tree.getroot()
        
        result = {
            'filename': os.path.basename(self.file_path),
            'bibliography': self._parse_bibliography(),
            'version_info': self._parse_version_info(),
            'entries': self._parse_all_entries(),
        }
        result['entry_count'] = len(result['entries'])
        return result
    
    def _parse_bibliography(self) -> Dict[str, str]:
        """Extract bibliography metadata."""
        bib = self.root.find('msq:bibliography', self.NAMESPACE)
        if bib is None:
            # Try without namespace
            bib = self.root.find('bibliography')
        if bib is None:
            return {}
        return dict(bib.attrib)
    
    def _parse_version_info(self) -> Dict[str, str]:
        """Extract version information."""
        info = self.root.find('msq:versionInfo', self.NAMESPACE)
        if info is None:
            info = self.root.find('versionInfo')
        if info is None:
            return {}
        return dict(info.attrib)
    
    def _parse_all_entries(self) -> List[Dict[str, Any]]:
        """Parse all constants and pcVariables from all pages."""
        entries = []
        
        # Find all pages (with and without namespace)
        pages = self.root.findall('msq:page', self.NAMESPACE)
        if not pages:
            pages = self.root.findall('page')
        
        for page in pages:
            page_number = page.get('number', 'config')
            
            # Parse constants
            for const in page.findall('msq:constant', self.NAMESPACE):
                entries.append(self._parse_element(const, 'constant', page_number))
            if not any(e['type'] == 'constant' for e in entries if entries):
                for const in page.findall('constant'):
                    entries.append(self._parse_element(const, 'constant', page_number))
            
            # Parse pcVariables
            for pcvar in page.findall('msq:pcVariable', self.NAMESPACE):
                entries.append(self._parse_element(pcvar, 'pcVariable', page_number))
            if not any(e['type'] == 'pcVariable' and e['page'] == page_number for e in entries):
                for pcvar in page.findall('pcVariable'):
                    entries.append(self._parse_element(pcvar, 'pcVariable', page_number))
        
        return entries
    
    def _parse_element(self, elem: ET.Element, elem_type: str,
                       page_number: str) -> Dict[str, Any]:
        """Parse a single constant or pcVariable element."""
        name = elem.get('name', '')
        units = elem.get('units', '')
        digits = elem.get('digits', '')
        rows = elem.get('rows', '')
        cols = elem.get('cols', '')
        
        # Get the text value
        raw_value = (elem.text or '').strip()
        
        # Determine if this is a table (multi-value)
        is_table = bool(rows or cols)
        
        if is_table:
            # For tables, show dimensions and clean up value
            row_count = int(rows) if rows else 1
            col_count = int(cols) if cols else 1
            # Split and clean multi-line values
            values = raw_value.split()
            display_value = ' '.join(values)
            dimensions = f"{row_count}x{col_count}"
        else:
            display_value = raw_value.strip('"')
            dimensions = ''
        
        return {
            'page': str(page_number),
            'type': elem_type,
            'name': name,
            'value': display_value,
            'units': units,
            'digits': digits,
            'dimensions': dimensions,
        }


class MLGParser:
    """
    Parser for TunerStudio MS .mlg binary log files.
    
    Handles MLVLG format with big-endian byte order.
    Supports format version 1 (version 2 could be added later).
    """
    
    # Constants
    MAX_RECORDS = 100000  # Safety limit for parsing
    
    # Field type mapping: (struct_format, byte_size)
    FIELD_TYPES = {
        0: ('B', 1),   # U08 - unsigned 8-bit
        1: ('b', 1),   # S08 - signed 8-bit
        2: ('H', 2),   # U16 - unsigned 16-bit
        3: ('h', 2),   # S16 - signed 16-bit
        4: ('I', 4),   # U32 - unsigned 32-bit
        5: ('i', 4),   # S32 - signed 32-bit
        6: ('q', 8),   # S64 - signed 64-bit
        7: ('f', 4),   # F32 - 32-bit float
        10: ('B', 1),  # U08 bitfield
        11: ('H', 2),  # U16 bitfield
        12: ('I', 4),  # U32 bitfield
    }
    
    def __init__(self, file_path: str) -> None:
        """Load file into memory."""
        with open(file_path, 'rb') as f:
            self.data = bytearray(f.read())
        self.offset = 0
        self.file_path = file_path
    
    def read(self, fmt: str, big_endian: bool = True) -> Any:
        """Read data using struct format string."""
        endian = '>' if big_endian else '<'
        size = struct.calcsize(endian + fmt)
        value = struct.unpack_from(endian + fmt, self.data, self.offset)
        self.offset += size
        return value[0] if len(value) == 1 else value
    
    def read_string(self, length: int) -> str:
        """Read and decode null-terminated string."""
        data = self.data[self.offset:self.offset + length]
        self.offset += length
        return data.decode('utf-8', errors='ignore').rstrip('\x00')
    
    def parse_header(self) -> Dict[str, Any]:
        """Parse MLG file header (22 bytes for v1, 24 bytes for v2)."""
        header = {}
        header['file_format'] = self.read_string(6)
        
        if header['file_format'] != 'MLVLG':
            raise ValueError(f"Invalid file format: {header['file_format']}. Expected 'MLVLG'.")
        
        header['format_version'] = self.read('H')   # uint16
        header['timestamp'] = self.read('I')        # uint32 Unix epoch
        
        # info_data_start is 4 bytes in v2, 2 bytes in v1
        if header['format_version'] >= 2:
            header['info_data_start'] = self.read('I')  # uint32
        else:
            header['info_data_start'] = self.read('H')  # uint16
        
        header['data_begin_index'] = self.read('I') # uint32
        header['record_length'] = self.read('H')    # uint16
        header['num_logger_fields'] = self.read('H') # uint16
        
        return header
    
    def parse_field_definition(self, version: int = 1) -> Dict[str, Any]:
        """Parse a single field definition (55 bytes for v1, 89 bytes for v2)."""
        field = {}
        field['field_type'] = self.read('B')       # uint8
        raw_name = self.read_string(34)
        # Strip leading control characters (bytes < 0x20)
        field['name'] = raw_name.lstrip('\x00\x01\x02\x03\x04\x05\x06\x07\x08\x09\x0a\x0b\x0c\x0d\x0e\x0f\x10\x11\x12\x13\x14\x15\x16\x17\x18\x19\x1a\x1b\x1c\x1d\x1e\x1f')
        field['units'] = self.read_string(10)
        field['display_style'] = self.read('B')    # uint8
        
        # Scalar fields have scale/transform
        if field['field_type'] < 10:
            field['scale'] = self.read('f')        # float32
            field['transform'] = self.read('f')    # float32
            field['digits'] = self.read('b')       # int8
        else:
            # Bitfield - skip for now (9 bytes)
            self.offset += 9
            field['scale'] = 1.0
            field['transform'] = 0.0
            field['digits'] = 0
        
        # Version 2 adds category (34 bytes)
        if version == 2:
            field['category'] = self.read_string(34)
        
        return field
    
    def find_data_start(self) -> int:
        """Find where binary data starts (after XML section)."""
        # Look for end of XML section
        xml_end = self.data.find(b'</msq>')
        if xml_end == -1:
            xml_end = self.data.find(b'</MegaTune>')
        if xml_end == -1:
            # No XML section, use calculated offset
            return self.offset
        
        # Skip past closing tag and whitespace
        data_start = xml_end + 10
        while data_start < len(self.data) and self.data[data_start] in (0x0a, 0x0d, 0x20):
            data_start += 1
        
        return data_start
    
    # Per-record header/footer sizes
    RECORD_HEADER_SIZE = 4   # 1 block_type + 1 counter + 2 timestamp
    RECORD_CRC_SIZE = 1      # 1 CRC byte after field data
    MARKER_MESSAGE_LENGTH = 50
    
    def parse_data_blocks(self, header: Dict, fields: List[Dict]) -> List[Dict[str, Any]]:
        """Parse data records with per-record headers (block_type + counter + timestamp)."""
        records = []
        
        # Use data_begin_index from header to find record start
        data_begin = header.get('data_begin_index', 0)
        if data_begin > 0 and data_begin < len(self.data):
            self.offset = data_begin
        else:
            # Fallback: find data start after XML section
            self.offset = self.find_data_start()
        
        # Calculate record size from field types
        record_size = sum(self.FIELD_TYPES.get(f['field_type'], (None, 0))[1] 
                         for f in fields if f['field_type'] in self.FIELD_TYPES)
        
        if record_size == 0:
            return records
        
        # Minimum bytes needed: record header + field data + CRC
        min_record_bytes = self.RECORD_HEADER_SIZE + record_size + self.RECORD_CRC_SIZE
        
        # Read records until end of file
        max_records = self.MAX_RECORDS
        record_count = 0
        
        while self.offset + self.RECORD_HEADER_SIZE <= len(self.data) and record_count < max_records:
            try:
                # Read per-record header (4 bytes)
                block_type = self.read('B')   # uint8: 0=field data, 1=marker
                self.read('B')                # uint8: counter (skip)
                self.read('H')                # uint16: record timestamp (skip)
                
                if block_type == 0:
                    # Field data record
                    if self.offset + record_size + self.RECORD_CRC_SIZE > len(self.data):
                        break
                    
                    record = {}
                    for field in fields:
                        if field['field_type'] in self.FIELD_TYPES:
                            fmt_char, size = self.FIELD_TYPES[field['field_type']]
                            raw_value = self.read(fmt_char)
                            
                            # Transform: (raw + transform) * scale
                            display_value = (raw_value + field['transform']) * field['scale']
                            
                            # Round to specified decimal places
                            if field['digits'] > 0:
                                display_value = round(display_value, field['digits'])
                            
                            record[field['name']] = display_value
                    
                    # Skip CRC byte
                    self.offset += self.RECORD_CRC_SIZE
                    
                    records.append(record)
                    record_count += 1
                
                elif block_type == 1:
                    # Marker record - skip message
                    self.offset += self.MARKER_MESSAGE_LENGTH
                
                else:
                    # Unknown block type - skip remaining data
                    break
                    
            except (struct.error, IndexError):
                # End of file or corrupted data
                break
        
        return records
    
    def parse(self) -> Dict[str, Any]:
        """Parse entire MLG file and return structured data."""
        result = {}
        
        # Parse header
        result['header'] = self.parse_header()
        version = result['header']['format_version']
        
        # Parse field definitions
        result['fields'] = []
        for _ in range(result['header']['num_logger_fields']):
            field = self.parse_field_definition(version)
            result['fields'].append(field)
        
        # Parse data blocks
        result['records'] = self.parse_data_blocks(result['header'], result['fields'])
        
        # Add metadata
        result['filename'] = os.path.basename(self.file_path)
        result['file_timestamp'] = datetime.fromtimestamp(result['header']['timestamp'])
        result['record_count'] = len(result['records'])
        result['field_count'] = len(result['fields'])
        
        return result


class LogData:
    """
    Data model for storing and accessing parsed log data.
    """
    
    def __init__(self, parsed_data: Dict[str, Any]) -> None:
        """Initialize from parser output."""
        self.filename = parsed_data.get('filename', 'Unknown')
        self.file_timestamp = parsed_data.get('file_timestamp')
        self.format_version = parsed_data['header']['format_version']
        self.fields = parsed_data['fields']
        self.records = parsed_data['records']
        self.record_count = len(self.records)
        self.field_count = len(self.fields)
    
    def get_channel_names(self) -> List[str]:
        """Return list of all channel/field names."""
        return [field['name'] for field in self.fields]
    
    def get_numeric_channel_names(self) -> List[str]:
        """Return list of numeric data channels, excluding text/config fields."""
        numeric_channels = []
        for field in self.fields:
            name = field['name']
            # Skip empty or very short names
            if not name or len(name) < 2:
                continue
            # Skip channels that look like XML or config data
            if any(marker in name for marker in ['<', '>', 'constant', 'pcVariable', 'xmlns', 'encoding', '/>', '<?', 'msq', 'page']):
                continue
            # Skip channels with too many special characters (likely text/config)
            if name.count('"') > 1 or name.count("'") > 1:
                continue
            # Skip channels with HTML entities or URL encoding
            if '%' in name or '&' in name or '\\x' in name:
                continue
            # Skip channels that start with whitespace or special chars
            if name[0] in ' \t\n\r<>':
                continue
            numeric_channels.append(name)
        return numeric_channels
    
    def get_channel_data(self, channel_name: str) -> List[float]:
        """Extract values for a specific channel."""
        values = []
        for record in self.records:
            if channel_name in record:
                values.append(record[channel_name])
            else:
                values.append(0.0)  # Missing values
        return values
    
    def get_time_data(self) -> List[float]:
        """Extract timestamp column (convert ms to seconds)."""
        # Find the time field by name (commonly 'Time', 'SecL', or 'timestamp')
        time_key = None
        for key_candidate in ['Time', 'time', 'timestamp', 'SecL']:
            if self.records and key_candidate in self.records[0]:
                time_key = key_candidate
                break
        
        if time_key is None and self.records:
            # Fallback: use the first field as time
            keys = list(self.records[0].keys())
            if keys:
                time_key = keys[0]
        
        if time_key is None:
            return []
        
        # Determine if values need conversion (ms to seconds)
        values = [record.get(time_key, 0) for record in self.records]
        if values and max(values) > 1000:
            # Values are likely in milliseconds, convert to seconds
            return [v / 1000.0 for v in values]
        return values
    
    def get_field_info(self, channel_name: str) -> Dict[str, Any]:
        """Get field metadata (units, scale, etc.)."""
        for field in self.fields:
            if field['name'] == channel_name:
                return field
        return None
    
    def get_statistics(self, channel_name: str) -> Dict[str, float]:
        """Calculate min, max, mean, std for a channel."""
        values = self.get_channel_data(channel_name)
        if not values:
            return {'min': 0, 'max': 0, 'mean': 0, 'count': 0}
        
        return {
            'min': min(values),
            'max': max(values),
            'mean': sum(values) / len(values),
            'count': len(values)
        }


class LogViewerApp(tk.Tk):
    """
    Main application window for MegaLogViewer.
    """
    
    # Class constants
    PAGE_SIZE = 1000
    MAX_FILE_SIZE_MB = 500
    WINDOW_WIDTH = 1200
    WINDOW_HEIGHT = 800
    
    # Theme color palettes
    LIGHT_THEME = {
        'bg': '#f0f0f0',
        'fg': '#000000',
        'surface': '#ffffff',
        'surface_alt': '#f5f5f5',
        'border': '#cccccc',
        'accent': '#2E86AB',
        'highlight_bg': '#0078d7',
        'highlight_fg': '#ffffff',
        'treeview_even': '#f0f0f0',
        'treeview_odd': '#ffffff',
        'input_bg': '#ffffff',
        'input_fg': '#000000',
        'menu_bg': '#f0f0f0',
        'menu_fg': '#000000',
        'statusbar_bg': '#f0f0f0',
        'statusbar_fg': '#000000',
        'debug_bg': '#f5f5f5',
        'debug_fg': '#000000',
        'debug_header': '#2E86AB',
        'debug_success': '#28a745',
        'debug_warning': '#fd7e14',
        'debug_error': '#dc3545',
        'debug_info': '#6c757d',
        'summary_bg': '#ffffff',
        'summary_fg': '#000000',
        'listbox_bg': '#ffffff',
        'listbox_fg': '#000000',
        'listbox_select_bg': '#0078d7',
        'listbox_select_fg': '#ffffff',
        'star_active': '#FFD700',
        'star_inactive': '#AAAAAA',
        'star_bg': '#f0f0f0',
        'tune_table_fg': '#2E86AB',
        'dir_label_fg': 'gray',
        'dir_label_active_fg': '#000000',
        'plot_bg': '#ffffff',
        'plot_face': '#ffffff',
        'plot_text': '#000000',
        'plot_grid': '#cccccc',
        'plot_spine': '#cccccc',
        'plot_tick': '#000000',
        'canvas_bg': '#ffffff',
    }
    
    DARK_THEME = {
        'bg': '#1e1e1e',
        'fg': '#d4d4d4',
        'surface': '#252526',
        'surface_alt': '#2d2d2d',
        'border': '#3c3c3c',
        'accent': '#4fc3f7',
        'highlight_bg': '#264f78',
        'highlight_fg': '#ffffff',
        'treeview_even': '#1e1e1e',
        'treeview_odd': '#252526',
        'input_bg': '#3c3c3c',
        'input_fg': '#d4d4d4',
        'menu_bg': '#252526',
        'menu_fg': '#d4d4d4',
        'statusbar_bg': '#007acc',
        'statusbar_fg': '#ffffff',
        'debug_bg': '#1e1e1e',
        'debug_fg': '#d4d4d4',
        'debug_header': '#4fc3f7',
        'debug_success': '#4ec9b0',
        'debug_warning': '#dcdcaa',
        'debug_error': '#f44747',
        'debug_info': '#808080',
        'summary_bg': '#1e1e1e',
        'summary_fg': '#d4d4d4',
        'listbox_bg': '#252526',
        'listbox_fg': '#d4d4d4',
        'listbox_select_bg': '#264f78',
        'listbox_select_fg': '#ffffff',
        'star_active': '#FFD700',
        'star_inactive': '#666666',
        'star_bg': '#1e1e1e',
        'tune_table_fg': '#4fc3f7',
        'dir_label_fg': '#808080',
        'dir_label_active_fg': '#d4d4d4',
        'plot_bg': '#1e1e1e',
        'plot_face': '#252526',
        'plot_text': '#d4d4d4',
        'plot_grid': '#3c3c3c',
        'plot_spine': '#3c3c3c',
        'plot_tick': '#d4d4d4',
        'canvas_bg': '#1e1e1e',
    }
    
    def __init__(self) -> None:
        super().__init__()
        
        self.title("MegaLogViewer - TunerStudio MS Log Viewer")
        self.geometry(f"{self.WINDOW_WIDTH}x{self.WINDOW_HEIGHT}")
        
        # Data storage
        self.log_data: LogData = None
        self.current_file: str = None
        self.current_directory: str = None
        self.file_info: dict = {}  # Maps filename to {records: int, size_mb: float}
        
        # MSQ tune data
        self.msq_data: Optional[Dict[str, Any]] = None
        self.msq_file: Optional[str] = None
        self._tune_sort_column: Optional[str] = None
        self._tune_sort_reverse: bool = False
        
        # Sort state
        self._sort_column: str = None
        self._sort_reverse: bool = False
        
        # Favorites
        self.favorite_channels: set = set()
        self.favorites_filter_active: bool = False
        
        # Launch filter
        self.launch_filter_active: bool = False
        
        # Plot state tracking for re-plotting on filter toggle
        self._plot_state: dict = {}  # {subplot_idx: {'channels': [...], 'single': bool}}
        self._saved_plot_selections: dict = {}  # Loaded from settings
        self.normalize_active: bool = False
        
        # Load saved settings (restores last_directory and favorites)
        self._load_settings()
        
        # Create UI components
        self.create_menu()
        self.create_toolbar()
        self.create_main_layout()
        self.create_statusbar()
        
        # Bind keyboard shortcuts
        self.bind("<Control-o>", lambda e: self.open_file())
        self.bind("<Control-e>", lambda e: self.export_csv())
        self.bind("<Control-t>", lambda e: self.open_msq_file())
        
        # Restore last folder after UI is ready
        self.after(100, self._restore_last_folder)
    
    def create_menu(self):
        """Create application menu bar."""
        menubar = tk.Menu(self)
        self.config(menu=menubar)
        
        # File menu
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(
            label="Open Log File...",
            command=self.open_file,
            accelerator="Ctrl+O"
        )
        file_menu.add_command(
            label="Export to CSV...",
            command=self.export_csv,
            accelerator="Ctrl+E"
        )
        file_menu.add_separator()
        file_menu.add_command(
            label="Open Tune File...",
            command=self.open_msq_file,
            accelerator="Ctrl+T"
        )
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.quit)
        
        # View menu
        view_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="View", menu=view_menu)
        view_menu.add_command(label="Data Grid", command=lambda: self.notebook.select(0))
        view_menu.add_command(label="Visualization", command=lambda: self.notebook.select(1))
        view_menu.add_command(label="Summary", command=lambda: self.notebook.select(2))
        view_menu.add_command(label="Tune", command=lambda: self.notebook.select(3))
        view_menu.add_command(label="Debug", command=lambda: self.notebook.select(4))
        view_menu.add_separator()
        view_menu.add_command(
            label="Toggle Dark Mode",
            command=self.toggle_dark_mode,
            accelerator="Ctrl+D"
        )
        self._view_menu = view_menu
        
        # Help menu
        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Help", menu=help_menu)
        help_menu.add_command(label="About", command=self.show_about)
    
    def create_toolbar(self):
        """Create toolbar with common actions."""
        toolbar = ttk.Frame(self, relief=tk.RAISED, padding=(5, 2))
        toolbar.pack(side=tk.TOP, fill=tk.X)
        
        # Open button
        ttk.Button(
            toolbar,
            text="Open",
            command=self.open_file
        ).pack(side=tk.LEFT, padx=2)
        
        # Export button
        ttk.Button(
            toolbar,
            text="Export CSV",
            command=self.export_csv
        ).pack(side=tk.LEFT, padx=2)
        
        # Separator
        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=10)
        
        # Channel selection
        ttk.Label(toolbar, text="Channel:").pack(side=tk.LEFT, padx=5)
        self.channel_var = tk.StringVar()
        self.channel_combo = ttk.Combobox(
            toolbar,
            textvariable=self.channel_var,
            width=25,
            state="readonly"
        )
        self.channel_combo.pack(side=tk.LEFT, padx=2)
        
        # Plot button
        ttk.Button(
            toolbar,
            text="Plot Selected",
            command=self.plot_selected_channel
        ).pack(side=tk.LEFT, padx=2)
    
    def create_statusbar(self):
        """Create status bar."""
        self.statusbar = ttk.Label(
            self,
            text="Ready",
            relief=tk.SUNKEN,
            anchor=tk.W
        )
        self.statusbar.pack(side=tk.BOTTOM, fill=tk.X)
    
    def create_main_layout(self):
        """Create main layout with file browser and notebook."""
        # Create PanedWindow for resizable split
        self.paned_window = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        self.paned_window.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Create file browser panel
        self.create_file_browser()
        
        # Create notebook panel
        self.create_notebook()
        
        # Add panels to paned window
        self.paned_window.add(self.browser_frame, weight=1)
        self.paned_window.add(self.notebook, weight=4)
    
    def create_file_browser(self):
        """Create file browser panel."""
        self.browser_frame = ttk.Frame(self.paned_window)
        
        # Browser header
        header_frame = ttk.Frame(self.browser_frame)
        header_frame.pack(side=tk.TOP, fill=tk.X, padx=5, pady=5)
        
        ttk.Label(header_frame, text="Log Files", font=('', 10, 'bold')).pack(side=tk.LEFT)
        
        ttk.Button(
            header_frame,
            text="Browse...",
            command=self.browse_folder,
            width=10
        ).pack(side=tk.RIGHT)
        
        # Current directory label
        self.dir_label = ttk.Label(
            self.browser_frame,
            text="No folder selected",
            foreground="gray",
            wraplength=200
        )
        self.dir_label.pack(side=tk.TOP, fill=tk.X, padx=5, pady=(0, 5))
        
        # File list with scrollbar
        list_frame = ttk.Frame(self.browser_frame)
        list_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        scrollbar = ttk.Scrollbar(list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.file_listbox = tk.Listbox(
            list_frame,
            yscrollcommand=scrollbar.set,
            selectmode=tk.SINGLE,
            activestyle='dotbox'
        )
        self.file_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.file_listbox.yview)
        
        # Bind selection event
        self.file_listbox.bind('<<ListboxSelect>>', self.on_file_select)
        self.file_listbox.bind('<Double-Button-1>', lambda e: self.on_file_select(e, force_reload=True))
        
        # File count label
        self.file_count_label = ttk.Label(
            self.browser_frame,
            text="0 files",
            foreground="gray"
        )
        self.file_count_label.pack(side=tk.BOTTOM, pady=(0, 5))
    
    def create_notebook(self):
        """Create tabbed notebook interface."""
        self.notebook = ttk.Notebook(self.paned_window)
        
        # Create three tabs
        self.grid_tab = ttk.Frame(self.notebook)
        self.plot_tab = ttk.Frame(self.notebook)
        self.summary_tab = ttk.Frame(self.notebook)
        
        self.notebook.add(self.grid_tab, text="Data Grid")
        self.notebook.add(self.plot_tab, text="Visualization")
        self.notebook.add(self.summary_tab, text="Summary")
        
        # Tune tab
        self.tune_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.tune_tab, text="Tune")
        
        # Debug tab
        self.debug_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.debug_tab, text="Debug")
        
        # Create grid view in first tab
        self.create_data_grid()
        
        # Create plot area in second tab
        self.create_plot_area()
        
        # Create summary view in third tab
        self.create_summary_view()
        
        # Create tune view in fourth tab
        self.create_tune_view()
        
        # Create debug view in fifth tab
        self.create_debug_view()
    
    def create_data_grid(self):
        """Create treeview data grid with scrollbars."""
        # Create frame for grid and scrollbars
        grid_frame = ttk.Frame(self.grid_tab)
        grid_frame.pack(fill=tk.BOTH, expand=True)
        
        # Create scrollbars
        vsb = ttk.Scrollbar(grid_frame, orient="vertical")
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        
        hsb = ttk.Scrollbar(grid_frame, orient="horizontal")
        hsb.pack(side=tk.BOTTOM, fill=tk.X)
        
        # Create treeview
        self.data_tree = ttk.Treeview(
            grid_frame,
            columns=(),
            show="tree headings",
            yscrollcommand=vsb.set,
            xscrollcommand=hsb.set,
            selectmode="extended"
        )
        self.data_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Connect scrollbars
        vsb.config(command=self.data_tree.yview)
        hsb.config(command=self.data_tree.xview)
        
        # Pagination controls frame
        self.pagination_frame = ttk.Frame(self.grid_tab)
        self.pagination_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=5)
        
        ttk.Button(self.pagination_frame, text="◄◄ First", 
                   command=self.goto_first_page).pack(side=tk.LEFT, padx=5)
        ttk.Button(self.pagination_frame, text="◄ Previous", 
                   command=self.goto_prev_page).pack(side=tk.LEFT)
        
        self.page_label = ttk.Label(self.pagination_frame, text="No data loaded")
        self.page_label.pack(side=tk.LEFT, padx=20)
        
        ttk.Button(self.pagination_frame, text="Next ►", 
                   command=self.goto_next_page).pack(side=tk.LEFT)
        ttk.Button(self.pagination_frame, text="Last ►►", 
                   command=self.goto_last_page).pack(side=tk.LEFT, padx=5)
        
        # Pagination state
        self.current_page = 0
        self.page_size = self.PAGE_SIZE
    
    def populate_grid(self, log_data: LogData) -> None:
        """Populate treeview with log data."""
        # Clear existing data
        for item in self.data_tree.get_children():
            self.data_tree.delete(item)
        
        # Configure columns from field names
        channel_names = log_data.get_channel_names()
        self.data_tree.config(columns=channel_names)
        
        # Configure row identifier column
        self.data_tree.column("#0", width=60, minwidth=50, anchor=tk.W)
        self.data_tree.heading("#0", text="Row")
        
        # Configure data columns with sort capability
        for channel in channel_names:
            self.data_tree.column(channel, width=100, minwidth=80, anchor=tk.E)
            self.data_tree.heading(
                channel, 
                text=channel,
                command=lambda c=channel: self.sort_by_column(c)
            )
        
        # Reset pagination
        self.current_page = 0
        self.display_current_page()
    
    def display_current_page(self) -> None:
        """Display current page of data."""
        if not self.log_data:
            return
        
        # Clear existing rows
        for item in self.data_tree.get_children():
            self.data_tree.delete(item)
        
        # Calculate page boundaries
        start_idx = self.current_page * self.page_size
        end_idx = min(start_idx + self.page_size, self.log_data.record_count)
        
        # Insert rows for current page
        for idx in range(start_idx, end_idx):
            record = self.log_data.records[idx]
            values = [record.get(ch, '') for ch in self.log_data.get_channel_names()]
            
            # Apply alternating row colors
            tags = ('evenrow',) if idx % 2 == 0 else ('oddrow',)
            self.data_tree.insert("", tk.END, text=str(idx + 1), values=values, tags=tags)
        
        # Configure row colors from theme
        t = self._get_theme()
        self.data_tree.tag_configure('evenrow', background=t['treeview_even'])
        self.data_tree.tag_configure('oddrow', background=t['treeview_odd'])
        
        # Update page label with sort indicator
        total_pages = (self.log_data.record_count + self.page_size - 1) // self.page_size
        sort_info = f" (sorted by {self._sort_column})" if self._sort_column else ""
        self.page_label.config(
            text=f"Page {self.current_page + 1} of {total_pages} | "
                 f"Records {start_idx + 1}-{end_idx} of {self.log_data.record_count}{sort_info}"
        )
        
        # Update column headers with sort indicators
        for channel in self.log_data.get_channel_names():
            if channel == self._sort_column:
                indicator = " ▼" if self._sort_reverse else " ▲"
                self.data_tree.heading(channel, text=f"{channel}{indicator}")
            else:
                self.data_tree.heading(channel, text=channel)
    
    def goto_next_page(self) -> None:
        """Navigate to next page."""
        if not self.log_data:
            return
        total_pages = (self.log_data.record_count + self.page_size - 1) // self.page_size
        if self.current_page < total_pages - 1:
            self.current_page += 1
            self.display_current_page()
    
    def goto_prev_page(self) -> None:
        """Navigate to previous page."""
        if self.current_page > 0:
            self.current_page -= 1
            self.display_current_page()
    
    def goto_first_page(self) -> None:
        """Navigate to first page."""
        self.current_page = 0
        self.display_current_page()
    
    def goto_last_page(self) -> None:
        """Navigate to last page."""
        if not self.log_data:
            return
        total_pages = (self.log_data.record_count + self.page_size - 1) // self.page_size
        self.current_page = total_pages - 1
        self.display_current_page()
    
    def sort_by_column(self, column: str) -> None:
        """Sort data by column, toggle ascending/descending."""
        if not self.log_data:
            return
        
        # Toggle sort direction if same column
        if self._sort_column == column:
            self._sort_reverse = not self._sort_reverse
        else:
            self._sort_column = column
            self._sort_reverse = False
        
        # Sort all records
        self.log_data.records.sort(
            key=lambda r: r.get(column, 0),
            reverse=self._sort_reverse
        )
        
        # Reset to first page and refresh
        self.current_page = 0
        self.display_current_page()
    
    def create_plot_area(self):
        """Create matplotlib plot area with channel selection and 4 subplots."""
        # Create main container with PanedWindow for resizable panels
        plot_paned = ttk.PanedWindow(self.plot_tab, orient=tk.HORIZONTAL)
        plot_paned.pack(fill=tk.BOTH, expand=True)
        
        # Left panel: Channel selection
        channel_frame = ttk.Frame(plot_paned)
        
        # Channel selection header
        header_frame = ttk.Frame(channel_frame)
        header_frame.pack(side=tk.TOP, fill=tk.X, padx=5, pady=5)
        ttk.Label(header_frame, text="Select Channels", font=('', 10, 'bold')).pack(side=tk.LEFT)
        
        # Target plot selector
        target_frame = ttk.Frame(channel_frame)
        target_frame.pack(side=tk.TOP, fill=tk.X, padx=5, pady=(0, 5))
        ttk.Label(target_frame, text="Target:").pack(side=tk.LEFT)
        self.plot_target_combo = ttk.Combobox(
            target_frame,
            values=["Plot 1", "Plot 2", "Plot 3", "Plot 4"],
            width=10, state="readonly"
        )
        self.plot_target_combo.current(0)
        self.plot_target_combo.pack(side=tk.LEFT, padx=5)
        
        # Plot action buttons
        button_frame = ttk.Frame(channel_frame)
        button_frame.pack(side=tk.TOP, fill=tk.X, padx=5, pady=(0, 3))
        ttk.Button(button_frame, text="All", command=self.select_all_channels, width=6).pack(side=tk.LEFT, padx=2)
        ttk.Button(button_frame, text="None", command=self.select_no_channels, width=6).pack(side=tk.LEFT, padx=2)
        ttk.Button(button_frame, text="Plot", command=self.plot_selected_channels, width=6).pack(side=tk.LEFT, padx=2)
        ttk.Button(button_frame, text="Clear", command=self.clear_target_plot, width=6).pack(side=tk.LEFT, padx=2)
        
        # Favorites buttons
        fav_frame = ttk.Frame(channel_frame)
        fav_frame.pack(side=tk.TOP, fill=tk.X, padx=5, pady=(0, 3))
        ttk.Button(fav_frame, text="★ Fav", command=self.add_selected_to_favorites, width=8).pack(side=tk.LEFT, padx=2)
        ttk.Button(fav_frame, text="Unfav", command=self.remove_selected_from_favorites, width=8).pack(side=tk.LEFT, padx=2)
        self.fav_filter_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(fav_frame, text="★ Only", variable=self.fav_filter_var,
                        command=self.toggle_favorites_filter).pack(side=tk.LEFT, padx=5)
        
        # Scrollable channel list
        list_frame = ttk.Frame(channel_frame)
        list_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        scrollbar = ttk.Scrollbar(list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Use canvas for scrollable checkboxes
        self.channel_canvas = tk.Canvas(list_frame, yscrollcommand=scrollbar.set, highlightthickness=0)
        self.channel_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.channel_canvas.yview)
        
        # Frame inside canvas to hold checkboxes
        self.channel_checkboxes_frame = ttk.Frame(self.channel_canvas)
        self.channel_canvas_window = self.channel_canvas.create_window(
            (0, 0), window=self.channel_checkboxes_frame, anchor='nw'
        )
        
        # Store checkbox variables and favorite labels
        self.channel_vars = {}
        self._channel_fav_labels = {}
        
        # Bind canvas configure to update scroll region
        self.channel_checkboxes_frame.bind(
            '<Configure>',
            lambda e: self.channel_canvas.configure(
                scrollregion=self.channel_canvas.bbox('all')
            )
        )
        
        # Right panel: Plot area with 2x2 subplot grid
        plot_frame = ttk.Frame(plot_paned)
        
        # Create matplotlib figure with 4 stacked subplots
        t = self._get_theme()
        self.fig = Figure(figsize=(14, 16), dpi=150, facecolor=t['plot_face'])
        self.axes = []
        for i in range(4):
            ax = self.fig.add_subplot(4, 1, i + 1)
            ax.set_facecolor(t['plot_bg'])
            ax.set_title(f"Plot {i + 1}", fontsize=10, color=t['plot_text'])
            ax.set_xlabel("Time (s)", fontsize=8, color=t['plot_text'])
            ax.set_ylabel("Value", fontsize=8, color=t['plot_text'])
            ax.tick_params(colors=t['plot_tick'], labelsize=7)
            ax.grid(True, alpha=0.3, color=t['plot_grid'])
            for spine in ax.spines.values():
                spine.set_color(t['plot_spine'])
            self.axes.append(ax)
        self.fig.tight_layout(pad=2.0)
        
        # Create canvas
        self.canvas = FigureCanvasTkAgg(self.fig, master=plot_frame)
        
        # Bottom toolbar area
        toolbar_row = ttk.Frame(plot_frame)
        toolbar_row.pack(side=tk.BOTTOM, fill=tk.X)
        self.toolbar_mpl = NavigationToolbar2Tk(self.canvas, toolbar_row, pack_toolbar=False)
        self.toolbar_mpl.update()
        self.toolbar_mpl.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # Launch filter toggle button
        self.launch_filter_var = tk.BooleanVar(value=False)
        self.launch_filter_btn = ttk.Checkbutton(
            toolbar_row, text="Launch Only",
            variable=self.launch_filter_var,
            command=self.toggle_launch_filter,
            style='Toolbutton'
        )
        self.launch_filter_btn.pack(side=tk.RIGHT, padx=5)
        
        # Launch cutoff seconds combobox
        self.launch_cutoff_var = tk.StringVar(value='12')
        self.launch_cutoff_combo = ttk.Combobox(
            toolbar_row,
            textvariable=self.launch_cutoff_var,
            values=[str(s) for s in range(1, 31)],
            width=3,
            state='readonly'
        )
        self.launch_cutoff_combo.pack(side=tk.RIGHT, padx=(0, 2))
        self.launch_cutoff_combo.bind('<<ComboboxSelected>>', lambda e: self._on_launch_cutoff_changed())
        ttk.Label(toolbar_row, text='Cutoff:').pack(side=tk.RIGHT, padx=(5, 0))
        
        # Normalize Y-axis toggle button
        self.normalize_var = tk.BooleanVar(value=False)
        self.normalize_btn = ttk.Checkbutton(
            toolbar_row, text="Normalize Y",
            variable=self.normalize_var,
            command=self.toggle_normalize,
            style='Toolbutton'
        )
        self.normalize_btn.pack(side=tk.RIGHT, padx=5)
        
        ttk.Button(toolbar_row, text="Clear All Plots",
                   command=self.clear_all_plots).pack(side=tk.RIGHT, padx=5)
        
        self.canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        
        # Draw initial canvas
        self.canvas.draw()
        
        # Add panels to paned window
        plot_paned.add(channel_frame, weight=1)
        plot_paned.add(plot_frame, weight=4)
    
    def populate_channel_checkboxes(self):
        """Populate the channel selection checkboxes with favorite indicators."""
        # Clear existing checkboxes
        for widget in self.channel_checkboxes_frame.winfo_children():
            widget.destroy()
        self.channel_vars.clear()
        self._channel_fav_labels.clear()
        
        if not self.log_data:
            return
        
        # Get channel names, optionally filtered to favorites only
        all_channels = self.log_data.get_numeric_channel_names()
        if self.favorites_filter_active:
            channel_names = [ch for ch in all_channels if ch in self.favorite_channels]
        else:
            channel_names = all_channels
        
        for channel in channel_names:
            row_frame = ttk.Frame(self.channel_checkboxes_frame)
            row_frame.pack(fill=tk.X, padx=2, pady=1)
            
            # Favorite star indicator (clickable)
            is_fav = channel in self.favorite_channels
            t = self._get_theme()
            star_label = tk.Label(
                row_frame,
                text="\u2605" if is_fav else "\u2606",
                fg=t['star_active'] if is_fav else t['star_inactive'],
                bg=t['star_bg'],
                cursor="hand2", font=('', 10)
            )
            star_label.pack(side=tk.LEFT, padx=(0, 2))
            star_label.bind('<Button-1>', lambda e, c=channel: self.toggle_favorite(c))
            self._channel_fav_labels[channel] = star_label
            
            # Selection checkbox
            var = tk.BooleanVar(value=False)
            self.channel_vars[channel] = var
            cb = ttk.Checkbutton(row_frame, text=channel, variable=var)
            cb.pack(side=tk.LEFT)
    
    def select_all_channels(self):
        """Select all channels."""
        for var in self.channel_vars.values():
            var.set(True)
    
    def select_no_channels(self):
        """Deselect all channels."""
        for var in self.channel_vars.values():
            var.set(False)
    
    def toggle_favorite(self, channel: str):
        """Toggle a channel's favorite status."""
        if channel in self.favorite_channels:
            self.favorite_channels.discard(channel)
        else:
            self.favorite_channels.add(channel)
        
        # Update star display
        if channel in self._channel_fav_labels:
            lbl = self._channel_fav_labels[channel]
            is_fav = channel in self.favorite_channels
            t = self._get_theme()
            lbl.config(
                text="\u2605" if is_fav else "\u2606",
                fg=t['star_active'] if is_fav else t['star_inactive']
            )
        
        self._save_settings()
    
    def add_selected_to_favorites(self):
        """Add all currently checked channels to favorites."""
        for name, var in self.channel_vars.items():
            if var.get():
                self.favorite_channels.add(name)
        self.populate_channel_checkboxes()
        self._save_settings()
    
    def remove_selected_from_favorites(self):
        """Remove all currently checked channels from favorites."""
        for name, var in self.channel_vars.items():
            if var.get():
                self.favorite_channels.discard(name)
        self.populate_channel_checkboxes()
        self._save_settings()
    
    def toggle_favorites_filter(self):
        """Toggle between showing all channels and favorites only."""
        self.favorites_filter_active = self.fav_filter_var.get()
        self.populate_channel_checkboxes()
    
    def toggle_launch_filter(self):
        """Toggle the launch timer filter on/off and replot."""
        self.launch_filter_active = self.launch_filter_var.get()
        self._replot_all()
    
    def toggle_normalize(self):
        """Toggle normalized Y axes on/off and replot."""
        self.normalize_active = self.normalize_var.get()
        self._replot_all()
    
    def _normalize_data(self, data: List[float]) -> List[float]:
        """Normalize data to 0-1 range using min-max scaling."""
        if not data:
            return data
        min_val = min(data)
        max_val = max(data)
        range_val = max_val - min_val
        if range_val == 0:
            return [0.5] * len(data)
        return [(v - min_val) / range_val for v in data]
    
    def _replot_all(self):
        """Re-plot all subplots using stored plot state."""
        if not self.log_data or not self._plot_state:
            return
        
        for subplot_idx, state in self._plot_state.items():
            channels = state.get('channels', [])
            single = state.get('single', False)
            if not channels:
                continue
            
            if single:
                self._do_plot_single(subplot_idx, channels[0])
            else:
                self._do_plot_multi(subplot_idx, channels)
    
    def _restore_plot_selections(self) -> None:
        """Restore saved plot selections after loading a log file."""
        if not self._saved_plot_selections or not self.log_data:
            return
        
        available_channels = set(self.log_data.get_channel_names())
        
        for idx_str, state in self._saved_plot_selections.items():
            try:
                subplot_idx = int(idx_str)
            except (ValueError, TypeError):
                continue
            
            if subplot_idx < 0 or subplot_idx >= len(self.axes):
                continue
            
            channels = state.get('channels', [])
            single = state.get('single', False)
            
            # Only restore channels that exist in the current log
            valid_channels = [c for c in channels if c in available_channels]
            if not valid_channels:
                continue
            
            self._plot_state[subplot_idx] = {
                'channels': valid_channels,
                'single': single and len(valid_channels) == 1
            }
            
            if self._plot_state[subplot_idx]['single']:
                self._do_plot_single(subplot_idx, valid_channels[0])
            else:
                self._do_plot_multi(subplot_idx, valid_channels)
    
    @property
    def launch_timer_cutoff(self) -> float:
        """Return current launch timer cutoff in seconds from the combobox."""
        try:
            return float(self.launch_cutoff_var.get())
        except (ValueError, AttributeError):
            return 12.0
    
    def _on_launch_cutoff_changed(self) -> None:
        """Handle launch cutoff combobox change."""
        if self.launch_filter_active:
            self._replot_all()
    
    def _get_launch_filter_mask(self) -> List[bool]:
        """Return a boolean mask where True means Launch timer is increasing
        and below the cutoff threshold.
        
        Includes the start point of each increasing segment so the full
        rising portion is visible. Excludes any points where the launch
        timer exceeds the selected cutoff seconds.
        """
        if not self.log_data:
            return []
        
        # Channel name as discovered in the MLG data
        launch_channel = 'Launch timer'
        launch_data = self.log_data.get_channel_data(launch_channel)
        
        if not launch_data or all(v == 0 for v in launch_data):
            return [True] * self.log_data.record_count
        
        mask = [False] * len(launch_data)
        cutoff = self.launch_timer_cutoff
        for i in range(1, len(launch_data)):
            if launch_data[i] > launch_data[i - 1] and launch_data[i] <= cutoff:
                mask[i] = True
                # Also include the start of this increasing segment
                if not mask[i - 1] and launch_data[i - 1] <= cutoff:
                    mask[i - 1] = True
        return mask
    
    def _apply_filter(self, data: List[float], mask: List[bool]) -> Tuple[List[float], List[int]]:
        """Apply boolean mask to data, returning filtered values and their indices."""
        filtered = []
        indices = []
        for i, (val, keep) in enumerate(zip(data, mask)):
            if keep:
                filtered.append(val)
                indices.append(i)
        return filtered, indices
    
    def clear_target_plot(self):
        """Clear the currently targeted subplot."""
        target_idx = self.plot_target_combo.current()
        if target_idx < 0:
            target_idx = 0
        t = self._get_theme()
        ax = self.axes[target_idx]
        ax.clear()
        ax.set_facecolor(t['plot_bg'])
        ax.set_title(f"Plot {target_idx + 1}", fontsize=10, color=t['plot_text'])
        ax.set_xlabel("Time (s)", fontsize=8, color=t['plot_text'])
        ax.set_ylabel("Value", fontsize=8, color=t['plot_text'])
        ax.tick_params(colors=t['plot_tick'], labelsize=7)
        ax.grid(True, alpha=0.3, color=t['plot_grid'])
        for spine in ax.spines.values():
            spine.set_color(t['plot_spine'])
        self.fig.tight_layout(pad=2.0)
        self.canvas.draw()
    
    def clear_all_plots(self):
        """Clear all 4 subplots."""
        t = self._get_theme()
        for i, ax in enumerate(self.axes):
            ax.clear()
            ax.set_facecolor(t['plot_bg'])
            ax.set_title(f"Plot {i + 1}", fontsize=10, color=t['plot_text'])
            ax.set_xlabel("Time (s)", fontsize=8, color=t['plot_text'])
            ax.set_ylabel("Value", fontsize=8, color=t['plot_text'])
            ax.tick_params(colors=t['plot_tick'], labelsize=7)
            ax.grid(True, alpha=0.3, color=t['plot_grid'])
            for spine in ax.spines.values():
                spine.set_color(t['plot_spine'])
        self.fig.tight_layout(pad=2.0)
        self.canvas.draw()
    
    def plot_selected_channels(self):
        """Plot selected channels on the target subplot."""
        if not self.log_data:
            messagebox.showwarning("No Data", "Please load a log file first.")
            return
        
        # Get selected channels
        selected_channels = [name for name, var in self.channel_vars.items() if var.get()]
        
        if not selected_channels:
            messagebox.showwarning("No Selection", "Please select at least one channel to plot.")
            return
        
        try:
            # Switch to plot tab
            self.notebook.select(self.plot_tab)
            
            # Get target subplot index
            target_idx = self.plot_target_combo.current()
            if target_idx < 0:
                target_idx = 0
            
            # Store plot state for re-plotting
            self._plot_state[target_idx] = {
                'channels': list(selected_channels),
                'single': False
            }
            
            self._do_plot_multi(target_idx, selected_channels)
            self._save_settings()
            
        except Exception as e:
            messagebox.showerror("Plot Error", f"Error creating plot:\n{str(e)}")
    
    def _do_plot_multi(self, target_idx: int, selected_channels: List[str]):
        """Internal: plot multiple channels on a subplot."""
        t = self._get_theme()
        ax = self.axes[target_idx]
        
        # Get time data
        time_data = self.log_data.get_time_data()
        
        # Apply launch filter if active
        mask = None
        if self.launch_filter_active:
            mask = self._get_launch_filter_mask()
            time_data, _ = self._apply_filter(time_data, mask)
        
        # Clear target subplot
        ax.clear()
        ax.set_facecolor(t['plot_bg'])
        ax.set_xlabel("Time (s)", fontsize=8, color=t['plot_text'])
        if self.normalize_active and len(selected_channels) > 1:
            ax.set_ylabel("Normalized (0-1)", fontsize=8, color=t['plot_text'])
        else:
            ax.set_ylabel("Value", fontsize=8, color=t['plot_text'])
        ax.tick_params(colors=t['plot_tick'], labelsize=7)
        ax.grid(True, alpha=0.3, color=t['plot_grid'])
        for spine in ax.spines.values():
            spine.set_color(t['plot_spine'])
        
        # Color palette for multiple lines
        colors = ['#2E86AB', '#A23B72', '#F18F01', '#C73E1D', '#6A994E', 
                  '#BC4B51', '#8675A9', '#C9ADA7', '#9A8C98', '#4A4E69']
        
        # Plot each selected channel
        for idx, channel in enumerate(selected_channels):
            channel_data = self.log_data.get_channel_data(channel)
            if self.launch_filter_active and mask:
                channel_data, _ = self._apply_filter(channel_data, mask)
            
            # Normalize if active and multiple channels
            plot_data = channel_data
            if self.normalize_active and len(selected_channels) > 1:
                plot_data = self._normalize_data(channel_data)
            
            color = colors[idx % len(colors)]
            ax.plot(time_data, plot_data, linewidth=1.2, label=channel, color=color)
        
        # Add legend if multiple channels
        if len(selected_channels) > 1:
            legend = ax.legend(loc='best', fontsize=7, framealpha=0.9,
                               facecolor=t['plot_face'], edgecolor=t['plot_spine'])
            if legend:
                for text in legend.get_texts():
                    text.set_color(t['plot_text'])
            ax.set_title(
                f"Plot {target_idx + 1}: {len(selected_channels)} channels",
                fontsize=10, fontweight='bold', color=t['plot_text']
            )
        else:
            # Single channel - show units in ylabel
            channel = selected_channels[0]
            field_info = self.log_data.get_field_info(channel)
            ylabel = channel
            if field_info and field_info.get('units'):
                ylabel += f" ({field_info['units']})"
            ax.set_ylabel(ylabel, fontsize=8, color=t['plot_text'])
            ax.set_title(
                f"Plot {target_idx + 1}: {channel}",
                fontsize=10, fontweight='bold', color=t['plot_text']
            )
        
        # Refresh canvas
        self.fig.tight_layout(pad=2.0)
        self.canvas.draw()
    
    def plot_selected_channel(self):
        """Plot the channel selected in toolbar dropdown to the target subplot."""
        if not self.log_data:
            messagebox.showwarning("No Data", "Please load a log file first.")
            return
        
        channel_name = self.channel_var.get()
        if not channel_name:
            messagebox.showwarning("No Selection", "Please select a channel to plot.")
            return
        
        try:
            self.notebook.select(self.plot_tab)
            
            # Get target subplot
            target_idx = 0
            if hasattr(self, 'plot_target_combo'):
                target_idx = self.plot_target_combo.current()
                if target_idx < 0:
                    target_idx = 0
            
            # Store plot state for re-plotting
            self._plot_state[target_idx] = {
                'channels': [channel_name],
                'single': True
            }
            
            self._do_plot_single(target_idx, channel_name)
            self._save_settings()
            
        except Exception as e:
            messagebox.showerror("Plot Error", f"Error creating plot:\n{str(e)}")
    
    def _do_plot_single(self, target_idx: int, channel_name: str):
        """Internal: plot a single channel on a subplot."""
        t = self._get_theme()
        ax = self.axes[target_idx]
        
        time_data = self.log_data.get_time_data()
        channel_data = self.log_data.get_channel_data(channel_name)
        
        # Apply launch filter if active
        if self.launch_filter_active:
            mask = self._get_launch_filter_mask()
            time_data, _ = self._apply_filter(time_data, mask)
            channel_data, _ = self._apply_filter(channel_data, mask)
        
        ax.clear()
        ax.set_facecolor(t['plot_bg'])
        ax.set_xlabel("Time (s)", fontsize=8, color=t['plot_text'])
        ax.tick_params(colors=t['plot_tick'], labelsize=7)
        ax.grid(True, alpha=0.3, color=t['plot_grid'])
        for spine in ax.spines.values():
            spine.set_color(t['plot_spine'])
        
        field_info = self.log_data.get_field_info(channel_name)
        ylabel = channel_name
        if field_info and field_info.get('units'):
            ylabel += f" ({field_info['units']})"
        ax.set_ylabel(ylabel, fontsize=8, color=t['plot_text'])
        ax.set_title(
            f"Plot {target_idx + 1}: {channel_name}",
            fontsize=10, fontweight='bold', color=t['plot_text']
        )
        
        ax.plot(time_data, channel_data, linewidth=1.2, color='#2E86AB')
        
        self.fig.tight_layout(pad=2.0)
        self.canvas.draw()
    
    def create_summary_view(self):
        """Create summary view with text widget."""
        # Create scrollable text widget
        text_frame = ttk.Frame(self.summary_tab)
        text_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        scrollbar = ttk.Scrollbar(text_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.summary_text = tk.Text(
            text_frame,
            wrap=tk.WORD,
            yscrollcommand=scrollbar.set,
            font=("Consolas", 10)
        )
        self.summary_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.summary_text.yview)
        
        # Initial message
        self.summary_text.insert("1.0", "No data loaded. Open a log file to view summary.")
        self.summary_text.config(state=tk.DISABLED)
    
    def create_debug_view(self):
        """Create debug view with scrollable text widget."""
        # Create toolbar for debug tab
        debug_toolbar = ttk.Frame(self.debug_tab)
        debug_toolbar.pack(side=tk.TOP, fill=tk.X, padx=5, pady=5)
        
        ttk.Button(
            debug_toolbar,
            text="Clear Debug Log",
            command=self.clear_debug
        ).pack(side=tk.LEFT, padx=2)
        
        ttk.Button(
            debug_toolbar,
            text="Save Debug Log",
            command=self.save_debug_log
        ).pack(side=tk.LEFT, padx=2)
        
        # Create scrollable text widget
        text_frame = ttk.Frame(self.debug_tab)
        text_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        scrollbar = ttk.Scrollbar(text_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        t = self._get_theme()
        self.debug_text = tk.Text(
            text_frame,
            wrap=tk.WORD,
            yscrollcommand=scrollbar.set,
            font=("Consolas", 9),
            background=t['debug_bg'],
            foreground=t['debug_fg'],
            insertbackground=t['fg']
        )
        self.debug_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.debug_text.yview)
        
        # Configure text tags for different log levels
        self.debug_text.tag_configure('header', font=('Consolas', 10, 'bold'), foreground=t['debug_header'])
        self.debug_text.tag_configure('success', foreground=t['debug_success'])
        self.debug_text.tag_configure('warning', foreground=t['debug_warning'])
        self.debug_text.tag_configure('error', foreground=t['debug_error'])
        self.debug_text.tag_configure('info', foreground=t['debug_info'])
        
        # Initial message
        self.log_debug("Debug log initialized. Load a file to see parsing details.", 'info')
    
    def update_summary(self):
        """Update summary view with log data statistics."""
        if not self.log_data:
            return
        
        self.summary_text.config(state=tk.NORMAL)
        self.summary_text.delete("1.0", tk.END)
        
        # File information
        summary = []
        summary.append("=" * 60)
        summary.append("LOG FILE SUMMARY")
        summary.append("=" * 60)
        summary.append(f"Filename: {self.log_data.filename}")
        summary.append(f"Timestamp: {self.log_data.file_timestamp}")
        summary.append(f"Format Version: {self.log_data.format_version}")
        summary.append(f"Total Records: {self.log_data.record_count}")
        summary.append(f"Total Fields: {self.log_data.field_count}")
        summary.append("")
        
        # Channel statistics
        summary.append("=" * 60)
        summary.append("CHANNEL STATISTICS")
        summary.append("=" * 60)
        summary.append(f"{'Channel':<30} {'Min':>10} {'Max':>10} {'Mean':>10}")
        summary.append("-" * 60)
        
        for channel in self.log_data.get_channel_names()[:20]:  # Limit to first 20
            stats = self.log_data.get_statistics(channel)
            summary.append(
                f"{channel:<30} {stats['min']:>10.2f} {stats['max']:>10.2f} {stats['mean']:>10.2f}"
            )
        
        if self.log_data.field_count > 20:
            summary.append(f"\n... and {self.log_data.field_count - 20} more channels")
        
        self.summary_text.insert("1.0", "\n".join(summary))
        self.summary_text.config(state=tk.DISABLED)
    
    def log_debug(self, message: str, tag: str = None) -> None:
        """Append a message to the debug log."""
        self.debug_text.config(state=tk.NORMAL)
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        
        if tag:
            self.debug_text.insert(tk.END, f"[{timestamp}] ", 'info')
            self.debug_text.insert(tk.END, f"{message}\n", tag)
        else:
            self.debug_text.insert(tk.END, f"[{timestamp}] {message}\n")
        
        self.debug_text.see(tk.END)
        self.debug_text.config(state=tk.DISABLED)
        self.update_idletasks()
    
    def clear_debug(self) -> None:
        """Clear the debug log."""
        self.debug_text.config(state=tk.NORMAL)
        self.debug_text.delete("1.0", tk.END)
        self.log_debug("Debug log cleared.", 'info')
    
    def save_debug_log(self) -> None:
        """Save debug log to a text file."""
        file_path = filedialog.asksaveasfilename(
            title="Save Debug Log",
            defaultextension=".txt",
            filetypes=[("Text Files", "*.txt"), ("All Files", "*.*")]
        )
        
        if not file_path:
            return
        
        try:
            with open(file_path, 'w') as f:
                f.write(self.debug_text.get("1.0", tk.END))
            self.log_debug(f"Debug log saved to {os.path.basename(file_path)}", 'success')
            messagebox.showinfo("Save Complete", f"Debug log saved to:\n{file_path}")
        except (IOError, OSError) as e:
            self.log_debug(f"Failed to save debug log: {str(e)}", 'error')
            messagebox.showerror("Save Error", f"Failed to save debug log:\n{str(e)}")
    
    def browse_folder(self):
        """Open folder browser dialog and populate file list."""
        initial_dir = self.current_directory or os.path.expanduser("~")
        folder_path = filedialog.askdirectory(
            title="Select Folder Containing .mlg Files",
            initialdir=initial_dir
        )
        
        if folder_path:
            self.current_directory = folder_path
            self._save_settings()
            self.populate_file_list()
    
    def populate_file_list(self):
        """Populate file listbox with .mlg files from current directory."""
        if not self.current_directory:
            return
        
        self.file_listbox.delete(0, tk.END)
        self.file_info.clear()
        
        try:
            # Get all .mlg files in directory
            mlg_files = []
            for file in os.listdir(self.current_directory):
                if file.lower().endswith('.mlg'):
                    mlg_files.append(file)
            
            # Sort files by name
            mlg_files.sort()
            
            # Update labels first
            dir_display = self.current_directory
            if len(dir_display) > 40:
                dir_display = f"...{dir_display[-40:]}"
            self.dir_label.config(text=dir_display, foreground="black")
            
            file_count_text = f"{len(mlg_files)} file{'s' if len(mlg_files) != 1 else ''}"
            self.file_count_label.config(text=file_count_text)
            
            # Parse each file to get record count
            for idx, file in enumerate(mlg_files, 1):
                file_path = os.path.join(self.current_directory, file)
                
                # Update status with progress
                self.statusbar.config(text=f"Scanning files... {idx}/{len(mlg_files)}")
                self.update_idletasks()
                
                try:
                    # Quick parse to get record count
                    parser = MLGParser(file_path)
                    parsed_data = parser.parse()
                    record_count = len(parsed_data['records'])
                    
                    # Store file info
                    self.file_info[file] = {
                        'records': record_count,
                        'size_mb': os.path.getsize(file_path) / (1024 * 1024)
                    }
                    
                    # Add to listbox with record count
                    display_text = f"{file} ({record_count:,} records)"
                    self.file_listbox.insert(tk.END, display_text)
                    
                except Exception as e:
                    # If parsing fails, still add the file but mark as error
                    self.file_info[file] = {'records': 0, 'size_mb': 0}
                    display_text = f"{file} (error reading)"
                    self.file_listbox.insert(tk.END, display_text)
            
            # Update status
            folder_name = os.path.basename(self.current_directory)
            self.statusbar.config(text=f"Found {len(mlg_files)} .mlg files in {folder_name}")
        
        except (OSError, PermissionError) as e:
            messagebox.showerror("Error", f"Cannot read directory:\n{str(e)}")
            self.statusbar.config(text="Error reading directory")
    
    def on_file_select(self, event, force_reload=False):
        """Handle file selection from listbox."""
        selection = self.file_listbox.curselection()
        if not selection:
            return
        
        # Extract filename from display text (format: "filename.mlg (X records)")
        display_text = self.file_listbox.get(selection[0])
        # Find the filename before the first " ("
        if " (" in display_text:
            selected_file = display_text.split(" (")[0]
        else:
            selected_file = display_text
        
        file_path = os.path.join(self.current_directory, selected_file)
        
        # Don't reload if it's already the current file (unless forced)
        if not force_reload and file_path == self.current_file:
            return
        
        # Load the file
        self.load_file(file_path)
    
    def open_file(self) -> None:
        """Open file dialog and load selected log file."""
        initial_dir = self.current_directory or os.path.join(os.getcwd(), "MyCar", "DataLogs") if os.path.exists("MyCar") else os.path.expanduser("~")
        
        file_path = filedialog.askopenfilename(
            title="Open Log File",
            filetypes=[("MegaLogViewer Files", "*.mlg"), ("All Files", "*.*")],
            initialdir=initial_dir
        )
        
        if not file_path:
            return
        
        # Update current directory and refresh file list
        new_directory = os.path.dirname(file_path)
        if new_directory != self.current_directory:
            self.current_directory = new_directory
            self._save_settings()
            self.populate_file_list()
        
        # Highlight the selected file in listbox
        filename = os.path.basename(file_path)
        for i in range(self.file_listbox.size()):
            display_text = self.file_listbox.get(i)
            # Extract filename from display text
            list_filename = display_text.split(" (")[0] if " (" in display_text else display_text
            if list_filename == filename:
                self.file_listbox.selection_clear(0, tk.END)
                self.file_listbox.selection_set(i)
                self.file_listbox.see(i)
                break
        
        self.load_file(file_path)
    
    def load_file(self, file_path):
        """Load log file from given path."""
        try:
            # Check file size
            file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
            if file_size_mb > self.MAX_FILE_SIZE_MB:
                result = messagebox.askyesno(
                    "Large File Warning",
                    f"File size is {file_size_mb:.1f} MB (>{self.MAX_FILE_SIZE_MB} MB).\n"
                    f"Loading may take time and use significant memory.\n\n"
                    f"Continue?"
                )
                if not result:
                    self.statusbar.config(text="Load cancelled")
                    return
            
            # Update status and debug log
            self.statusbar.config(text=f"Loading {os.path.basename(file_path)}...")
            self.update_idletasks()
            
            # Clear previous debug log
            self.debug_text.config(state=tk.NORMAL)
            self.debug_text.delete("1.0", tk.END)
            self.debug_text.config(state=tk.DISABLED)
            
            self.log_debug("=" * 70, 'header')
            self.log_debug(f"LOADING FILE: {os.path.basename(file_path)}", 'header')
            self.log_debug("=" * 70, 'header')
            self.log_debug(f"File path: {file_path}")
            self.log_debug(f"File size: {file_size_mb:.2f} MB")
            
            # Parse file
            self.log_debug("\nInitializing parser...", 'info')
            parser = MLGParser(file_path)
            self.log_debug("✓ Parser initialized", 'success')
            
            self.log_debug("\nParsing file structure...", 'info')
            parsed_data = parser.parse()
            
            # Log header information
            self.log_debug("\n" + "=" * 70, 'header')
            self.log_debug("HEADER INFORMATION", 'header')
            self.log_debug("=" * 70, 'header')
            header = parsed_data['header']
            self.log_debug(f"Format: {header['file_format']}")
            self.log_debug(f"Version: {header['format_version']}")
            self.log_debug(f"Timestamp: {header['timestamp']} ({datetime.fromtimestamp(header['timestamp'])})")
            self.log_debug(f"Info data start: {header['info_data_start']}")
            self.log_debug(f"Data begin index: {header['data_begin_index']}")
            self.log_debug(f"Record length: {header['record_length']}")
            self.log_debug(f"Number of logger fields: {header['num_logger_fields']}")
            
            # Log field information
            self.log_debug("\n" + "=" * 70, 'header')
            self.log_debug("FIELD DEFINITIONS", 'header')
            self.log_debug("=" * 70, 'header')
            self.log_debug(f"Total fields: {len(parsed_data['fields'])}")
            self.log_debug("\nFirst 10 fields:")
            for i, field in enumerate(parsed_data['fields'][:10]):
                self.log_debug(f"  {i+1}. {field['name']:30s} Type: {field['field_type']:2d}  "
                             f"Units: {field['units']:10s}  Scale: {field['scale']:.2f}  "
                             f"Transform: {field['transform']:.2f}")
            if len(parsed_data['fields']) > 10:
                self.log_debug(f"  ... and {len(parsed_data['fields']) - 10} more fields")
            
            # Log data parsing results
            self.log_debug("\n" + "=" * 70, 'header')
            self.log_debug("DATA PARSING RESULTS", 'header')
            self.log_debug("=" * 70, 'header')
            self.log_debug(f"Total records parsed: {len(parsed_data['records'])}")
            
            if parsed_data['records']:
                self.log_debug("\nFirst record sample (first 5 fields):")
                first_record = parsed_data['records'][0]
                for i, (key, value) in enumerate(list(first_record.items())[:5]):
                    self.log_debug(f"  {key}: {value}")
                
                self.log_debug("\nLast record sample (first 5 fields):")
                last_record = parsed_data['records'][-1]
                for i, (key, value) in enumerate(list(last_record.items())[:5]):
                    self.log_debug(f"  {key}: {value}")
            
            self.log_debug("\n" + "=" * 70, 'success')
            self.log_debug("✓ PARSING COMPLETED SUCCESSFULLY", 'success')
            self.log_debug("=" * 70, 'success')
            
            # Create data model
            self.log_data = LogData(parsed_data)
            self.current_file = file_path
            
            # Update UI components
            self.populate_grid(self.log_data)
            
            # Update channel dropdown and checkboxes
            channel_names = self.log_data.get_numeric_channel_names()
            self.channel_combo['values'] = channel_names
            if channel_names:
                self.channel_combo.current(0)
            
            # Populate channel selection checkboxes
            self.populate_channel_checkboxes()
            
            # Update summary
            self.update_summary()
            
            # Update window title and status
            self.title(f"MegaLogViewer - {self.log_data.filename}")
            self.statusbar.config(
                text=f"Loaded {self.log_data.record_count} records from {self.log_data.filename}"
            )
            
            self.log_debug(f"\n✓ UI updated successfully", 'success')
            self.log_debug(f"Ready for analysis and visualization.", 'info')
            
            # Highlight current file in browser
            filename = os.path.basename(file_path)
            for i in range(self.file_listbox.size()):
                display_text = self.file_listbox.get(i)
                # Extract filename from display text
                list_filename = display_text.split(" (")[0] if " (" in display_text else display_text
                if list_filename == filename:
                    self.file_listbox.selection_clear(0, tk.END)
                    self.file_listbox.selection_set(i)
                    self.file_listbox.see(i)
                    break
            
            # Auto-detect and load MSQ tune file from project structure
            self._auto_detect_msq(file_path)
            
            # Restore saved plot selections
            self._restore_plot_selections()
            
        except (ValueError, IOError) as e:
            self.log_debug(f"\n✗ PARSING FAILED", 'error')
            self.log_debug(f"Error: {str(e)}", 'error')
            messagebox.showerror("Error Loading File", f"Failed to load file:\n{str(e)}")
            self.statusbar.config(text="Error loading file")
        except (OSError, PermissionError) as e:
            self.log_debug(f"\n✗ FILE ACCESS FAILED", 'error')
            self.log_debug(f"Error: {str(e)}", 'error')
            messagebox.showerror("File Access Error", f"Could not access file:\n{str(e)}")
            self.statusbar.config(text="File access denied")
        except Exception as e:
            self.log_debug(f"\n✗ UNEXPECTED ERROR", 'error')
            self.log_debug(f"Error type: {type(e).__name__}", 'error')
            self.log_debug(f"Error message: {str(e)}", 'error')
            messagebox.showerror("Unexpected Error", f"An unexpected error occurred:\n{str(e)}")
            self.statusbar.config(text="Error loading file")
    
    def _get_settings_path(self) -> str:
        """Return path to settings file."""
        return os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            '.megalogviewer_settings.json'
        )
    
    def _load_settings(self):
        """Load application settings from config file."""
        settings_path = self._get_settings_path()
        try:
            if os.path.exists(settings_path):
                with open(settings_path, 'r') as f:
                    settings = json.load(f)
                self.current_directory = settings.get('last_directory')
                self.favorite_channels = set(settings.get('favorites', []))
                self.dark_mode = settings.get('dark_mode', False)
                self._saved_plot_selections = settings.get('plot_selections', {})
        except (json.JSONDecodeError, IOError, OSError):
            pass  # Use defaults on error
    
    def _save_settings(self):
        """Save application settings to config file."""
        settings_path = self._get_settings_path()
        try:
            settings = {
                'last_directory': self.current_directory,
                'favorites': sorted(self.favorite_channels),
                'dark_mode': self.dark_mode,
                'plot_selections': {str(k): v for k, v in self._plot_state.items()}
            }
            with open(settings_path, 'w') as f:
                json.dump(settings, f, indent=2)
        except (IOError, OSError):
            pass  # Silent fail for settings save
    
    def _restore_last_folder(self):
        """Restore the last opened folder on startup."""
        if self.current_directory and os.path.isdir(self.current_directory):
            self.populate_file_list()
    
    def export_csv(self):
        """Export current log data to CSV file."""
        if not self.log_data:
            messagebox.showwarning("No Data", "Please load a log file first.")
            return
        
        # Show save dialog
        file_path = filedialog.asksaveasfilename(
            title="Export to CSV",
            defaultextension=".csv",
            filetypes=[("CSV Files", "*.csv"), ("All Files", "*.*")]
        )
        
        if not file_path:
            return
        
        try:
            # Update status
            self.statusbar.config(text=f"Exporting to {os.path.basename(file_path)}...")
            self.update_idletasks()
            
            # Write CSV
            with open(file_path, 'w', newline='') as csvfile:
                fieldnames = self.log_data.get_channel_names()
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                
                writer.writeheader()
                for record in self.log_data.records:
                    writer.writerow(record)
            
            # Update status
            self.statusbar.config(text=f"Exported {self.log_data.record_count} records to CSV")
            messagebox.showinfo("Export Complete", f"Data exported successfully to:\n{file_path}")
            
        except (IOError, OSError) as e:
            messagebox.showerror("Export Error", f"Failed to export CSV:\n{str(e)}")
            self.statusbar.config(text="Export failed")
    
    # --- Tune Tab Methods ---
    
    def create_tune_view(self):
        """Create tune view with search and treeview for MSQ constants."""
        # Toolbar with search and file controls
        tune_toolbar = ttk.Frame(self.tune_tab)
        tune_toolbar.pack(side=tk.TOP, fill=tk.X, padx=5, pady=5)
        
        ttk.Button(
            tune_toolbar,
            text="Open Tune...",
            command=self.open_msq_file
        ).pack(side=tk.LEFT, padx=2)
        
        ttk.Button(
            tune_toolbar,
            text="Export Tune CSV",
            command=self.export_tune_csv
        ).pack(side=tk.LEFT, padx=2)
        
        ttk.Separator(tune_toolbar, orient=tk.VERTICAL).pack(
            side=tk.LEFT, fill=tk.Y, padx=10
        )
        
        # Search controls
        ttk.Label(tune_toolbar, text="Search:").pack(side=tk.LEFT, padx=(5, 2))
        self.tune_search_var = tk.StringVar()
        self.tune_search_var.trace_add('write', self._on_tune_search_changed)
        self.tune_search_entry = ttk.Entry(
            tune_toolbar,
            textvariable=self.tune_search_var,
            width=30
        )
        self.tune_search_entry.pack(side=tk.LEFT, padx=2)
        
        ttk.Button(
            tune_toolbar,
            text="Clear",
            command=lambda: self.tune_search_var.set('')
        ).pack(side=tk.LEFT, padx=2)
        
        # Filter by type
        ttk.Separator(tune_toolbar, orient=tk.VERTICAL).pack(
            side=tk.LEFT, fill=tk.Y, padx=10
        )
        ttk.Label(tune_toolbar, text="Type:").pack(side=tk.LEFT, padx=(5, 2))
        self.tune_type_var = tk.StringVar(value="All")
        self.tune_type_combo = ttk.Combobox(
            tune_toolbar,
            textvariable=self.tune_type_var,
            values=["All", "constant", "pcVariable"],
            width=12,
            state="readonly"
        )
        self.tune_type_combo.pack(side=tk.LEFT, padx=2)
        self.tune_type_combo.bind('<<ComboboxSelected>>', lambda e: self._apply_tune_filter())
        
        # Entry count label
        self.tune_count_label = ttk.Label(tune_toolbar, text="0 entries", foreground="gray")
        self.tune_count_label.pack(side=tk.RIGHT, padx=10)
        
        # Treeview with scrollbars
        tree_frame = ttk.Frame(self.tune_tab)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=(0, 5))
        
        vsb = ttk.Scrollbar(tree_frame, orient="vertical")
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        
        hsb = ttk.Scrollbar(tree_frame, orient="horizontal")
        hsb.pack(side=tk.BOTTOM, fill=tk.X)
        
        tune_columns = ('page', 'type', 'name', 'value', 'units', 'digits', 'dimensions')
        self.tune_tree = ttk.Treeview(
            tree_frame,
            columns=tune_columns,
            show='headings',
            yscrollcommand=vsb.set,
            xscrollcommand=hsb.set,
            selectmode='extended'
        )
        self.tune_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        vsb.config(command=self.tune_tree.yview)
        hsb.config(command=self.tune_tree.xview)
        
        # Configure columns
        column_config = {
            'page': ('Page', 60, 'center'),
            'type': ('Type', 90, 'w'),
            'name': ('Name', 250, 'w'),
            'value': ('Value', 300, 'w'),
            'units': ('Units', 80, 'center'),
            'digits': ('Digits', 60, 'center'),
            'dimensions': ('Dims', 60, 'center'),
        }
        
        for col_id, (heading, width, anchor) in column_config.items():
            self.tune_tree.column(col_id, width=width, minwidth=40, anchor=anchor)
            self.tune_tree.heading(
                col_id,
                text=heading,
                command=lambda c=col_id: self._sort_tune_by_column(c)
            )
        
        # Alternating row colors from theme
        t = self._get_theme()
        self.tune_tree.tag_configure('evenrow', background=t['treeview_even'])
        self.tune_tree.tag_configure('oddrow', background=t['treeview_odd'])
        self.tune_tree.tag_configure('table_row', foreground=t['tune_table_fg'])
        
        # Initial message
        self.tune_tree.insert(
            '', tk.END, values=('', '', 'No tune file loaded', 'Open a .msq file or load a log from a project folder', '', '', '')
        )
    
    def open_msq_file(self) -> None:
        """Open file dialog to select and load an MSQ tune file."""
        initial_dir = self.current_directory or os.path.expanduser('~')
        
        # Try to find an MSQ file in parent directory
        if self.current_directory:
            parent = os.path.dirname(self.current_directory)
            if parent:
                initial_dir = parent
        
        file_path = filedialog.askopenfilename(
            title="Open Tune File",
            filetypes=[
                ("MegaSquirt Tune Files", "*.msq"),
                ("All Files", "*.*")
            ],
            initialdir=initial_dir
        )
        
        if file_path:
            self.load_msq_file(file_path)
    
    def load_msq_file(self, file_path: str) -> None:
        """Load and parse an MSQ tune file."""
        try:
            self.statusbar.config(text=f"Loading tune file {os.path.basename(file_path)}...")
            self.update_idletasks()
            
            parser = MSQParser(file_path)
            self.msq_data = parser.parse()
            self.msq_file = file_path
            
            self.log_debug(f"Loaded tune file: {os.path.basename(file_path)}", 'success')
            self.log_debug(f"  Entries: {self.msq_data['entry_count']}", 'info')
            bib = self.msq_data.get('bibliography', {})
            if bib.get('author'):
                self.log_debug(f"  Author: {bib['author']}", 'info')
            if bib.get('writeDate'):
                self.log_debug(f"  Date: {bib['writeDate']}", 'info')
            
            self._populate_tune_tree()
            
            self.statusbar.config(
                text=f"Loaded {self.msq_data['entry_count']} tune entries from {os.path.basename(file_path)}"
            )
            
            # Switch to tune tab
            self.notebook.select(self.tune_tab)
            
        except ET.ParseError as e:
            messagebox.showerror("XML Parse Error", f"Failed to parse tune file:\n{str(e)}")
            self.statusbar.config(text="Error loading tune file")
        except (IOError, OSError) as e:
            messagebox.showerror("File Error", f"Could not read tune file:\n{str(e)}")
            self.statusbar.config(text="Error loading tune file")
        except Exception as e:
            messagebox.showerror("Error", f"Unexpected error loading tune file:\n{str(e)}")
            self.statusbar.config(text="Error loading tune file")
    
    def _populate_tune_tree(self) -> None:
        """Populate tune treeview with all entries."""
        if not self.msq_data:
            return
        
        self._apply_tune_filter()
    
    def _apply_tune_filter(self) -> None:
        """Apply search and type filters to tune treeview."""
        if not self.msq_data:
            return
        
        # Clear existing items
        for item in self.tune_tree.get_children():
            self.tune_tree.delete(item)
        
        search_text = self.tune_search_var.get().lower()
        type_filter = self.tune_type_var.get()
        
        filtered = []
        for entry in self.msq_data['entries']:
            # Type filter
            if type_filter != 'All' and entry['type'] != type_filter:
                continue
            
            # Search filter (match name, value, or units)
            if search_text:
                searchable = f"{entry['name']} {entry['value']} {entry['units']}".lower()
                if search_text not in searchable:
                    continue
            
            filtered.append(entry)
        
        # Apply current sort if active
        if self._tune_sort_column:
            filtered.sort(
                key=lambda e: e.get(self._tune_sort_column, ''),
                reverse=self._tune_sort_reverse
            )
        
        # Insert filtered entries
        for idx, entry in enumerate(filtered):
            tags = ('evenrow',) if idx % 2 == 0 else ('oddrow',)
            if entry['dimensions']:
                tags = tags + ('table_row',)
            
            self.tune_tree.insert(
                '', tk.END,
                values=(
                    entry['page'],
                    entry['type'],
                    entry['name'],
                    entry['value'],
                    entry['units'],
                    entry['digits'],
                    entry['dimensions'],
                ),
                tags=tags
            )
        
        # Update count label
        total = self.msq_data['entry_count']
        shown = len(filtered)
        if shown == total:
            self.tune_count_label.config(text=f"{total} entries")
        else:
            self.tune_count_label.config(text=f"{shown} of {total} entries")
    
    def _on_tune_search_changed(self, *args) -> None:
        """Handle tune search text changes."""
        if self.msq_data:
            self._apply_tune_filter()
    
    def _sort_tune_by_column(self, column: str) -> None:
        """Sort tune treeview by column."""
        if not self.msq_data:
            return
        
        if self._tune_sort_column == column:
            self._tune_sort_reverse = not self._tune_sort_reverse
        else:
            self._tune_sort_column = column
            self._tune_sort_reverse = False
        
        # Update column headers with sort indicators
        columns = ('page', 'type', 'name', 'value', 'units', 'digits', 'dimensions')
        headings = {'page': 'Page', 'type': 'Type', 'name': 'Name', 'value': 'Value',
                    'units': 'Units', 'digits': 'Digits', 'dimensions': 'Dims'}
        for col in columns:
            if col == column:
                indicator = ' \u25bc' if self._tune_sort_reverse else ' \u25b2'
                self.tune_tree.heading(col, text=f"{headings[col]}{indicator}")
            else:
                self.tune_tree.heading(col, text=headings[col])
        
        self._apply_tune_filter()
    
    def export_tune_csv(self) -> None:
        """Export tune data to CSV file."""
        if not self.msq_data:
            messagebox.showwarning("No Data", "Please load a tune file first.")
            return
        
        file_path = filedialog.asksaveasfilename(
            title="Export Tune to CSV",
            defaultextension=".csv",
            filetypes=[("CSV Files", "*.csv"), ("All Files", "*.*")]
        )
        
        if not file_path:
            return
        
        try:
            with open(file_path, 'w', newline='') as csvfile:
                writer = csv.DictWriter(
                    csvfile,
                    fieldnames=['page', 'type', 'name', 'value', 'units', 'digits', 'dimensions']
                )
                writer.writeheader()
                for entry in self.msq_data['entries']:
                    writer.writerow(entry)
            
            self.statusbar.config(text=f"Exported {self.msq_data['entry_count']} tune entries to CSV")
            messagebox.showinfo("Export Complete", f"Tune data exported to:\n{file_path}")
        except (IOError, OSError) as e:
            messagebox.showerror("Export Error", f"Failed to export tune CSV:\n{str(e)}")
    
    def _auto_detect_msq(self, log_file_path: str) -> None:
        """Auto-detect and load MSQ file from project directory structure."""
        # Walk up from the log file's directory to find an MSQ file
        log_dir = os.path.dirname(log_file_path)
        
        # Check parent directory (MyCar/DataLogs -> MyCar/CurrentTune.msq)
        parent_dir = os.path.dirname(log_dir)
        if parent_dir:
            for f in os.listdir(parent_dir):
                if f.lower().endswith('.msq'):
                    msq_path = os.path.join(parent_dir, f)
                    if msq_path != self.msq_file:
                        self.load_msq_file(msq_path)
                    return
        
        # Check same directory
        for f in os.listdir(log_dir):
            if f.lower().endswith('.msq'):
                msq_path = os.path.join(log_dir, f)
                if msq_path != self.msq_file:
                    self.load_msq_file(msq_path)
                return
    
    # --- Theme Methods ---
    
    def _get_theme(self) -> Dict[str, str]:
        """Return current theme color palette."""
        return LogViewerApp.DARK_THEME if self.dark_mode else LogViewerApp.LIGHT_THEME
    
    def toggle_dark_mode(self) -> None:
        """Toggle between light and dark mode."""
        self.dark_mode = not self.dark_mode
        self._apply_theme()
        self._save_settings()
    
    def _apply_theme(self) -> None:
        """Apply current theme colors to all widgets."""
        t = self._get_theme()
        
        # Root window
        self.configure(bg=t['bg'])
        
        # ttk style configuration
        style = ttk.Style(self)
        
        # Frame backgrounds
        style.configure('TFrame', background=t['bg'])
        style.configure('TLabel', background=t['bg'], foreground=t['fg'])
        style.configure('TButton', background=t['surface'], foreground=t['fg'])
        style.configure('TCheckbutton', background=t['bg'], foreground=t['fg'])
        style.configure('Toolbutton', background=t['bg'], foreground=t['fg'])
        
        # Notebook (tabs)
        style.configure('TNotebook', background=t['bg'])
        style.configure('TNotebook.Tab', background=t['surface'],
                        foreground=t['fg'], padding=[8, 4])
        style.map('TNotebook.Tab',
                  background=[('selected', t['accent']), ('active', t['highlight_bg'])],
                  foreground=[('selected', t['highlight_fg']), ('active', t['highlight_fg'])])
        
        # Treeview
        style.configure('Treeview',
                        background=t['surface'],
                        foreground=t['fg'],
                        fieldbackground=t['surface'],
                        bordercolor=t['border'],
                        lightcolor=t['border'],
                        darkcolor=t['border'])
        style.configure('Treeview.Heading',
                        background=t['surface_alt'],
                        foreground=t['fg'],
                        bordercolor=t['border'])
        style.map('Treeview',
                  background=[('selected', t['highlight_bg'])],
                  foreground=[('selected', t['highlight_fg'])])
        style.map('Treeview.Heading',
                  background=[('active', t['border'])])
        
        # Combobox
        style.configure('TCombobox',
                        fieldbackground=t['input_bg'],
                        foreground=t['input_fg'],
                        background=t['surface'],
                        selectbackground=t['highlight_bg'],
                        selectforeground=t['highlight_fg'])
        style.map('TCombobox',
                  fieldbackground=[('readonly', t['input_bg'])],
                  foreground=[('readonly', t['input_fg'])])
        
        # Entry
        style.configure('TEntry',
                        fieldbackground=t['input_bg'],
                        foreground=t['input_fg'])
        
        # Separator
        style.configure('TSeparator', background=t['border'])
        
        # PanedWindow
        style.configure('TPanedwindow', background=t['bg'])
        
        # Scrollbar
        style.configure('TScrollbar',
                        background=t['surface_alt'],
                        troughcolor=t['bg'],
                        bordercolor=t['border'])
        
        # Menu colors
        self._apply_menu_theme(self['menu'], t)
        
        # Statusbar
        if hasattr(self, 'statusbar'):
            self.statusbar.configure(
                background=t['statusbar_bg'],
                foreground=t['statusbar_fg']
            )
        
        # File browser listbox
        if hasattr(self, 'file_listbox'):
            self.file_listbox.configure(
                bg=t['listbox_bg'],
                fg=t['listbox_fg'],
                selectbackground=t['listbox_select_bg'],
                selectforeground=t['listbox_select_fg'],
                highlightbackground=t['border'],
                highlightcolor=t['accent']
            )
        
        # Directory label
        if hasattr(self, 'dir_label'):
            self.dir_label.configure(foreground=t['dir_label_fg'])
        
        # File count label
        if hasattr(self, 'file_count_label'):
            self.file_count_label.configure(foreground=t['dir_label_fg'])
        
        # Channel canvas
        if hasattr(self, 'channel_canvas'):
            self.channel_canvas.configure(bg=t['bg'], highlightbackground=t['border'])
        
        # Update star labels in channel checkboxes
        if hasattr(self, '_channel_fav_labels'):
            for channel, lbl in self._channel_fav_labels.items():
                is_fav = channel in self.favorite_channels
                lbl.configure(
                    bg=t['star_bg'],
                    fg=t['star_active'] if is_fav else t['star_inactive']
                )
        
        # Summary text widget
        if hasattr(self, 'summary_text'):
            self.summary_text.configure(
                bg=t['summary_bg'],
                fg=t['summary_fg'],
                insertbackground=t['fg']
            )
        
        # Debug text widget
        if hasattr(self, 'debug_text'):
            self.debug_text.configure(
                bg=t['debug_bg'],
                fg=t['debug_fg'],
                insertbackground=t['fg']
            )
            self.debug_text.tag_configure('header', foreground=t['debug_header'])
            self.debug_text.tag_configure('success', foreground=t['debug_success'])
            self.debug_text.tag_configure('warning', foreground=t['debug_warning'])
            self.debug_text.tag_configure('error', foreground=t['debug_error'])
            self.debug_text.tag_configure('info', foreground=t['debug_info'])
        
        # Data grid row colors
        if hasattr(self, 'data_tree'):
            self.data_tree.tag_configure('evenrow', background=t['treeview_even'])
            self.data_tree.tag_configure('oddrow', background=t['treeview_odd'])
        
        # Tune tree row colors
        if hasattr(self, 'tune_tree'):
            self.tune_tree.tag_configure('evenrow', background=t['treeview_even'])
            self.tune_tree.tag_configure('oddrow', background=t['treeview_odd'])
            self.tune_tree.tag_configure('table_row', foreground=t['tune_table_fg'])
        
        # Tune count label
        if hasattr(self, 'tune_count_label'):
            self.tune_count_label.configure(foreground=t['dir_label_fg'])
        
        # Matplotlib figure
        if hasattr(self, 'fig'):
            self._apply_plot_theme()
        
        # Update page label
        if hasattr(self, 'page_label'):
            self.page_label.configure(background=t['bg'], foreground=t['fg'])
    
    def _apply_menu_theme(self, menu_path: str, t: Dict[str, str]) -> None:
        """Apply theme to menus recursively."""
        try:
            menu_widget = self.nametowidget(menu_path)
            if isinstance(menu_widget, tk.Menu):
                menu_widget.configure(
                    bg=t['menu_bg'],
                    fg=t['menu_fg'],
                    activebackground=t['highlight_bg'],
                    activeforeground=t['highlight_fg'],
                    selectcolor=t['accent']
                )
                # Apply to submenus
                last = menu_widget.index(tk.END)
                if last is not None:
                    for i in range(last + 1):
                        try:
                            submenu = menu_widget.entrycget(i, 'menu')
                            if submenu:
                                self._apply_menu_theme(submenu, t)
                        except tk.TclError:
                            continue
        except (tk.TclError, KeyError):
            pass
    
    def _apply_plot_theme(self) -> None:
        """Apply current theme to matplotlib figure and axes."""
        t = self._get_theme()
        
        self.fig.set_facecolor(t['plot_face'])
        
        for ax in self.axes:
            ax.set_facecolor(t['plot_bg'])
            ax.tick_params(colors=t['plot_tick'], labelsize=7)
            ax.xaxis.label.set_color(t['plot_text'])
            ax.yaxis.label.set_color(t['plot_text'])
            ax.title.set_color(t['plot_text'])
            for spine in ax.spines.values():
                spine.set_color(t['plot_spine'])
            ax.grid(True, alpha=0.3, color=t['plot_grid'])
        
        self.fig.tight_layout(pad=2.0)
        self.canvas.draw()
    
    def show_about(self) -> None:
        """Show about dialog."""
        messagebox.showinfo(
            "About MegaLogViewer",
            "MegaLogViewer\n"
            "Version 2.0\n\n"
            "A Python application for viewing and analyzing\n"
            "TunerStudio MS MegaSquirt .mlg log files.\n\n"
            "Features:\n"
            "\u2022 Browse folders and select files\n"
            "\u2022 View log data in tabular format\n"
            "\u2022 Plot channels over time\n"
            "\u2022 Export data to CSV\n"
            "\u2022 View MSQ tune file constants\n"
            "\u2022 Sort columns by clicking headers\n\n"
            "Built with tkinter and matplotlib"
        )


if __name__ == "__main__":
    """Entry point for MegaLogViewer application."""
    app = LogViewerApp()
    app.mainloop()
