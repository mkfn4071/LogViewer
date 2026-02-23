# Testing Guide for MLG Log Viewer

This document provides comprehensive testing procedures for the MLG Log Viewer application. Follow these steps to verify functionality before deployment or after making code changes.

## Prerequisites

- Python 3.7+ installed
- matplotlib package installed
- Sample `.mlg` files available in `MyCar/DataLogs/` directory
- At least one valid log file with multiple channels and records

## Automated Unit Tests

The project includes a comprehensive unit test suite (`test_mlg_viewer.py`) that covers parser logic and data model functionality. These tests use mock data and do not require sample .mlg files.

### Running Automated Tests

**Run all tests**:

```bash
python -m unittest test_mlg_viewer.py
```

**Auto-discover all test files**:

```bash
python -m unittest discover
```

**Expected output**:

```
...............
----------------------------------------------------------------------
Ran 15 tests in 0.025s

OK
```

### What Automated Tests Cover

- ✅ MLGParser: Header parsing, field definitions, data blocks, byte order handling
- ✅ Error scenarios: Invalid formats, corrupted data
- ✅ LogData: Channel access, statistics calculation, metadata retrieval
- ✅ Integration: Full parse workflow

### When to Use Automated Tests

- After code changes to parser or data model
- Before committing code
- As part of continuous integration
- Quick validation without .mlg files

**Note**: Automated tests complement but do not replace the manual testing procedures below, which validate GUI behavior and real-world file handling.

## Test Categories

### 1. Parser Tests

#### Test 1.1: Valid File Parsing
**Objective**: Verify parser correctly reads valid MLVLG files

**Steps**:
1. Open a known-good `.mlg` file via GUI or CLI
2. Check status bar shows "Loaded X records from [filename]"
3. Verify Summary tab displays correct filename and record count
4. Confirm channel count matches expected value

**Expected Result**: File loads without errors, metadata displayed correctly

#### Test 1.2: Invalid File Handling
**Objective**: Ensure parser rejects invalid files gracefully

**Steps**:
1. Create a text file with `.mlg` extension
2. Attempt to open via File → Open
3. Observe error dialog

**Expected Result**: Error dialog appears: "Invalid file format: File does not start with MLVLG magic string"

#### Test 1.3: Field Type Coverage
**Objective**: Verify all supported field types parse correctly

**Steps**:
1. Open log file containing various data types (U08, S08, U16, S16, U32, S32, F32)
2. Check Data Grid displays values for all channels
3. Plot channels of different types

**Expected Result**: All field types display and plot without errors

#### Test 1.4: Large File Handling
**Objective**: Test file size validation and warning

**Steps**:
1. Attempt to open file >500 MB (or modify MAX_FILE_SIZE_MB for testing)
2. Observe warning dialog with file size information
3. Click "No" to cancel
4. Verify status bar shows "Load cancelled"

**Expected Result**: Warning appears before parsing, cancellation works correctly

### 2. GUI Tests

#### Test 2.1: Window Creation
**Objective**: Verify application window initializes properly

**Steps**:
1. Launch application without arguments
2. Check window appears with title "MLG Log Viewer"
3. Verify menu bar (File, Help) present
4. Confirm toolbar buttons visible
5. Check three tabs: Data Grid, Visualization, Summary

**Expected Result**: Window opens 1200x800 with all UI elements visible

#### Test 2.2: Menu Functionality
**Objective**: Test all menu items work correctly

**Steps**:
1. Click File → Open, observe file dialog
2. Click File → Export CSV (without file loaded), check error handling
3. Click Help → About, verify dialog appears
4. Test keyboard shortcuts: Ctrl+O, Ctrl+E, Ctrl+Q

**Expected Result**: All menu items and shortcuts function as expected

#### Test 2.3: Toolbar Buttons
**Objective**: Verify toolbar actions

**Steps**:
1. Click "Open" button, check file dialog appears
2. Load a file
3. Click "Export CSV" button, verify save dialog

**Expected Result**: Toolbar buttons match menu functionality

### 3. File Operations

#### Test 3.1: File Open Dialog
**Objective**: Test file selection dialog

**Steps**:
1. Click File → Open
2. Verify dialog shows `.mlg` file filter
3. Navigate to `MyCar/DataLogs/` (if exists)
4. Cancel dialog, confirm application remains responsive

**Expected Result**: Dialog displays correctly, cancellation handled gracefully

#### Test 3.2: CLI File Loading
**Objective**: Verify command-line file argument

**Steps**:
1. Run: `python mlg_log_viewer.py MyCar/DataLogs/2025-11-02_15.10.56.mlg`
2. Check file loads automatically on startup
3. Verify data appears in all tabs

**Expected Result**: File loads without user interaction, data populated

#### Test 3.3: CSV Export
**Objective**: Test export functionality

**Steps**:
1. Load a log file
2. Click File → Export CSV
3. Choose destination and filename
4. Check CSV file created with readable data
5. Verify first row contains channel names
6. Confirm data rows match source

**Expected Result**: Valid CSV file created with all records

#### Test 3.4: Export Without Data
**Objective**: Verify error handling for export with no file loaded

**Steps**:
1. Launch application
2. Click File → Export CSV immediately
3. Observe error dialog

**Expected Result**: Error dialog: "Please load a log file first"

### 4. Data Grid Tests

#### Test 4.1: Grid Population
**Objective**: Verify data grid displays correctly

**Steps**:
1. Load file with known record count
2. Switch to Data Grid tab
3. Check columns appear for all channels
4. Verify rows show first 1000 records (or less if file smaller)
5. Confirm record numbers displayed correctly

**Expected Result**: Grid populated with correct columns and data

#### Test 4.2: Pagination Controls
**Objective**: Test all page navigation functions

**Steps**:
1. Load file with >1000 records
2. Click "Next Page", verify page 2 data displayed
3. Click "Last Page", check final page shown
4. Click "Previous Page", confirm navigation backward
5. Click "First Page", verify return to page 1
6. Enter specific page number in entry field, press Enter

**Expected Result**: All navigation controls work, page indicator updates

#### Test 4.3: Pagination Edge Cases
**Objective**: Test boundary conditions

**Steps**:
1. On first page, click "Previous" button (should remain on page 1)
2. On last page, click "Next" button (should remain on last page)
3. Enter invalid page number (0, negative, > total pages)

**Expected Result**: Buttons handle edges gracefully, invalid entries ignored or corrected

#### Test 4.4: Column Sorting (Ascending)
**Objective**: Verify ascending sort functionality

**Steps**:
1. Load file with numeric channel (e.g., RPM, temperature)
2. Click column header once
3. Check for ▲ indicator in header
4. Verify data sorted low to high
5. Paginate through data to confirm sort persists

**Expected Result**: Column sorts ascending, indicator visible, sort applies to all pages

#### Test 4.5: Column Sorting (Descending)
**Objective**: Verify descending sort functionality

**Steps**:
1. Click same column header again
2. Check for ▼ indicator
3. Verify data sorted high to low

**Expected Result**: Sort direction toggles, indicator updates, data reordered

#### Test 4.6: Multi-Column Sorting
**Objective**: Test sorting different columns

**Steps**:
1. Sort by first column (e.g., "Time")
2. Note sort indicator
3. Click different column header
4. Verify new column sorted, indicator moved

**Expected Result**: Only one column shows sort indicator at a time

### 5. Visualization Tests

#### Test 5.1: Channel Selection
**Objective**: Verify channel dropdown populated

**Steps**:
1. Load file
2. Switch to Visualization tab
3. Check dropdown lists all channels
4. Select different channels from list

**Expected Result**: All channels available in dropdown

#### Test 5.2: Plot Generation
**Objective**: Test plotting functionality

**Steps**:
1. Select channel from dropdown
2. Click "Plot Channel" button
3. Verify line chart appears
4. Check X-axis shows record numbers
5. Confirm Y-axis shows channel values with units
6. Verify title displays channel name

**Expected Result**: Correct plot displayed with proper labels

#### Test 5.3: Statistics Display
**Objective**: Verify statistics calculation

**Steps**:
1. Plot a channel
2. Check statistics text below plot
3. Verify Min, Max, Mean, Std values displayed
4. Compare values to known data or manual calculation

**Expected Result**: Accurate statistics formatted to 2 decimal places

#### Test 5.4: Matplotlib Toolbar
**Objective**: Test embedded matplotlib controls

**Steps**:
1. Plot channel
2. Use Pan/Zoom tool to navigate plot
3. Click Home to reset view
4. Try Save button to export plot as PNG

**Expected Result**: All matplotlib tools function normally

#### Test 5.5: Multi-File Plot Cleanup
**Objective**: Verify matplotlib resource cleanup

**Steps**:
1. Load file and plot channel
2. Load different file
3. Plot channel in new file
4. Repeat 5-10 times
5. Monitor memory usage (Task Manager/Activity Monitor)

**Expected Result**: Memory usage stable, no continuous growth (leak fixed)

### 6. Error Handling Tests

#### Test 6.1: File Permission Errors
**Objective**: Test handling of access-denied scenarios

**Steps**:
1. Create `.mlg` file and set read-only permissions (or lock file)
2. Attempt to open file
3. Observe error dialog

**Expected Result**: Dialog shows "File Access Error: Could not access file" with OSError details

#### Test 6.2: Corrupted File Handling
**Objective**: Verify graceful handling of malformed data

**Steps**:
1. Truncate valid `.mlg` file (remove last 50%)
2. Attempt to load truncated file
3. Check error handling

**Expected Result**: Error dialog appears, application remains stable

#### Test 6.3: Export Permission Errors
**Objective**: Test CSV export error handling

**Steps**:
1. Load file
2. Export CSV to read-only directory (or filename)
3. Observe error dialog

**Expected Result**: Dialog shows "Export Error: Failed to export CSV" with IOError details

### 7. Performance Tests

#### Test 7.1: Large File Loading
**Objective**: Measure performance with maximum data

**Steps**:
1. Load file with ~100,000 records (near MAX_RECORDS limit)
2. Time loading process
3. Check memory usage
4. Navigate all tabs to verify responsiveness

**Expected Result**: Loads in reasonable time (<30s), memory <500 MB, UI responsive

#### Test 7.2: Pagination Speed
**Objective**: Verify grid updates quickly

**Steps**:
1. Load large file
2. Rapidly click Next Page multiple times
3. Jump to last page
4. Return to first page

**Expected Result**: Page changes appear within 1 second

#### Test 7.3: Plot Rendering Speed
**Objective**: Test visualization performance

**Steps**:
1. Load file with 10,000+ records
2. Plot channel, measure time to display
3. Switch channels multiple times

**Expected Result**: Plots render in <5 seconds, switching smooth

### 8. Integration Tests

#### Test 8.1: Full Workflow
**Objective**: Test complete user journey

**Steps**:
1. Launch application
2. Open log file via File → Open
3. Navigate to Data Grid, page through data
4. Sort by multiple columns
5. Switch to Visualization, plot 2-3 channels
6. Check Summary tab
7. Export to CSV
8. Open exported CSV in spreadsheet software
9. Quit application

**Expected Result**: All operations complete successfully, no errors

#### Test 8.2: Multi-File Session
**Objective**: Verify file switching works correctly

**Steps**:
1. Load first file, note channel count
2. Load second file (different channels/record count)
3. Verify new file data replaces old
4. Check all tabs update correctly
5. Load third file, repeat verification

**Expected Result**: Each file fully replaces previous, no data mixing

## Regression Testing Checklist

After any code modifications, verify:

- [ ] File opening (GUI and CLI)
- [ ] Data grid population and pagination
- [ ] Column sorting (ascending and descending)
- [ ] Plot generation and toolbar
- [ ] CSV export
- [ ] Memory cleanup (multi-file load)
- [ ] Error dialogs (invalid file, permissions)
- [ ] File size warning (>500 MB)
- [ ] Keyboard shortcuts
- [ ] All three tabs display correctly

## Troubleshooting Test Failures

### Parser Failures
- Verify test file is valid MLVLG format
- Check struct format strings match field types
- Ensure big-endian byte order ('>' prefix)

### GUI Display Issues
- Update tkinter/matplotlib packages
- Check screen resolution (minimum 1024x768)
- Try different operating systems (Windows/Mac/Linux)

### Performance Issues
- Reduce MAX_RECORDS for testing
- Use smaller test files (<10 MB)
- Profile code with cProfile

### Memory Leaks
- Verify `plt.close(self.fig)` called in cleanup
- Check all file handles closed
- Use memory profiler to identify leaks

## Test Data Recommendations

Maintain test dataset with:
- Small file: ~100 records, 5-10 channels (quick tests)
- Medium file: ~5,000 records, 20 channels (functionality tests)
- Large file: ~50,000 records, 30+ channels (performance tests)
- Invalid file: Text file with `.mlg` extension (error handling)
- Corrupted file: Truncated valid file (robustness testing)

## Automated Testing

For future enhancement, consider:
- Unit tests for `MLGParser` class methods
- Mock file I/O for testing without sample files
- Automated GUI testing with `unittest` and `unittest.mock`
- Continuous integration with test suite execution
