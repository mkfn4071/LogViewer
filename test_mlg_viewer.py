"""
Unit tests for MLG Log Viewer

Tests MLGParser and LogData classes using unittest framework.
Uses mock data to avoid file system dependencies.

Run tests:
    python -m unittest test_mlg_viewer.py
    python -m unittest discover
"""

import unittest
from unittest.mock import Mock, patch, mock_open, MagicMock
import struct
from typing import Dict, List
import io

from mlg_log_viewer import MLGParser, LogData, MSQParser


class TestMLGParser(unittest.TestCase):
    """Tests for MLGParser class - binary file parsing logic."""
    
    def create_valid_header(self) -> bytes:
        """Create minimal valid MLVLG header (24 bytes for v2, 22 for v1)."""
        header = b'MLVLG'  # Magic string (6 bytes with null padding)
        header += b'\x00'  # Padding to 6 bytes
        header += struct.pack('>H', 1)  # Format version (uint16)
        header += struct.pack('>I', 1699000000)  # Timestamp (uint32)
        header += struct.pack('>H', 22)  # Info data start (uint16, v1 uses 2 bytes)
        header += struct.pack('>I', 100)  # Data begin index (uint32)
        header += struct.pack('>H', 10)  # Record length (uint16)
        header += struct.pack('>H', 2)  # Number of logger fields (uint16)
        return header
    
    def create_valid_header_v2(self, info_start: int = 24, data_begin: int = 200,
                                rec_len: int = 10, num_fields: int = 2) -> bytes:
        """Create valid MLVLG v2 header (24 bytes)."""
        header = b'MLVLG'
        header += b'\x00'
        header += struct.pack('>H', 2)  # Format version (uint16)
        header += struct.pack('>I', 1699000000)  # Timestamp (uint32)
        header += struct.pack('>I', info_start)  # Info data start (uint32, 4 bytes in v2)
        header += struct.pack('>I', data_begin)  # Data begin index (uint32)
        header += struct.pack('>H', rec_len)  # Record length (uint16)
        header += struct.pack('>H', num_fields)  # Number of logger fields (uint16)
        return header
    
    def create_field_definition(self, field_type: int = 0, name: str = "TestField", 
                                units: str = "units", scale: float = 1.0, 
                                transform: float = 0.0) -> bytes:
        """Create field definition (55 bytes for version 1)."""
        field = struct.pack('>B', field_type)  # Field type (uint8)
        field += name.ljust(34, '\x00').encode('utf-8')  # Name (34 bytes)
        field += units.ljust(10, '\x00').encode('utf-8')  # Units (10 bytes)
        field += struct.pack('>B', 0)  # Display style (uint8)
        field += struct.pack('>f', scale)  # Scale (float32)
        field += struct.pack('>f', transform)  # Transform (float32)
        field += struct.pack('>b', 2)  # Digits (int8)
        return field
    
    def create_data_block(self, values: List[int]) -> bytes:
        """Create data block with counter and timestamp."""
        block = struct.pack('>b', 0)  # Block type (int8)
        block += struct.pack('>B', 1)  # Counter (uint8)
        block += struct.pack('>H', 100)  # Timestamp ms (uint16)
        for val in values:
            block += struct.pack('>B', val)  # Data values (U08 type)
        return block
    
    def test_parse_header_valid_file(self):
        """Test parsing valid MLVLG header."""
        header_data = self.create_valid_header()
        
        parser = MLGParser.__new__(MLGParser)
        parser.data = bytearray(header_data)
        parser.offset = 0
        
        header = parser.parse_header()
        
        self.assertEqual(header['file_format'], 'MLVLG')
        self.assertEqual(header['format_version'], 1)
        self.assertEqual(header['timestamp'], 1699000000)
        self.assertEqual(header['num_logger_fields'], 2)
    
    def test_invalid_magic_string_raises_error(self):
        """Test that invalid magic string raises ValueError."""
        invalid_data = b'WRONG\x00' + struct.pack('>h', 1)
        
        parser = MLGParser.__new__(MLGParser)
        parser.data = bytearray(invalid_data)
        parser.offset = 0
        
        with self.assertRaises(ValueError) as context:
            parser.parse_header()
        
        self.assertIn('Invalid file format', str(context.exception))
        self.assertIn('MLVLG', str(context.exception))
    
    def test_parse_field_definition_scalar(self):
        """Test parsing scalar field definition (U08, S16, F32)."""
        field_data = self.create_field_definition(
            field_type=0, name="RPM", units="RPM", scale=1.5, transform=10.0
        )
        
        parser = MLGParser.__new__(MLGParser)
        parser.data = bytearray(field_data)
        parser.offset = 0
        
        field = parser.parse_field_definition(version=1)
        
        self.assertEqual(field['field_type'], 0)
        self.assertEqual(field['name'], 'RPM')
        self.assertEqual(field['units'], 'RPM')
        self.assertAlmostEqual(field['scale'], 1.5)
        self.assertAlmostEqual(field['transform'], 10.0)
    
    def test_field_type_coverage(self):
        """Test all supported field types (0-7)."""
        field_types = {
            0: ('B', 1),  # U08
            1: ('b', 1),  # S08
            2: ('H', 2),  # U16
            3: ('h', 2),  # S16
            4: ('I', 4),  # U32
            5: ('i', 4),  # S32
            6: ('q', 8),  # S64
            7: ('f', 4),  # F32
        }
        
        for field_type, (fmt, size) in field_types.items():
            with self.subTest(field_type=field_type):
                self.assertIn(field_type, MLGParser.FIELD_TYPES)
                self.assertEqual(MLGParser.FIELD_TYPES[field_type], (fmt, size))
    
    def test_big_endian_byte_order(self):
        """Test that big-endian byte order is used correctly."""
        # Create data with known big-endian value
        test_value = 0x1234
        test_data = struct.pack('>H', test_value)  # Big-endian
        
        parser = MLGParser.__new__(MLGParser)
        parser.data = bytearray(test_data)
        parser.offset = 0
        
        result = parser.read('H', big_endian=True)
        
        self.assertEqual(result, test_value)
        
        # Verify little-endian would give different result
        parser.offset = 0
        result_le = parser.read('H', big_endian=False)
        self.assertNotEqual(result_le, test_value)
    
    def test_read_string_null_termination(self):
        """Test string reading with null termination."""
        test_string = b'TestName\x00\x00\x00'  # Padded with nulls
        
        parser = MLGParser.__new__(MLGParser)
        parser.data = bytearray(test_string)
        parser.offset = 0
        
        result = parser.read_string(len(test_string))
        
        self.assertEqual(result, 'TestName')
        self.assertEqual(parser.offset, len(test_string))
    
    def test_read_advances_offset(self):
        """Test that read operations advance offset correctly."""
        test_data = struct.pack('>HHH', 100, 200, 300)
        
        parser = MLGParser.__new__(MLGParser)
        parser.data = bytearray(test_data)
        parser.offset = 0
        
        val1 = parser.read('H')
        self.assertEqual(val1, 100)
        self.assertEqual(parser.offset, 2)
        
        val2 = parser.read('H')
        self.assertEqual(val2, 200)
        self.assertEqual(parser.offset, 4)
        
        val3 = parser.read('H')
        self.assertEqual(val3, 300)
        self.assertEqual(parser.offset, 6)
    
    @patch('builtins.open', new_callable=mock_open)
    def test_max_records_limit(self, mock_file):
        """Test that MAX_RECORDS constant exists."""
        self.assertEqual(MLGParser.MAX_RECORDS, 100000)
        
        # Verify constant is accessible
        parser = MLGParser.__new__(MLGParser)
        self.assertTrue(hasattr(parser, 'MAX_RECORDS'))
    
    def test_parse_data_blocks_single_record(self):
        """Test parsing single data block with per-record header."""
        # Create v1 header with 2 fields (U08 each, 2 bytes of field data per record)
        # Header: 22 bytes, 2 fields × 55 bytes = 110 bytes, data starts at 132
        header_data = self.create_valid_header()  # v1, 22 bytes
        field1 = self.create_field_definition(field_type=0, name="RPM")
        field2 = self.create_field_definition(field_type=0, name="MAP")
        
        # Data block: 4-byte record header + 2 bytes field data + 1 byte CRC
        data_block = struct.pack('>B', 0)   # Block type (field data)
        data_block += struct.pack('>B', 1)  # Counter
        data_block += struct.pack('>H', 100)  # Timestamp
        data_block += struct.pack('>B', 50)  # RPM value (U08)
        data_block += struct.pack('>B', 75)  # MAP value (U08)
        data_block += struct.pack('>B', 0)  # CRC
        
        file_data = header_data + field1 + field2 + data_block
        
        parser = MLGParser.__new__(MLGParser)
        parser.data = bytearray(file_data)
        parser.offset = 0
        
        # Parse header
        header = parser.parse_header()
        # Fix data_begin to point to actual data start
        header['data_begin_index'] = len(header_data) + len(field1) + len(field2)
        
        # Parse fields
        fields = []
        for _ in range(2):
            field = parser.parse_field_definition(version=1)
            fields.append(field)
        
        # Parse data blocks
        blocks = parser.parse_data_blocks(header, fields)
        
        # Verify one block was parsed with correct values
        self.assertEqual(len(blocks), 1)
        self.assertAlmostEqual(blocks[0]['RPM'], 50.0)
        self.assertAlmostEqual(blocks[0]['MAP'], 75.0)
    
    @patch('builtins.open', new_callable=mock_open)
    def test_init_reads_file(self, mock_file):
        """Test that __init__ reads file into memory."""
        test_content = b'test data'
        mock_file.return_value.read.return_value = test_content
        
        parser = MLGParser('test.mlg')
        
        mock_file.assert_called_once_with('test.mlg', 'rb')
        self.assertEqual(parser.data, bytearray(test_content))
        self.assertEqual(parser.offset, 0)
        self.assertEqual(parser.file_path, 'test.mlg')


class TestLogData(unittest.TestCase):
    """Tests for LogData class - data model and access."""
    
    def create_test_data(self) -> Dict:
        """Create test data matching MLGParser.parse() output format."""
        return {
            'header': {
                'file_format': 'MLVLG',
                'format_version': 1,
                'timestamp': 1699000000,
                'num_logger_fields': 3
            },
            'fields': [
                {'name': 'RPM', 'units': 'RPM', 'scale': 1.0, 'transform': 0.0, 'field_type': 2},
                {'name': 'MAP', 'units': 'kPa', 'scale': 1.0, 'transform': 0.0, 'field_type': 0},
                {'name': 'TPS', 'units': '%', 'scale': 1.0, 'transform': 0.0, 'field_type': 0}
            ],
            'records': [
                {'RPM': 1000.0, 'MAP': 50.0, 'TPS': 10.0},
                {'RPM': 1500.0, 'MAP': 60.0, 'TPS': 20.0},
                {'RPM': 2000.0, 'MAP': 70.0, 'TPS': 30.0},
                {'RPM': 2500.0, 'MAP': 80.0, 'TPS': 40.0},
                {'RPM': 3000.0, 'MAP': 90.0, 'TPS': 50.0}
            ],
            'filename': 'test.mlg',
            'file_timestamp': None,
            'record_count': 5,
            'field_count': 3
        }
    
    def test_get_channel_names(self):
        """Test retrieving list of channel names."""
        log_data = LogData(self.create_test_data())
        
        channel_names = log_data.get_channel_names()
        
        self.assertIsInstance(channel_names, list)
        self.assertEqual(len(channel_names), 3)
        self.assertIn('RPM', channel_names)
        self.assertIn('MAP', channel_names)
        self.assertIn('TPS', channel_names)
    
    def test_get_channel_data(self):
        """Test retrieving data for specific channel."""
        log_data = LogData(self.create_test_data())
        
        rpm_data = log_data.get_channel_data('RPM')
        
        self.assertIsInstance(rpm_data, list)
        self.assertEqual(len(rpm_data), 5)
        self.assertEqual(rpm_data, [1000.0, 1500.0, 2000.0, 2500.0, 3000.0])
    
    def test_get_statistics_calculation(self):
        """Test min/max/mean calculation accuracy."""
        log_data = LogData(self.create_test_data())
        
        stats = log_data.get_statistics('RPM')
        
        self.assertAlmostEqual(stats['min'], 1000.0)
        self.assertAlmostEqual(stats['max'], 3000.0)
        self.assertAlmostEqual(stats['mean'], 2000.0)
        # Note: get_statistics() returns min/max/mean only (no std)
    
    def test_get_field_info(self):
        """Test retrieving field metadata."""
        log_data = LogData(self.create_test_data())
        
        rpm_info = log_data.get_field_info('RPM')
        
        self.assertEqual(rpm_info['name'], 'RPM')
        self.assertEqual(rpm_info['units'], 'RPM')
        self.assertEqual(rpm_info['scale'], 1.0)
        self.assertEqual(rpm_info['transform'], 0.0)
    
    def test_record_count_property(self):
        """Test record_count property."""
        log_data = LogData(self.create_test_data())
        
        self.assertEqual(log_data.record_count, 5)
    
    def test_field_count_property(self):
        """Test field_count property."""
        log_data = LogData(self.create_test_data())
        
        self.assertEqual(log_data.field_count, 3)
    
    def test_empty_data_handling(self):
        """Test handling of empty channel data."""
        empty_data = {
            'header': {
                'file_format': 'MLVLG',
                'format_version': 1,
                'timestamp': 1699000000,
                'num_logger_fields': 0
            },
            'fields': [],
            'records': [],
            'filename': 'empty.mlg',
            'file_timestamp': None,
            'record_count': 0,
            'field_count': 0
        }
        log_data = LogData(empty_data)
        
        self.assertEqual(log_data.record_count, 0)
        self.assertEqual(log_data.field_count, 0)
        self.assertEqual(log_data.get_channel_names(), [])
    
    def test_data_transformation_scale_and_transform(self):
        """Test that scale/transform are preserved in field info."""
        test_data = {
            'header': {
                'file_format': 'MLVLG',
                'format_version': 1,
                'timestamp': 1699000000,
                'num_logger_fields': 1
            },
            'fields': [
                {'name': 'Temp', 'units': '°C', 'scale': 1.8, 'transform': 32.0, 'field_type': 7}
            ],
            'records': [
                {'Temp': 20.0},
                {'Temp': 25.0},
                {'Temp': 30.0}
            ],
            'filename': 'test.mlg',
            'file_timestamp': None,
            'record_count': 3,
            'field_count': 1
        }
        log_data = LogData(test_data)
        
        field_info = log_data.get_field_info('Temp')
        
        self.assertEqual(field_info['scale'], 1.8)
        self.assertEqual(field_info['transform'], 32.0)


class TestIntegration(unittest.TestCase):
    """Integration tests for full parsing workflow."""
    
    @patch('builtins.open', new_callable=mock_open)
    def test_full_parse_workflow(self, mock_file):
        """Test complete parse workflow from file to LogData."""
        # Create complete v1 mock file (v1 has 22-byte header)
        header = b'MLVLG\x00'
        header += struct.pack('>H', 1)  # Version
        header += struct.pack('>I', 1699000000)  # Timestamp
        header += struct.pack('>H', 22)  # Info start (v1 = 2 bytes)
        # header is 16 bytes so far; field defs: 2 * 55 = 110
        # data_begin = 22 + 110 = 132
        header += struct.pack('>I', 132)  # Data begin
        header += struct.pack('>H', 3)  # Record length (U16=2 + U08=1 = 3 bytes)
        header += struct.pack('>H', 2)  # 2 fields
        
        # Field 1: RPM (U16 type)
        field1 = struct.pack('>B', 2)  # U16
        field1 += b'RPM' + b'\x00' * 31
        field1 += b'RPM' + b'\x00' * 7
        field1 += struct.pack('>B', 0)  # Display style
        field1 += struct.pack('>f', 1.0)  # Scale
        field1 += struct.pack('>f', 0.0)  # Transform
        field1 += struct.pack('>b', 0)  # Digits
        
        # Field 2: MAP (U08 type)
        field2 = struct.pack('>B', 0)  # U08
        field2 += b'MAP' + b'\x00' * 31
        field2 += b'kPa' + b'\x00' * 7
        field2 += struct.pack('>B', 0)
        field2 += struct.pack('>f', 1.0)
        field2 += struct.pack('>f', 0.0)
        field2 += struct.pack('>b', 1)
        
        # Data block with per-record header: type(1) + counter(1) + ts(2) + data(3) + crc(1)
        data_block = struct.pack('>B', 0)  # Block type = field data
        data_block += struct.pack('>B', 1)  # Counter
        data_block += struct.pack('>H', 100)  # Timestamp
        data_block += struct.pack('>H', 1500)  # RPM (U16)
        data_block += struct.pack('>B', 75)  # MAP (U08)
        data_block += struct.pack('>B', 0)  # CRC
        
        complete_file = header + field1 + field2 + data_block
        mock_file.return_value.read.return_value = complete_file
        
        # Parse file
        parser = MLGParser('test.mlg')
        result = parser.parse()
        log_data = LogData(result)
        
        # Verify results
        self.assertEqual(log_data.field_count, 2)
        self.assertIn('RPM', log_data.get_channel_names())
        self.assertIn('MAP', log_data.get_channel_names())
        self.assertEqual(log_data.record_count, 1)
        self.assertAlmostEqual(log_data.records[0]['RPM'], 1500.0)
        self.assertAlmostEqual(log_data.records[0]['MAP'], 75.0)


class TestMSQParser(unittest.TestCase):
    """Tests for MSQParser class - XML tune file parsing."""
    
    MINIMAL_MSQ = '''<?xml version="1.0" encoding="ISO-8859-1"?>
<msq xmlns="http://www.msefi.com/:msq">
    <bibliography author="TunerStudio MS" tuneComment="" writeDate="Sun Feb 22 12:57:42 CST 2026"/>
    <versionInfo fileFormat="5.0" firmwareInfo="MS3" nPages="1" signature="MS3 Format"/>
    <page number="0" size="1024">
        <constant name="nCylinders">"8"</constant>
        <constant digits="0" name="crankingRPM" units="RPM">300.0</constant>
        <constant digits="1" name="triggerOffset" units="deg">15.0</constant>
        <constant cols="1" digits="0" name="fuelCorr" rows="2" units="%">
         100.0 
         163.0 
      </constant>
    </page>
    <page>
        <pcVariable digits="0" name="rpmhigh" units="rpm">9000.0</pcVariable>
        <pcVariable name="sensor01Alias">Oil Pressure</pcVariable>
    </page>
</msq>'''
    
    def _parse_string(self, xml_content: str) -> dict:
        """Parse MSQ from string using a temp file mock."""
        import tempfile
        import os
        fd, path = tempfile.mkstemp(suffix='.msq')
        try:
            with os.fdopen(fd, 'w') as f:
                f.write(xml_content)
            parser = MSQParser(path)
            return parser.parse()
        finally:
            os.unlink(path)
    
    def test_parse_bibliography(self):
        """Test bibliography metadata extraction."""
        result = self._parse_string(self.MINIMAL_MSQ)
        bib = result['bibliography']
        self.assertEqual(bib['author'], 'TunerStudio MS')
        self.assertIn('writeDate', bib)
    
    def test_parse_version_info(self):
        """Test version info extraction."""
        result = self._parse_string(self.MINIMAL_MSQ)
        info = result['version_info']
        self.assertEqual(info['fileFormat'], '5.0')
        self.assertEqual(info['nPages'], '1')
    
    def test_parse_constants(self):
        """Test constant element parsing."""
        result = self._parse_string(self.MINIMAL_MSQ)
        entries = result['entries']
        
        # Find nCylinders constant
        cyl = next(e for e in entries if e['name'] == 'nCylinders')
        self.assertEqual(cyl['type'], 'constant')
        self.assertEqual(cyl['value'], '8')
        self.assertEqual(cyl['page'], '0')
    
    def test_parse_constant_with_units_digits(self):
        """Test constant with units and digits attributes."""
        result = self._parse_string(self.MINIMAL_MSQ)
        entries = result['entries']
        
        rpm = next(e for e in entries if e['name'] == 'crankingRPM')
        self.assertEqual(rpm['units'], 'RPM')
        self.assertEqual(rpm['digits'], '0')
        self.assertEqual(rpm['value'], '300.0')
    
    def test_parse_table_constant(self):
        """Test table constant with rows and cols."""
        result = self._parse_string(self.MINIMAL_MSQ)
        entries = result['entries']
        
        fc = next(e for e in entries if e['name'] == 'fuelCorr')
        self.assertEqual(fc['dimensions'], '2x1')
        self.assertIn('100.0', fc['value'])
        self.assertIn('163.0', fc['value'])
    
    def test_parse_pc_variables(self):
        """Test pcVariable element parsing."""
        result = self._parse_string(self.MINIMAL_MSQ)
        entries = result['entries']
        
        pc_entries = [e for e in entries if e['type'] == 'pcVariable']
        self.assertTrue(len(pc_entries) >= 2)
        
        rpmhigh = next(e for e in pc_entries if e['name'] == 'rpmhigh')
        self.assertEqual(rpmhigh['value'], '9000.0')
        self.assertEqual(rpmhigh['units'], 'rpm')
    
    def test_entry_count(self):
        """Test total entry count."""
        result = self._parse_string(self.MINIMAL_MSQ)
        self.assertEqual(result['entry_count'], len(result['entries']))
        self.assertTrue(result['entry_count'] >= 6)  # 4 constants + 2 pcVariables
    
    def test_filename_stored(self):
        """Test that filename is stored in result."""
        result = self._parse_string(self.MINIMAL_MSQ)
        self.assertTrue(result['filename'].endswith('.msq'))
    
    def test_empty_msq(self):
        """Test parsing MSQ with no entries."""
        empty_msq = '''<?xml version="1.0" encoding="ISO-8859-1"?>
<msq xmlns="http://www.msefi.com/:msq">
    <bibliography author="Test"/>
    <versionInfo fileFormat="5.0"/>
</msq>'''
        result = self._parse_string(empty_msq)
        self.assertEqual(result['entry_count'], 0)
        self.assertEqual(len(result['entries']), 0)
    
    def test_constant_without_optional_attrs(self):
        """Test constant missing optional attributes."""
        msq = '''<?xml version="1.0" encoding="ISO-8859-1"?>
<msq xmlns="http://www.msefi.com/:msq">
    <page number="0">
        <constant name="simple">42.0</constant>
    </page>
</msq>'''
        result = self._parse_string(msq)
        entry = result['entries'][0]
        self.assertEqual(entry['name'], 'simple')
        self.assertEqual(entry['value'], '42.0')
        self.assertEqual(entry['units'], '')
        self.assertEqual(entry['digits'], '')
        self.assertEqual(entry['dimensions'], '')


if __name__ == '__main__':
    unittest.main()
