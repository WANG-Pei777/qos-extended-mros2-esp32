#!/usr/bin/env python3
"""
G4: Memory Budget - Quick test for parameter upper bounds
Modifies config.h, builds, flashes, and extracts free heap from serial output
"""
import re
import subprocess
import sys
import time
from pathlib import Path

import serial

PROJECT_ROOT = Path("/home/wsde-47/mROS2-QoS")
CONFIG_H = PROJECT_ROOT / "platform/rtps/config.h"
PORT = sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyUSB0"
RESULTS_CSV = PROJECT_ROOT / "results/g4_memory_budget.csv"

# Create results directory
RESULTS_CSV.parent.mkdir(parents=True, exist_ok=True)

# Backup config.h
backup = CONFIG_H.with_suffix(".h.g4_backup")
if not backup.exists():
    backup.write_text(CONFIG_H.read_text())
    print(f"[backup] Created: {backup}")


def modify_config(param_pattern: str, new_value: int) -> bool:
    """Modify a parameter in config.h"""
    content = CONFIG_H.read_text()

    # Match pattern like "const uint8_t NUM_STATEFUL_WRITERS = 8;"
    pattern = f"({param_pattern}\\s*=\\s*)\\d+"

    if not re.search(pattern, content):
        print(f"[ERROR] Pattern not found: {param_pattern}")
        return False

    new_content = re.sub(pattern, f"\\g<1>{new_value}", content)
    CONFIG_H.write_text(new_content)
    return True


def build_and_flash() -> bool:
    """Build and flash firmware"""
    # Source ESP-IDF and build
    build_cmd = f"cd {PROJECT_ROOT} && source /home/wsde-47/esp-idf/export.sh > /dev/null 2>&1 && idf.py build"

    result = subprocess.run(build_cmd, shell=True, executable='/bin/bash',
                          capture_output=True, text=True)

    if result.returncode != 0:
        print("[FAIL] Build failed")
        return False

    print("[OK] Build successful")

    # Flash
    flash_cmd = f"cd {PROJECT_ROOT} && source /home/wsde-47/esp-idf/export.sh > /dev/null 2>&1 && idf.py -p {PORT} flash"

    result = subprocess.run(flash_cmd, shell=True, executable='/bin/bash',
                          capture_output=True, text=True)

    if result.returncode != 0:
        print("[FAIL] Flash failed")
        return False

    print("[OK] Flash successful")
    return True


def capture_serial_and_extract_heap() -> tuple[str, int]:
    """Reset ESP32 and capture serial output to extract free heap"""
    ser = serial.Serial(PORT, 115200, timeout=0.5)

    # Hardware reset
    try:
        ser.dtr = False
        ser.rts = True
        time.sleep(0.15)
        ser.rts = False
        time.sleep(0.3)
    except Exception as e:
        print(f"[WARN] Reset: {e}")

    # Capture output for 15 seconds
    print("[serial] Capturing boot sequence...")
    start = time.time()
    output_lines = []

    while time.time() - start < 15:
        data = ser.read(4096)
        if data:
            text = data.decode('utf-8', 'replace')
            output_lines.append(text)

    ser.close()

    full_output = ''.join(output_lines)

    # Check for crashes
    if any(marker in full_output for marker in ['abort()', 'Guru Meditation', 'LoadProhibited', 'StoreProhibited']):
        return 'CRASH', 0

    # Extract free heap
    heap_match = re.search(r'Free heap:\s+(\d+)\s+bytes', full_output)
    if heap_match:
        heap = int(heap_match.group(1))
        return 'OK', heap

    return 'UNKNOWN', 0


def test_parameter(param_name: str, param_pattern: str, values: list[int]):
    """Test a parameter with multiple values"""
    print(f"\n{'='*60}")
    print(f"Testing: {param_name}")
    print(f"{'='*60}")

    for value in values:
        print(f"\n--- {param_name} = {value} ---")

        # Restore backup before each test
        CONFIG_H.write_text(backup.read_text())

        # Modify parameter
        if not modify_config(param_pattern, value):
            continue

        # Build and flash
        if not build_and_flash():
            with open(RESULTS_CSV, 'a') as f:
                f.write(f"{param_name},{value},0,BUILD_FAIL,Build or flash failed\n")
            continue

        # Wait for flash to settle
        time.sleep(2)

        # Capture serial and extract heap
        status, heap = capture_serial_and_extract_heap()

        print(f"[result] Status={status}, Free heap={heap} bytes")

        # Record result
        with open(RESULTS_CSV, 'a') as f:
            f.write(f"{param_name},{value},{heap},{status},\n")

        # Stop if crashed
        if status == 'CRASH':
            print(f"[STOP] Crashed at {value}, stopping {param_name} tests")
            break


def main():
    print("="*60)
    print("G4: Memory Budget Testing")
    print("="*60)
    print(f"Config: {CONFIG_H}")
    print(f"Port: {PORT}")
    print(f"Results: {RESULTS_CSV}")
    print()

    # Initialize results CSV
    with open(RESULTS_CSV, 'w') as f:
        f.write("parameter,value,free_heap_bytes,status,notes\n")

    # Test 1: NUM_STATEFUL_WRITERS
    test_parameter(
        "NUM_STATEFUL_WRITERS",
        "const uint8_t NUM_STATEFUL_WRITERS",
        [8, 12, 16, 24, 32]
    )

    # Test 2: HISTORY_SIZE_STATEFUL
    test_parameter(
        "HISTORY_SIZE_STATEFUL",
        "const uint8_t HISTORY_SIZE_STATEFUL",
        [10, 20, 30, 50, 100]
    )

    # Restore original config
    CONFIG_H.write_text(backup.read_text())

    print("\n" + "="*60)
    print("G4: Memory Budget Testing Complete")
    print("="*60)
    print(f"Results saved to: {RESULTS_CSV}")
    print()
    print("Summary:")
    print(RESULTS_CSV.read_text())


if __name__ == '__main__':
    main()
