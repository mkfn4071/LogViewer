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
import sys
import traceback
import threading
import queue
import ctypes
from PIL import Image, ImageDraw, ImageTk
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.ticker import AutoMinorLocator
import numpy as np
from mpl_toolkits.mplot3d import Axes3D


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
    
    def parse_data_blocks(self, header: Dict, fields: List[Dict],
                          progress_callback=None, cancelled_fn=None) -> List[Dict[str, Any]]:
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
        
        # Estimate total records for progress reporting
        data_remaining = len(self.data) - self.offset
        bytes_per_record = self.RECORD_HEADER_SIZE + record_size + self.RECORD_CRC_SIZE
        estimated_total = max(1, data_remaining // bytes_per_record)
        
        # Read records until end of file
        max_records = self.MAX_RECORDS
        record_count = 0
        
        while self.offset + self.RECORD_HEADER_SIZE <= len(self.data) and record_count < max_records:
            if cancelled_fn and record_count % 500 == 0 and cancelled_fn():
                break
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
                    
                    if progress_callback and record_count % 500 == 0:
                        progress_callback(record_count, estimated_total)
                
                elif block_type == 1:
                    # Marker record - skip message
                    self.offset += self.MARKER_MESSAGE_LENGTH
                
                else:
                    # Unknown block type - skip remaining data
                    break
                    
            except (struct.error, IndexError):
                # End of file or corrupted data
                break
        
        if progress_callback:
            progress_callback(record_count, record_count)
        
        return records
    
    def parse(self, progress_callback=None, cancelled_fn=None) -> Dict[str, Any]:
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
        result['records'] = self.parse_data_blocks(
            result['header'], result['fields'], progress_callback, cancelled_fn)
        
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
    
    # Channel tuning priority: lower number = more important for tuning.
    # Channels not listed get a default priority that sorts them after all listed ones.
    CHANNEL_TUNING_PRIORITY = {
        # Tier 1 — Core tuning channels (always need these)
        'Time':         10,
        'SecL':         11,
        'RPM':          20,
        'MAP':          30,
        'TPS':          40,
        'AFR':          50,
        'AFR1':         51,
        'AFR2':         52,
        'afr1':         53,
        'afr2':         54,
        'Lambda':       55,
        'lambda':       56,
        'AFRtgt':       60,
        'AFRtrgt1':     61,
        'AFRerr1':      62,
        'EGOcor1':      63,
        'EGOcor2':      64,
        'Advance':      70,
        'SpkAdv':       71,
        'Spark':        72,
        'VE1':          80,
        'VE':           81,
        'VEcurr1':      82,
        'PW':           90,
        'PW1':          91,
        'PW2':          92,
        'pw1':          93,
        'pw2':          94,
        'DutyCy1':      95,
        'DutyCy2':      96,
        'Inj Duty':     97,

        # Tier 2 — Sensors and engine state
        'CLT':         100,
        'Coolant':     101,
        'MAT':         110,
        'IAT':         111,
        'IAT2':        112,
        'Baro':        120,
        'BaroADC':     121,
        'Battery':     130,
        'BattV':       131,
        'batt':        132,

        # Tier 3 — Fueling corrections
        'GammaE':      200,
        'Gair':        201,
        'Gbaro':       202,
        'Gwarm':       203,
        'Gcrank':      204,
        'Gase':        205,
        'Gtotal':      206,
        'WallFuel1':   210,
        'WallFuel2':   211,
        'AccelEnrich': 220,
        'Accel':       221,
        'TPSdot':      222,
        'MAPdot':      223,

        # Tier 4 — Idle and closed-loop control
        'IdleDC':      300,
        'IdleAdv':     301,
        'IdleTarget':  302,
        'IACV':        303,
        'Idle_dcA':    304,
        'IAC':         305,

        # Tier 5 — Boost and turbo
        'Boost':       400,
        'BoostTgt':    401,
        'BoostDuty':   402,
        'boost_targ':  403,
        'bcDC':        404,

        # Tier 6 — Knock
        'Knock':       500,
        'KnockCnt':    501,
        'KnockRet':    502,
        'knock':       503,

        # Tier 7 — Speed, gear, launch
        'VSS':         600,
        'VSS1':        601,
        'VSS2':        602,
        'Gear':        610,
        'Launch':      620,
        'FlatShift':   621,
        'NitOn':       625,
        'N2Otime1':    626,

        # Tier 8 — VVT / Cam
        'VVTtgt':      700,
        'VVTact':      701,
        'VVTerr':      702,
        'VVTduty':     703,

        # Tier 9 — EGT, fuel/oil pressure, flex
        'EGT1':        800,
        'EGT2':        801,
        'EGT3':        802,
        'EGT4':        803,
        'FuelPress':   810,
        'OilPress':    811,
        'FuelP':       812,
        'OilP':        813,
        'FlexFuel':    820,
        'EthPct':      821,

        # Tier 10 — CAN, status, diagnostic
        'Sync':        900,
        'SyncReason':  901,
        'Status1':     910,
        'Status2':     911,
        'Status3':     912,
        'CEL':         920,
        'Errors':      921,
        'Porta':       950,
        'Portb':       951,
        'Portc':       952,
    }
    _DEFAULT_PRIORITY = 999

    def _channel_sort_key(self, name: str) -> Tuple[int, str]:
        """Return sort key (priority, name) for a channel."""
        prio = self.CHANNEL_TUNING_PRIORITY.get(name, self._DEFAULT_PRIORITY)
        return (prio, name.lower())

    def get_numeric_channel_names(self) -> List[str]:
        """Return list of numeric data channels sorted by tuning importance."""
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
        numeric_channels.sort(key=self._channel_sort_key)
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

    def add_calculated_channel(self, name: str, units: str,
                               compute_fn, digits: int = 1) -> None:
        """Add a calculated channel derived from existing record data.

        Args:
            name: Channel name for the new field.
            units: Display units (e.g. '%').
            compute_fn: Callable(record) -> float or None.  Return None to
                        skip (the record will store 0.0).
            digits: Decimal digits for display.
        """
        # Register as a field so it appears in channel lists and the data grid
        self.fields.append({
            'name': name,
            'units': units,
            'field_type': 0,
            'display_style': 0,
            'scale': 1.0,
            'transform': 0.0,
            'digits': digits,
        })
        self.field_count = len(self.fields)

        # Compute and inject the value into every record
        for record in self.records:
            val = compute_fn(record)
            record[name] = val if val is not None else 0.0


class ToolTip:
    """Apple-style rounded tooltip with subtle shadow."""

    SHOW_DELAY_MS = 500
    OFFSET_Y = 4
    PADDING = (10, 6, 10, 6)
    CORNER_RADIUS = 8

    def __init__(self, widget: tk.Widget, text: str, theme_callback=None):
        self.widget = widget
        self.text = text
        self.theme_callback = theme_callback
        self._tipwindow: Optional[tk.Toplevel] = None
        self._show_id: Optional[str] = None
        self._img = None

        widget.bind('<Enter>', self._schedule_show, add='+')
        widget.bind('<Leave>', self._hide, add='+')
        widget.bind('<Button>', self._hide, add='+')

    def update_text(self, text: str) -> None:
        self.text = text

    def _schedule_show(self, _event=None):
        self._cancel()
        self._show_id = self.widget.after(self.SHOW_DELAY_MS, self._show)

    def _cancel(self):
        if self._show_id:
            self.widget.after_cancel(self._show_id)
            self._show_id = None

    def _hide(self, _event=None):
        self._cancel()
        if self._tipwindow:
            self._tipwindow.destroy()
            self._tipwindow = None
            self._img = None

    def _show(self):
        if self._tipwindow or not self.text:
            return

        tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_attributes('-topmost', True)

        img = self._render_image()
        self._img = ImageTk.PhotoImage(img, master=tw)

        transparent = '#f0f0f0'
        try:
            tw.attributes('-transparentcolor', transparent)
            tw.configure(bg=transparent)
            lbl = tk.Label(tw, image=self._img, bg=transparent, bd=0)
        except tk.TclError:
            tw.configure(bg='#333333')
            lbl = tk.Label(tw, image=self._img, bd=0)
        lbl.pack()

        tw.update_idletasks()
        tw_w = tw.winfo_reqwidth()
        tw_h = tw.winfo_reqheight()

        x = self.widget.winfo_rootx() + self.widget.winfo_width() // 2 - tw_w // 2
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + self.OFFSET_Y

        screen_w = self.widget.winfo_screenwidth()
        screen_h = self.widget.winfo_screenheight()
        if x + tw_w > screen_w:
            x = screen_w - tw_w - 4
        if x < 0:
            x = 4
        if y + tw_h > screen_h:
            y = self.widget.winfo_rooty() - tw_h - self.OFFSET_Y

        tw.wm_geometry(f'+{x}+{y}')
        self._tipwindow = tw

        try:
            hwnd = ctypes.windll.user32.GetParent(tw.winfo_id())
            val = ctypes.c_int(2)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, 33, ctypes.byref(val), ctypes.sizeof(val))
        except Exception:
            pass

    def _render_image(self) -> Image.Image:
        t = self.theme_callback() if self.theme_callback else {}
        bg_hex = t.get('surface_alt', '#333333')
        fg_hex = t.get('fg', '#FFFFFF')

        from PIL import ImageFont
        try:
            font = ImageFont.truetype('segoeui.ttf', 13)
        except OSError:
            font = ImageFont.load_default()

        dummy = Image.new('RGBA', (1, 1))
        bbox = ImageDraw.Draw(dummy).textbbox((0, 0), self.text, font=font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]

        pad = self.PADDING
        w = tw + pad[0] + pad[2]
        h = th + pad[1] + pad[3]
        shadow = 6

        img = Image.new('RGBA', (w + shadow * 2, h + shadow * 2), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        draw.rounded_rectangle(
            [(shadow + 2, shadow + 2), (shadow + w + 1, shadow + h + 1)],
            radius=self.CORNER_RADIUS, fill=(0, 0, 0, 35))

        r, g, b = int(bg_hex[1:3], 16), int(bg_hex[3:5], 16), int(bg_hex[5:7], 16)
        draw.rounded_rectangle(
            [(shadow, shadow), (shadow + w - 1, shadow + h - 1)],
            radius=self.CORNER_RADIUS, fill=(r, g, b, 230))

        r2, g2, b2 = int(fg_hex[1:3], 16), int(fg_hex[3:5], 16), int(fg_hex[5:7], 16)
        draw.text((shadow + pad[0], shadow + pad[1]), self.text,
                  fill=(r2, g2, b2, 255), font=font)

        return img


class LogViewerApp(tk.Tk):
    """
    Main application window for MegaLogViewer.
    """
    
    # Class constants
    PAGE_SIZE = 1000
    MAX_FILE_SIZE_MB = 500
    WINDOW_WIDTH = 1200
    WINDOW_HEIGHT = 800
    
    # Theme crossfade animation
    _THEME_ANIM_FRAMES = 15
    _THEME_ANIM_INTERVAL_MS = 20  # 15 × 20 ms ≈ 300 ms
    
    # Apple-style theme color palettes
    LIGHT_THEME = {
        'bg': '#ECECEC',
        'fg': '#000000',
        'surface': '#FFFFFF',
        'surface_alt': '#F4F5F5',
        'border': '#C6C6C8',
        'accent': '#007AFF',
        'highlight_bg': '#007AFF',
        'highlight_fg': '#FFFFFF',
        'treeview_even': '#FFFFFF',
        'treeview_odd': '#F4F5F5',
        'input_bg': '#FFFFFF',
        'input_fg': '#000000',
        'menu_bg': '#F5F5F5',
        'menu_fg': '#000000',
        'statusbar_bg': '#F5F5F5',
        'statusbar_fg': '#8E8E93',
        'debug_bg': '#FFFFFF',
        'debug_fg': '#000000',
        'debug_header': '#007AFF',
        'debug_success': '#34C759',
        'debug_warning': '#FF9500',
        'debug_error': '#FF3B30',
        'debug_info': '#8E8E93',
        'summary_bg': '#FFFFFF',
        'summary_fg': '#000000',
        'listbox_bg': '#FFFFFF',
        'listbox_fg': '#000000',
        'listbox_select_bg': '#007AFF',
        'listbox_select_fg': '#FFFFFF',
        'star_active': '#FF9F0A',
        'star_inactive': '#C5C5C7',
        'star_bg': '#ECECEC',
        'tune_table_fg': '#007AFF',
        'dir_label_fg': '#8E8E93',
        'dir_label_active_fg': '#000000',
        'plot_bg': '#FFFFFF',
        'plot_face': '#FFFFFF',
        'plot_text': '#000000',
        'plot_grid': '#E5E5EA',
        'plot_spine': '#C6C6C8',
        'plot_tick': '#000000',
        'canvas_bg': '#FFFFFF',
    }
    
    DARK_THEME = {
        'bg': '#1E1E1E',
        'fg': '#FFFFFF',
        'surface': '#232324',
        'surface_alt': '#2A2A2B',
        'border': '#3D3D40',
        'accent': '#0A84FF',
        'highlight_bg': '#0058D0',
        'highlight_fg': '#FFFFFF',
        'treeview_even': '#232324',
        'treeview_odd': '#2A2A2B',
        'input_bg': '#3A3A3C',
        'input_fg': '#FFFFFF',
        'menu_bg': '#2B2B2D',
        'menu_fg': '#FFFFFF',
        'statusbar_bg': '#2B2B2D',
        'statusbar_fg': '#98989D',
        'debug_bg': '#1E1E1E',
        'debug_fg': '#FFFFFF',
        'debug_header': '#0A84FF',
        'debug_success': '#30D158',
        'debug_warning': '#FF9F0A',
        'debug_error': '#FF453A',
        'debug_info': '#98989D',
        'summary_bg': '#1E1E1E',
        'summary_fg': '#FFFFFF',
        'listbox_bg': '#232324',
        'listbox_fg': '#FFFFFF',
        'listbox_select_bg': '#0058D0',
        'listbox_select_fg': '#FFFFFF',
        'star_active': '#FF9F0A',
        'star_inactive': '#545456',
        'star_bg': '#1E1E1E',
        'tune_table_fg': '#0A84FF',
        'dir_label_fg': '#98989D',
        'dir_label_active_fg': '#FFFFFF',
        'plot_bg': '#1E1E1E',
        'plot_face': '#232324',
        'plot_text': '#FFFFFF',
        'plot_grid': '#48484A',
        'plot_spine': '#3D3D40',
        'plot_tick': '#FFFFFF',
        'canvas_bg': '#1E1E1E',
    }
    
    # Apple system plot color palettes
    PLOT_COLORS_LIGHT = [
        '#007AFF',  # Blue
        '#FF9500',  # Orange
        '#34C759',  # Green
        '#FF3B30',  # Red
        '#AF52DE',  # Purple
        '#5AC8FA',  # Teal
        '#FF2D55',  # Pink
        '#FFCC00',  # Yellow
        '#8E8E93',  # Gray
        '#00C7BE',  # Mint
    ]
    
    PLOT_COLORS_DARK = [
        '#0A84FF',  # Blue
        '#FF9F0A',  # Orange
        '#30D158',  # Green
        '#FF453A',  # Red
        '#BF5AF2',  # Purple
        '#64D2FF',  # Teal
        '#FF375F',  # Pink
        '#FFD60A',  # Yellow
        '#98989D',  # Gray
        '#63E6E2',  # Mint
    ]
    
    # Apple accent color palette
    ACCENT_COLORS = {
        'Blue':     {'light': '#007AFF', 'dark': '#0A84FF'},
        'Purple':   {'light': '#AF52DE', 'dark': '#BF5AF2'},
        'Pink':     {'light': '#FF2D55', 'dark': '#FF375F'},
        'Red':      {'light': '#FF3B30', 'dark': '#FF453A'},
        'Orange':   {'light': '#FF9500', 'dark': '#FF9F0A'},
        'Yellow':   {'light': '#FFCC00', 'dark': '#FFD60A'},
        'Green':    {'light': '#34C759', 'dark': '#30D158'},
        'Graphite': {'light': '#8E8E93', 'dark': '#98989D'},
    }
    
    @staticmethod
    def _detect_font() -> str:
        """Detect best available font: SF Pro > Segoe UI."""
        try:
            import tkinter.font as tkfont
            root = tk._default_root
            if root:
                available = tkfont.families(root)
                for candidate in ('SF Pro Text', 'SF Pro', 'SF Pro Display'):
                    if candidate in available:
                        return candidate
        except Exception:
            pass
        return 'Segoe UI'
    
    @staticmethod
    def _detect_system_dark_mode() -> bool:
        """Detect Windows system dark mode from registry."""
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r'Software\Microsoft\Windows\CurrentVersion\Themes\Personalize'
            )
            value, _ = winreg.QueryValueEx(key, 'AppsUseLightTheme')
            winreg.CloseKey(key)
            return value == 0  # 0 = dark mode, 1 = light mode
        except Exception:
            return False  # Default to light mode

    def _apply_dark_title_bar(self) -> None:
        """Apply dark/light title bar on Windows 10+ using DWM API."""
        try:
            hwnd = ctypes.windll.user32.GetParent(self.winfo_id())
            DWMWA_USE_IMMERSIVE_DARK_MODE = 20
            value = ctypes.c_int(1 if self.dark_mode else 0)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE,
                ctypes.byref(value), ctypes.sizeof(value)
            )
        except Exception:
            pass

    @staticmethod
    def _apply_rounded_corners(hwnd: int) -> None:
        """Apply rounded corners to a window via DWM on Windows 11+."""
        try:
            DWMWA_WINDOW_CORNER_PREFERENCE = 33
            DWMWCP_ROUND = ctypes.c_int(2)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, DWMWA_WINDOW_CORNER_PREFERENCE,
                ctypes.byref(DWMWCP_ROUND), ctypes.sizeof(DWMWCP_ROUND)
            )
        except Exception:
            pass

    def _round_combobox_popdowns(self) -> None:
        """Apply rounded corners to all combobox popdown windows."""
        for combo in self._get_all_comboboxes():
            try:
                popdown_path = str(combo) + '.popdown'
                popdown = self.nametowidget(popdown_path)
                popdown_id = popdown.winfo_id()
                hwnd = ctypes.windll.user32.GetParent(popdown_id)
                self._apply_rounded_corners(hwnd)
            except Exception:
                pass

    def _get_all_comboboxes(self) -> List[ttk.Combobox]:
        """Collect all Combobox widgets in the application."""
        combos = []
        def _walk(widget):
            if isinstance(widget, ttk.Combobox):
                combos.append(widget)
            for child in widget.winfo_children():
                _walk(child)
        _walk(self)
        return combos

    def _create_tab_images(self, theme: Dict[str, str]) -> None:
        """Generate DPI-scaled rounded-rectangle tab images for each state."""
        scale = getattr(self, '_dpi_scale', 1.0)
        w = int(48 * scale)
        h = int(28 * scale)
        radius = int(6 * scale)
        border = max(int(6 * scale), 1)

        def _make_pill(fill_color):
            img = Image.new('RGBA', (w, h), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)
            draw.rounded_rectangle(
                [(0, 0), (w - 1, h - 1)], radius=radius, fill=fill_color)
            return img

        pil_rest = _make_pill(theme['surface_alt'])
        pil_selected = _make_pill(theme['accent'])
        pil_hover = _make_pill(theme['surface'])

        if hasattr(self, '_tab_img_rest'):
            # Update existing images in place so the element picks up new colors
            self._tab_img_rest.paste(pil_rest)
            self._tab_img_selected.paste(pil_selected)
            self._tab_img_hover.paste(pil_hover)
        else:
            self._tab_img_rest = ImageTk.PhotoImage(pil_rest, master=self)
            self._tab_img_selected = ImageTk.PhotoImage(pil_selected, master=self)
            self._tab_img_hover = ImageTk.PhotoImage(pil_hover, master=self)
            self._tab_border = border
    
    def _create_close_images(self, theme: Dict[str, str]) -> None:
        """Generate DPI-scaled × close-button images for notebook tabs."""
        scale = getattr(self, '_dpi_scale', 1.0)
        size = int(14 * scale)
        margin = int(3 * scale)
        lw = max(int(1.5 * scale), 1)

        def _make_x(fg_color, bg_color=None):
            img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)
            if bg_color:
                r, g, b = int(bg_color[1:3], 16), int(bg_color[3:5], 16), int(bg_color[5:7], 16)
                draw.ellipse([(0, 0), (size - 1, size - 1)], fill=(r, g, b, 180))
            r, g, b = int(fg_color[1:3], 16), int(fg_color[3:5], 16), int(fg_color[5:7], 16)
            draw.line([(margin, margin), (size - margin - 1, size - margin - 1)],
                      fill=(r, g, b, 255), width=lw)
            draw.line([(size - margin - 1, margin), (margin, size - margin - 1)],
                      fill=(r, g, b, 255), width=lw)
            return img

        pil_normal = _make_x(theme['statusbar_fg'])
        pil_hover = _make_x(theme['fg'], theme['surface_alt'])
        pil_pressed = _make_x(theme['highlight_fg'], theme['accent'])

        if hasattr(self, '_close_img_normal'):
            self._close_img_normal.paste(pil_normal)
            self._close_img_hover.paste(pil_hover)
            self._close_img_pressed.paste(pil_pressed)
        else:
            self._close_img_normal = ImageTk.PhotoImage(pil_normal, master=self)
            self._close_img_hover = ImageTk.PhotoImage(pil_hover, master=self)
            self._close_img_pressed = ImageTk.PhotoImage(pil_pressed, master=self)

    # ── Tab animation helpers ──────────────────────────────────────────
    _TAB_ANIM_FRAMES = 8
    _TAB_ANIM_INTERVAL_MS = 18  # ~150 ms total

    @staticmethod
    def _lerp_color(c1: str, c2: str, t: float) -> str:
        """Linearly interpolate between two hex colours."""
        r1, g1, b1 = int(c1[1:3], 16), int(c1[3:5], 16), int(c1[5:7], 16)
        r2, g2, b2 = int(c2[1:3], 16), int(c2[3:5], 16), int(c2[5:7], 16)
        r = int(r1 + (r2 - r1) * t)
        g = int(g1 + (g2 - g1) * t)
        b = int(b1 + (b2 - b1) * t)
        return f'#{r:02x}{g:02x}{b:02x}'

    def _on_tab_changed(self, _event=None) -> None:
        """Kick off a colour-fade animation on the newly selected tab."""
        if getattr(self, '_tab_anim_id', None):
            self.after_cancel(self._tab_anim_id)
            self._tab_anim_id = None

        theme = self._get_theme()
        self._tab_anim_from = theme['surface_alt']  # rest colour
        self._tab_anim_to = theme['accent']          # selected colour
        self._tab_anim_step = 0
        self._animate_tab_step()

    def _animate_tab_step(self) -> None:
        """Render one animation frame, schedule the next or finish."""
        n = self._TAB_ANIM_FRAMES
        step = self._tab_anim_step
        t = step / n  # 0 → 1
        # Ease-out quad
        t = 1 - (1 - t) * (1 - t)

        mid = self._lerp_color(self._tab_anim_from, self._tab_anim_to, t)

        scale = getattr(self, '_dpi_scale', 1.0)
        w, h = int(48 * scale), int(28 * scale)
        radius = int(6 * scale)
        img = Image.new('RGBA', (w, h), (0, 0, 0, 0))
        ImageDraw.Draw(img).rounded_rectangle(
            [(0, 0), (w - 1, h - 1)], radius=radius, fill=mid)
        self._tab_img_selected.paste(img)

        self._tab_anim_step += 1
        if self._tab_anim_step <= n:
            self._tab_anim_id = self.after(
                self._TAB_ANIM_INTERVAL_MS, self._animate_tab_step)
        else:
            self._tab_anim_id = None

    # ── Tab close button handlers ──────────────────────────────────────

    def _on_tab_click(self, event) -> Optional[str]:
        """Intercept clicks on the close button element and start drag tracking."""
        element = self.notebook.identify(event.x, event.y)
        if 'close' in str(element):
            index = self.notebook.index(f'@{event.x},{event.y}')
            self._close_tab(index)
            return 'break'
        # Track potential drag start
        try:
            self._drag_tab_index = self.notebook.index(f'@{event.x},{event.y}')
            self._drag_start_x = event.x
        except tk.TclError:
            self._drag_tab_index = None
        return None

    def _on_tab_drag(self, event) -> None:
        """Move tab during drag if threshold exceeded."""
        if getattr(self, '_drag_tab_index', None) is None:
            return
        if self._drag_tab_index == 0:
            self._drag_tab_index = None
            return
        if abs(event.x - self._drag_start_x) < 5:
            return
        self.notebook.configure(cursor='fleur')
        try:
            target = self.notebook.index(f'@{event.x},{event.y}')
        except tk.TclError:
            return
        if target == 0:
            target = 1
        if target != self._drag_tab_index:
            tab_id = self.notebook.tabs()[self._drag_tab_index]
            self.notebook.insert(target, tab_id)
            self._drag_tab_index = target

    def _on_tab_drag_end(self, _event=None) -> None:
        """End drag operation and reset cursor."""
        self._drag_tab_index = None
        self.notebook.configure(cursor='')

    def _close_tab(self, index: int) -> None:
        """Hide a tab (preserves widget state). Protects the first tab."""
        if index == 0:
            return  # Data Grid tab cannot be closed
        tab_id = self.notebook.tabs()[index]
        self.notebook.hide(tab_id)

    def _show_tab(self, tab_widget) -> None:
        """Restore a previously hidden tab."""
        self.notebook.add(tab_widget)
        self.notebook.select(tab_widget)

    # ── Sidebar animation ──────────────────────────────────────────────
    _SIDEBAR_ANIM_FRAMES = 12
    _SIDEBAR_ANIM_INTERVAL_MS = 16

    def _toggle_sidebar(self) -> None:
        """Toggle sidebar visibility with smooth slide animation."""
        if getattr(self, '_sidebar_anim_id', None):
            self.after_cancel(self._sidebar_anim_id)

        current_pos = self.paned_window.sashpos(0)

        if current_pos > 10:
            self._sidebar_saved_pos = current_pos
            self._sidebar_anim_from = current_pos
            self._sidebar_anim_to = 0
            self._sidebar_collapsed = True
        else:
            target = getattr(self, '_sidebar_saved_pos', 250)
            self._sidebar_anim_from = current_pos
            self._sidebar_anim_to = target
            self._sidebar_collapsed = False

        self._sidebar_anim_step = 0
        self._animate_sidebar_step()

    def _animate_sidebar_step(self) -> None:
        """Render one sidebar slide frame."""
        n = self._SIDEBAR_ANIM_FRAMES
        step = self._sidebar_anim_step
        t = step / n
        t = 1 - (1 - t) ** 3  # Ease-out cubic

        pos = int(self._sidebar_anim_from +
                  (self._sidebar_anim_to - self._sidebar_anim_from) * t)
        try:
            self.paned_window.sashpos(0, pos)
        except Exception:
            pass

        self._sidebar_anim_step += 1
        if self._sidebar_anim_step <= n:
            self._sidebar_anim_id = self.after(
                self._SIDEBAR_ANIM_INTERVAL_MS, self._animate_sidebar_step)
        else:
            self._sidebar_anim_id = None

    # ── Keyboard shortcuts overlay ─────────────────────────────────────

    SHORTCUTS = [
        ('File', [
            ('Ctrl+O', 'Open Log Folder'),
            ('Ctrl+E', 'Export to CSV'),
            ('Ctrl+T', 'Open Tune File'),
        ]),
        ('View', [
            ('Ctrl+D', 'Toggle Dark Mode'),
            ('Ctrl+B', 'Toggle Sidebar'),
            ('Ctrl+F', 'Search Data Grid'),
            ('Ctrl+/', 'Keyboard Shortcuts'),
        ]),
        ('AFR Heatmap Edit', [
            ('Arrow Keys', 'Navigate cells'),
            ('Shift+Arrows', 'Extend selection'),
            ('+  /  \u2212', 'Adjust value \u00b11'),
            ('Ctrl+Z / Y', 'Undo / Redo'),
            ('Ctrl+C / V', 'Copy / Paste'),
        ]),
    ]

    def _show_shortcuts_overlay(self) -> None:
        """Toggle the keyboard shortcuts overlay."""
        if getattr(self, '_shortcuts_overlay', None):
            self._shortcuts_overlay.destroy()
            self._shortcuts_overlay = None
            return

        t = self._get_theme()
        _font = getattr(self, '_font_family', 'Segoe UI')

        ov = tk.Toplevel(self)
        ov.title('Keyboard Shortcuts')
        ov.transient(self)
        ov.resizable(False, False)

        w, h = 380, 420
        x = self.winfo_x() + (self.winfo_width() - w) // 2
        y = self.winfo_y() + (self.winfo_height() - h) // 2
        ov.geometry(f'{w}x{h}+{x}+{y}')
        ov.configure(bg=t['bg'])

        self._apply_dark_title_bar()
        try:
            hwnd = ctypes.windll.user32.GetParent(ov.winfo_id())
            val = ctypes.c_int(2)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, 33, ctypes.byref(val), ctypes.sizeof(val))
        except Exception:
            pass

        container = ttk.Frame(ov)
        container.pack(fill=tk.BOTH, expand=True, padx=20, pady=16)

        ttk.Label(container, text='Keyboard Shortcuts',
                  font=(_font, 15, 'bold')).pack(anchor=tk.W, pady=(0, 12))

        for section, items in self.SHORTCUTS:
            ttk.Label(container, text=section,
                      font=(_font, 11, 'bold'),
                      foreground=t['statusbar_fg']).pack(anchor=tk.W, pady=(8, 4))
            for key, desc in items:
                row = ttk.Frame(container)
                row.pack(fill=tk.X, pady=1)
                ttk.Label(row, text=key, font=(_font, 11, 'bold'),
                          foreground=t['accent'], width=16,
                          anchor=tk.W).pack(side=tk.LEFT)
                ttk.Label(row, text=desc, font=(_font, 11),
                          foreground=t['fg']).pack(side=tk.LEFT)

        self._shortcuts_overlay = ov
        ov.protocol('WM_DELETE_WINDOW', self._show_shortcuts_overlay)
        ov.bind('<Escape>', lambda e: self._show_shortcuts_overlay())

    def __init__(self) -> None:
        print("[STARTUP] Initializing LogViewerApp...")
        super().__init__()
        
        # Detect DPI scale factor
        self._dpi_scale = self.winfo_fpixels('1i') / 96.0
        
        self.title("MegaLogViewer")
        self.geometry(f"{self.WINDOW_WIDTH}x{self.WINDOW_HEIGHT}")
        print(f"[STARTUP] Window geometry set to {self.WINDOW_WIDTH}x{self.WINDOW_HEIGHT} (DPI scale: {self._dpi_scale:.2f})")
        
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
        
        # Loading state
        self._loading: bool = False
        self._load_thread: Optional[threading.Thread] = None
        self._progress_queue: queue.Queue = queue.Queue()
        self._load_cancelled: threading.Event = threading.Event()
        
        # Sort state
        self._sort_column: str = None
        self._sort_reverse: bool = False
        
        # Grid filter state
        self._filtered_indices: Optional[list] = None
        self._filter_query: str = ''
        
        # Favorites
        self.favorite_channels: set = set()
        self.favorites_filter_active: bool = False
        
        # Launch filter
        self.launch_filter_active: bool = False
        
        # Plot state tracking for re-plotting on filter toggle
        self._plot_state: dict = {}  # {subplot_idx: {'channels': [...], 'single': bool}}
        self._saved_plot_selections: dict = {}  # Loaded from settings
        self.normalize_active: bool = False
        
        # Default theme setting (must be set before _load_settings)
        self.dark_mode = self._detect_system_dark_mode()
        print(f"[STARTUP] Dark mode detected: {self.dark_mode}")
        self._last_file = None
        self.accent_color_name = 'Blue'  # Default Apple accent
        self._font_family = self._detect_font()
        print(f"[STARTUP] Font family: {self._font_family}")
        
        # Load saved settings (restores last_directory and favorites)
        print("[STARTUP] Loading settings...")
        self._load_settings()
        print(f"[STARTUP] Settings loaded. Last directory: {self.current_directory}")
        
        # Create UI components
        print("[STARTUP] Creating menu...")
        self.create_menu()
        print("[STARTUP] Creating toolbar...")
        self.create_toolbar()
        print("[STARTUP] Creating main layout...")
        self.create_main_layout()
        print("[STARTUP] Creating statusbar...")
        self.create_statusbar()
        
        # Bind keyboard shortcuts
        self.bind("<Control-o>", lambda e: self.browse_folder())
        self.bind("<Control-e>", lambda e: self.export_csv())
        self.bind("<Control-t>", lambda e: self.open_msq_file())
        self.bind("<Control-d>", lambda e: self.toggle_dark_mode())
        self.bind("<Control-b>", lambda e: self._toggle_sidebar())
        self.bind("<Control-f>", lambda e: self._focus_grid_search())
        self.bind("<Control-question>", lambda e: self._show_shortcuts_overlay())
        self.bind("<Control-slash>", lambda e: self._show_shortcuts_overlay())
        
        # Apply theme on startup
        print("[STARTUP] Applying theme...")
        self._apply_theme()
        print("[STARTUP] Theme applied successfully.")
        
        # Apply rounded corners to combobox popdowns after UI is mapped
        self.after(300, self._round_combobox_popdowns)
        
        # Restore last folder after UI is ready (sash must be set first)
        self.after(100, self._restore_last_folder)
        print("[STARTUP] Initialization complete.")
    
    def create_menu(self):
        """Create application menu bar."""
        menubar = tk.Menu(self)
        self.config(menu=menubar)
        
        # File menu
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(
            label="Open Log Folder...",
            command=self.browse_folder,
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
        view_menu.add_command(label="Data Grid", command=lambda: self._show_tab(self.grid_tab))
        view_menu.add_command(label="Visualization", command=lambda: self._show_tab(self.plot_tab))
        view_menu.add_command(label="Summary", command=lambda: self._show_tab(self.summary_tab))
        view_menu.add_command(label="Tune", command=lambda: self._show_tab(self.tune_tab))
        view_menu.add_command(label="AFR Tuning", command=lambda: self._show_tab(self.afr_tab))
        view_menu.add_command(label="Debug", command=lambda: self._show_tab(self.debug_tab))
        view_menu.add_separator()
        view_menu.add_command(
            label="Toggle Sidebar",
            command=self._toggle_sidebar,
            accelerator="Ctrl+B"
        )
        view_menu.add_command(
            label="Toggle Dark Mode",
            command=self.toggle_dark_mode,
            accelerator="Ctrl+D"
        )
        
        # Accent color submenu
        accent_menu = tk.Menu(view_menu, tearoff=0)
        view_menu.add_cascade(label="Accent Color", menu=accent_menu)
        self._accent_var = tk.StringVar(value=self.accent_color_name)
        for color_name in self.ACCENT_COLORS:
            accent_menu.add_radiobutton(
                label=color_name,
                variable=self._accent_var,
                value=color_name,
                command=lambda n=color_name: self._set_accent_color(n)
            )
        
        self._view_menu = view_menu
        
        # Help menu
        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Help", menu=help_menu)
        help_menu.add_command(
            label="Keyboard Shortcuts",
            command=self._show_shortcuts_overlay,
            accelerator="Ctrl+/"
        )
        help_menu.add_command(label="About", command=self.show_about)
    
    def create_toolbar(self):
        """Create toolbar with common actions."""
        toolbar = ttk.Frame(self, relief=tk.FLAT, padding=(12, 6))
        toolbar.pack(side=tk.TOP, fill=tk.X)
        
        # Open button
        open_btn = ttk.Button(toolbar, text="Open Folder",
                              command=self.browse_folder)
        open_btn.pack(side=tk.LEFT, padx=4)
        ToolTip(open_btn, "Open a log folder (Ctrl+O)", self._get_theme)
        
        # Export button
        export_btn = ttk.Button(toolbar, text="Export CSV",
                                command=self.export_csv)
        export_btn.pack(side=tk.LEFT, padx=4)
        ToolTip(export_btn, "Export data to CSV", self._get_theme)
        
        # Separator
        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=12)
        
        # Channel selection
        ttk.Label(toolbar, text="Channel:").pack(side=tk.LEFT, padx=(8, 4))
        self.channel_var = tk.StringVar()
        self.channel_combo = ttk.Combobox(
            toolbar,
            textvariable=self.channel_var,
            width=25,
            state="readonly"
        )
        self.channel_combo.pack(side=tk.LEFT, padx=4)
        
        # Plot button
        plot_btn = ttk.Button(toolbar, text="Plot Selected",
                              command=self.plot_selected_channel)
        plot_btn.pack(side=tk.LEFT, padx=4)
        ToolTip(plot_btn, "Plot the selected channel", self._get_theme)
        
        # Separator
        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=12)
        
        # Sidebar toggle button
        sidebar_btn = ttk.Button(toolbar, text="\u25e7", command=self._toggle_sidebar,
                                 width=3)
        sidebar_btn.pack(side=tk.LEFT, padx=4)
        ToolTip(sidebar_btn, "Toggle sidebar (Ctrl+B)", self._get_theme)
    
    def create_statusbar(self):
        """Create status bar."""
        self._statusbar_frame = ttk.Frame(self)
        self._statusbar_frame.pack(side=tk.BOTTOM, fill=tk.X)
        
        self.statusbar = ttk.Label(
            self._statusbar_frame,
            text="Ready",
            relief=tk.FLAT,
            anchor=tk.W,
            padding=(12, 4)
        )
        self.statusbar.pack(side=tk.BOTTOM, fill=tk.X)
        
        # Progress bar (hidden until loading)
        self._progress_frame = ttk.Frame(self._statusbar_frame)
        _font = getattr(self, '_font_family', 'Segoe UI')
        self._progress_label = ttk.Label(
            self._progress_frame, text="Loading...",
            font=(_font, 11), padding=(12, 2)
        )
        self._progress_label.pack(side=tk.LEFT)
        self._progress_bar = ttk.Progressbar(
            self._progress_frame, mode='determinate',
            maximum=100, length=250
        )
        self._progress_bar.pack(side=tk.LEFT, padx=(4, 12), pady=4, fill=tk.X, expand=True)
        self._progress_cancel_btn = ttk.Button(
            self._progress_frame, text="Cancel",
            command=self._cancel_load
        )
        self._progress_cancel_btn.pack(side=tk.RIGHT, padx=(0, 12))
    
    def create_main_layout(self):
        """Create main layout with file browser and notebook."""
        # Create PanedWindow for resizable split
        self.paned_window = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        self.paned_window.pack(fill=tk.BOTH, expand=True, padx=0, pady=0)
        
        # Create file browser panel
        self.create_file_browser()
        
        # Create notebook panel
        self.create_notebook()
        
        # Add panels to paned window with minimum browser width
        self.browser_frame.configure(width=250)
        self.browser_frame.pack_propagate(False)
        self.paned_window.add(self.browser_frame, weight=1)
        self.paned_window.add(self.notebook, weight=4)
        
        # Force the sash position after the window is rendered
        self.after(200, lambda: self._set_initial_sash())
    
    def _set_initial_sash(self):
        """Set initial sash position to ensure file browser is visible."""
        try:
            if getattr(self, '_sidebar_collapsed', False):
                self.paned_window.sashpos(0, 0)
            else:
                pos = getattr(self, '_sidebar_saved_pos', 250)
                self.paned_window.sashpos(0, pos)
        except Exception:
            pass
        # Retry once more after mainloop settles
        self.after(300, self._ensure_sash_visible)

    def _ensure_sash_visible(self):
        """Ensure the browser sash is in a usable position."""
        if getattr(self, '_sidebar_collapsed', False):
            return
        try:
            pos = self.paned_window.sashpos(0)
            if pos < 100:
                self.paned_window.sashpos(0, 250)
        except Exception:
            pass
    
    def create_file_browser(self):
        """Create file browser panel with Apple-style section headers."""
        self.browser_frame = ttk.Frame(self.paned_window)

        # Browser header
        header_frame = ttk.Frame(self.browser_frame)
        header_frame.pack(side=tk.TOP, fill=tk.X, padx=12, pady=(12, 4))

        _font = getattr(self, '_font_family', 'Segoe UI')
        ttk.Label(header_frame, text="Log Files", font=(_font, 13, 'bold')).pack(side=tk.LEFT)

        ttk.Button(
            header_frame,
            text="Browse",
            command=self.browse_folder,
            width=8
        ).pack(side=tk.RIGHT)

        # Current directory label
        self.dir_label = ttk.Label(
            self.browser_frame,
            text="No folder selected",
            foreground="#8E8E93",
            wraplength=220
        )
        self.dir_label.pack(side=tk.TOP, fill=tk.X, padx=12, pady=(0, 8))

        # File list as Treeview with section headers
        list_frame = ttk.Frame(self.browser_frame)
        list_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=12, pady=(0, 8))

        self.file_tree = ttk.Treeview(
            list_frame,
            selectmode='browse',
            show='tree',
            style='Sidebar.Treeview'
        )
        self.file_tree.pack(fill=tk.BOTH, expand=True)

        # Overlay scrollbar — placed on top of tree, auto-hides
        self._browser_scrollbar = ttk.Scrollbar(list_frame, command=self.file_tree.yview)
        self.file_tree.configure(yscrollcommand=self._browser_scrollbar.set)
        self._browser_sb_visible = False

        def _show_browser_sb(e=None):
            if not self._browser_sb_visible:
                self._browser_scrollbar.place(relx=1.0, rely=0.0,
                                              relheight=1.0, anchor='ne', width=8)
                self._browser_sb_visible = True

        def _hide_browser_sb(e=None):
            if self._browser_sb_visible:
                self._browser_scrollbar.place_forget()
                self._browser_sb_visible = False

        list_frame.bind('<Enter>', _show_browser_sb)
        list_frame.bind('<Leave>', _hide_browser_sb)
        self.file_tree.bind('<Enter>', _show_browser_sb)
        self.file_tree.bind('<Leave>', _hide_browser_sb)

        # Create section header items
        self._recent_section = self.file_tree.insert('', 'end', iid='_recent',
                                                      text='Recent Files', open=True,
                                                      tags=('section',))
        self._allfiles_section = self.file_tree.insert('', 'end', iid='_allfiles',
                                                        text='All Files', open=True,
                                                        tags=('section',))

        # Bind selection event
        self.file_tree.bind('<<TreeviewSelect>>', self._on_tree_select)
        self.file_tree.bind('<Double-Button-1>', lambda e: self._on_tree_select(e, force_reload=True))

        # Backward-compatible alias used by _apply_theme
        self.file_listbox = self.file_tree

        # File count label
        self.file_count_label = ttk.Label(
            self.browser_frame,
            text="0 files",
            foreground="#8E8E93"
        )
        self.file_count_label.pack(side=tk.BOTTOM, pady=(0, 8))
    
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
        
        # AFR Tuning tab
        self.afr_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.afr_tab, text="AFR Tuning")
        
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
        
        # Create AFR tuning view in fifth tab
        self.create_afr_tuning_view()
        
        # Create debug view in sixth tab
        self.create_debug_view()
        
        # Bind tab-change animation, close-button clicks, and drag-to-reorder
        self.notebook.bind('<<NotebookTabChanged>>', self._on_tab_changed)
        self.notebook.bind('<Button-1>', self._on_tab_click)
        self.notebook.bind('<B1-Motion>', self._on_tab_drag)
        self.notebook.bind('<ButtonRelease-1>', self._on_tab_drag_end)
    
    def _focus_grid_search(self) -> None:
        """Focus the grid search entry, switching to the Data tab if needed."""
        if hasattr(self, 'notebook'):
            self.notebook.select(self.grid_tab)
        if hasattr(self, '_grid_search_entry'):
            self._grid_search_entry.focus_set()
            self._grid_search_entry.select_range(0, tk.END)

    def _apply_grid_filter(self) -> None:
        """Filter data grid rows by search query."""
        if not self.log_data:
            return
        query = self._grid_search_entry.get().strip()
        if not query:
            self._clear_grid_filter()
            return
        
        column = self._grid_search_col.get()
        mode = self._grid_search_mode.get()
        channels = self.log_data.get_channel_names()
        search_channels = channels if column == 'All Columns' else [column]
        
        import re as _re
        if mode == 'Regex':
            try:
                pattern = _re.compile(query, _re.IGNORECASE)
            except _re.error:
                from tkinter import messagebox
                messagebox.showerror('Invalid Regex', f'Bad regex pattern: {query}')
                return
        
        matched = []
        for idx, record in enumerate(self.log_data.records):
            for ch in search_channels:
                val = str(record.get(ch, ''))
                if mode == 'Contains' and query.lower() in val.lower():
                    matched.append(idx)
                    break
                elif mode == 'Exact' and val.lower() == query.lower():
                    matched.append(idx)
                    break
                elif mode == 'Regex' and pattern.search(val):
                    matched.append(idx)
                    break
        
        self._filtered_indices = matched
        self._filter_query = query
        self.current_page = 0
        self.display_current_page()

    def _clear_grid_filter(self) -> None:
        """Clear the active grid filter."""
        self._filtered_indices = None
        self._filter_query = ''
        if hasattr(self, '_grid_search_entry'):
            self._grid_search_entry.delete(0, tk.END)
        self.current_page = 0
        self.display_current_page()

    def create_data_grid(self):
        """Create treeview data grid with overlay scrollbars."""
        # Search / filter bar
        search_frame = ttk.Frame(self.grid_tab)
        search_frame.pack(side=tk.TOP, fill=tk.X, padx=6, pady=(6, 2))
        
        ttk.Label(search_frame, text='\U0001F50D').pack(side=tk.LEFT, padx=(0, 4))
        self._grid_search_entry = ttk.Entry(search_frame, width=28)
        self._grid_search_entry.pack(side=tk.LEFT, padx=2)
        self._grid_search_entry.bind('<Return>', lambda e: self._apply_grid_filter())
        self._grid_search_entry.bind('<Escape>', lambda e: self._clear_grid_filter())
        
        self._grid_search_col = ttk.Combobox(
            search_frame, values=['All Columns'], state='readonly', width=16)
        self._grid_search_col.current(0)
        self._grid_search_col.pack(side=tk.LEFT, padx=2)
        
        self._grid_search_mode = ttk.Combobox(
            search_frame, values=['Contains', 'Exact', 'Regex'],
            state='readonly', width=10)
        self._grid_search_mode.current(0)
        self._grid_search_mode.pack(side=tk.LEFT, padx=2)
        
        ttk.Button(search_frame, text='Filter',
                   command=self._apply_grid_filter).pack(side=tk.LEFT, padx=2)
        ttk.Button(search_frame, text='Clear',
                   command=self._clear_grid_filter).pack(side=tk.LEFT, padx=2)
        
        self._grid_filter_label = ttk.Label(search_frame, text='')
        self._grid_filter_label.pack(side=tk.LEFT, padx=(8, 0))
        
        # Create frame for grid
        grid_frame = ttk.Frame(self.grid_tab)
        grid_frame.pack(fill=tk.BOTH, expand=True)
        
        # Create treeview
        self.data_tree = ttk.Treeview(
            grid_frame,
            columns=(),
            show="tree headings",
            selectmode="extended"
        )
        self.data_tree.pack(fill=tk.BOTH, expand=True)
        
        # Overlay scrollbars — placed on top of tree, auto-show on hover
        self._grid_vsb = ttk.Scrollbar(grid_frame, orient="vertical",
                                        command=self.data_tree.yview)
        self._grid_hsb = ttk.Scrollbar(grid_frame, orient="horizontal",
                                        command=self.data_tree.xview)
        self.data_tree.configure(yscrollcommand=self._grid_vsb.set,
                                 xscrollcommand=self._grid_hsb.set)
        self._grid_sb_visible = False

        def _show_grid_sb(e=None):
            if not self._grid_sb_visible:
                self._grid_vsb.place(relx=1.0, rely=0.0,
                                     relheight=1.0, anchor='ne', width=8)
                self._grid_hsb.place(relx=0.0, rely=1.0,
                                     relwidth=1.0, anchor='sw', height=8)
                self._grid_sb_visible = True

        def _hide_grid_sb(e=None):
            if self._grid_sb_visible:
                self._grid_vsb.place_forget()
                self._grid_hsb.place_forget()
                self._grid_sb_visible = False

        grid_frame.bind('<Enter>', _show_grid_sb)
        grid_frame.bind('<Leave>', _hide_grid_sb)
        
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
        
        # Update search column dropdown
        if hasattr(self, '_grid_search_col'):
            self._grid_search_col['values'] = ['All Columns'] + list(channel_names)
            self._grid_search_col.current(0)
        
        # Clear any active filter and reset pagination
        self._filtered_indices = None
        self._filter_query = ''
        self.current_page = 0
        self.display_current_page()
    
    def display_current_page(self) -> None:
        """Display current page of data."""
        if not self.log_data:
            return
        
        # Clear existing rows
        for item in self.data_tree.get_children():
            self.data_tree.delete(item)
        
        # Determine which record indices to display
        if self._filtered_indices is not None:
            source_indices = self._filtered_indices
            total_records = len(source_indices)
        else:
            source_indices = None
            total_records = self.log_data.record_count
        
        # Calculate page boundaries
        start_idx = self.current_page * self.page_size
        end_idx = min(start_idx + self.page_size, total_records)
        
        # Insert rows for current page
        channels = self.log_data.get_channel_names()
        for page_pos in range(start_idx, end_idx):
            idx = source_indices[page_pos] if source_indices is not None else page_pos
            record = self.log_data.records[idx]
            values = [record.get(ch, '') for ch in channels]
            
            # Apply alternating row colors
            tags = ('evenrow',) if page_pos % 2 == 0 else ('oddrow',)
            self.data_tree.insert("", tk.END, text=str(idx + 1), values=values, tags=tags)
        
        # Configure row colors from theme
        t = self._get_theme()
        self.data_tree.tag_configure('evenrow', background=t['treeview_even'])
        self.data_tree.tag_configure('oddrow', background=t['treeview_odd'])
        
        # Update page label with sort and filter info
        total_pages = max(1, (total_records + self.page_size - 1) // self.page_size)
        sort_info = f" (sorted by {self._sort_column})" if self._sort_column else ""
        if self._filtered_indices is not None:
            filter_info = f" | Filtered: {total_records} of {self.log_data.record_count}"
        else:
            filter_info = ""
        display_start = start_idx + 1 if total_records > 0 else 0
        self.page_label.config(
            text=f"Page {self.current_page + 1} of {total_pages} | "
                 f"Records {display_start}-{end_idx} of {total_records}{sort_info}{filter_info}"
        )
        
        # Update filter badge
        if hasattr(self, '_grid_filter_label'):
            if self._filtered_indices is not None:
                self._grid_filter_label.config(
                    text=f"{len(self._filtered_indices)} matches",
                    foreground=t['accent'])
            else:
                self._grid_filter_label.config(text='')
        
        # Update column headers with sort indicators
        for channel in channels:
            if channel == self._sort_column:
                indicator = " ▼" if self._sort_reverse else " ▲"
                self.data_tree.heading(channel, text=f"{channel}{indicator}")
            else:
                self.data_tree.heading(channel, text=channel)
    
    def goto_next_page(self) -> None:
        """Navigate to next page."""
        if not self.log_data:
            return
        total = len(self._filtered_indices) if self._filtered_indices is not None else self.log_data.record_count
        total_pages = max(1, (total + self.page_size - 1) // self.page_size)
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
        total = len(self._filtered_indices) if self._filtered_indices is not None else self.log_data.record_count
        total_pages = max(1, (total + self.page_size - 1) // self.page_size)
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
        
        # Re-apply active filter against new sort order
        if self._filter_query and hasattr(self, '_grid_search_entry'):
            self._apply_grid_filter()
        else:
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
        header_frame.pack(side=tk.TOP, fill=tk.X, padx=12, pady=(12, 4))
        _font = getattr(self, '_font_family', 'Segoe UI')
        ttk.Label(header_frame, text="Channels", font=(_font, 13, 'bold')).pack(side=tk.LEFT)
        
        # Target plot selector
        target_frame = ttk.Frame(channel_frame)
        target_frame.pack(side=tk.TOP, fill=tk.X, padx=12, pady=(0, 8))
        ttk.Label(target_frame, text="Target:").pack(side=tk.LEFT)
        self.plot_target_combo = ttk.Combobox(
            target_frame,
            values=["Plot 1", "Plot 2", "Plot 3", "Plot 4"],
            width=10, state="readonly"
        )
        self.plot_target_combo.current(0)
        self.plot_target_combo.pack(side=tk.LEFT, padx=8)
        
        # Plot action buttons
        button_frame = ttk.Frame(channel_frame)
        button_frame.pack(side=tk.TOP, fill=tk.X, padx=12, pady=(0, 4))
        ttk.Button(button_frame, text="All", command=self.select_all_channels, width=6).pack(side=tk.LEFT, padx=3)
        ttk.Button(button_frame, text="None", command=self.select_no_channels, width=6).pack(side=tk.LEFT, padx=3)
        ttk.Button(button_frame, text="Plot", command=self.plot_selected_channels, width=6).pack(side=tk.LEFT, padx=3)
        ttk.Button(button_frame, text="Clear", command=self.clear_target_plot, width=6).pack(side=tk.LEFT, padx=3)
        
        # Favorites buttons
        fav_frame = ttk.Frame(channel_frame)
        fav_frame.pack(side=tk.TOP, fill=tk.X, padx=12, pady=(0, 4))
        ttk.Button(fav_frame, text="★ Fav", command=self.add_selected_to_favorites, width=8).pack(side=tk.LEFT, padx=3)
        ttk.Button(fav_frame, text="Unfav", command=self.remove_selected_from_favorites, width=8).pack(side=tk.LEFT, padx=3)
        self.fav_filter_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(fav_frame, text="★ Only", variable=self.fav_filter_var,
                        command=self.toggle_favorites_filter).pack(side=tk.LEFT, padx=8)
        
        # Channel search box
        search_frame = ttk.Frame(channel_frame)
        search_frame.pack(side=tk.TOP, fill=tk.X, padx=12, pady=(0, 8))
        ttk.Label(search_frame, text="Filter:").pack(side=tk.LEFT)
        self.channel_search_var = tk.StringVar()
        self.channel_search_var.trace_add('write', lambda *_: self.populate_channel_checkboxes())
        self.channel_search_entry = ttk.Entry(
            search_frame, textvariable=self.channel_search_var, width=20
        )
        self.channel_search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(8, 0))
        
        # Scrollable channel list
        list_frame = ttk.Frame(channel_frame)
        list_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=12, pady=(0, 8))
        
        # Use canvas for scrollable checkboxes
        self.channel_canvas = tk.Canvas(list_frame, highlightthickness=0)
        self.channel_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Overlay scrollbar — placed on top of canvas, auto-shows on hover
        self._channel_scrollbar = ttk.Scrollbar(list_frame, command=self.channel_canvas.yview)
        self.channel_canvas.configure(yscrollcommand=self._channel_scrollbar.set)
        self._channel_sb_visible = False

        def _show_channel_sb(e=None):
            if not self._channel_sb_visible:
                self._channel_scrollbar.place(relx=1.0, rely=0.0,
                                              relheight=1.0, anchor='ne', width=8)
                self._channel_sb_visible = True

        def _hide_channel_sb(e=None):
            if self._channel_sb_visible:
                self._channel_scrollbar.place_forget()
                self._channel_sb_visible = False

        list_frame.bind('<Enter>', _show_channel_sb)
        list_frame.bind('<Leave>', _hide_channel_sb)
        self.channel_canvas.bind('<Enter>', _show_channel_sb)
        self.channel_canvas.bind('<Leave>', _hide_channel_sb)

        # Mousewheel scrolling
        def _on_channel_mousewheel(event):
            self.channel_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        self.channel_canvas.bind('<MouseWheel>', _on_channel_mousewheel)
        
        # Frame inside canvas to hold checkboxes
        self.channel_checkboxes_frame = ttk.Frame(self.channel_canvas)
        self.channel_canvas_window = self.channel_canvas.create_window(
            (0, 0), window=self.channel_checkboxes_frame, anchor='nw'
        )
        self.channel_checkboxes_frame.bind('<MouseWheel>', _on_channel_mousewheel)
        
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
            share = self.axes[0] if self.axes else None
            ax = self.fig.add_subplot(4, 1, i + 1, sharex=share)
            ax.set_facecolor(t['plot_bg'])
            _pfont = getattr(self, '_font_family', 'Segoe UI')
            ax.set_xlabel("Time (s)", fontsize=9, color=t['plot_text'], fontfamily=_pfont)
            ax.set_ylabel("Value", fontsize=9, color=t['plot_text'], fontfamily=_pfont)
            ax.tick_params(colors=t['plot_tick'], labelsize=8)
            ax.grid(True, which='major', alpha=0.2, color=t['plot_grid'])
            ax.xaxis.set_minor_locator(AutoMinorLocator())
            ax.yaxis.set_minor_locator(AutoMinorLocator())
            ax.grid(True, which='minor', alpha=0.1, color=t['plot_grid'], linestyle=':')
            for spine in ax.spines.values():
                spine.set_color(t['plot_spine'])
            self.axes.append(ax)
        self.fig.subplots_adjust(left=0.06, right=0.98, top=0.98, bottom=0.04, hspace=0.15)
        
        # Create canvas
        self.canvas = FigureCanvasTkAgg(self.fig, master=plot_frame)
        
        # Create hover annotation and vertical cursor line for each subplot
        self._annotations = []
        self._vlines = []
        for ax in self.axes:
            annot = ax.annotate(
                "", xy=(0, 0), xytext=(15, 15),
                textcoords="offset points",
                bbox=dict(boxstyle="round,pad=0.4", fc="#2C2C2E", ec="#48484A", alpha=0.92),
                color="white", fontsize=9, fontfamily=getattr(self, '_font_family', 'Segoe UI'),
                arrowprops=dict(arrowstyle="->", color="#98989D"),
                visible=False, zorder=100
            )
            self._annotations.append(annot)
            vline = ax.axvline(x=0, color='#98989D', linewidth=0.8, linestyle='--', visible=False, zorder=99)
            self._vlines.append(vline)
        
        # Connect mouse motion event for hover annotations
        self.canvas.mpl_connect("motion_notify_event", self._on_plot_hover)

        # Mouse interaction: scroll to zoom, right-drag to pan, double-right to reset,
        # left-drag to rubber-band zoom
        self._pan_start = None   # (ax, x, y, xlim, ylim) while right-dragging
        self._zoom_box = None    # (ax, x0, y0) while left-dragging
        self._zoom_rect = None   # matplotlib Rectangle patch
        self.canvas.mpl_connect("scroll_event", self._on_plot_scroll)
        self.canvas.mpl_connect("button_press_event", self._on_plot_button_press)
        self.canvas.mpl_connect("button_release_event", self._on_plot_button_release)
        self.canvas.mpl_connect("motion_notify_event", self._on_plot_pan_motion)
        
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
        
        # Apply search filter
        search_text = self.channel_search_var.get().lower() if hasattr(self, 'channel_search_var') else ''
        if search_text:
            channel_names = [ch for ch in channel_names if search_text in ch.lower()]
        
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

            # Enable mousewheel scrolling on all child widgets
            for w in (row_frame, star_label, cb):
                w.bind('<MouseWheel>',
                       lambda e: self.channel_canvas.yview_scroll(
                           int(-1 * (e.delta / 120)), "units"))
    
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
            if not channels:
                continue
            
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
    
    def _on_plot_hover(self, event):
        """Handle mouse hover to show values from all plots at the same x position."""
        if event.inaxes is None:
            for annot in self._annotations:
                if annot.get_visible():
                    annot.set_visible(False)
            for vline in self._vlines:
                if vline.get_visible():
                    vline.set_visible(False)
            self.canvas.draw_idle()
            return
        
        # Get the x coordinate from whichever subplot the mouse is in
        x_mouse = event.xdata
        if x_mouse is None:
            return
        
        import numpy as np
        
        needs_redraw = False
        for ax_idx, ax in enumerate(self.axes):
            annot = self._annotations[ax_idx]
            vline = self._vlines[ax_idx]
            lines = [l for l in ax.get_lines() if not l.get_label().startswith('_') and l is not vline]
            
            if not lines:
                if annot.get_visible():
                    annot.set_visible(False)
                    needs_redraw = True
                continue
            
            # Build text from all lines on this subplot at the mouse x position
            parts = []
            anchor_x = None
            anchor_y = None
            for line in lines:
                xdata = line.get_xdata()
                ydata = line.get_ydata()
                if len(xdata) == 0:
                    continue
                # Find nearest index to x_mouse
                idx = int(np.searchsorted(xdata, x_mouse))
                idx = max(0, min(idx, len(xdata) - 1))
                # Check neighbor for closer match
                if idx > 0 and abs(xdata[idx - 1] - x_mouse) < abs(xdata[idx] - x_mouse):
                    idx = idx - 1
                x_val = xdata[idx]
                y_val = ydata[idx]
                # Use original data if available (normalized plots)
                orig = getattr(line, '_original_ydata', None)
                if orig is not None and idx < len(orig):
                    display_val = orig[idx]
                else:
                    display_val = y_val
                if anchor_x is None:
                    anchor_x = x_val
                    anchor_y = y_val
                label = line.get_label()
                parts.append(f"{label}: {display_val:.2f}")
            
            if parts and anchor_x is not None:
                text = f"{anchor_x:.2f}s\n" + "\n".join(parts)
                annot.xy = (anchor_x, anchor_y)
                annot.set_text(text)
                annot.set_visible(True)
                vline.set_xdata([anchor_x])
                vline.set_visible(True)
                needs_redraw = True
            elif annot.get_visible():
                annot.set_visible(False)
                vline.set_visible(False)
                needs_redraw = True
        
        if needs_redraw:
            self.canvas.draw_idle()
    
    def _recreate_annotation(self, ax_idx):
        """Recreate the hover annotation and vertical line for a subplot after ax.clear()."""
        ax = self.axes[ax_idx]
        annot = ax.annotate(
            "", xy=(0, 0), xytext=(15, 15),
            textcoords="offset points",
            bbox=dict(boxstyle="round,pad=0.3", fc="#333333", ec="#555555", alpha=0.9),
            color="white", fontsize=8,
            arrowprops=dict(arrowstyle="->", color="#aaaaaa"),
            visible=False, zorder=100
        )
        self._annotations[ax_idx] = annot
        vline = ax.axvline(x=0, color='#aaaaaa', linewidth=0.8, linestyle='--', visible=False, zorder=99)
        self._vlines[ax_idx] = vline

    # --- Mouse zoom / pan helpers ---

    def _on_plot_scroll(self, event):
        """Zoom in/out on scroll wheel for the axis under the cursor."""
        if event.inaxes is None:
            return
        ax = event.inaxes
        if ax not in self.axes:
            return

        base_scale = 0.8  # <1 = zoom in per step
        if event.button == 'up':
            scale = base_scale
        elif event.button == 'down':
            scale = 1.0 / base_scale
        else:
            return

        x, y = event.xdata, event.ydata

        xlim = ax.get_xlim()
        ylim = ax.get_ylim()

        # Zoom centred on cursor position
        new_width = (xlim[1] - xlim[0]) * scale
        new_height = (ylim[1] - ylim[0]) * scale
        relx = (x - xlim[0]) / (xlim[1] - xlim[0])
        rely = (y - ylim[0]) / (ylim[1] - ylim[0])

        ax.set_xlim(x - new_width * relx, x + new_width * (1 - relx))
        ax.set_ylim(y - new_height * rely, y + new_height * (1 - rely))
        self.canvas.draw_idle()

    def _on_plot_button_press(self, event):
        """Start pan on right-click; reset on double-right-click; box-zoom on left-click."""
        if event.inaxes is None or event.inaxes not in self.axes:
            return
        ax = event.inaxes

        # Double-right-click → auto-scale
        if event.button == 3 and event.dblclick:
            ax.autoscale()
            self.canvas.draw_idle()
            return

        # Single right-click → start pan
        if event.button == 3:
            self._pan_start = (ax, event.xdata, event.ydata,
                               ax.get_xlim(), ax.get_ylim())

        # Left-click → start rubber-band zoom box
        if event.button == 1 and not event.dblclick:
            self._zoom_box = (ax, event.xdata, event.ydata)

    def _on_plot_button_release(self, event):
        """End pan on right-button release; apply zoom box on left-button release."""
        if event.button == 3:
            self._pan_start = None

        if event.button == 1 and self._zoom_box is not None:
            ax, x0, y0 = self._zoom_box
            self._zoom_box = None

            # Remove the rectangle overlay
            if self._zoom_rect is not None:
                self._zoom_rect.remove()
                self._zoom_rect = None

            if event.inaxes != ax or event.xdata is None:
                self.canvas.draw_idle()
                return

            x1, y1 = event.xdata, event.ydata

            # Only zoom if the drag was large enough (> 3 pixels in both axes)
            dx_pixels = abs(event.x - ax.transData.transform((x0, y0))[0])
            dy_pixels = abs(event.y - ax.transData.transform((x0, y0))[1])
            if dx_pixels < 3 and dy_pixels < 3:
                self.canvas.draw_idle()
                return

            ax.set_xlim(min(x0, x1), max(x0, x1))
            ax.set_ylim(min(y0, y1), max(y0, y1))
            self.canvas.draw_idle()

    def _on_plot_pan_motion(self, event):
        """Drag the view while right button is held; draw rubber-band while left button is held."""
        # Right-drag pan
        if self._pan_start is not None:
            ax, x0, y0, xlim0, ylim0 = self._pan_start
            if event.inaxes != ax or event.xdata is None:
                return
            dx = x0 - event.xdata
            dy = y0 - event.ydata
            ax.set_xlim(xlim0[0] + dx, xlim0[1] + dx)
            ax.set_ylim(ylim0[0] + dy, ylim0[1] + dy)
            self.canvas.draw_idle()
            return

        # Left-drag rubber-band zoom rectangle
        if self._zoom_box is not None:
            ax, x0, y0 = self._zoom_box
            if event.inaxes != ax or event.xdata is None:
                return
            x1, y1 = event.xdata, event.ydata
            if self._zoom_rect is not None:
                self._zoom_rect.remove()
            from matplotlib.patches import Rectangle
            self._zoom_rect = ax.add_patch(Rectangle(
                (min(x0, x1), min(y0, y1)),
                abs(x1 - x0), abs(y1 - y0),
                linewidth=1, edgecolor='#00bfff', facecolor='#00bfff',
                alpha=0.15, linestyle='--', zorder=200
            ))
            self.canvas.draw_idle()

    def clear_target_plot(self):
        """Clear the currently targeted subplot."""
        target_idx = self.plot_target_combo.current()
        if target_idx < 0:
            target_idx = 0
        self._plot_state.pop(target_idx, None)
        t = self._get_theme()
        ax = self.axes[target_idx]
        ax.clear()
        self._recreate_annotation(target_idx)
        ax.set_facecolor(t['plot_bg'])
        ax.set_xlabel("Time (s)", fontsize=8, color=t['plot_text'])
        ax.set_ylabel("Value", fontsize=8, color=t['plot_text'])
        ax.tick_params(colors=t['plot_tick'], labelsize=7)
        ax.grid(True, which='major', alpha=0.3, color=t['plot_grid'])
        ax.xaxis.set_minor_locator(AutoMinorLocator())
        ax.yaxis.set_minor_locator(AutoMinorLocator())
        ax.grid(True, which='minor', alpha=0.15, color=t['plot_grid'], linestyle=':')
        for spine in ax.spines.values():
            spine.set_color(t['plot_spine'])
        self.fig.subplots_adjust(left=0.06, right=0.98, top=0.98, bottom=0.04, hspace=0.15)
        self.canvas.draw()
    
    def clear_all_plots(self):
        """Clear all 4 subplots."""
        self._plot_state.clear()
        t = self._get_theme()
        for i, ax in enumerate(self.axes):
            ax.clear()
            self._recreate_annotation(i)
            ax.set_facecolor(t['plot_bg'])
            ax.set_xlabel("Time (s)", fontsize=8, color=t['plot_text'])
            ax.set_ylabel("Value", fontsize=8, color=t['plot_text'])
            ax.tick_params(colors=t['plot_tick'], labelsize=7)
            ax.grid(True, which='major', alpha=0.3, color=t['plot_grid'])
            ax.xaxis.set_minor_locator(AutoMinorLocator())
            ax.yaxis.set_minor_locator(AutoMinorLocator())
            ax.grid(True, which='minor', alpha=0.15, color=t['plot_grid'], linestyle=':')
            for spine in ax.spines.values():
                spine.set_color(t['plot_spine'])
        self.fig.subplots_adjust(left=0.06, right=0.98, top=0.98, bottom=0.04, hspace=0.15)
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
            }
            
            self._do_plot_multi(target_idx, selected_channels)
            
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
        self._recreate_annotation(target_idx)
        ax.set_facecolor(t['plot_bg'])
        ax.set_xlabel("Time (s)", fontsize=8, color=t['plot_text'])
        if self.normalize_active and len(selected_channels) > 1:
            ax.set_ylabel("Normalized (0-1)", fontsize=8, color=t['plot_text'])
        else:
            ax.set_ylabel("Value", fontsize=8, color=t['plot_text'])
        ax.tick_params(colors=t['plot_tick'], labelsize=7)
        ax.grid(True, which='major', alpha=0.3, color=t['plot_grid'])
        ax.xaxis.set_minor_locator(AutoMinorLocator())
        ax.yaxis.set_minor_locator(AutoMinorLocator())
        ax.grid(True, which='minor', alpha=0.15, color=t['plot_grid'], linestyle=':')
        for spine in ax.spines.values():
            spine.set_color(t['plot_spine'])
        
        # Color palette for multiple lines (Apple system colors)
        colors = self.PLOT_COLORS_DARK if self.dark_mode else self.PLOT_COLORS_LIGHT
        
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
            line_obj, = ax.plot(time_data, plot_data, linewidth=1.2, label=channel, color=color, picker=5)
            # Store original data for hover annotations when normalized
            if self.normalize_active and len(selected_channels) > 1:
                line_obj._original_ydata = channel_data

        # Overlay matching channels from extra log files
        extra_line_styles = ['--', ':', '-.']
        has_extra = False
        for file_idx, extra_ld in enumerate(getattr(self, '_extra_log_data', [])):
            extra_time = extra_ld.get_time_data()
            style = extra_line_styles[file_idx % len(extra_line_styles)]
            for idx, channel in enumerate(selected_channels):
                if channel in extra_ld.get_channel_names():
                    has_extra = True
                    extra_data = extra_ld.get_channel_data(channel)
                    plot_data = extra_data
                    if self.normalize_active and len(selected_channels) > 1:
                        plot_data = self._normalize_data(extra_data)
                    color = colors[idx % len(colors)]
                    label = f"{channel} ({extra_ld.filename})"
                    ax.plot(extra_time, plot_data, linewidth=1.0,
                            linestyle=style, label=label, color=color, alpha=0.7)
        
        # Add legend if multiple channels or extra files
        if len(selected_channels) > 1 or has_extra:
            legend = ax.legend(loc='best', fontsize=7, framealpha=0.9,
                               facecolor=t['plot_face'], edgecolor=t['plot_spine'])
            if legend:
                for text in legend.get_texts():
                    text.set_color(t['plot_text'])
        else:
            # Single channel - show units in ylabel
            channel = selected_channels[0]
            field_info = self.log_data.get_field_info(channel)
            ylabel = channel
            if field_info and field_info.get('units'):
                ylabel += f" ({field_info['units']})"
            ax.set_ylabel(ylabel, fontsize=8, color=t['plot_text']
            )
        
        # Refresh canvas
        self.fig.subplots_adjust(left=0.06, right=0.98, top=0.98, bottom=0.04, hspace=0.15)
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
            }
            
            self._do_plot_multi(target_idx, [channel_name])
            
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
        self._recreate_annotation(target_idx)
        ax.set_facecolor(t['plot_bg'])
        ax.set_xlabel("Time (s)", fontsize=8, color=t['plot_text'])
        ax.tick_params(colors=t['plot_tick'], labelsize=7)
        ax.grid(True, which='major', alpha=0.3, color=t['plot_grid'])
        ax.xaxis.set_minor_locator(AutoMinorLocator())
        ax.yaxis.set_minor_locator(AutoMinorLocator())
        ax.grid(True, which='minor', alpha=0.15, color=t['plot_grid'], linestyle=':')
        for spine in ax.spines.values():
            spine.set_color(t['plot_spine'])
        
        field_info = self.log_data.get_field_info(channel_name)
        ylabel = channel_name
        if field_info and field_info.get('units'):
            ylabel += f" ({field_info['units']})"
        ax.set_ylabel(ylabel, fontsize=8, color=t['plot_text'])
        
        ax.plot(time_data, channel_data, linewidth=1.2, color=t['accent'], picker=5)
        
        self.fig.subplots_adjust(left=0.06, right=0.98, top=0.98, bottom=0.04, hspace=0.15)
        self.canvas.draw()
    
    def create_summary_view(self):
        """Create summary view with text widget."""
        # Create scrollable text widget
        text_frame = ttk.Frame(self.summary_tab)
        text_frame.pack(fill=tk.BOTH, expand=True, padx=16, pady=16)
        
        scrollbar = ttk.Scrollbar(text_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.summary_text = tk.Text(
            text_frame,
            wrap=tk.WORD,
            yscrollcommand=scrollbar.set,
            font=(getattr(self, '_font_family', 'Segoe UI'), 11),
            borderwidth=0,
            highlightthickness=0
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
        debug_toolbar.pack(side=tk.TOP, fill=tk.X, padx=12, pady=(12, 4))
        
        ttk.Button(
            debug_toolbar,
            text="Clear Debug Log",
            command=self.clear_debug
        ).pack(side=tk.LEFT, padx=4)
        
        ttk.Button(
            debug_toolbar,
            text="Save Debug Log",
            command=self.save_debug_log
        ).pack(side=tk.LEFT, padx=4)
        
        # Create scrollable text widget
        text_frame = ttk.Frame(self.debug_tab)
        text_frame.pack(fill=tk.BOTH, expand=True, padx=16, pady=(4, 16))
        
        scrollbar = ttk.Scrollbar(text_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        t = self._get_theme()
        self.debug_text = tk.Text(
            text_frame,
            wrap=tk.WORD,
            yscrollcommand=scrollbar.set,
            font=('Cascadia Mono', 10),
            background=t['debug_bg'],
            foreground=t['debug_fg'],
            insertbackground=t['fg'],
            borderwidth=0,
            highlightthickness=0
        )
        self.debug_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.debug_text.yview)
        
        # Configure text tags for different log levels
        self.debug_text.tag_configure('header', font=('Cascadia Mono', 10, 'bold'), foreground=t['debug_header'])
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
        """Populate file tree with .mlg files, grouped by Recent and All Files."""
        if not self.current_directory:
            return
        if self._loading:
            return

        # Clear existing file items (keep section nodes)
        for child in self.file_tree.get_children('_recent'):
            self.file_tree.delete(child)
        for child in self.file_tree.get_children('_allfiles'):
            self.file_tree.delete(child)
        self.file_info.clear()

        try:
            # Get all .mlg files in directory
            mlg_files = []
            for file in os.listdir(self.current_directory):
                if file.lower().endswith('.mlg'):
                    mlg_files.append(file)
        except (OSError, PermissionError) as e:
            messagebox.showerror("Error", f"Cannot read directory:\n{str(e)}")
            self.statusbar.config(text="Error reading directory")
            return

        # Sort files by name
        mlg_files.sort()

        if not mlg_files:
            self.file_count_label.config(text="0 files")
            t = self._get_theme()
            dir_display = self.current_directory
            if len(dir_display) > 40:
                dir_display = f"...{dir_display[-40:]}"
            self.dir_label.config(text=dir_display, foreground=t['fg'])
            self.statusbar.config(text="No .mlg files found")
            return

        # Update labels
        t = self._get_theme()
        dir_display = self.current_directory
        if len(dir_display) > 40:
            dir_display = f"...{dir_display[-40:]}"
        self.dir_label.config(text=dir_display, foreground=t['fg'])
        file_count_text = f"{len(mlg_files)} file{'s' if len(mlg_files) != 1 else ''}"
        self.file_count_label.config(text=file_count_text)

        # Build set of recent files in this directory
        recent_in_dir = []
        for rf in getattr(self, '_recent_files', []):
            if os.path.dirname(rf) == self.current_directory:
                fname = os.path.basename(rf)
                if fname.lower().endswith('.mlg') and fname in mlg_files:
                    recent_in_dir.append(fname)

        # Show progress bar and scan files in background thread
        self._loading = True
        self._load_cancelled.clear()
        self._scan_mlg_files = mlg_files
        self._scan_recent_in_dir = recent_in_dir
        self._scan_directory = self.current_directory
        self._show_progress(f"Scanning {len(mlg_files)} files...")

        # Drain stale messages
        while not self._progress_queue.empty():
            try:
                self._progress_queue.get_nowait()
            except queue.Empty:
                break

        self._load_thread = threading.Thread(
            target=self._scan_files_worker,
            args=(self.current_directory, mlg_files),
            daemon=True
        )
        self._load_thread.start()
        self.after(50, self._poll_scan_progress)

    def _scan_files_worker(self, directory, mlg_files):
        """Background worker: scan MLG files for record counts."""
        try:
            total = len(mlg_files)
            file_info = {}
            file_displays = {}
            for idx, file in enumerate(mlg_files, 1):
                if self._load_cancelled.is_set():
                    self._progress_queue.put(('cancelled',))
                    return
                file_path = os.path.join(directory, file)
                try:
                    parser = MLGParser(file_path)
                    parsed_data = parser.parse()
                    record_count = len(parsed_data['records'])
                    file_info[file] = {
                        'records': record_count,
                        'size_mb': os.path.getsize(file_path) / (1024 * 1024)
                    }
                    file_displays[file] = f"{file} ({record_count:,} records)"
                except Exception:
                    file_info[file] = {'records': 0, 'size_mb': 0}
                    file_displays[file] = f"{file} (error reading)"

                pct = int(idx / total * 100)
                self._progress_queue.put(('progress', pct, f"Scanning files... {idx}/{total}"))

            self._progress_queue.put(('scan_done', file_info, file_displays))
        except Exception as e:
            self._progress_queue.put(('error', str(e), traceback.format_exc()))

    def _poll_scan_progress(self):
        """Main-thread poll: update progress bar during folder scanning."""
        try:
            while True:
                msg = self._progress_queue.get_nowait()
                if msg[0] == 'progress':
                    self._update_progress(msg[1], msg[2])
                elif msg[0] == 'scan_done':
                    self._finish_scan(msg[1], msg[2])
                    return
                elif msg[0] == 'error':
                    self._hide_progress()
                    self._loading = False
                    messagebox.showerror("Error", f"Cannot read directory:\n{msg[1]}")
                    self.statusbar.config(text="Error reading directory")
                    return
                elif msg[0] == 'cancelled':
                    self._hide_progress()
                    self._loading = False
                    self.statusbar.config(text="Scan cancelled")
                    return
        except queue.Empty:
            pass

        if self._load_thread and self._load_thread.is_alive():
            self.after(50, self._poll_scan_progress)
        else:
            self._hide_progress()
            self._loading = False

    def _finish_scan(self, file_info, file_displays):
        """Apply scan results to UI (runs on main thread)."""
        self.file_info.update(file_info)
        mlg_files = self._scan_mlg_files
        recent_in_dir = self._scan_recent_in_dir

        # Populate Recent section
        for fname in recent_in_dir:
            display = file_displays.get(fname, fname)
            self.file_tree.insert('_recent', 'end', text=display,
                                  values=(fname,), tags=('file',))

        # Update Recent section visibility
        if not recent_in_dir:
            self.file_tree.item('_recent', open=False)
        else:
            self.file_tree.item('_recent', open=True)

        # Populate All Files section
        for file in mlg_files:
            display = file_displays.get(file, file)
            self.file_tree.insert('_allfiles', 'end', text=display,
                                  values=(file,), tags=('file',))

        # Update status
        folder_name = os.path.basename(self._scan_directory)
        self._hide_progress()
        self._loading = False
        self.statusbar.config(text=f"Found {len(mlg_files)} .mlg files in {folder_name}")

        # Load any pending file (e.g. from session restore)
        pending = getattr(self, '_pending_load_file', None)
        if pending:
            self._pending_load_file = None
            if os.path.isfile(pending):
                self.load_file(pending)
    
    def _on_tree_select(self, event, force_reload=False):
        """Handle file selection from sidebar Treeview."""
        if self._loading:
            return
        
        selection = self.file_tree.selection()
        if not selection:
            return

        item_id = selection[0]
        # Ignore clicks on section headers
        if item_id in ('_recent', '_allfiles'):
            return

        values = self.file_tree.item(item_id, 'values')
        if not values:
            return
        selected_file = values[0]

        file_path = os.path.join(self.current_directory, selected_file)

        # Don't reload if it's already the current file (unless forced)
        if not force_reload and file_path == self.current_file:
            return

        self.load_file(file_path)

    def on_file_select(self, event, force_reload=False):
        """Handle file selection (delegates to tree handler)."""
        self._on_tree_select(event, force_reload=force_reload)

    def _select_file_in_tree(self, filename: str) -> None:
        """Select and reveal a file in the sidebar Treeview."""
        for section in ('_allfiles', '_recent'):
            for child in self.file_tree.get_children(section):
                if self.file_tree.item(child, 'text').rstrip(' ★') == filename:
                    self.file_tree.selection_set(child)
                    self.file_tree.see(child)
                    return

    def load_file(self, file_path: str) -> None:
        """Load and parse an MLG file (non-blocking, runs in background thread)."""
        if self._loading:
            return
        
        try:
            # Check file size (main thread — may show dialog)
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
        except OSError:
            return
        
        # Clear previous debug log
        self.debug_text.config(state=tk.NORMAL)
        self.debug_text.delete("1.0", tk.END)
        self.debug_text.config(state=tk.DISABLED)
        
        self.log_debug("=" * 70, 'header')
        self.log_debug(f"LOADING FILE: {os.path.basename(file_path)}", 'header')
        self.log_debug("=" * 70, 'header')
        self.log_debug(f"File path: {file_path}")
        self.log_debug(f"File size: {file_size_mb:.2f} MB")
        
        # Show progress bar and start background thread
        self._loading = True
        self._load_cancelled.clear()
        self._load_file_path = file_path
        self._show_progress(f"Loading {os.path.basename(file_path)}...")
        
        # Drain any stale messages from the queue
        while not self._progress_queue.empty():
            try:
                self._progress_queue.get_nowait()
            except queue.Empty:
                break
        
        self._load_thread = threading.Thread(
            target=self._load_worker, args=(file_path,), daemon=True
        )
        self._load_thread.start()
        self.after(50, self._poll_load_progress)
    
    def _load_worker(self, file_path):
        """Background worker: parse MLG file and push results to queue."""
        try:
            parser = MLGParser(file_path)
            
            def on_progress(current, total):
                self._progress_queue.put(('progress', current, total))
            
            parsed_data = parser.parse(
                progress_callback=on_progress,
                cancelled_fn=self._load_cancelled.is_set
            )
            if self._load_cancelled.is_set():
                self._progress_queue.put(('cancelled',))
            else:
                self._progress_queue.put(('done', parsed_data))
        except Exception as e:
            self._progress_queue.put(('error', str(e), traceback.format_exc()))
    
    def _poll_load_progress(self):
        """Main-thread poll: drain queue, update progress bar, finish when done."""
        try:
            while True:
                msg = self._progress_queue.get_nowait()
                if msg[0] == 'progress':
                    _, current, total = msg
                    pct = min(100, int(current / max(1, total) * 100))
                    self._update_progress(pct, f"Parsing records... {current:,}")
                elif msg[0] == 'done':
                    self._finish_load(msg[1])
                    return
                elif msg[0] == 'error':
                    self._finish_load_error(msg[1], msg[2] if len(msg) > 2 else '')
                    return
                elif msg[0] == 'cancelled':
                    self._hide_progress()
                    self._loading = False
                    self.statusbar.config(text="Load cancelled")
                    self.log_debug("\n⚠ Load cancelled by user", 'warning')
                    return
        except queue.Empty:
            pass
        
        # Thread still running — poll again
        if self._load_thread and self._load_thread.is_alive():
            self.after(50, self._poll_load_progress)
        else:
            # Thread ended without sending done/error (shouldn't happen)
            self._hide_progress()
            self._loading = False
    
    def _finish_load(self, parsed_data):
        """Apply parsed data to UI (runs on main thread)."""
        file_path = self._load_file_path
        
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

        # Track in recent files
        self._add_recent_file(file_path)

        # Add calculated channels
        self._add_calculated_channels()

        # Update UI components with progress feedback
        self._update_progress(100, "Building data grid...")
        self.update_idletasks()
        self.populate_grid(self.log_data)
        
        # Update channel dropdown and checkboxes
        self._update_progress(100, "Loading channels...")
        self.update_idletasks()
        channel_names = self.log_data.get_numeric_channel_names()
        self.channel_combo['values'] = channel_names
        if channel_names:
            self.channel_combo.current(0)
        
        # Populate channel selection checkboxes
        self.populate_channel_checkboxes()
        
        # Update summary
        self._update_progress(100, "Calculating summary...")
        self.update_idletasks()
        self.update_summary()
        
        # Update window title and status
        self.title(f"MegaLogViewer - {self.log_data.filename}")
        
        self.log_debug(f"\n✓ UI updated successfully", 'success')
        self.log_debug(f"Ready for analysis and visualization.", 'info')
        
        # Hide progress bar and restore statusbar
        self._hide_progress()
        self._loading = False
        self.statusbar.config(
            text=f"Loaded {self.log_data.record_count:,} records from {self.log_data.filename}"
        )
        
        # Highlight current file in browser
        filename = os.path.basename(file_path)
        self._select_file_in_tree(filename)
        
        # Auto-detect and load MSQ tune file from project structure
        self._auto_detect_msq(file_path)
        
        # Update AFR record slider range
        self._update_record_slider_range()
    
    def _finish_load_error(self, error_msg, tb_str=''):
        """Handle load failure (runs on main thread)."""
        self._hide_progress()
        self._loading = False
        self.log_debug(f"\n✗ PARSING FAILED", 'error')
        self.log_debug(f"Error: {error_msg}", 'error')
        if tb_str:
            self.log_debug(f"Traceback:\n{tb_str}", 'error')
        messagebox.showerror("Error Loading File", f"Failed to load file:\n{error_msg}")
        self.statusbar.config(text="Error loading file")
    
    def _show_progress(self, text="Loading..."):
        """Show the progress bar in the statusbar area."""
        self._progress_label.config(text=text)
        self._progress_bar['value'] = 0
        self.statusbar.pack_forget()
        self._progress_frame.pack(side=tk.BOTTOM, fill=tk.X)
    
    def _hide_progress(self):
        """Hide the progress bar and restore the statusbar."""
        self._progress_bar.stop()
        self._progress_bar.config(mode='determinate')
        self._progress_frame.pack_forget()
        self.statusbar.pack(side=tk.BOTTOM, fill=tk.X)
    
    def _update_progress(self, value, text=None):
        """Update progress bar value (0-100) and optional label text."""
        self._progress_bar['value'] = value
        if text:
            self._progress_label.config(text=text)
    
    def _cancel_load(self):
        """Signal the background worker to stop parsing."""
        self._load_cancelled.set()
    
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
                self.dark_mode = settings.get('dark_mode', self.dark_mode)
                self._last_file = settings.get('last_file')
                self.accent_color_name = settings.get('accent_color', 'Blue')
                self._recent_files = settings.get('recent_files', [])
                self._sidebar_collapsed = settings.get('sidebar_collapsed', False)
                self._sidebar_saved_pos = settings.get('sidebar_width', 250)
        except (json.JSONDecodeError, IOError, OSError):
            pass  # Use defaults on error
        if not hasattr(self, '_recent_files'):
            self._recent_files = []
    
    def _save_settings(self):
        """Save application settings to config file."""
        settings_path = self._get_settings_path()
        try:
            settings = {
                'last_directory': self.current_directory,
                'last_file': self.current_file,
                'favorites': sorted(self.favorite_channels),
                'dark_mode': self.dark_mode,
                'accent_color': self.accent_color_name,
                'recent_files': getattr(self, '_recent_files', [])[:10],
                'sidebar_collapsed': getattr(self, '_sidebar_collapsed', False),
                'sidebar_width': getattr(self, '_sidebar_saved_pos', 250),
            }
            with open(settings_path, 'w') as f:
                json.dump(settings, f, indent=2)
        except (IOError, OSError):
            pass  # Silent fail for settings save
    
    def _restore_last_folder(self):
        """Ask the user whether to reopen the last folder and file on startup."""
        last_file = getattr(self, '_last_file', None)
        if self.current_directory and os.path.isdir(self.current_directory):
            msg = f"Open the last folder?\n\n{self.current_directory}"
            if last_file and os.path.isfile(last_file):
                msg += f"\n\nLast file: {os.path.basename(last_file)}"
            result = messagebox.askyesno("Restore Last Session", msg)
            if result:
                # Store file to load after scan completes
                if last_file and os.path.isfile(last_file):
                    self._pending_load_file = last_file
                self.populate_file_list()
            else:
                self.current_directory = None
    
    def export_csv(self):
        """Export current log data to CSV file."""
        if not self.log_data:
            messagebox.showwarning("No Data", "Please load a log file first.")
            return

        if self._loading:
            messagebox.showwarning("Busy", "A file operation is already in progress.")
            return

        # Show save dialog
        file_path = filedialog.asksaveasfilename(
            title="Export to CSV",
            defaultextension=".csv",
            filetypes=[("CSV Files", "*.csv"), ("All Files", "*.*")]
        )

        if not file_path:
            return

        self._loading = True
        self._load_cancelled.clear()
        self._show_progress(f"Exporting to {os.path.basename(file_path)}...")

        records = list(self.log_data.records)
        fieldnames = list(self.log_data.get_channel_names())

        self._load_thread = threading.Thread(
            target=self._export_csv_worker,
            args=(file_path, records, fieldnames),
            daemon=True
        )
        self._load_thread.start()
        self.after(50, self._poll_export_progress, file_path)

    def _export_csv_worker(self, file_path, records, fieldnames):
        """Background worker: write CSV and send progress via queue."""
        try:
            total = len(records)
            with open(file_path, 'w', newline='') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                for i, record in enumerate(records, 1):
                    if self._load_cancelled.is_set():
                        self._progress_queue.put(('cancelled',))
                        return
                    writer.writerow(record)
                    if i % 1000 == 0:
                        pct = int(i / total * 100) if total else 100
                        self._progress_queue.put(
                            ('progress', pct, f"Exporting row {i:,}/{total:,}"))
            self._progress_queue.put(('done',))
        except (IOError, OSError) as e:
            self._progress_queue.put(('error', str(e)))

    def _poll_export_progress(self, file_path):
        """Poll queue for export worker messages."""
        try:
            while not self._progress_queue.empty():
                msg = self._progress_queue.get_nowait()
                if msg[0] == 'progress':
                    self._update_progress(msg[1], msg[2])
                elif msg[0] == 'done':
                    self._finish_export(file_path)
                    return
                elif msg[0] == 'error':
                    self._finish_export_error(msg[1])
                    return
                elif msg[0] == 'cancelled':
                    self._loading = False
                    self._hide_progress()
                    self.statusbar.config(text="Export cancelled")
                    # Remove partial file
                    try:
                        os.remove(file_path)
                    except OSError:
                        pass
                    return
        except Exception:
            pass
        self.after(50, self._poll_export_progress, file_path)

    def _finish_export(self, file_path):
        """Handle successful export completion."""
        self._loading = False
        self._hide_progress()
        count = self.log_data.record_count if self.log_data else 0
        self.statusbar.config(text=f"Exported {count} records to CSV")
        messagebox.showinfo("Export Complete",
                            f"Data exported successfully to:\n{file_path}")

    def _finish_export_error(self, error_msg):
        """Handle export error."""
        self._loading = False
        self._hide_progress()
        messagebox.showerror("Export Error",
                             f"Failed to export CSV:\n{error_msg}")
        self.statusbar.config(text="Export failed")
    
    # --- Tune Tab Methods ---
    
    def create_tune_view(self):
        """Create tune view with search and treeview for MSQ constants."""
        # Toolbar with search and file controls
        tune_toolbar = ttk.Frame(self.tune_tab)
        tune_toolbar.pack(side=tk.TOP, fill=tk.X, padx=12, pady=(12, 4))
        
        ttk.Button(
            tune_toolbar,
            text="Open Tune",
            command=self.open_msq_file
        ).pack(side=tk.LEFT, padx=4)
        
        ttk.Button(
            tune_toolbar,
            text="Export Tune CSV",
            command=self.export_tune_csv
        ).pack(side=tk.LEFT, padx=4)
        
        ttk.Separator(tune_toolbar, orient=tk.VERTICAL).pack(
            side=tk.LEFT, fill=tk.Y, padx=12
        )
        
        # Search controls
        ttk.Label(tune_toolbar, text="Search:").pack(side=tk.LEFT, padx=(8, 4))
        self.tune_search_var = tk.StringVar()
        self.tune_search_var.trace_add('write', self._on_tune_search_changed)
        self.tune_search_entry = ttk.Entry(
            tune_toolbar,
            textvariable=self.tune_search_var,
            width=30
        )
        self.tune_search_entry.pack(side=tk.LEFT, padx=4)
        
        ttk.Button(
            tune_toolbar,
            text="Clear",
            command=lambda: self.tune_search_var.set('')
        ).pack(side=tk.LEFT, padx=4)
        
        # Filter by type
        ttk.Separator(tune_toolbar, orient=tk.VERTICAL).pack(
            side=tk.LEFT, fill=tk.Y, padx=12
        )
        ttk.Label(tune_toolbar, text="Type:").pack(side=tk.LEFT, padx=(8, 4))
        self.tune_type_var = tk.StringVar(value="All")
        self.tune_type_combo = ttk.Combobox(
            tune_toolbar,
            textvariable=self.tune_type_var,
            values=["All", "constant", "pcVariable"],
            width=12,
            state="readonly"
        )
        self.tune_type_combo.pack(side=tk.LEFT, padx=4)
        self.tune_type_combo.bind('<<ComboboxSelected>>', lambda e: self._apply_tune_filter())
        
        # Entry count label
        self.tune_count_label = ttk.Label(tune_toolbar, text="0 entries", foreground="#8E8E93")
        self.tune_count_label.pack(side=tk.RIGHT, padx=12)
        
        # Treeview with scrollbars
        tree_frame = ttk.Frame(self.tune_tab)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 12))
        
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
        """Load and parse an MSQ tune file (non-blocking)."""
        if self._loading:
            return
        
        self._loading = True
        self._load_cancelled.clear()
        self._load_file_path = file_path
        self._show_progress(f"Loading tune {os.path.basename(file_path)}...")
        self._progress_bar.config(mode='indeterminate')
        self._progress_bar.start(15)
        
        # Drain stale messages
        while not self._progress_queue.empty():
            try:
                self._progress_queue.get_nowait()
            except queue.Empty:
                break
        
        self._load_thread = threading.Thread(
            target=self._load_msq_worker, args=(file_path,), daemon=True
        )
        self._load_thread.start()
        self.after(50, self._poll_msq_progress)
    
    def _load_msq_worker(self, file_path):
        """Background worker: parse MSQ file and push result to queue."""
        try:
            parser = MSQParser(file_path)
            msq_data = parser.parse()
            if self._load_cancelled.is_set():
                self._progress_queue.put(('cancelled',))
            else:
                self._progress_queue.put(('done', msq_data))
        except Exception as e:
            self._progress_queue.put(('error', str(e), traceback.format_exc()))
    
    def _poll_msq_progress(self):
        """Main-thread poll for MSQ loading."""
        try:
            while True:
                msg = self._progress_queue.get_nowait()
                if msg[0] == 'done':
                    self._finish_msq_load(msg[1])
                    return
                elif msg[0] == 'error':
                    self._finish_load_error(msg[1], msg[2] if len(msg) > 2 else '')
                    return
                elif msg[0] == 'cancelled':
                    self._hide_progress()
                    self._loading = False
                    self.statusbar.config(text="Load cancelled")
                    return
        except queue.Empty:
            pass
        
        if self._load_thread and self._load_thread.is_alive():
            self.after(50, self._poll_msq_progress)
        else:
            self._hide_progress()
            self._loading = False
    
    def _finish_msq_load(self, msq_data):
        """Apply parsed MSQ data to UI (runs on main thread)."""
        file_path = self._load_file_path
        self.msq_data = msq_data
        self.msq_file = file_path
        
        self.log_debug(f"Loaded tune file: {os.path.basename(file_path)}", 'success')
        self.log_debug(f"  Entries: {self.msq_data['entry_count']}", 'info')
        bib = self.msq_data.get('bibliography', {})
        if bib.get('author'):
            self.log_debug(f"  Author: {bib['author']}", 'info')
        if bib.get('writeDate'):
            self.log_debug(f"  Date: {bib['writeDate']}", 'info')
        
        self._progress_bar.stop()
        self._progress_bar.config(mode='determinate')
        self._populate_tune_tree()
        self._populate_afr_tables()
        
        self._hide_progress()
        self._loading = False
        self.statusbar.config(
            text=f"Loaded {self.msq_data['entry_count']} tune entries from {os.path.basename(file_path)}"
        )
        
        # Switch to tune tab
        self.notebook.select(self.tune_tab)
    
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
    
    def create_afr_tuning_view(self):
        """Create AFR Tuning view with VE table heatmap, 3D surface, comparison, and editing."""
        # Row 1: Main toolbar
        afr_toolbar = ttk.Frame(self.afr_tab)
        afr_toolbar.pack(side=tk.TOP, fill=tk.X, padx=12, pady=(12, 4))

        ttk.Button(
            afr_toolbar,
            text="Open Tune",
            command=self.open_msq_file
        ).pack(side=tk.LEFT, padx=4)

        ttk.Button(
            afr_toolbar,
            text="Add Log",
            command=self._add_extra_log_file
        ).pack(side=tk.LEFT, padx=4)
        self._extra_log_data: List[LogData] = []
        self._extra_log_label = ttk.Label(afr_toolbar, text="")
        self._extra_log_label.pack(side=tk.LEFT, padx=4)

        ttk.Separator(afr_toolbar, orient=tk.VERTICAL).pack(
            side=tk.LEFT, fill=tk.Y, padx=12
        )

        # Table selector
        ttk.Label(afr_toolbar, text="Table:").pack(side=tk.LEFT, padx=(8, 4))
        self.afr_table_var = tk.StringVar()
        self.afr_table_combo = ttk.Combobox(
            afr_toolbar,
            textvariable=self.afr_table_var,
            width=25,
            state="readonly"
        )
        self.afr_table_combo.pack(side=tk.LEFT, padx=4)

        # Plot type toggle (includes Compare mode)
        ttk.Separator(afr_toolbar, orient=tk.VERTICAL).pack(
            side=tk.LEFT, fill=tk.Y, padx=12
        )
        ttk.Label(afr_toolbar, text="View:").pack(side=tk.LEFT, padx=(8, 4))
        self.afr_plot_type_var = tk.StringVar(value="2D Heatmap")
        self.afr_plot_type_combo = ttk.Combobox(
            afr_toolbar,
            textvariable=self.afr_plot_type_var,
            values=["2D Heatmap", "3D Surface", "Compare", "AFR Analysis",
                    "Hit Count", "VE Difference", "Log Comparison"],
            width=14,
            state="readonly"
        )
        self.afr_plot_type_combo.pack(side=tk.LEFT, padx=4)
        self.afr_plot_type_combo.bind('<<ComboboxSelected>>', self._on_afr_view_changed)

        ttk.Button(
            afr_toolbar,
            text="Plot",
            command=self._plot_afr_table
        ).pack(side=tk.LEFT, padx=8)

        # Info label
        self.afr_info_label = ttk.Label(
            afr_toolbar, text="No tune file loaded", foreground="#8E8E93"
        )
        self.afr_info_label.pack(side=tk.RIGHT, padx=12)

        # Row 2: Compare & Log Position toolbar
        afr_toolbar2 = ttk.Frame(self.afr_tab)
        afr_toolbar2.pack(side=tk.TOP, fill=tk.X, padx=12, pady=(0, 4))

        # Compare table selector (shown when Compare mode selected)
        self._afr_compare_frame = ttk.Frame(afr_toolbar2)
        self._afr_compare_frame.pack(side=tk.LEFT)
        ttk.Label(self._afr_compare_frame, text="Compare with:").pack(side=tk.LEFT, padx=(0, 2))
        self.afr_compare_var = tk.StringVar()
        self.afr_compare_combo = ttk.Combobox(
            self._afr_compare_frame,
            textvariable=self.afr_compare_var,
            width=25,
            state="readonly"
        )
        self.afr_compare_combo.pack(side=tk.LEFT, padx=2)
        # Initially hidden until Compare mode is selected
        self._afr_compare_frame.pack_forget()

        # AFR Analysis filter frame (shown when AFR Analysis or Hit Count selected)
        self._afr_filter_frame = ttk.Frame(afr_toolbar2)
        self._afr_filter_frame.pack(side=tk.LEFT)
        self.afr_filter_enabled_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            self._afr_filter_frame,
            text="Filter",
            variable=self.afr_filter_enabled_var
        ).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Label(self._afr_filter_frame, text="Min RPM:").pack(side=tk.LEFT, padx=(0, 2))
        self.afr_filter_rpm_var = tk.StringVar(value="500")
        ttk.Entry(self._afr_filter_frame, textvariable=self.afr_filter_rpm_var,
                  width=6).pack(side=tk.LEFT, padx=2)
        ttk.Label(self._afr_filter_frame, text="Min CLT:").pack(side=tk.LEFT, padx=(8, 2))
        self.afr_filter_clt_var = tk.StringVar(value="150")
        ttk.Entry(self._afr_filter_frame, textvariable=self.afr_filter_clt_var,
                  width=6).pack(side=tk.LEFT, padx=2)
        ttk.Label(self._afr_filter_frame, text="Min TPS:").pack(side=tk.LEFT, padx=(8, 2))
        self.afr_filter_tps_var = tk.StringVar(value="0")
        ttk.Entry(self._afr_filter_frame, textvariable=self.afr_filter_tps_var,
                  width=6).pack(side=tk.LEFT, padx=2)
        ttk.Label(self._afr_filter_frame, text="RPM Δmax:").pack(side=tk.LEFT, padx=(8, 2))
        self.afr_filter_rpm_delta_var = tk.StringVar(value="200")
        ttk.Entry(self._afr_filter_frame, textvariable=self.afr_filter_rpm_delta_var,
                  width=6).pack(side=tk.LEFT, padx=2)
        ttk.Separator(self._afr_filter_frame, orient=tk.VERTICAL).pack(
            side=tk.LEFT, fill=tk.Y, padx=8
        )
        ttk.Label(self._afr_filter_frame, text="Target AFR:").pack(side=tk.LEFT, padx=(0, 2))
        self.afr_target_source_var = tk.StringVar(value="Log Channel")
        self.afr_target_source_combo = ttk.Combobox(
            self._afr_filter_frame,
            textvariable=self.afr_target_source_var,
            width=18,
            state="readonly"
        )
        self.afr_target_source_combo['values'] = ["Log Channel"]
        self.afr_target_source_combo.pack(side=tk.LEFT, padx=2)
        self._afr_filter_frame.pack_forget()

        ttk.Separator(afr_toolbar2, orient=tk.VERTICAL).pack(
            side=tk.LEFT, fill=tk.Y, padx=10
        )

        # Log scatter overlay checkbox
        self.afr_scatter_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            afr_toolbar2,
            text="Show Log Points",
            variable=self.afr_scatter_var,
            command=self._on_scatter_toggle
        ).pack(side=tk.LEFT, padx=5)

        # Cell confidence indicator checkbox
        self.afr_confidence_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            afr_toolbar2,
            text="Confidence",
            variable=self.afr_confidence_var,
            command=self._on_confidence_toggle
        ).pack(side=tk.LEFT, padx=5)

        ttk.Separator(afr_toolbar2, orient=tk.VERTICAL).pack(
            side=tk.LEFT, fill=tk.Y, padx=5
        )

        # Log position highlight controls
        self.afr_log_highlight_var = tk.BooleanVar(value=False)
        self.afr_log_highlight_cb = ttk.Checkbutton(
            afr_toolbar2,
            text="Show Log Position",
            variable=self.afr_log_highlight_var,
            command=self._on_log_highlight_toggle
        )
        self.afr_log_highlight_cb.pack(side=tk.LEFT, padx=5)

        ttk.Label(afr_toolbar2, text="Record:").pack(side=tk.LEFT, padx=(10, 2))
        self.afr_record_var = tk.IntVar(value=0)
        self.afr_record_slider = ttk.Scale(
            afr_toolbar2,
            from_=0, to=1,
            orient=tk.HORIZONTAL,
            variable=self.afr_record_var,
            command=self._on_record_slider_changed
        )
        self.afr_record_slider.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)
        self.afr_record_label = ttk.Label(afr_toolbar2, text="0/0", width=12)
        self.afr_record_label.pack(side=tk.LEFT, padx=2)

        # Row 3: Edit toolbar
        afr_edit_toolbar = ttk.Frame(self.afr_tab)
        afr_edit_toolbar.pack(side=tk.TOP, fill=tk.X, padx=12, pady=(0, 4))

        self.afr_edit_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            afr_edit_toolbar,
            text="Edit Mode",
            variable=self.afr_edit_var,
            command=self._on_edit_mode_toggle
        ).pack(side=tk.LEFT, padx=5)

        ttk.Button(
            afr_edit_toolbar,
            text="+1",
            command=lambda: self._adjust_selected_cell(1),
            width=4
        ).pack(side=tk.LEFT, padx=2)
        ttk.Button(
            afr_edit_toolbar,
            text="-1",
            command=lambda: self._adjust_selected_cell(-1),
            width=4
        ).pack(side=tk.LEFT, padx=2)
        ttk.Button(
            afr_edit_toolbar,
            text="+5",
            command=lambda: self._adjust_selected_cell(5),
            width=4
        ).pack(side=tk.LEFT, padx=2)
        ttk.Button(
            afr_edit_toolbar,
            text="-5",
            command=lambda: self._adjust_selected_cell(-5),
            width=4
        ).pack(side=tk.LEFT, padx=2)

        ttk.Separator(afr_edit_toolbar, orient=tk.VERTICAL).pack(
            side=tk.LEFT, fill=tk.Y, padx=10
        )

        ttk.Button(
            afr_edit_toolbar,
            text="Undo",
            command=self._undo_afr_edit
        ).pack(side=tk.LEFT, padx=2)
        ttk.Button(
            afr_edit_toolbar,
            text="Redo",
            command=self._redo_afr_edit
        ).pack(side=tk.LEFT, padx=2)

        ttk.Button(
            afr_edit_toolbar,
            text="Export MSQ...",
            command=self._export_edited_msq
        ).pack(side=tk.LEFT, padx=2)

        ttk.Separator(afr_edit_toolbar, orient=tk.VERTICAL).pack(
            side=tk.LEFT, fill=tk.Y, padx=10
        )

        ttk.Button(
            afr_edit_toolbar,
            text="Apply Suggested VE",
            command=self._apply_suggested_ve
        ).pack(side=tk.LEFT, padx=2)

        ttk.Button(
            afr_edit_toolbar,
            text="Smooth",
            command=self._smooth_ve_table
        ).pack(side=tk.LEFT, padx=2)

        ttk.Button(
            afr_edit_toolbar,
            text="Auto-Tune",
            command=self._auto_tune_ve
        ).pack(side=tk.LEFT, padx=2)

        ttk.Separator(afr_edit_toolbar, orient=tk.VERTICAL).pack(
            side=tk.LEFT, fill=tk.Y, padx=10
        )

        ttk.Button(
            afr_edit_toolbar,
            text="History",
            command=self._show_export_history
        ).pack(side=tk.LEFT, padx=2)

        self.afr_edit_info = ttk.Label(
            afr_edit_toolbar, text="", foreground="#8E8E93"
        )
        self.afr_edit_info.pack(side=tk.RIGHT, padx=12)

        # Edit state tracking
        self._afr_edit_data = None  # np.ndarray copy of current table data
        self._afr_edit_original = None  # original copy for undo-all
        self._afr_undo_stack = []  # list of np.ndarray snapshots for undo
        self._afr_redo_stack = []  # list of np.ndarray snapshots for redo
        self._afr_selected_cell = None  # (row, col) of selected cell
        self._afr_selection_end = None  # (row, col) for multi-cell range end
        self._afr_edit_table_name = None  # name of table being edited
        self._afr_export_history = []  # list of export records

        # Matplotlib figure area
        plot_frame = ttk.Frame(self.afr_tab)
        plot_frame.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 12))

        t = self._get_theme()
        self.afr_fig = Figure(figsize=(10, 8), dpi=100, facecolor=t['plot_face'])
        self.afr_ax = self.afr_fig.add_subplot(111)
        self.afr_ax.set_facecolor(t['plot_bg'])
        self.afr_ax.text(
            0.5, 0.5, 'Load a tune file to view VE tables',
            transform=self.afr_ax.transAxes, ha='center', va='center',
            fontsize=14, color=t['plot_text']
        )

        self.afr_canvas = FigureCanvasTkAgg(self.afr_fig, master=plot_frame)

        # Connect click event for cell editing
        self.afr_canvas.mpl_connect('button_press_event', self._on_afr_click)
        self.afr_canvas.mpl_connect('motion_notify_event', self._on_afr_hover)

        # Tooltip annotation (hidden by default)
        self._afr_tooltip = None
        self._afr_hover_cell = None  # Track last hovered cell to avoid redundant redraws
        self._afr_cell_stats = None  # Cached per-cell AFR stats from correction analysis

        # Toolbar
        afr_nav_frame = ttk.Frame(plot_frame)
        afr_nav_frame.pack(side=tk.BOTTOM, fill=tk.X)
        self.afr_toolbar_mpl = NavigationToolbar2Tk(
            self.afr_canvas, afr_nav_frame, pack_toolbar=False
        )
        self.afr_toolbar_mpl.update()
        self.afr_toolbar_mpl.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.afr_canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        self.afr_canvas.draw()

        # Keyboard bindings for edit mode
        canvas_widget = self.afr_canvas.get_tk_widget()
        canvas_widget.configure(takefocus=True)
        canvas_widget.bind('<Up>', self._on_afr_key)
        canvas_widget.bind('<Down>', self._on_afr_key)
        canvas_widget.bind('<Left>', self._on_afr_key)
        canvas_widget.bind('<Right>', self._on_afr_key)
        canvas_widget.bind('<Shift-Up>', self._on_afr_key)
        canvas_widget.bind('<Shift-Down>', self._on_afr_key)
        canvas_widget.bind('<Shift-Left>', self._on_afr_key)
        canvas_widget.bind('<Shift-Right>', self._on_afr_key)
        canvas_widget.bind('<plus>', self._on_afr_key)
        canvas_widget.bind('<minus>', self._on_afr_key)
        canvas_widget.bind('<KP_Add>', self._on_afr_key)
        canvas_widget.bind('<KP_Subtract>', self._on_afr_key)
        canvas_widget.bind('<Control-z>', self._on_afr_key)
        canvas_widget.bind('<Control-y>', self._on_afr_key)
        canvas_widget.bind('<Control-c>', self._on_afr_key)
        canvas_widget.bind('<Control-v>', self._on_afr_key)

    def _extract_table_entries(self) -> List[Dict[str, Any]]:
        """Find all 2D table entries from MSQ data (entries with rows and cols)."""
        if not self.msq_data:
            return []
        tables = []
        for entry in self.msq_data['entries']:
            if entry['dimensions'] and 'x' in entry['dimensions']:
                parts = entry['dimensions'].split('x')
                rows = int(parts[0])
                cols = int(parts[1])
                if rows > 1 and cols > 1:
                    tables.append(entry)
        return tables

    def _find_bins_for_table(self, table_name: str) -> Tuple[Optional[List[float]], Optional[List[float]], str, str]:
        """Find RPM and Load bins matching a table name.

        Returns (rpm_bins, load_bins, rpm_label, load_label).
        """
        if not self.msq_data:
            return None, None, 'RPM', 'kPa'

        # Determine table number suffix (e.g. '1' from 'veTable1')
        suffix = ''
        for ch in reversed(table_name):
            if ch.isdigit():
                suffix = ch + suffix
            else:
                break

        # Common bin name patterns for MegaSquirt
        rpm_candidates = [
            f'rpmBins{suffix}', f'rpm_range{suffix}', f'rpmBins',
            'rpmBins1', 'rpmBins2',
        ]
        load_candidates = [
            f'fuelLoadBins{suffix}', f'mapBins{suffix}', f'loadBins{suffix}',
            f'kpaBins{suffix}', 'fuelLoadBins1', 'fuelLoadBins2',
        ]

        rpm_bins = None
        load_bins = None
        rpm_label = 'RPM'
        load_label = 'kPa'

        for entry in self.msq_data['entries']:
            name = entry['name']
            if name in rpm_candidates and entry['value']:
                try:
                    rpm_bins = [float(v) for v in entry['value'].split()]
                    rpm_label = f"RPM ({entry.get('units', '')})" if entry.get('units') else 'RPM'
                except ValueError:
                    pass
            if name in load_candidates and entry['value']:
                try:
                    load_bins = [float(v) for v in entry['value'].split()]
                    load_label = f"{entry.get('units', 'kPa')}" if entry.get('units') else 'kPa'
                except ValueError:
                    pass

        return rpm_bins, load_bins, rpm_label, load_label

    def _populate_afr_tables(self) -> None:
        """Populate AFR Tuning table selector from MSQ data."""
        tables = self._extract_table_entries()
        if not tables:
            self.afr_table_combo['values'] = []
            self.afr_compare_combo['values'] = []
            self.afr_info_label.config(text="No 2D tables found")
            return

        table_names = [t['name'] for t in tables]
        self.afr_table_combo['values'] = table_names
        self.afr_compare_combo['values'] = table_names
        self.afr_info_label.config(text=f"{len(table_names)} tables found")

        # Auto-select veTable1 if available, otherwise first table
        default = 'veTable1'
        if default in table_names:
            self.afr_table_combo.set(default)
        else:
            self.afr_table_combo.current(0)

        # Set compare combo to second table or same as primary
        if len(table_names) > 1:
            self.afr_compare_combo.current(1)
        else:
            self.afr_compare_combo.current(0)

        # Populate AFR target source combo with AFR tables from MSQ
        afr_target_options = ["Log Channel"]
        for name in table_names:
            lower = name.lower()
            if 'afr' in lower or 'target' in lower or 'lambda' in lower:
                afr_target_options.append(name)
        self.afr_target_source_combo['values'] = afr_target_options
        self.afr_target_source_var.set("Log Channel")

        # Update record slider if log data is loaded
        self._update_record_slider_range()

        # Reset edit state
        self._afr_edit_data = None
        self._afr_edit_original = None
        self._afr_selected_cell = None
        self._afr_edit_table_name = None

        # Auto-plot the selected table
        self._plot_afr_table()

    def _plot_afr_table(self) -> None:
        """Plot the selected table based on chosen view type."""
        table_name = self.afr_table_var.get()
        if not table_name or not self.msq_data:
            return

        # Find the table entry
        table_entry = None
        for entry in self.msq_data['entries']:
            if entry['name'] == table_name:
                table_entry = entry
                break
        if not table_entry:
            return

        # Parse dimensions and values
        parts = table_entry['dimensions'].split('x')
        rows = int(parts[0])
        cols = int(parts[1])
        try:
            values = [float(v) for v in table_entry['value'].split()]
        except ValueError:
            self.afr_info_label.config(text="Cannot parse table values as numbers")
            return

        if len(values) != rows * cols:
            self.afr_info_label.config(text=f"Value count {len(values)} != {rows}x{cols}")
            return

        data = np.array(values).reshape(rows, cols)

        # Store edit data if table changed or no edit data exists
        if self._afr_edit_table_name != table_name:
            self._afr_edit_data = data.copy()
            self._afr_edit_original = data.copy()
            self._afr_edit_table_name = table_name
            self._afr_selected_cell = None
            self._afr_undo_stack.clear()
            self._afr_redo_stack.clear()
        elif self._afr_edit_data is not None and self.afr_edit_var.get():
            # Use edited data for display
            data = self._afr_edit_data

        # Find axis bins
        rpm_bins, load_bins, rpm_label, load_label = self._find_bins_for_table(table_name)
        if rpm_bins is None:
            rpm_bins = list(range(cols))
            rpm_label = 'Column'
        if load_bins is None:
            load_bins = list(range(rows))
            load_label = 'Row'

        # Trim bins to match data dimensions
        rpm_bins = rpm_bins[:cols]
        load_bins = load_bins[:rows]

        units = table_entry.get('units', '')
        title = f"{table_name}" + (f" ({units})" if units else "")

        # Store bins for highlight overlay
        self._afr_rpm_bins = rpm_bins
        self._afr_load_bins = load_bins

        plot_type = self.afr_plot_type_var.get()
        if plot_type == "3D Surface":
            self._plot_ve_surface(data, rpm_bins, load_bins, rpm_label, load_label, title)
        elif plot_type == "Compare":
            self._plot_ve_comparison(data, rpm_bins, load_bins, rpm_label, load_label, title,
                                     table_name)
        elif plot_type == "AFR Analysis":
            self._plot_afr_correction_map(data, rpm_bins, load_bins, rpm_label, load_label,
                                          title, table_name)
        elif plot_type == "Hit Count":
            self._plot_hit_count_map(rpm_bins, load_bins, rpm_label, load_label, title)
        elif plot_type == "VE Difference":
            self._plot_ve_difference(data, rpm_bins, load_bins, rpm_label, load_label,
                                     title, table_name)
        elif plot_type == "Log Comparison":
            self._plot_log_comparison(data, rpm_bins, load_bins, rpm_label, load_label,
                                      title, table_name)
        else:
            self._plot_ve_heatmap(data, rpm_bins, load_bins, rpm_label, load_label, title)

        # Apply log position highlight if enabled
        if self.afr_log_highlight_var.get() and plot_type == "2D Heatmap":
            self._update_ve_highlight()

    def _plot_ve_heatmap(self, data: np.ndarray, rpm_bins: List[float],
                         load_bins: List[float], rpm_label: str,
                         load_label: str, title: str) -> None:
        """Render 2D heatmap with cell annotations, TunerStudio style."""
        # Reset tooltip state on replot
        self._afr_tooltip = None
        self._afr_hover_cell = None

        t = self._get_theme()
        self.afr_fig.clear()
        ax = self.afr_fig.add_subplot(111)
        ax.set_facecolor(t['plot_bg'])

        rows, cols = data.shape
        im = ax.pcolormesh(
            range(cols + 1), range(rows + 1), data,
            cmap='jet', shading='flat'
        )

        # Annotate cells with values
        text_color = 'white'
        for r in range(rows):
            for c in range(cols):
                val = data[r, c]
                ax.text(
                    c + 0.5, r + 0.5, f'{val:.0f}',
                    ha='center', va='center',
                    fontsize=max(5, min(8, 120 // max(rows, cols))),
                    color=text_color, fontweight='bold'
                )

        # Axis labels with bin values
        ax.set_xticks([i + 0.5 for i in range(cols)])
        ax.set_xticklabels([f'{v:.0f}' for v in rpm_bins], fontsize=7, color=t['plot_tick'])
        ax.set_yticks([i + 0.5 for i in range(rows)])
        ax.set_yticklabels([f'{v:.0f}' for v in load_bins], fontsize=7, color=t['plot_tick'])

        ax.set_xlabel(rpm_label, fontsize=10, color=t['plot_text'])
        ax.set_ylabel(load_label, fontsize=10, color=t['plot_text'])
        ax.set_title(title, fontsize=12, color=t['plot_text'], pad=10)
        ax.tick_params(colors=t['plot_tick'])

        # Colorbar
        cbar = self.afr_fig.colorbar(im, ax=ax, pad=0.02)
        cbar.ax.tick_params(colors=t['plot_tick'], labelsize=8)

        self.afr_fig.set_facecolor(t['plot_face'])
        self.afr_fig.tight_layout()
        self.afr_ax = ax

        # Overlay log scatter points if enabled
        if self.afr_scatter_var.get():
            self._draw_scatter_overlay(ax, rpm_bins, load_bins)

        # Overlay confidence borders if enabled
        if self.afr_confidence_var.get():
            self._draw_confidence_borders(ax, rpm_bins, load_bins)

        self.afr_canvas.draw()

    def _plot_ve_difference(self, data: np.ndarray, rpm_bins: List[float],
                            load_bins: List[float], rpm_label: str,
                            load_label: str, title: str,
                            table_name: str) -> None:
        """Show delta between edited and original VE values with diverging colormap."""
        if self._afr_edit_original is None or self._afr_edit_data is None:
            self.afr_info_label.config(text="Enter Edit Mode and make changes first")
            return

        diff = self._afr_edit_data - self._afr_edit_original
        changed = int(np.sum(diff != 0))
        if changed == 0:
            self.afr_info_label.config(text="No VE edits to display — make changes in Edit Mode")

        t = self._get_theme()
        self.afr_fig.clear()
        ax = self.afr_fig.add_subplot(111)
        ax.set_facecolor(t['plot_bg'])

        rows, cols = diff.shape
        vmax = max(abs(diff.min()), abs(diff.max())) or 1
        im = ax.pcolormesh(
            range(cols + 1), range(rows + 1), diff,
            cmap='RdBu_r', shading='flat', vmin=-vmax, vmax=vmax
        )

        # Annotate cells with delta values
        font_size = max(5, min(8, 120 // max(rows, cols)))
        for r in range(rows):
            for c in range(cols):
                d = diff[r, c]
                if d != 0:
                    sign = '+' if d > 0 else ''
                    ax.text(c + 0.5, r + 0.5,
                            f'{sign}{d:.1f}\n({self._afr_edit_original[r, c]:.0f}\u2192'
                            f'{self._afr_edit_data[r, c]:.0f})',
                            ha='center', va='center', fontsize=max(4, font_size - 1),
                            color='white', fontweight='bold')
                else:
                    ax.text(c + 0.5, r + 0.5, '0',
                            ha='center', va='center', fontsize=font_size,
                            color='gray')

        ax.set_xticks([i + 0.5 for i in range(cols)])
        ax.set_xticklabels([f'{v:.0f}' for v in rpm_bins], fontsize=7, color=t['plot_tick'])
        ax.set_yticks([i + 0.5 for i in range(rows)])
        ax.set_yticklabels([f'{v:.0f}' for v in load_bins], fontsize=7, color=t['plot_tick'])
        ax.set_xlabel(rpm_label, fontsize=10, color=t['plot_text'])
        ax.set_ylabel(load_label, fontsize=10, color=t['plot_text'])
        ax.set_title(f'VE Difference — {table_name}', fontsize=12, color=t['plot_text'], pad=10)
        ax.tick_params(colors=t['plot_tick'])

        cbar = self.afr_fig.colorbar(im, ax=ax, pad=0.02)
        cbar.ax.tick_params(colors=t['plot_tick'], labelsize=8)
        cbar.set_label('VE Change', color=t['plot_text'], fontsize=9)

        self.afr_fig.set_facecolor(t['plot_face'])
        self.afr_fig.tight_layout()
        self.afr_ax = ax
        self.afr_canvas.draw()

        total = rows * cols
        self.afr_info_label.config(
            text=f"VE Difference: {changed}/{total} cells changed | "
                 f"Range: {diff.min():+.1f} to {diff.max():+.1f}")

    def _on_scatter_toggle(self) -> None:
        """Handle toggling of log scatter overlay."""
        if self.afr_scatter_var.get() and not self.log_data:
            self.afr_info_label.config(text="Load a log file first for scatter overlay")
            self.afr_scatter_var.set(False)
            return
        self._plot_afr_table()

    def _on_confidence_toggle(self) -> None:
        """Handle toggling of cell confidence indicator overlay."""
        if self.afr_confidence_var.get() and not self.log_data:
            self.afr_info_label.config(text="Load a log file first for confidence overlay")
            self.afr_confidence_var.set(False)
            return
        self._plot_afr_table()

    def _compute_cell_hit_counts(self, rpm_bins: List[float],
                                  load_bins: List[float]) -> np.ndarray:
        """Compute per-cell sample count from all loaded log data."""
        rows = len(load_bins)
        cols = len(rpm_bins)
        counts = np.zeros((rows, cols), dtype=int)
        log_sources = [self.log_data] + getattr(self, '_extra_log_data', [])
        for ld in log_sources:
            if not ld or not ld.records:
                continue
            available = set(ld.records[0].keys())
            rpm_ch = next((ch for ch in ['RPM', 'rpm', 'Rpm'] if ch in available), None)
            map_ch = next((ch for ch in ['MAP', 'fuelLoad', 'kPa', 'map', 'MAP_kPa']
                           if ch in available), None)
            if not rpm_ch or not map_ch:
                continue
            for record in ld.records:
                col = self._find_bin_index(record.get(rpm_ch, 0), rpm_bins)
                row = self._find_bin_index(record.get(map_ch, 0), load_bins)
                if 0 <= row < rows and 0 <= col < cols:
                    counts[row, col] += 1
        return counts

    def _draw_confidence_borders(self, ax, rpm_bins: List[float],
                                  load_bins: List[float]) -> None:
        """Draw colored borders around cells based on sample count confidence."""
        from matplotlib.patches import Rectangle
        counts = self._compute_cell_hit_counts(rpm_bins, load_bins)
        rows, cols = counts.shape
        for r in range(rows):
            for c in range(cols):
                n = counts[r, c]
                if n < 3:
                    color = '#ff4444'   # red — low confidence
                elif n < 10:
                    color = '#ffaa00'   # yellow — moderate
                else:
                    color = '#44cc44'   # green — high confidence
                lw = 1.5
                rect = Rectangle((c, r), 1, 1, linewidth=lw,
                                 edgecolor=color, facecolor='none', zorder=6)
                ax.add_patch(rect)

    def _draw_scatter_overlay(self, ax, rpm_bins: List[float],
                               load_bins: List[float]) -> None:
        """Overlay log RPM/MAP data points on the heatmap, colored by AFR error."""
        if not self.log_data or not self.log_data.records:
            return

        available = set(self.log_data.records[0].keys())
        rpm_ch = None
        for ch in ['RPM', 'rpm', 'Rpm']:
            if ch in available:
                rpm_ch = ch
                break
        map_ch = None
        for ch in ['MAP', 'fuelLoad', 'kPa', 'map', 'MAP_kPa']:
            if ch in available:
                map_ch = ch
                break
        if not rpm_ch or not map_ch:
            return

        # Detect AFR channels for coloring
        actual_ch, target_ch = self._find_afr_channels()
        has_afr = actual_ch is not None and target_ch is not None

        rpm_vals = []
        map_vals = []
        afr_errors = []

        for record in self.log_data.records:
            rpm_val = record.get(rpm_ch, 0)
            map_val = record.get(map_ch, 0)

            # Map RPM/MAP to heatmap cell coordinates (fractional)
            col_f = self._find_bin_frac(rpm_val, rpm_bins)
            row_f = self._find_bin_frac(map_val, load_bins)
            rpm_vals.append(col_f)
            map_vals.append(row_f)

            if has_afr:
                actual = record.get(actual_ch, 0)
                target = record.get(target_ch, 0)
                if actual > 0 and target > 0:
                    afr_errors.append(target - actual)
                else:
                    afr_errors.append(0)

        if not rpm_vals:
            return

        if has_afr and afr_errors:
            vmax = max(abs(min(afr_errors)), abs(max(afr_errors))) or 1
            sc = ax.scatter(rpm_vals, map_vals, c=afr_errors, cmap='RdBu_r',
                           vmin=-vmax, vmax=vmax, s=6, alpha=0.3, zorder=5,
                           edgecolors='none')
        else:
            ax.scatter(rpm_vals, map_vals, c='white', s=6, alpha=0.3,
                      zorder=5, edgecolors='none')

    def _find_bin_frac(self, value: float, bins: List[float]) -> float:
        """Find the fractional bin position for a value (for scatter overlay).

        Returns a float in [0, len(bins)] mapping the value into cell space.
        """
        if not bins or len(bins) < 2:
            return 0.5
        if value <= bins[0]:
            return 0.5
        if value >= bins[-1]:
            return len(bins) - 0.5
        for i in range(len(bins) - 1):
            if value < bins[i + 1]:
                frac = (value - bins[i]) / (bins[i + 1] - bins[i])
                return i + 0.5 + frac * 1.0
        return len(bins) - 0.5

    def _plot_ve_surface(self, data: np.ndarray, rpm_bins: List[float],
                         load_bins: List[float], rpm_label: str,
                         load_label: str, title: str) -> None:
        """Render 3D surface plot of VE table."""
        t = self._get_theme()
        self.afr_fig.clear()
        ax = self.afr_fig.add_subplot(111, projection='3d')
        ax.set_facecolor(t['plot_bg'])

        rows, cols = data.shape
        X, Y = np.meshgrid(np.array(rpm_bins[:cols]), np.array(load_bins[:rows]))

        surf = ax.plot_surface(
            X, Y, data,
            cmap='jet', edgecolors='k', linewidth=0.3, alpha=0.9
        )

        ax.set_xlabel(rpm_label, fontsize=9, color=t['plot_text'], labelpad=10)
        ax.set_ylabel(load_label, fontsize=9, color=t['plot_text'], labelpad=10)
        ax.set_zlabel('Value', fontsize=9, color=t['plot_text'], labelpad=10)
        ax.set_title(title, fontsize=12, color=t['plot_text'], pad=15)
        ax.tick_params(colors=t['plot_tick'], labelsize=7)

        # Colorbar
        cbar = self.afr_fig.colorbar(surf, ax=ax, shrink=0.6, pad=0.1)
        cbar.ax.tick_params(colors=t['plot_tick'], labelsize=8)

        self.afr_fig.set_facecolor(t['plot_face'])
        self.afr_ax = ax
        self.afr_canvas.draw()

    # --- Compare Mode ---

    def _on_afr_view_changed(self, event=None) -> None:
        """Show/hide compare and filter controls based on view type selection."""
        view = self.afr_plot_type_var.get()
        if view == "Compare":
            self._afr_compare_frame.pack(side=tk.LEFT)
        else:
            self._afr_compare_frame.pack_forget()
        if view in ("AFR Analysis", "Hit Count", "Log Comparison"):
            self._afr_filter_frame.pack(side=tk.LEFT)
            if not self.log_data:
                self.afr_info_label.config(text="Load a log file for this view")
        else:
            self._afr_filter_frame.pack_forget()

    def _plot_ve_comparison(self, data_a: np.ndarray, rpm_bins: List[float],
                            load_bins: List[float], rpm_label: str,
                            load_label: str, title_a: str,
                            table_name_a: str) -> None:
        """Render side-by-side comparison of two VE tables with difference plot."""
        compare_name = self.afr_compare_var.get()
        if not compare_name or not self.msq_data:
            self.afr_info_label.config(text="Select a comparison table")
            return

        # Find and parse comparison table
        compare_entry = None
        for entry in self.msq_data['entries']:
            if entry['name'] == compare_name:
                compare_entry = entry
                break
        if not compare_entry:
            self.afr_info_label.config(text=f"Table '{compare_name}' not found")
            return

        parts_b = compare_entry['dimensions'].split('x')
        rows_b = int(parts_b[0])
        cols_b = int(parts_b[1])
        try:
            values_b = [float(v) for v in compare_entry['value'].split()]
        except ValueError:
            self.afr_info_label.config(text="Cannot parse comparison table values")
            return
        if len(values_b) != rows_b * cols_b:
            self.afr_info_label.config(text=f"Comparison table size mismatch")
            return
        data_b = np.array(values_b).reshape(rows_b, cols_b)

        # Get bins for comparison table
        rpm_bins_b, load_bins_b, rpm_label_b, load_label_b = self._find_bins_for_table(compare_name)
        if rpm_bins_b is None:
            rpm_bins_b = list(range(cols_b))
        if load_bins_b is None:
            load_bins_b = list(range(rows_b))
        rpm_bins_b = rpm_bins_b[:cols_b]
        load_bins_b = load_bins_b[:rows_b]

        t = self._get_theme()
        self.afr_fig.clear()

        # Compute difference if dimensions match
        can_diff = data_a.shape == data_b.shape

        if can_diff:
            axes = self.afr_fig.subplots(1, 3)
            diff = data_a - data_b
        else:
            axes = self.afr_fig.subplots(1, 2)

        # Plot Table A
        self._draw_comparison_subplot(axes[0], data_a, rpm_bins, load_bins,
                                      rpm_label, load_label, title_a, t, 'jet')

        # Plot Table B
        units_b = compare_entry.get('units', '')
        title_b = f"{compare_name}" + (f" ({units_b})" if units_b else "")
        self._draw_comparison_subplot(axes[1], data_b, rpm_bins_b, load_bins_b,
                                      rpm_label_b, load_label_b, title_b, t, 'jet')

        # Plot Difference
        if can_diff:
            vmax = max(abs(diff.min()), abs(diff.max())) or 1
            self._draw_comparison_subplot(axes[2], diff, rpm_bins, load_bins,
                                          rpm_label, load_label,
                                          f"Difference ({table_name_a} - {compare_name})",
                                          t, 'RdBu_r', vmin=-vmax, vmax=vmax)

        self.afr_fig.set_facecolor(t['plot_face'])
        self.afr_fig.tight_layout()
        self.afr_ax = axes[0]
        self.afr_canvas.draw()

    def _draw_comparison_subplot(self, ax, data: np.ndarray, rpm_bins: List[float],
                                 load_bins: List[float], rpm_label: str,
                                 load_label: str, title: str,
                                 t: Dict[str, str], cmap: str,
                                 vmin=None, vmax=None) -> None:
        """Draw a single heatmap subplot for comparison view."""
        rows, cols = data.shape
        ax.set_facecolor(t['plot_bg'])
        kwargs = {'cmap': cmap, 'shading': 'flat'}
        if vmin is not None:
            kwargs['vmin'] = vmin
            kwargs['vmax'] = vmax
        im = ax.pcolormesh(range(cols + 1), range(rows + 1), data, **kwargs)

        # Annotate cells
        font_size = max(4, min(6, 80 // max(rows, cols)))
        for r in range(rows):
            for c in range(cols):
                ax.text(c + 0.5, r + 0.5, f'{data[r, c]:.0f}',
                        ha='center', va='center', fontsize=font_size,
                        color='white', fontweight='bold')

        ax.set_xticks([i + 0.5 for i in range(cols)])
        ax.set_xticklabels([f'{v:.0f}' for v in rpm_bins], fontsize=5, color=t['plot_tick'],
                           rotation=45)
        ax.set_yticks([i + 0.5 for i in range(rows)])
        ax.set_yticklabels([f'{v:.0f}' for v in load_bins], fontsize=5, color=t['plot_tick'])
        ax.set_xlabel(rpm_label, fontsize=8, color=t['plot_text'])
        ax.set_ylabel(load_label, fontsize=8, color=t['plot_text'])
        ax.set_title(title, fontsize=9, color=t['plot_text'], pad=6)
        ax.tick_params(colors=t['plot_tick'])

        cbar = self.afr_fig.colorbar(im, ax=ax, pad=0.02)
        cbar.ax.tick_params(colors=t['plot_tick'], labelsize=6)

    # --- AFR Correction Analysis ---

    def _add_calculated_channels(self) -> None:
        """Inject calculated channels into the loaded log data."""
        actual_ch, target_ch = self._find_afr_channels()
        if actual_ch and target_ch:
            def afr_pct_off(record: Dict[str, Any]) -> Optional[float]:
                target = record.get(target_ch, 0.0)
                if target == 0.0:
                    return 0.0
                actual = record.get(actual_ch, 0.0)
                return ((actual - target) / target) * 100.0

            self.log_data.add_calculated_channel(
                'AFR Off Target', 'pct', afr_pct_off, digits=1)
            self.log_debug(
                f"Added calculated channel 'AFR Off Target' "
                f"from {actual_ch} / {target_ch}", 'info')

    def _find_afr_channels(self) -> Tuple[Optional[str], Optional[str]]:
        """Detect actual AFR and target AFR channel names from log data."""
        if not self.log_data or not self.log_data.records:
            return None, None

        available = set(self.log_data.records[0].keys())

        # Actual AFR channel candidates (in priority order)
        actual_candidates = ['AFR1', 'afr1', 'AFR', 'afr', 'EGO1', 'ego1',
                             'AFR1_aux', 'wbo2_en1']
        actual_ch = None
        for ch in actual_candidates:
            if ch in available:
                actual_ch = ch
                break

        # Target AFR channel candidates
        target_candidates = ['afrTarget1', 'AFRtgt1', 'afrTarget', 'AFRtgt',
                             'targetAFR', 'targetAFR1', 'afr_target1',
                             'afrTarget1_aux']
        target_ch = None
        for ch in target_candidates:
            if ch in available:
                target_ch = ch
                break

        return actual_ch, target_ch

    def _load_afr_target_table(self, rpm_bins: List[float],
                                load_bins: List[float]) -> Optional[np.ndarray]:
        """Load AFR target table from MSQ if override is selected.

        Returns a 2D array matching the VE table grid, or None to use log channel.
        """
        source = self.afr_target_source_var.get()
        if source == "Log Channel" or not source:
            return None
        if not self.msq_data:
            return None

        # Find the selected AFR target table entry
        for entry in self.msq_data['entries']:
            if entry['name'] == source and entry['dimensions']:
                parts = entry['dimensions'].split('x')
                rows_t, cols_t = int(parts[0]), int(parts[1])
                try:
                    values = [float(v) for v in entry['value'].split()]
                except ValueError:
                    return None
                if len(values) != rows_t * cols_t:
                    return None
                afr_table = np.array(values).reshape(rows_t, cols_t)

                # If dimensions match VE table, use directly
                if rows_t == len(load_bins) and cols_t == len(rpm_bins):
                    return afr_table

                # Otherwise interpolate to match VE grid
                afr_rpm, afr_load, _, _ = self._find_bins_for_table(source)
                if afr_rpm is None or afr_load is None:
                    return None
                afr_rpm = afr_rpm[:cols_t]
                afr_load = afr_load[:rows_t]

                try:
                    from scipy.interpolate import RegularGridInterpolator
                except ImportError:
                    return None  # scipy not available; can't interpolate
                interp = RegularGridInterpolator(
                    (afr_load, afr_rpm), afr_table,
                    method='linear', bounds_error=False, fill_value=None
                )
                load_grid, rpm_grid = np.meshgrid(load_bins, rpm_bins, indexing='ij')
                return interp((load_grid, rpm_grid))
        return None

    def _plot_afr_correction_map(self, ve_data: np.ndarray, rpm_bins: List[float],
                                  load_bins: List[float], rpm_label: str,
                                  load_label: str, title: str,
                                  table_name: str) -> None:
        """Compute and display per-cell AFR error and suggested VE corrections.

        For each log record, maps RPM/MAP to a VE table cell, accumulates
        actual vs target AFR, then computes:
          correction% = ((target / actual) - 1) * 100
          suggested_VE = current_VE * (target / actual)
        """
        if not self.log_data:
            self.afr_info_label.config(text="Load a log file for AFR Analysis")
            return

        # Check for AFR target table override from MSQ
        afr_target_table = self._load_afr_target_table(rpm_bins, load_bins)
        use_msq_target = afr_target_table is not None

        actual_ch, target_ch = self._find_afr_channels()
        if not actual_ch:
            self.afr_info_label.config(
                text="No AFR channel found (expected AFR1, afr1, EGO1, etc.)")
            return
        if not target_ch and not use_msq_target:
            self.afr_info_label.config(
                text=f"Found {actual_ch} but no target AFR channel "
                     f"(expected afrTarget1, AFRtgt1, etc.)")
            return

        # Detect RPM and MAP channels
        available = set(self.log_data.records[0].keys())
        rpm_ch = None
        for ch in ['RPM', 'rpm', 'Rpm']:
            if ch in available:
                rpm_ch = ch
                break
        map_ch = None
        for ch in ['MAP', 'fuelLoad', 'kPa', 'map', 'MAP_kPa']:
            if ch in available:
                map_ch = ch
                break
        if not rpm_ch or not map_ch:
            self.afr_info_label.config(text="RPM or MAP channel not found in log")
            return

        # Detect optional filter channels
        clt_ch = None
        for ch in ['CLT', 'coolant', 'clt', 'Coolant', 'CoolantTemp']:
            if ch in available:
                clt_ch = ch
                break
        tps_ch = None
        for ch in ['TPS', 'tps', 'Tps', 'throttle', 'TPSdot']:
            if ch in available:
                tps_ch = ch
                break

        # Read filter thresholds
        filtering = self.afr_filter_enabled_var.get()
        min_rpm = self._get_filter_float(self.afr_filter_rpm_var, 500) if filtering else 0
        min_clt = self._get_filter_float(self.afr_filter_clt_var, 150) if filtering else -999
        min_tps = self._get_filter_float(self.afr_filter_tps_var, 0) if filtering else -999
        rpm_delta_max = self._get_filter_float(self.afr_filter_rpm_delta_var, 200) if filtering else 99999

        rows, cols = ve_data.shape
        # Accumulate per-cell: sum of (target/actual) ratios and count
        ratio_sum = np.zeros((rows, cols))
        ratio_count = np.zeros((rows, cols), dtype=int)
        actual_sum = np.zeros((rows, cols))
        target_sum = np.zeros((rows, cols))
        filtered_out = 0
        records = self.log_data.records

        for i, record in enumerate(records):
            rpm_val = record.get(rpm_ch, 0)
            map_val = record.get(map_ch, 0)
            actual = record.get(actual_ch, 0)

            # Get target from MSQ table or log channel
            col = self._find_bin_index(rpm_val, rpm_bins)
            row = self._find_bin_index(map_val, load_bins)
            if use_msq_target:
                if 0 <= row < rows and 0 <= col < cols:
                    target = float(afr_target_table[row, col])
                else:
                    continue
            else:
                target = record.get(target_ch, 0)

            # Skip invalid readings
            if actual <= 0 or target <= 0:
                continue

            if filtering:
                # Apply filters
                if rpm_val < min_rpm:
                    filtered_out += 1
                    continue
                if clt_ch and record.get(clt_ch, 999) < min_clt:
                    filtered_out += 1
                    continue
                if tps_ch and record.get(tps_ch, 999) < min_tps:
                    filtered_out += 1
                    continue
                # Steady-state: check RPM stability over a small window
                if rpm_delta_max < 99999 and i >= 3:
                    rpm_window = [records[j].get(rpm_ch, 0) for j in range(max(0, i - 3), i + 1)]
                    if max(rpm_window) - min(rpm_window) > rpm_delta_max:
                        filtered_out += 1
                        continue

            if 0 <= row < rows and 0 <= col < cols:
                ratio_sum[row, col] += target / actual
                ratio_count[row, col] += 1
                actual_sum[row, col] += actual
                target_sum[row, col] += target

        # Cache per-cell AFR stats for tooltip display
        self._afr_cell_stats = {
            'count': ratio_count,
            'actual_sum': actual_sum,
            'target_sum': target_sum,
        }

        # Compute correction percentage: ((avg target/actual) - 1) * 100
        with np.errstate(divide='ignore', invalid='ignore'):
            avg_ratio = np.where(ratio_count > 0, ratio_sum / ratio_count, 1.0)
        correction_pct = (avg_ratio - 1.0) * 100.0

        # Suggested new VE values
        suggested_ve = ve_data * avg_ratio

        # Total sampled cells
        sampled_cells = int(np.sum(ratio_count > 0))
        total_samples = int(np.sum(ratio_count))

        t = self._get_theme()
        self.afr_fig.clear()

        # Layout: 3 subplots — Current VE, Correction %, Suggested VE
        axes = self.afr_fig.subplots(1, 3)

        # Subplot 1: Current VE table
        self._draw_comparison_subplot(axes[0], ve_data, rpm_bins, load_bins,
                                      rpm_label, load_label,
                                      f"Current {table_name}", t, 'jet')

        # Subplot 2: Correction % (diverging colormap)
        vmax = max(abs(correction_pct.min()), abs(correction_pct.max())) or 1
        ax_corr = axes[1]
        ax_corr.set_facecolor(t['plot_bg'])
        im = ax_corr.pcolormesh(
            range(cols + 1), range(rows + 1), correction_pct,
            cmap='RdBu_r', shading='flat', vmin=-vmax, vmax=vmax
        )

        # Annotate cells with correction values and sample counts
        font_size = max(4, min(6, 80 // max(rows, cols)))
        for r in range(rows):
            for c in range(cols):
                count = ratio_count[r, c]
                if count > 0:
                    pct = correction_pct[r, c]
                    sign = '+' if pct >= 0 else ''
                    ax_corr.text(
                        c + 0.5, r + 0.5,
                        f'{sign}{pct:.1f}%\n({count})',
                        ha='center', va='center', fontsize=font_size,
                        color='white', fontweight='bold')
                else:
                    ax_corr.text(
                        c + 0.5, r + 0.5, '—',
                        ha='center', va='center', fontsize=font_size,
                        color='gray')

        ax_corr.set_xticks([i + 0.5 for i in range(cols)])
        ax_corr.set_xticklabels([f'{v:.0f}' for v in rpm_bins], fontsize=5,
                                 color=t['plot_tick'], rotation=45)
        ax_corr.set_yticks([i + 0.5 for i in range(rows)])
        ax_corr.set_yticklabels([f'{v:.0f}' for v in load_bins], fontsize=5,
                                 color=t['plot_tick'])
        ax_corr.set_xlabel(rpm_label, fontsize=8, color=t['plot_text'])
        ax_corr.set_ylabel(load_label, fontsize=8, color=t['plot_text'])
        ax_corr.set_title(f'VE Correction % ({actual_ch} vs {target_ch})',
                          fontsize=9, color=t['plot_text'], pad=6)
        ax_corr.tick_params(colors=t['plot_tick'])
        cbar = self.afr_fig.colorbar(im, ax=ax_corr, pad=0.02)
        cbar.ax.tick_params(colors=t['plot_tick'], labelsize=6)

        # Subplot 3: Suggested VE values
        self._draw_comparison_subplot(axes[2], suggested_ve, rpm_bins, load_bins,
                                      rpm_label, load_label,
                                      f"Suggested {table_name}", t, 'jet')

        self.afr_fig.set_facecolor(t['plot_face'])
        self.afr_fig.tight_layout()
        self.afr_ax = axes[1]
        self.afr_canvas.draw()

        target_label = self.afr_target_source_var.get() if use_msq_target else target_ch
        self.afr_info_label.config(
            text=f"AFR Analysis: {actual_ch}\u2192{target_label} | "
                 f"{sampled_cells}/{rows * cols} cells sampled ({total_samples} records"
                 f", {filtered_out} filtered)" if filtered_out else
            f"AFR Analysis: {actual_ch}\u2192{target_label} | "
            f"{sampled_cells}/{rows * cols} cells sampled ({total_samples} records)")

    def _get_filter_float(self, var: tk.StringVar, default: float) -> float:
        """Parse a filter entry value as float, returning default on error."""
        try:
            return float(var.get())
        except (ValueError, tk.TclError):
            return default

    def _get_filter_channels(self) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """Detect RPM, MAP, CLT, and TPS channel names from log data.

        Returns (clt_ch, tps_ch, rpm_ch, map_ch) but we only need clt and tps
        since rpm and map are detected inline in callers.
        """
        if not self.log_data or not self.log_data.records:
            return None, None
        available = set(self.log_data.records[0].keys())
        clt_ch = None
        for ch in ['CLT', 'coolant', 'clt', 'Coolant', 'CoolantTemp']:
            if ch in available:
                clt_ch = ch
                break
        tps_ch = None
        for ch in ['TPS', 'tps', 'Tps', 'throttle']:
            if ch in available:
                tps_ch = ch
                break
        return clt_ch, tps_ch

    # --- Hit Count Heatmap ---

    def _plot_hit_count_map(self, rpm_bins: List[float], load_bins: List[float],
                             rpm_label: str, load_label: str,
                             title: str) -> None:
        """Show per-cell sample count from log data as a heatmap."""
        if not self.log_data:
            self.afr_info_label.config(text="Load a log file for Hit Count view")
            return

        available = set(self.log_data.records[0].keys())
        rpm_ch = None
        for ch in ['RPM', 'rpm', 'Rpm']:
            if ch in available:
                rpm_ch = ch
                break
        map_ch = None
        for ch in ['MAP', 'fuelLoad', 'kPa', 'map', 'MAP_kPa']:
            if ch in available:
                map_ch = ch
                break
        if not rpm_ch or not map_ch:
            self.afr_info_label.config(text="RPM or MAP channel not found in log")
            return

        clt_ch, tps_ch = self._get_filter_channels()
        filtering = self.afr_filter_enabled_var.get()
        min_rpm = self._get_filter_float(self.afr_filter_rpm_var, 500) if filtering else 0
        min_clt = self._get_filter_float(self.afr_filter_clt_var, 150) if filtering else -999
        min_tps = self._get_filter_float(self.afr_filter_tps_var, 0) if filtering else -999
        rpm_delta_max = self._get_filter_float(self.afr_filter_rpm_delta_var, 200) if filtering else 99999

        rows = len(load_bins)
        cols = len(rpm_bins)
        hit_count = np.zeros((rows, cols), dtype=int)
        filtered_out = 0

        # Process all loaded log sources (primary + extras)
        all_log_sources = [self.log_data] + getattr(self, '_extra_log_data', [])
        for ld in all_log_sources:
            if not ld or not ld.records:
                continue
            avail = set(ld.records[0].keys())
            r_ch = next((ch for ch in ['RPM', 'rpm', 'Rpm'] if ch in avail), None)
            m_ch = next((ch for ch in ['MAP', 'fuelLoad', 'kPa', 'map', 'MAP_kPa']
                         if ch in avail), None)
            if not r_ch or not m_ch:
                continue
            c_ch = next((ch for ch in ['CLT', 'coolant', 'clt'] if ch in avail), None)
            t_ch = next((ch for ch in ['TPS', 'tps', 'Tps'] if ch in avail), None)
            records = ld.records

            for i, record in enumerate(records):
                rpm_val = record.get(r_ch, 0)
                map_val = record.get(m_ch, 0)

                if filtering:
                    if rpm_val < min_rpm:
                        filtered_out += 1
                        continue
                    if c_ch and record.get(c_ch, 999) < min_clt:
                        filtered_out += 1
                        continue
                    if t_ch and record.get(t_ch, 999) < min_tps:
                        filtered_out += 1
                        continue
                    if rpm_delta_max < 99999 and i >= 3:
                        rpm_window = [records[j].get(r_ch, 0) for j in range(max(0, i - 3), i + 1)]
                        if max(rpm_window) - min(rpm_window) > rpm_delta_max:
                            filtered_out += 1
                            continue

                col = self._find_bin_index(rpm_val, rpm_bins)
                row = self._find_bin_index(map_val, load_bins)
                if 0 <= row < rows and 0 <= col < cols:
                    hit_count[row, col] += 1

        t = self._get_theme()
        self.afr_fig.clear()
        ax = self.afr_fig.add_subplot(111)
        ax.set_facecolor(t['plot_bg'])

        # Use log scale for better visualization of count distribution
        from matplotlib.colors import LogNorm
        max_count = hit_count.max() or 1
        # Replace zeros with NaN for log scale display
        display_data = hit_count.astype(float)
        display_data[display_data == 0] = np.nan

        im = ax.pcolormesh(
            range(cols + 1), range(rows + 1), display_data,
            cmap='YlOrRd', shading='flat',
            norm=LogNorm(vmin=1, vmax=max(max_count, 2))
        )

        # Annotate cells with counts
        font_size = max(5, min(8, 120 // max(rows, cols)))
        for r in range(rows):
            for c in range(cols):
                count = hit_count[r, c]
                if count > 0:
                    ax.text(c + 0.5, r + 0.5, str(count),
                            ha='center', va='center', fontsize=font_size,
                            color='white' if count > max_count * 0.3 else 'black',
                            fontweight='bold')
                else:
                    ax.text(c + 0.5, r + 0.5, '0',
                            ha='center', va='center', fontsize=font_size,
                            color='gray')

        ax.set_xticks([i + 0.5 for i in range(cols)])
        ax.set_xticklabels([f'{v:.0f}' for v in rpm_bins], fontsize=7, color=t['plot_tick'])
        ax.set_yticks([i + 0.5 for i in range(rows)])
        ax.set_yticklabels([f'{v:.0f}' for v in load_bins], fontsize=7, color=t['plot_tick'])
        ax.set_xlabel(rpm_label, fontsize=10, color=t['plot_text'])
        ax.set_ylabel(load_label, fontsize=10, color=t['plot_text'])

        sampled_cells = int(np.sum(hit_count > 0))
        total_samples = int(np.sum(hit_count))
        ax.set_title(f'Cell Hit Count — {title}', fontsize=12, color=t['plot_text'], pad=10)
        ax.tick_params(colors=t['plot_tick'])

        cbar = self.afr_fig.colorbar(im, ax=ax, pad=0.02)
        cbar.ax.tick_params(colors=t['plot_tick'], labelsize=8)
        cbar.set_label('Sample Count', color=t['plot_text'], fontsize=9)

        self.afr_fig.set_facecolor(t['plot_face'])
        self.afr_fig.tight_layout()
        self.afr_ax = ax
        self.afr_canvas.draw()

        filter_str = f", {filtered_out} filtered" if filtered_out else ""
        extra_str = (f", {len(self._extra_log_data)} extra log(s)"
                     if getattr(self, '_extra_log_data', []) else "")
        self.afr_info_label.config(
            text=f"Hit Count: {sampled_cells}/{rows * cols} cells hit "
                 f"({total_samples} samples{filter_str}{extra_str})")

    # --- Log Comparison ---

    def _plot_log_comparison(self, ve_data: np.ndarray, rpm_bins: List[float],
                              load_bins: List[float], rpm_label: str,
                              load_label: str, title: str,
                              table_name: str) -> None:
        """Show side-by-side AFR correction maps from primary and extra log files."""
        if not self.log_data:
            self.afr_info_label.config(text="Load a log file first")
            return
        if not self._extra_log_data:
            self.afr_info_label.config(
                text="Use 'Add Log...' to load additional log files for comparison")
            return

        rows, cols = ve_data.shape
        n_logs = 1 + len(self._extra_log_data)
        # Limit to 4 panels max for readability
        n_panels = min(n_logs, 4)

        t = self._get_theme()
        self.afr_fig.clear()
        axes = self.afr_fig.subplots(1, n_panels)
        if n_panels == 1:
            axes = [axes]

        # Gather all log sources with labels
        log_sources = [(self.log_data, os.path.basename(self.current_file or "Primary"))]
        for ld in self._extra_log_data[:3]:
            log_sources.append((ld, ld.filename))

        for idx, (ld, label) in enumerate(log_sources[:n_panels]):
            correction = self._compute_afr_correction_for_log(
                ld, ve_data, rpm_bins, load_bins)
            if correction is None:
                # No AFR channels — show empty
                axes[idx].set_facecolor(t['plot_bg'])
                axes[idx].set_title(f"{label}\n(no AFR data)", fontsize=8,
                                    color=t['plot_text'])
                continue
            corr_pct, counts = correction
            vmax = max(abs(corr_pct.min()), abs(corr_pct.max())) or 1
            ax = axes[idx]
            ax.set_facecolor(t['plot_bg'])
            im = ax.pcolormesh(
                range(cols + 1), range(rows + 1), corr_pct,
                cmap='RdBu_r', shading='flat', vmin=-vmax, vmax=vmax
            )
            font_size = max(4, min(6, 80 // max(rows, cols)))
            for r in range(rows):
                for c in range(cols):
                    count = counts[r, c]
                    if count > 0:
                        pct = corr_pct[r, c]
                        sign = '+' if pct >= 0 else ''
                        ax.text(c + 0.5, r + 0.5,
                                f'{sign}{pct:.1f}%\n({count})',
                                ha='center', va='center', fontsize=font_size,
                                color='white', fontweight='bold')
                    else:
                        ax.text(c + 0.5, r + 0.5, '\u2014',
                                ha='center', va='center', fontsize=font_size,
                                color='gray')
            ax.set_xticks([i + 0.5 for i in range(cols)])
            ax.set_xticklabels([f'{v:.0f}' for v in rpm_bins], fontsize=5,
                               color=t['plot_tick'], rotation=45)
            ax.set_yticks([i + 0.5 for i in range(rows)])
            ax.set_yticklabels([f'{v:.0f}' for v in load_bins], fontsize=5,
                               color=t['plot_tick'])
            ax.set_xlabel(rpm_label, fontsize=7, color=t['plot_text'])
            ax.set_ylabel(load_label, fontsize=7, color=t['plot_text'])
            ax.set_title(label, fontsize=8, color=t['plot_text'], pad=6)
            ax.tick_params(colors=t['plot_tick'])
            cbar = self.afr_fig.colorbar(im, ax=ax, pad=0.02)
            cbar.ax.tick_params(colors=t['plot_tick'], labelsize=5)

        self.afr_fig.set_facecolor(t['plot_face'])
        self.afr_fig.tight_layout()
        self.afr_ax = axes[0]
        self.afr_canvas.draw()
        self.afr_info_label.config(
            text=f"Log Comparison: {n_panels} log files | "
                 f"{table_name}")

    def _compute_afr_correction_for_log(
            self, ld: LogData, ve_data: np.ndarray,
            rpm_bins: List[float],
            load_bins: List[float]) -> Optional[Tuple[np.ndarray, np.ndarray]]:
        """Compute per-cell AFR correction % and sample counts for one log source."""
        if not ld or not ld.records:
            return None
        available = set(ld.records[0].keys())
        rpm_ch = next((ch for ch in ['RPM', 'rpm', 'Rpm'] if ch in available), None)
        map_ch = next((ch for ch in ['MAP', 'fuelLoad', 'kPa', 'map', 'MAP_kPa']
                       if ch in available), None)
        if not rpm_ch or not map_ch:
            return None

        # AFR channels
        actual_ch = next((ch for ch in ['AFR1', 'afr1', 'AFR', 'afr', 'EGO1', 'ego1']
                          if ch in available), None)

        # Check for MSQ target override
        afr_target_table = self._load_afr_target_table(rpm_bins, load_bins)
        use_msq_target = afr_target_table is not None

        target_ch = None
        if not use_msq_target:
            target_ch = next((ch for ch in ['afrTarget1', 'AFRtgt1', 'afrTarget', 'AFRtgt',
                                            'targetAFR', 'targetAFR1']
                              if ch in available), None)

        if not actual_ch or (not target_ch and not use_msq_target):
            return None

        # Read filter thresholds
        filtering = self.afr_filter_enabled_var.get()
        min_rpm = self._get_filter_float(self.afr_filter_rpm_var, 500) if filtering else 0
        clt_ch = next((ch for ch in ['CLT', 'coolant', 'clt'] if ch in available), None)
        tps_ch = next((ch for ch in ['TPS', 'tps', 'Tps'] if ch in available), None)
        min_clt = self._get_filter_float(self.afr_filter_clt_var, 150) if filtering else -999
        min_tps = self._get_filter_float(self.afr_filter_tps_var, 0) if filtering else -999
        rpm_delta_max = self._get_filter_float(self.afr_filter_rpm_delta_var, 200) if filtering else 99999

        rows, cols = ve_data.shape
        ratio_sum = np.zeros((rows, cols))
        ratio_count = np.zeros((rows, cols), dtype=int)
        records = ld.records

        for i, record in enumerate(records):
            rpm_val = record.get(rpm_ch, 0)
            map_val = record.get(map_ch, 0)
            actual = record.get(actual_ch, 0)

            col = self._find_bin_index(rpm_val, rpm_bins)
            row = self._find_bin_index(map_val, load_bins)
            if use_msq_target:
                if 0 <= row < rows and 0 <= col < cols:
                    target = float(afr_target_table[row, col])
                else:
                    continue
            else:
                target = record.get(target_ch, 0)

            if actual <= 0 or target <= 0:
                continue
            if filtering:
                if rpm_val < min_rpm:
                    continue
                if clt_ch and record.get(clt_ch, 999) < min_clt:
                    continue
                if tps_ch and record.get(tps_ch, 999) < min_tps:
                    continue
                if rpm_delta_max < 99999 and i >= 3:
                    rpm_window = [records[j].get(rpm_ch, 0)
                                  for j in range(max(0, i - 3), i + 1)]
                    if max(rpm_window) - min(rpm_window) > rpm_delta_max:
                        continue

            if 0 <= row < rows and 0 <= col < cols:
                ratio_sum[row, col] += target / actual
                ratio_count[row, col] += 1

        with np.errstate(divide='ignore', invalid='ignore'):
            avg_ratio = np.where(ratio_count > 0, ratio_sum / ratio_count, 1.0)
        correction_pct = (avg_ratio - 1.0) * 100.0
        return correction_pct, ratio_count

    # --- Keyboard Navigation for Edit Mode ---

    def _on_afr_key(self, event) -> None:
        """Handle keyboard input for edit mode navigation and adjustment."""
        if not self.afr_edit_var.get() or self._afr_edit_data is None:
            return
        if self.afr_plot_type_var.get() != "2D Heatmap":
            return

        rows, cols = self._afr_edit_data.shape
        shift = bool(event.state & 0x1)

        if event.keysym in ('Up', 'Down', 'Left', 'Right'):
            if self._afr_selected_cell is None:
                self._afr_selected_cell = (0, 0)
                self._afr_selection_end = None

            # Determine which anchor to move
            if shift:
                # Extend selection range
                if self._afr_selection_end is None:
                    self._afr_selection_end = self._afr_selected_cell
                row, col = self._afr_selection_end
            else:
                # Single-cell navigation resets range
                self._afr_selection_end = None
                row, col = self._afr_selected_cell

            if event.keysym == 'Up' and row > 0:
                row -= 1
            elif event.keysym == 'Down' and row < rows - 1:
                row += 1
            elif event.keysym == 'Left' and col > 0:
                col -= 1
            elif event.keysym == 'Right' and col < cols - 1:
                col += 1

            if shift:
                self._afr_selection_end = (row, col)
            else:
                self._afr_selected_cell = (row, col)

            # Update info and redraw
            sel_count = self._get_selection_count()
            if sel_count > 1:
                self.afr_edit_info.config(
                    text=f"{sel_count} cells selected — use +/- to adjust all")
            else:
                r, c = self._afr_selected_cell
                val = self._afr_edit_data[r, c]
                orig_val = self._afr_edit_original[r, c]
                d = val - orig_val
                delta_str = f" (Δ{d:+.0f})" if d != 0 else ""
                self.afr_edit_info.config(
                    text=f"Selected [{r},{c}] = {val:.1f}{delta_str}")
            self._plot_afr_table()
            self._draw_edit_selection()

        elif event.keysym in ('plus', 'KP_Add'):
            self._adjust_selected_cell(1)
        elif event.keysym in ('minus', 'KP_Subtract'):
            self._adjust_selected_cell(-1)
        elif event.keysym == 'z' and (event.state & 0x4):  # Ctrl+Z
            self._undo_afr_edit()
        elif event.keysym == 'y' and (event.state & 0x4):  # Ctrl+Y
            self._redo_afr_edit()
        elif event.keysym == 'c' and (event.state & 0x4):  # Ctrl+C
            self._copy_ve_selection()
        elif event.keysym == 'v' and (event.state & 0x4):  # Ctrl+V
            self._paste_ve_selection()

    # --- Live VE Cell Highlight ---

    def _update_record_slider_range(self) -> None:
        """Update the record slider range based on loaded log data."""
        if self.log_data and self.log_data.record_count > 0:
            self.afr_record_slider.configure(to=self.log_data.record_count - 1)
            self.afr_record_label.config(text=f"0/{self.log_data.record_count - 1}")
        else:
            self.afr_record_slider.configure(to=1)
            self.afr_record_label.config(text="0/0")

    def _on_log_highlight_toggle(self) -> None:
        """Handle toggling of log position highlight."""
        if self.afr_log_highlight_var.get():
            if not self.log_data:
                self.afr_info_label.config(text="Load a log file first for position highlight")
                self.afr_log_highlight_var.set(False)
                return
            self._update_record_slider_range()
            self._update_ve_highlight()
        else:
            # Replot without highlight
            self._plot_afr_table()

    def _on_record_slider_changed(self, value) -> None:
        """Handle record slider movement."""
        idx = int(float(value))
        if self.log_data:
            self.afr_record_label.config(text=f"{idx}/{self.log_data.record_count - 1}")
        if self.afr_log_highlight_var.get():
            self._update_ve_highlight()

    def _update_ve_highlight(self) -> None:
        """Overlay the current operating point on the heatmap."""
        if not self.log_data or not self.msq_data:
            return
        if self.afr_plot_type_var.get() != "2D Heatmap":
            return

        record_idx = int(float(self.afr_record_slider.get()))
        if record_idx >= self.log_data.record_count:
            return

        # Find RPM channel
        rpm_val = None
        for ch in ['RPM', 'rpm', 'Rpm']:
            if self.log_data.records[0] and ch in self.log_data.records[0]:
                rpm_val = self.log_data.records[record_idx].get(ch, 0)
                break
        if rpm_val is None:
            return

        # Find MAP/load channel
        map_val = None
        for ch in ['MAP', 'fuelLoad', 'kPa', 'map', 'MAP_kPa']:
            if self.log_data.records[0] and ch in self.log_data.records[0]:
                map_val = self.log_data.records[record_idx].get(ch, 0)
                break
        if map_val is None:
            return

        # Map RPM and MAP to cell coordinates using bin arrays
        rpm_bins = getattr(self, '_afr_rpm_bins', None)
        load_bins = getattr(self, '_afr_load_bins', None)
        if rpm_bins is None or load_bins is None:
            return

        col = self._find_bin_index(rpm_val, rpm_bins)
        row = self._find_bin_index(map_val, load_bins)

        # Draw highlight rectangle on the existing axes
        ax = self.afr_ax
        if ax is None:
            return

        # Remove previous highlight patches
        for patch in list(ax.patches):
            patch.remove()

        # Draw highlight rectangle
        from matplotlib.patches import Rectangle
        rect = Rectangle((col, row), 1, 1, linewidth=3, edgecolor='lime',
                          facecolor='none', zorder=10)
        ax.add_patch(rect)

        # Update info label with current values
        self.afr_info_label.config(
            text=f"Record {record_idx}: RPM={rpm_val:.0f}, Load={map_val:.1f} → "
                 f"Cell [{row},{col}]"
        )
        self.afr_canvas.draw_idle()

    def _find_bin_index(self, value: float, bins: List[float]) -> int:
        """Find the bin index for a given value (nearest lower bin)."""
        if not bins:
            return 0
        for i in range(len(bins) - 1):
            if value < bins[i + 1]:
                return i
        return len(bins) - 1

    # --- Table Value Editing ---

    def _on_edit_mode_toggle(self) -> None:
        """Handle edit mode toggle."""
        if self.afr_edit_var.get():
            if not self.msq_data:
                self.afr_info_label.config(text="Load a tune file first")
                self.afr_edit_var.set(False)
                return
            table_name = self.afr_table_var.get()
            if not table_name:
                self.afr_edit_var.set(False)
                return
            if self._afr_edit_table_name != table_name or self._afr_edit_data is None:
                # Initialize edit data from current table
                self._plot_afr_table()
            self.afr_edit_info.config(text="Click a cell to select, then use +/- buttons or arrow keys")
            self.afr_canvas.get_tk_widget().focus_set()
        else:
            self._afr_selected_cell = None
            self.afr_edit_info.config(text="")
            self._plot_afr_table()

    def _on_afr_click(self, event) -> None:
        """Handle click on AFR heatmap for cell selection in edit mode."""
        if not self.afr_edit_var.get():
            return
        if event.inaxes is None or self._afr_edit_data is None:
            return
        if self.afr_plot_type_var.get() != "2D Heatmap":
            return

        # Convert click coordinates to cell indices
        col = int(event.xdata)
        row = int(event.ydata)
        rows, cols = self._afr_edit_data.shape
        if 0 <= row < rows and 0 <= col < cols:
            self._afr_selected_cell = (row, col)
            val = self._afr_edit_data[row, col]
            orig_val = self._afr_edit_original[row, col]
            delta = val - orig_val
            delta_str = f" (Δ{delta:+.0f})" if delta != 0 else ""
            self.afr_edit_info.config(
                text=f"Selected [{row},{col}] = {val:.1f}{delta_str}"
            )
            # Replot to show selection highlight
            self._plot_afr_table()
            # Draw selection rectangle
            self._draw_edit_selection()
            self.afr_canvas.get_tk_widget().focus_set()

    def _on_afr_hover(self, event) -> None:
        """Show tooltip with cell details when hovering over the heatmap."""
        if event.inaxes is None or self.afr_ax is None:
            if self._afr_tooltip is not None:
                self._afr_tooltip.set_visible(False)
                self._afr_hover_cell = None
                self.afr_canvas.draw_idle()
            return

        # Only show tooltip on 2D Heatmap view
        if self.afr_plot_type_var.get() != "2D Heatmap":
            return

        col = int(event.xdata) if event.xdata is not None else -1
        row = int(event.ydata) if event.ydata is not None else -1

        # Get data dimensions
        data = self._afr_edit_data if (self._afr_edit_data is not None and self.afr_edit_var.get()) else None
        if data is None:
            # Fall back to current table data
            table_name = self.afr_table_var.get()
            if not table_name or not self.msq_data:
                return
            for entry in self.msq_data['entries']:
                if entry['name'] == table_name:
                    parts = entry['dimensions'].split('x')
                    rows_n, cols_n = int(parts[0]), int(parts[1])
                    try:
                        values = [float(v) for v in entry['value'].split()]
                        data = np.array(values).reshape(rows_n, cols_n)
                    except (ValueError, IndexError):
                        return
                    break
        if data is None:
            return

        rows, cols = data.shape
        if not (0 <= row < rows and 0 <= col < cols):
            if self._afr_tooltip is not None:
                self._afr_tooltip.set_visible(False)
                self._afr_hover_cell = None
                self.afr_canvas.draw_idle()
            return

        # Skip if same cell as last hover
        if self._afr_hover_cell == (row, col):
            return
        self._afr_hover_cell = (row, col)

        # Build tooltip text
        val = data[row, col]
        rpm_bins = getattr(self, '_afr_rpm_bins', None)
        load_bins = getattr(self, '_afr_load_bins', None)
        rpm_str = f"{rpm_bins[col]:.0f}" if rpm_bins and col < len(rpm_bins) else str(col)
        load_str = f"{load_bins[row]:.0f}" if load_bins and row < len(load_bins) else str(row)

        lines = [f"VE: {val:.1f}", f"RPM: {rpm_str}  kPa: {load_str}"]

        # Add edit delta if in edit mode
        if self._afr_edit_original is not None and self.afr_edit_var.get():
            orig = self._afr_edit_original[row, col]
            delta = val - orig
            if delta != 0:
                lines.append(f"\u0394: {delta:+.1f}")

        # Add AFR stats if cached
        if self._afr_cell_stats is not None:
            stats = self._afr_cell_stats
            count = stats['count'][row, col]
            if count > 0:
                avg_actual = stats['actual_sum'][row, col] / count
                avg_target = stats['target_sum'][row, col] / count
                corr_pct = (avg_target / avg_actual - 1) * 100
                lines.append(f"AFR: {avg_actual:.1f} \u2192 {avg_target:.1f}")
                lines.append(f"Corr: {corr_pct:+.1f}%  ({count} samples)")

        tooltip_text = '\n'.join(lines)

        # Remove old tooltip and create new one
        if self._afr_tooltip is not None:
            self._afr_tooltip.remove()

        self._afr_tooltip = self.afr_ax.annotate(
            tooltip_text,
            xy=(col + 0.5, row + 0.5),
            xytext=(15, 15), textcoords='offset points',
            fontsize=8,
            color='white',
            bbox=dict(boxstyle='round,pad=0.4', fc='#333333', ec='#666666', alpha=0.92),
            zorder=20
        )
        self.afr_canvas.draw_idle()

    def _draw_edit_selection(self) -> None:
        """Draw a selection rectangle on the currently selected cell(s)."""
        if self._afr_selected_cell is None or self.afr_ax is None:
            return
        if self.afr_plot_type_var.get() != "2D Heatmap":
            return
        from matplotlib.patches import Rectangle
        r1, c1 = self._afr_selected_cell
        if self._afr_selection_end:
            r2, c2 = self._afr_selection_end
            top = min(r1, r2)
            left = min(c1, c2)
            height = abs(r2 - r1) + 1
            width = abs(c2 - c1) + 1
        else:
            top, left, height, width = r1, c1, 1, 1
        rect = Rectangle((left, top), width, height, linewidth=3, edgecolor='cyan',
                          facecolor='none', zorder=10, linestyle='--')
        self.afr_ax.add_patch(rect)
        self.afr_canvas.draw_idle()

    def _get_selection_range(self) -> Tuple[int, int, int, int]:
        """Return (r_start, r_end, c_start, c_end) inclusive for current selection."""
        if self._afr_selected_cell is None:
            return (0, 0, 0, 0)
        r1, c1 = self._afr_selected_cell
        if self._afr_selection_end:
            r2, c2 = self._afr_selection_end
            return (min(r1, r2), max(r1, r2), min(c1, c2), max(c1, c2))
        return (r1, r1, c1, c1)

    def _get_selection_count(self) -> int:
        """Return the number of cells currently selected."""
        r1, r2, c1, c2 = self._get_selection_range()
        return (r2 - r1 + 1) * (c2 - c1 + 1)

    def _push_undo_state(self) -> None:
        """Save current edit data snapshot to undo stack."""
        if self._afr_edit_data is not None:
            self._afr_undo_stack.append(self._afr_edit_data.copy())
            self._afr_redo_stack.clear()
            # Limit stack depth
            if len(self._afr_undo_stack) > 50:
                self._afr_undo_stack.pop(0)

    def _undo_afr_edit(self) -> None:
        """Undo the last edit operation."""
        if not self._afr_undo_stack:
            self.afr_edit_info.config(text="Nothing to undo")
            return
        self._afr_redo_stack.append(self._afr_edit_data.copy())
        self._afr_edit_data = self._afr_undo_stack.pop()
        remaining = len(self._afr_undo_stack)
        self.afr_edit_info.config(text=f"Undo ({remaining} more available)")
        self._plot_afr_table()
        if self._afr_selected_cell:
            self._draw_edit_selection()

    def _redo_afr_edit(self) -> None:
        """Redo a previously undone edit operation."""
        if not self._afr_redo_stack:
            self.afr_edit_info.config(text="Nothing to redo")
            return
        self._afr_undo_stack.append(self._afr_edit_data.copy())
        self._afr_edit_data = self._afr_redo_stack.pop()
        remaining = len(self._afr_redo_stack)
        self.afr_edit_info.config(text=f"Redo ({remaining} more available)")
        self._plot_afr_table()
        if self._afr_selected_cell:
            self._draw_edit_selection()

    def _copy_ve_selection(self) -> None:
        """Copy selected VE cells to clipboard as tab-separated values."""
        if self._afr_edit_data is None or self._afr_selected_cell is None:
            return
        r_start, r_end, c_start, c_end = self._get_selection_range()
        rows_data = []
        for r in range(r_start, r_end + 1):
            row_vals = []
            for c in range(c_start, c_end + 1):
                row_vals.append(f"{self._afr_edit_data[r, c]:.1f}")
            rows_data.append('\t'.join(row_vals))
        text = '\n'.join(rows_data)
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        count = (r_end - r_start + 1) * (c_end - c_start + 1)
        self.afr_edit_info.config(text=f"Copied {count} cell(s) to clipboard")

    def _paste_ve_selection(self) -> None:
        """Paste tab-separated values from clipboard into VE table at selected cell."""
        if not self.afr_edit_var.get() or self._afr_edit_data is None:
            return
        if self._afr_selected_cell is None:
            self.afr_edit_info.config(text="Select a cell first")
            return
        try:
            text = self.root.clipboard_get()
        except tk.TclError:
            self.afr_edit_info.config(text="Clipboard is empty")
            return
        lines = text.strip().split('\n')
        paste_rows = []
        for line in lines:
            vals = []
            for v in line.split('\t'):
                try:
                    vals.append(float(v.strip()))
                except ValueError:
                    pass
            if vals:
                paste_rows.append(vals)
        if not paste_rows:
            self.afr_edit_info.config(text="No numeric data in clipboard")
            return
        self._push_undo_state()
        r0, c0 = self._afr_selected_cell
        rows, cols = self._afr_edit_data.shape
        pasted = 0
        for ri, row_vals in enumerate(paste_rows):
            for ci, val in enumerate(row_vals):
                r, c = r0 + ri, c0 + ci
                if 0 <= r < rows and 0 <= c < cols:
                    self._afr_edit_data[r, c] = val
                    pasted += 1
        self.afr_edit_info.config(text=f"Pasted {pasted} cell(s)")
        self._plot_afr_table()
        if self._afr_selected_cell:
            self._draw_edit_selection()

    def _adjust_selected_cell(self, delta: float) -> None:
        """Adjust the value of all selected cells by delta."""
        if not self.afr_edit_var.get() or self._afr_selected_cell is None:
            return
        if self._afr_edit_data is None:
            return
        self._push_undo_state()
        r_start, r_end, c_start, c_end = self._get_selection_range()
        rows, cols = self._afr_edit_data.shape
        changed = 0
        for r in range(max(0, r_start), min(rows, r_end + 1)):
            for c in range(max(0, c_start), min(cols, c_end + 1)):
                self._afr_edit_data[r, c] += delta
                changed += 1
        if changed == 1:
            r, c = self._afr_selected_cell
            val = self._afr_edit_data[r, c]
            orig_val = self._afr_edit_original[r, c]
            d = val - orig_val
            delta_str = f" (Δ{d:+.0f})" if d != 0 else ""
            self.afr_edit_info.config(
                text=f"Selected [{r},{c}] = {val:.1f}{delta_str}")
        else:
            self.afr_edit_info.config(
                text=f"Adjusted {changed} cells by {delta:+.0f}")
        self._plot_afr_table()
        self._draw_edit_selection()

    def _undo_afr_edits_all(self) -> None:
        """Reset edited data back to original values (full undo)."""
        if self._afr_edit_original is not None:
            self._push_undo_state()
            self._afr_edit_data = self._afr_edit_original.copy()
            self._afr_selected_cell = None
            self._afr_selection_end = None
            self.afr_edit_info.config(text="All changes undone")
            self._plot_afr_table()

    def _export_edited_msq(self) -> None:
        """Export edited VE table values to a new MSQ file."""
        if self._afr_edit_data is None or not self.msq_file:
            self.afr_edit_info.config(text="No edits to export")
            return

        # Check if there are any changes
        if self._afr_edit_original is not None and np.array_equal(self._afr_edit_data, self._afr_edit_original):
            self.afr_edit_info.config(text="No changes to export")
            return

        # Show change summary dialog; abort if user cancels
        if not self._show_change_summary():
            return

        save_path = filedialog.asksaveasfilename(
            title="Export Modified Tune File",
            filetypes=[("MegaSquirt Tune Files", "*.msq"), ("All Files", "*.*")],
            defaultextension=".msq",
            initialfile=os.path.splitext(os.path.basename(self.msq_file))[0] + "_modified.msq"
        )
        if not save_path:
            return

        try:
            # Parse the original MSQ as XML
            tree = ET.parse(self.msq_file)
            root = tree.getroot()

            table_name = self._afr_edit_table_name
            # Find the matching constant element and update its text
            for page_elem in root.findall('.//page'):
                for const_elem in page_elem.findall('constant'):
                    if const_elem.get('name') == table_name:
                        # Format values as space-separated string
                        flat_values = self._afr_edit_data.flatten()
                        const_elem.text = ' '.join(f'{v:.1f}' for v in flat_values)
                        break

            tree.write(save_path, xml_declaration=True, encoding='utf-8')
            changed_count = int(np.sum(self._afr_edit_data != self._afr_edit_original))
            diff = self._afr_edit_data - self._afr_edit_original
            avg_change = float(np.mean(np.abs(diff[diff != 0]))) if changed_count > 0 else 0
            from datetime import datetime
            self._afr_export_history.append({
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'file': os.path.basename(save_path),
                'table': self._afr_edit_table_name or '',
                'changed': changed_count,
                'avg_change': avg_change,
            })
            self.afr_edit_info.config(
                text=f"Exported {changed_count} changes to {os.path.basename(save_path)}"
            )
            self.log_debug(f"Exported modified tune: {save_path}", 'success')
        except Exception as e:
            messagebox.showerror("Export Error", f"Failed to export MSQ:\n{str(e)}")

    def _show_change_summary(self) -> bool:
        """Show a dialog summarizing VE table changes. Returns True to proceed, False to cancel."""
        diff = self._afr_edit_data - self._afr_edit_original
        changed_mask = diff != 0
        changed_count = int(np.sum(changed_mask))

        if changed_count == 0:
            return True

        rpm_bins = getattr(self, '_afr_rpm_bins', None)
        load_bins = getattr(self, '_afr_load_bins', None)

        dialog = tk.Toplevel(self.root)
        dialog.title("VE Change Summary")
        dialog.geometry("520x420")
        dialog.transient(self.root)
        dialog.grab_set()

        result = [False]

        # Header
        table_name = self._afr_edit_table_name or "VE Table"
        avg_abs_change = float(np.mean(np.abs(diff[changed_mask])))
        max_change = float(np.max(np.abs(diff[changed_mask])))
        header_text = (f"{table_name}: {changed_count} cell(s) changed\n"
                       f"Avg change: {avg_abs_change:.1f}   "
                       f"Max change: {max_change:.1f}")
        ttk.Label(dialog, text=header_text, font=('TkDefaultFont', 10, 'bold')).pack(
            padx=10, pady=(10, 5), anchor='w')

        # Scrollable change list
        list_frame = ttk.Frame(dialog)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        scrollbar = ttk.Scrollbar(list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        text_widget = tk.Text(list_frame, wrap=tk.NONE, font=('Consolas', 9),
                              yscrollcommand=scrollbar.set, state=tk.NORMAL)
        text_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=text_widget.yview)

        rows, cols = diff.shape
        for r in range(rows):
            for c in range(cols):
                if diff[r, c] != 0:
                    old_val = self._afr_edit_original[r, c]
                    new_val = self._afr_edit_data[r, c]
                    d = diff[r, c]
                    rpm_str = f"RPM {rpm_bins[c]:.0f}" if rpm_bins and c < len(rpm_bins) else f"col {c}"
                    load_str = f"kPa {load_bins[r]:.0f}" if load_bins and r < len(load_bins) else f"row {r}"
                    text_widget.insert(tk.END,
                        f"  [{r:2d},{c:2d}]  {load_str:>10s}  {rpm_str:>10s}    "
                        f"{old_val:6.1f} \u2192 {new_val:6.1f}   (\u0394{d:+.1f})\n")

        text_widget.config(state=tk.DISABLED)

        # Buttons
        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(fill=tk.X, padx=10, pady=10)

        def on_ok():
            result[0] = True
            dialog.destroy()

        def on_cancel():
            dialog.destroy()

        ttk.Button(btn_frame, text="Export", command=on_ok).pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn_frame, text="Cancel", command=on_cancel).pack(side=tk.RIGHT, padx=5)

        dialog.protocol("WM_DELETE_WINDOW", on_cancel)
        dialog.wait_window()
        return result[0]

    def _show_export_history(self) -> None:
        """Show a dialog listing all VE table exports from this session."""
        if not self._afr_export_history:
            self.afr_edit_info.config(text="No exports yet this session")
            return

        dialog = tk.Toplevel(self.root)
        dialog.title("Export History")
        dialog.geometry("500x300")
        dialog.transient(self.root)
        dialog.grab_set()

        ttk.Label(dialog, text=f"{len(self._afr_export_history)} export(s) this session",
                  font=('TkDefaultFont', 10, 'bold')).pack(padx=10, pady=(10, 5), anchor='w')

        list_frame = ttk.Frame(dialog)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        scrollbar = ttk.Scrollbar(list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        text_widget = tk.Text(list_frame, wrap=tk.NONE, font=('Consolas', 9),
                              yscrollcommand=scrollbar.set, state=tk.NORMAL)
        text_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=text_widget.yview)

        for i, record in enumerate(self._afr_export_history, 1):
            text_widget.insert(tk.END,
                f"#{i}  {record['timestamp']}  {record['file']}\n"
                f"    Table: {record['table']}  |  "
                f"{record['changed']} cells changed  |  "
                f"Avg \u0394: {record['avg_change']:.1f}\n\n")

        text_widget.config(state=tk.DISABLED)

        ttk.Button(dialog, text="Close", command=dialog.destroy).pack(
            side=tk.BOTTOM, pady=10)

        dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)

    def _smooth_ve_table(self) -> None:
        """Apply Gaussian smoothing to the edited VE table to reduce abrupt transitions."""
        if self._afr_edit_data is None:
            self.afr_edit_info.config(text="Enter edit mode first")
            return
        if not self.afr_edit_var.get():
            self.afr_edit_info.config(text="Enable edit mode to smooth")
            return

        try:
            from scipy.ndimage import uniform_filter
        except ImportError:
            self.afr_edit_info.config(text="scipy required for smoothing (pip install scipy)")
            return
        self._push_undo_state()
        data = self._afr_edit_data.copy()

        # Apply a 3x3 uniform (box) filter for gentle smoothing
        smoothed = uniform_filter(data, size=3, mode='nearest')

        # Blend: 50% original + 50% smoothed for subtle effect
        self._afr_edit_data = (data + smoothed) / 2.0

        self.afr_edit_info.config(text="Smoothing applied (3x3 blend)")
        self._plot_afr_table()
        if self._afr_selected_cell:
            self._draw_edit_selection()

    def _apply_suggested_ve(self) -> None:
        """Copy AFR Analysis suggested VE values into the edit data."""
        if not self.log_data or not self.msq_data:
            self.afr_edit_info.config(text="Load both log and tune files first")
            return

        table_name = self.afr_table_var.get()
        if not table_name:
            return

        # Find the table entry to get current VE data
        table_entry = None
        for entry in self.msq_data['entries']:
            if entry['name'] == table_name:
                table_entry = entry
                break
        if not table_entry:
            return

        parts = table_entry['dimensions'].split('x')
        rows = int(parts[0])
        cols = int(parts[1])
        try:
            values = [float(v) for v in table_entry['value'].split()]
        except ValueError:
            return
        if len(values) != rows * cols:
            return
        ve_data = np.array(values).reshape(rows, cols)

        # Get bins
        rpm_bins, load_bins, _, _ = self._find_bins_for_table(table_name)
        if rpm_bins is None:
            rpm_bins = list(range(cols))
        if load_bins is None:
            load_bins = list(range(rows))
        rpm_bins = rpm_bins[:cols]
        load_bins = load_bins[:rows]

        # Check for AFR target table override from MSQ
        afr_target_table = self._load_afr_target_table(rpm_bins, load_bins)
        use_msq_target = afr_target_table is not None

        # Detect AFR channels
        actual_ch, target_ch = self._find_afr_channels()
        if not actual_ch:
            self.afr_edit_info.config(text="AFR actual channel not found in log")
            return
        if not target_ch and not use_msq_target:
            self.afr_edit_info.config(text="AFR target not found (select MSQ table or load log with target)")
            return

        # Detect RPM/MAP channels
        available = set(self.log_data.records[0].keys())
        rpm_ch = None
        for ch in ['RPM', 'rpm', 'Rpm']:
            if ch in available:
                rpm_ch = ch
                break
        map_ch = None
        for ch in ['MAP', 'fuelLoad', 'kPa', 'map', 'MAP_kPa']:
            if ch in available:
                map_ch = ch
                break
        if not rpm_ch or not map_ch:
            self.afr_edit_info.config(text="RPM or MAP channel not found")
            return

        # Detect filter channels
        clt_ch = None
        for ch in ['CLT', 'coolant', 'clt', 'Coolant', 'CoolantTemp']:
            if ch in available:
                clt_ch = ch
                break
        tps_ch = None
        for ch in ['TPS', 'tps', 'Tps', 'throttle']:
            if ch in available:
                tps_ch = ch
                break

        filtering = self.afr_filter_enabled_var.get()
        min_rpm = self._get_filter_float(self.afr_filter_rpm_var, 500) if filtering else 0
        min_clt = self._get_filter_float(self.afr_filter_clt_var, 150) if filtering else -999
        min_tps = self._get_filter_float(self.afr_filter_tps_var, 0) if filtering else -999
        rpm_delta_max = self._get_filter_float(self.afr_filter_rpm_delta_var, 200) if filtering else 99999

        # Accumulate correction ratios
        ratio_sum = np.zeros((rows, cols))
        ratio_count = np.zeros((rows, cols), dtype=int)
        records = self.log_data.records

        for i, record in enumerate(records):
            rpm_val = record.get(rpm_ch, 0)
            map_val = record.get(map_ch, 0)
            actual = record.get(actual_ch, 0)

            col = self._find_bin_index(rpm_val, rpm_bins)
            row = self._find_bin_index(map_val, load_bins)
            if use_msq_target:
                if 0 <= row < rows and 0 <= col < cols:
                    target = float(afr_target_table[row, col])
                else:
                    continue
            else:
                target = record.get(target_ch, 0)

            if actual <= 0 or target <= 0:
                continue
            if filtering:
                if rpm_val < min_rpm:
                    continue
                if clt_ch and record.get(clt_ch, 999) < min_clt:
                    continue
                if tps_ch and record.get(tps_ch, 999) < min_tps:
                    continue
                if rpm_delta_max < 99999 and i >= 3:
                    rpm_window = [records[j].get(rpm_ch, 0) for j in range(max(0, i - 3), i + 1)]
                    if max(rpm_window) - min(rpm_window) > rpm_delta_max:
                        continue
            if 0 <= row < rows and 0 <= col < cols:
                ratio_sum[row, col] += target / actual
                ratio_count[row, col] += 1

        with np.errstate(divide='ignore', invalid='ignore'):
            avg_ratio = np.where(ratio_count > 0, ratio_sum / ratio_count, 1.0)
        suggested_ve = ve_data * avg_ratio

        # Apply to edit data
        if self._afr_edit_data is not None:
            self._push_undo_state()
        self._afr_edit_data = suggested_ve.copy()
        self._afr_edit_original = ve_data.copy()
        self._afr_edit_table_name = table_name
        self._afr_selected_cell = None
        self._afr_selection_end = None
        self.afr_edit_var.set(True)

        changed_cells = int(np.sum(ratio_count > 0))
        self.afr_edit_info.config(
            text=f"Applied suggested VE corrections to {changed_cells} cells")

        # Switch to 2D Heatmap to show editable view
        self.afr_plot_type_var.set("2D Heatmap")
        self._on_afr_view_changed()
        self._plot_afr_table()

    def _auto_tune_ve(self) -> None:
        """One-click auto-tune: compute AFR corrections and apply with configurable strength."""
        if not self.log_data or not self.msq_data:
            self.afr_edit_info.config(text="Load both log and tune files first")
            return

        table_name = self.afr_table_var.get()
        if not table_name:
            return

        # Find the table entry
        table_entry = None
        for entry in self.msq_data['entries']:
            if entry['name'] == table_name:
                table_entry = entry
                break
        if not table_entry:
            return

        parts = table_entry['dimensions'].split('x')
        rows = int(parts[0])
        cols = int(parts[1])
        try:
            values = [float(v) for v in table_entry['value'].split()]
        except ValueError:
            return
        if len(values) != rows * cols:
            return
        ve_data = np.array(values).reshape(rows, cols)

        rpm_bins, load_bins, _, _ = self._find_bins_for_table(table_name)
        if rpm_bins is None:
            rpm_bins = list(range(cols))
        if load_bins is None:
            load_bins = list(range(rows))
        rpm_bins = rpm_bins[:cols]
        load_bins = load_bins[:rows]

        afr_target_table = self._load_afr_target_table(rpm_bins, load_bins)
        use_msq_target = afr_target_table is not None

        actual_ch, target_ch = self._find_afr_channels()
        if not actual_ch:
            self.afr_edit_info.config(text="AFR channel not found")
            return
        if not target_ch and not use_msq_target:
            self.afr_edit_info.config(text="AFR target not found")
            return

        available = set(self.log_data.records[0].keys())
        rpm_ch = next((ch for ch in ['RPM', 'rpm', 'Rpm'] if ch in available), None)
        map_ch = next((ch for ch in ['MAP', 'fuelLoad', 'kPa', 'map', 'MAP_kPa']
                       if ch in available), None)
        if not rpm_ch or not map_ch:
            self.afr_edit_info.config(text="RPM or MAP channel not found")
            return

        clt_ch = next((ch for ch in ['CLT', 'coolant', 'clt', 'Coolant'] if ch in available), None)
        tps_ch = next((ch for ch in ['TPS', 'tps', 'Tps', 'throttle'] if ch in available), None)

        filtering = self.afr_filter_enabled_var.get()
        min_rpm = self._get_filter_float(self.afr_filter_rpm_var, 500) if filtering else 0
        min_clt = self._get_filter_float(self.afr_filter_clt_var, 150) if filtering else -999
        min_tps = self._get_filter_float(self.afr_filter_tps_var, 0) if filtering else -999
        rpm_delta_max = self._get_filter_float(self.afr_filter_rpm_delta_var, 200) if filtering else 99999
        min_samples = 3

        ratio_sum = np.zeros((rows, cols))
        ratio_count = np.zeros((rows, cols), dtype=int)
        records = self.log_data.records

        for i, record in enumerate(records):
            rpm_val = record.get(rpm_ch, 0)
            map_val = record.get(map_ch, 0)
            actual = record.get(actual_ch, 0)

            col = self._find_bin_index(rpm_val, rpm_bins)
            row = self._find_bin_index(map_val, load_bins)
            if use_msq_target:
                if 0 <= row < rows and 0 <= col < cols:
                    target = float(afr_target_table[row, col])
                else:
                    continue
            else:
                target = record.get(target_ch, 0)

            if actual <= 0 or target <= 0:
                continue
            if filtering:
                if rpm_val < min_rpm:
                    continue
                if clt_ch and record.get(clt_ch, 999) < min_clt:
                    continue
                if tps_ch and record.get(tps_ch, 999) < min_tps:
                    continue
                if rpm_delta_max < 99999 and i >= 3:
                    rpm_window = [records[j].get(rpm_ch, 0)
                                  for j in range(max(0, i - 3), i + 1)]
                    if max(rpm_window) - min(rpm_window) > rpm_delta_max:
                        continue
            if 0 <= row < rows and 0 <= col < cols:
                ratio_sum[row, col] += target / actual
                ratio_count[row, col] += 1

        with np.errstate(divide='ignore', invalid='ignore'):
            avg_ratio = np.where(ratio_count >= min_samples,
                                 ratio_sum / ratio_count, 1.0)
        suggested_ve = ve_data * avg_ratio

        if self._afr_edit_data is not None:
            self._push_undo_state()
        self._afr_edit_data = suggested_ve.copy()
        self._afr_edit_original = ve_data.copy()
        self._afr_edit_table_name = table_name
        self._afr_selected_cell = None
        self._afr_selection_end = None
        self.afr_edit_var.set(True)

        changed_cells = int(np.sum(ratio_count >= min_samples))
        skipped_cells = int(np.sum((ratio_count > 0) & (ratio_count < min_samples)))
        self.afr_edit_info.config(
            text=f"Auto-Tune: {changed_cells} cells updated, "
                 f"{skipped_cells} skipped (<{min_samples} samples)")

        self.afr_plot_type_var.set("2D Heatmap")
        self._on_afr_view_changed()
        self._plot_afr_table()

    # --- Multi-Log File Support ---

    def _add_extra_log_file(self) -> None:
        """Open dialog to add an additional log file for multi-log analysis."""
        initial_dir = self.current_directory or os.path.expanduser("~")
        file_paths = filedialog.askopenfilenames(
            title="Add Log File(s) for Comparison",
            filetypes=[("MegaLogViewer Files", "*.mlg"), ("All Files", "*.*")],
            initialdir=initial_dir
        )
        if not file_paths:
            return

        for file_path in file_paths:
            try:
                parser = MLGParser(file_path)
                parsed_data = parser.parse()
                ld = LogData(parsed_data)
                self._extra_log_data.append(ld)
            except (ValueError, IOError) as e:
                messagebox.showerror("Error",
                                     f"Failed to load {os.path.basename(file_path)}:\n{e}")

        n = len(self._extra_log_data)
        if n > 0:
            names = ", ".join(ld.filename for ld in self._extra_log_data[-len(file_paths):])
            self._extra_log_label.config(text=f"+{n} log(s)")
            self.afr_info_label.config(
                text=f"Added {names} | {n} extra log file(s) loaded")

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
        """Return current theme color palette with accent color applied."""
        base = dict(LogViewerApp.DARK_THEME if self.dark_mode else LogViewerApp.LIGHT_THEME)
        # Apply selected accent color
        accent_name = getattr(self, 'accent_color_name', 'Blue')
        accent_entry = self.ACCENT_COLORS.get(accent_name, self.ACCENT_COLORS['Blue'])
        mode_key = 'dark' if self.dark_mode else 'light'
        accent = accent_entry[mode_key]
        base['accent'] = accent
        base['highlight_bg'] = accent
        base['debug_header'] = accent
        base['tune_table_fg'] = accent
        base['listbox_select_bg'] = accent
        return base
    
    def _set_accent_color(self, name: str) -> None:
        """Set the accent color and reapply theme."""
        self.accent_color_name = name
        self._accent_var.set(name)
        self._apply_theme()
        self._save_settings()
        # Re-plot if plots are active
        if hasattr(self, 'fig') and self.fig.axes:
            self._apply_plot_theme()

    def _add_recent_file(self, file_path: str) -> None:
        """Add a file to the recent files list (max 10)."""
        if not hasattr(self, '_recent_files'):
            self._recent_files = []
        # Remove if already present, then prepend
        self._recent_files = [f for f in self._recent_files if f != file_path]
        self._recent_files.insert(0, file_path)
        self._recent_files = self._recent_files[:10]
        self._save_settings()

    def toggle_dark_mode(self) -> None:
        """Toggle between light and dark mode with animated crossfade."""
        source = self._get_theme()
        self.dark_mode = not self.dark_mode
        target = self._get_theme()
        self._save_settings()

        # Title bar can switch immediately
        self._apply_dark_title_bar()

        # Cancel any in-progress crossfade
        if getattr(self, '_theme_anim_id', None):
            self.after_cancel(self._theme_anim_id)

        self._theme_anim_source = source
        self._theme_anim_target = target
        self._theme_anim_step = 0
        self._animate_theme_step()

    # ── Tier-1 keys animated during crossfade ───────────────────────────
    _CROSSFADE_KEYS = (
        'bg', 'surface', 'surface_alt', 'border', 'fg',
        'statusbar_bg', 'statusbar_fg',
    )

    def _animate_theme_step(self) -> None:
        """Render one crossfade frame; call _apply_theme() on the last frame."""
        n = self._THEME_ANIM_FRAMES
        step = self._theme_anim_step
        t = step / n
        # Smooth-step ease-in-out
        t = t * t * (3 - 2 * t)

        src = self._theme_anim_source
        tgt = self._theme_anim_target
        mid = {k: self._lerp_color(src[k], tgt[k], t) for k in self._CROSSFADE_KEYS}

        style = ttk.Style(self)
        style.configure('TFrame', background=mid['bg'])
        style.configure('TLabel', background=mid['bg'], foreground=mid['fg'])
        style.configure('TNotebook', background=mid['bg'])
        style.configure('Treeview', background=mid['surface'],
                        fieldbackground=mid['surface'])
        self.configure(bg=mid['bg'])

        if hasattr(self, 'statusbar'):
            self.statusbar.configure(background=mid['statusbar_bg'],
                                     foreground=mid['statusbar_fg'])

        # Tab images
        scale = getattr(self, '_dpi_scale', 1.0)
        w, h = int(48 * scale), int(28 * scale)
        radius = int(6 * scale)

        def _pill(color):
            img = Image.new('RGBA', (w, h), (0, 0, 0, 0))
            ImageDraw.Draw(img).rounded_rectangle(
                [(0, 0), (w - 1, h - 1)], radius=radius, fill=color)
            return img

        self._tab_img_rest.paste(_pill(mid['surface_alt']))
        accent = self._lerp_color(src['accent'], tgt['accent'], t)
        self._tab_img_selected.paste(_pill(accent))
        self._tab_img_hover.paste(_pill(mid['surface']))

        self._theme_anim_step += 1
        if self._theme_anim_step <= n:
            self._theme_anim_id = self.after(
                self._THEME_ANIM_INTERVAL_MS, self._animate_theme_step)
        else:
            self._theme_anim_id = None
            # Final frame — apply full theme for all remaining properties
            self._apply_theme()
    
    def _apply_theme(self) -> None:
        """Apply current theme colors to all widgets."""
        t = self._get_theme()
        
        # Apply dark/light title bar on Windows
        self._apply_dark_title_bar()
        
        # Generate pill-shaped tab images for current theme
        self._create_tab_images(t)
        self._create_close_images(t)
        
        # Apple-style font family (detected or fallback)
        _font = getattr(self, '_font_family', 'Segoe UI')
        _mono = 'Cascadia Mono'
        print(f"[THEME] Applying theme (dark_mode={self.dark_mode}, font={_font}, accent={self.accent_color_name})")
        
        # Root window
        self.configure(bg=t['bg'])
        self.option_add('*Font', f'{{{_font}}} 11')
        
        # ttk style configuration - use 'clam' theme so custom colors are honored
        style = ttk.Style(self)
        style.theme_use('clam')
        
        # Remove scrollbar arrows from layout for modern appearance
        style.layout('Vertical.TScrollbar', [
            ('Vertical.Scrollbar.trough', {'sticky': 'ns', 'children': [
                ('Vertical.Scrollbar.thumb', {'expand': '1', 'sticky': 'nswe'})
            ]})
        ])
        style.layout('Horizontal.TScrollbar', [
            ('Horizontal.Scrollbar.trough', {'sticky': 'ew', 'children': [
                ('Horizontal.Scrollbar.thumb', {'expand': '1', 'sticky': 'nswe'})
            ]})
        ])
        
        # Frame backgrounds
        style.configure('TFrame', background=t['bg'])
        style.configure('TLabel', background=t['bg'], foreground=t['fg'],
                        font=(_font, 11))
        
        # Buttons - flat modern Apple-style
        style.configure('TButton',
                        background=t['surface_alt'],
                        foreground=t['fg'],
                        bordercolor=t['border'],
                        lightcolor=t['surface_alt'],
                        darkcolor=t['surface_alt'],
                        focuscolor=t['accent'],
                        font=(_font, 11),
                        padding=[12, 5])
        style.map('TButton',
                  background=[('active', t['accent']), ('pressed', t['accent'])],
                  foreground=[('active', t['highlight_fg']), ('pressed', t['highlight_fg'])],
                  bordercolor=[('active', t['accent'])],
                  lightcolor=[('active', t['accent']), ('pressed', t['accent'])],
                  darkcolor=[('active', t['accent']), ('pressed', t['accent'])])
        
        # Checkbuttons - Apple style
        style.configure('TCheckbutton',
                        background=t['bg'],
                        foreground=t['fg'],
                        font=(_font, 11),
                        indicatorbackground=t['input_bg'],
                        indicatorforeground=t['accent'])
        style.map('TCheckbutton',
                  background=[('active', t['bg'])],
                  foreground=[('active', t['fg'])],
                  indicatorbackground=[('selected', t['accent']),
                                      ('active', t['surface_alt'])])
        
        # Toolbutton style - flat Apple toggle appearance
        style.configure('Toolbutton',
                        background=t['bg'],
                        foreground=t['fg'],
                        bordercolor=t['bg'],
                        lightcolor=t['bg'],
                        darkcolor=t['bg'],
                        font=(_font, 11),
                        padding=[8, 4])
        style.map('Toolbutton',
                  background=[('selected', t['accent']), ('active', t['accent'])],
                  foreground=[('selected', t['highlight_fg']), ('active', t['highlight_fg'])],
                  bordercolor=[('selected', t['accent']), ('active', t['accent'])],
                  lightcolor=[('selected', t['accent']), ('active', t['accent'])],
                  darkcolor=[('selected', t['accent']), ('active', t['accent'])])
        
        # Notebook (tabs) - pill-shaped segmented control via images
        if not hasattr(self, '_tab_element_created'):
            style.element_create('Notebook.tab', 'image',
                                 self._tab_img_rest,
                                 ('selected', self._tab_img_selected),
                                 ('active', self._tab_img_hover),
                                 border=self._tab_border, padding=[16, 6])
            style.element_create('Notebook.close', 'image',
                                 self._close_img_normal,
                                 ('active', '!pressed', self._close_img_hover),
                                 ('active', 'pressed', self._close_img_pressed),
                                 sticky='', padding=[4, 0, 0, 0])
            style.layout('TNotebook.Tab', [
                ('Notebook.tab', {'sticky': 'nswe', 'children': [
                    ('Notebook.padding', {'side': 'top', 'sticky': 'nswe', 'children': [
                        ('Notebook.label', {'side': 'left', 'sticky': ''}),
                        ('Notebook.close', {'side': 'right', 'sticky': ''})
                    ]})
                ]})
            ])
            self._tab_element_created = True
        style.configure('TNotebook',
                        background=t['bg'],
                        bordercolor=t['bg'],
                        lightcolor=t['bg'],
                        darkcolor=t['bg'],
                        tabmargins=[4, 8, 4, 0])
        style.configure('TNotebook.Tab',
                        foreground=t['statusbar_fg'],
                        focuscolor='',
                        font=(_font, 11),
                        padding=[16, 6])
        style.map('TNotebook.Tab',
                  foreground=[('selected', t['highlight_fg']), ('active', t['fg'])])
        
        # Treeview - Apple list style with generous row height
        style.configure('Treeview',
                        background=t['surface'],
                        foreground=t['fg'],
                        fieldbackground=t['surface'],
                        bordercolor=t['border'],
                        lightcolor=t['surface'],
                        darkcolor=t['surface'],
                        font=(_font, 11),
                        rowheight=36)
        style.configure('Treeview.Heading',
                        background=t['surface_alt'],
                        foreground=t['fg'],
                        bordercolor=t['border'],
                        lightcolor=t['surface_alt'],
                        darkcolor=t['surface_alt'],
                        relief='flat',
                        font=(_font, 11, 'bold'))
        style.map('Treeview',
                  background=[('selected', t['highlight_bg'])],
                  foreground=[('selected', t['highlight_fg'])])
        style.map('Treeview.Heading',
                  background=[('active', t['surface'])],
                  lightcolor=[('active', t['surface'])],
                  darkcolor=[('active', t['surface'])])
        
        # Combobox - modern flat Apple style
        style.configure('TCombobox',
                        fieldbackground=t['input_bg'],
                        foreground=t['input_fg'],
                        background=t['surface_alt'],
                        selectbackground=t['highlight_bg'],
                        selectforeground=t['highlight_fg'],
                        bordercolor=t['border'],
                        lightcolor=t['input_bg'],
                        darkcolor=t['input_bg'],
                        arrowcolor=t['statusbar_fg'],
                        arrowsize=14,
                        font=(_font, 11),
                        padding=[6, 4])
        style.map('TCombobox',
                  fieldbackground=[('readonly', t['input_bg']), ('disabled', t['bg'])],
                  foreground=[('readonly', t['input_fg']), ('disabled', t['statusbar_fg'])],
                  background=[('active', t['surface']), ('readonly', t['surface_alt'])],
                  bordercolor=[('focus', t['accent']), ('active', t['accent'])],
                  lightcolor=[('focus', t['accent'])],
                  arrowcolor=[('active', t['fg']), ('disabled', t['statusbar_fg'])])
        # Style the dropdown popup listbox
        self.option_add('*TCombobox*Listbox.background', t['input_bg'])
        self.option_add('*TCombobox*Listbox.foreground', t['input_fg'])
        self.option_add('*TCombobox*Listbox.selectBackground', t['highlight_bg'])
        self.option_add('*TCombobox*Listbox.selectForeground', t['highlight_fg'])
        self.option_add('*TCombobox*Listbox.font', (_font, 11))
        
        # Entry - modern flat Apple style
        style.configure('TEntry',
                        fieldbackground=t['input_bg'],
                        foreground=t['input_fg'],
                        bordercolor=t['border'],
                        lightcolor=t['input_bg'],
                        darkcolor=t['input_bg'],
                        font=(_font, 11),
                        padding=[6, 4])
        style.map('TEntry',
                  bordercolor=[('focus', t['accent'])],
                  lightcolor=[('focus', t['accent'])])
        
        # Separator
        style.configure('TSeparator', background=t['border'])
        
        # PanedWindow - flat sash
        style.configure('TPanedwindow', background=t['bg'])
        style.configure('Sash', sashthickness=4, gripcount=0,
                        background=t['border'])
        
        # Scrollbar - modern thin macOS-style (no arrows, no grip)
        style.configure('Vertical.TScrollbar',
                        background=t['surface_alt'],
                        troughcolor=t['bg'],
                        bordercolor=t['bg'],
                        lightcolor=t['surface_alt'],
                        darkcolor=t['surface_alt'],
                        arrowcolor=t['bg'],
                        arrowsize=0,
                        gripcount=0,
                        width=8)
        style.map('Vertical.TScrollbar',
                  background=[('active', t['border']), ('pressed', t['border'])],
                  bordercolor=[('active', t['bg'])],
                  lightcolor=[('active', t['border'])],
                  darkcolor=[('active', t['border'])])
        style.configure('Horizontal.TScrollbar',
                        background=t['surface_alt'],
                        troughcolor=t['bg'],
                        bordercolor=t['bg'],
                        lightcolor=t['surface_alt'],
                        darkcolor=t['surface_alt'],
                        arrowcolor=t['bg'],
                        arrowsize=0,
                        gripcount=0,
                        width=8)
        style.map('Horizontal.TScrollbar',
                  background=[('active', t['border']), ('pressed', t['border'])],
                  bordercolor=[('active', t['bg'])],
                  lightcolor=[('active', t['border'])],
                  darkcolor=[('active', t['border'])])
        
        # Menu colors
        self._apply_menu_theme(self['menu'], t)
        
        # Statusbar
        if hasattr(self, 'statusbar'):
            self.statusbar.configure(
                background=t['statusbar_bg'],
                foreground=t['statusbar_fg']
            )
        
        # Sidebar Treeview - Apple source list style (flat)
        style.configure('Sidebar.Treeview',
                        background=t['listbox_bg'],
                        foreground=t['listbox_fg'],
                        fieldbackground=t['listbox_bg'],
                        bordercolor=t['listbox_bg'],
                        lightcolor=t['listbox_bg'],
                        darkcolor=t['listbox_bg'],
                        font=(_font, 11),
                        rowheight=34,
                        indent=16)
        style.map('Sidebar.Treeview',
                  background=[('selected', t['listbox_select_bg'])],
                  foreground=[('selected', t['listbox_select_fg'])])

        # Apply section header tag styling
        if hasattr(self, 'file_tree'):
            self.file_tree.tag_configure('section',
                                         font=(_font, 9, 'bold'),
                                         foreground=t['dir_label_fg'])
            self.file_tree.tag_configure('file',
                                         font=(_font, 11))
        
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
                insertbackground=t['fg'],
                font=(_font, 11)
            )
        
        # Debug text widget
        if hasattr(self, 'debug_text'):
            self.debug_text.configure(
                bg=t['debug_bg'],
                fg=t['debug_fg'],
                insertbackground=t['fg'],
                font=('Cascadia Mono', 10)
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
        
        # AFR Tuning info label
        if hasattr(self, 'afr_info_label'):
            self.afr_info_label.configure(foreground=t['dir_label_fg'])
        
        # AFR edit info label
        if hasattr(self, 'afr_edit_info'):
            self.afr_edit_info.configure(foreground=t['dir_label_fg'])
        
        # AFR record label
        if hasattr(self, 'afr_record_label'):
            self.afr_record_label.configure(foreground=t['dir_label_fg'])
        
        # AFR Tuning matplotlib figure
        if hasattr(self, 'afr_fig'):
            self.afr_fig.set_facecolor(t['plot_face'])
            for ax in self.afr_fig.axes:
                ax.set_facecolor(t['plot_bg'])
                ax.tick_params(colors=t['plot_tick'], labelsize=7)
                ax.xaxis.label.set_color(t['plot_text'])
                ax.yaxis.label.set_color(t['plot_text'])
                ax.title.set_color(t['plot_text'])
                for spine in ax.spines.values():
                    spine.set_color(t['plot_spine'])
            self.afr_canvas.draw()
        
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
            ax.tick_params(colors=t['plot_tick'], labelsize=8)
            ax.xaxis.label.set_color(t['plot_text'])
            ax.yaxis.label.set_color(t['plot_text'])
            ax.title.set_color(t['plot_text'])
            for spine in ax.spines.values():
                spine.set_color(t['plot_spine'])
            ax.grid(True, which='major', alpha=0.2, color=t['plot_grid'])
            ax.xaxis.set_minor_locator(AutoMinorLocator())
            ax.yaxis.set_minor_locator(AutoMinorLocator())
            ax.grid(True, which='minor', alpha=0.1, color=t['plot_grid'], linestyle=':')
        
        self.fig.subplots_adjust(left=0.06, right=0.98, top=0.98, bottom=0.04, hspace=0.15)
        self.canvas.draw()
    
    def show_about(self) -> None:
        """Show about dialog."""
        messagebox.showinfo(
            "About MegaLogViewer",
            "MegaLogViewer\n"
            "Version 2.0\n\n"
            "View and analyze TunerStudio MS\n"
            "MegaSquirt .mlg log files.\n\n"
            "Features\n"
            "\u2022 Browse and select log files\n"
            "\u2022 Tabular data view with sorting\n"
            "\u2022 Multi-channel time series plots\n"
            "\u2022 CSV export\n"
            "\u2022 MSQ tune file viewer\n"
            "\u2022 AFR tuning analysis\n\n"
            "Built with Python, tkinter, and matplotlib"
        )


if __name__ == "__main__":
    """Entry point for MegaLogViewer application."""
    # Enable DPI awareness before creating any Tk windows
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass
    try:
        app = LogViewerApp()
        app.mainloop()
    except Exception as e:
        print(f"[FATAL] An unexpected error occurred: {e}", file=sys.stderr)
        traceback.print_exc()
        sys.exit(1)
