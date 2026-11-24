#!/usr/bin/env python3
"""
Modify RTPS config.h parameters for automated parameter sweeps.
"""
import argparse
import json
import re
import sys
from pathlib import Path


def load_config(config_path: Path) -> dict:
    """Load automation configuration."""
    with open(config_path) as f:
        return json.load(f)


def backup_file(file_path: Path) -> Path:
    """Create backup of original file."""
    backup_path = file_path.with_suffix(file_path.suffix + '.backup')
    if not backup_path.exists():
        backup_path.write_text(file_path.read_text())
        print(f"[backup] Created: {backup_path}")
    return backup_path


def restore_file(file_path: Path) -> None:
    """Restore original file from backup."""
    backup_path = file_path.with_suffix(file_path.suffix + '.backup')
    if backup_path.exists():
        file_path.write_text(backup_path.read_text())
        print(f"[restore] Restored: {file_path}")
    else:
        print(f"[restore] No backup found: {backup_path}", file=sys.stderr)
        sys.exit(1)


def modify_parameter(file_path: Path, line_pattern: str, new_value, value_format: str = None) -> bool:
    """
    Modify a parameter in the config file.

    Args:
        file_path: Path to config.h
        line_pattern: Pattern to match the line (e.g., "const uint16_t SF_WRITER_HB_PERIOD_MS =")
        new_value: New value to set (can be int, dict for Duration_t)
        value_format: Optional format string for complex types

    Returns:
        True if modified, False if not found
    """
    content = file_path.read_text()
    lines = content.splitlines()

    modified = False
    new_lines = []

    for line in lines:
        if line_pattern in line:
            # Extract indentation and preserve comment
            match = re.match(r'(\s*)(.+?)(//.*)?$', line)
            if match:
                indent = match.group(1)
                comment = match.group(3) or ''

                # Format the new value
                if value_format and isinstance(new_value, dict):
                    # Duration_t format: {seconds, nanoseconds}
                    formatted_value = value_format.format(**new_value)
                else:
                    formatted_value = str(new_value)

                # Reconstruct line
                new_line = f"{indent}{line_pattern} {formatted_value};"
                if comment:
                    new_line += f" {comment}"

                new_lines.append(new_line)
                modified = True
                print(f"[modify] {line_pattern.strip()}")
                print(f"  OLD: {line.strip()}")
                print(f"  NEW: {new_line.strip()}")
            else:
                new_lines.append(line)
        else:
            new_lines.append(line)

    if modified:
        file_path.write_text('\n'.join(new_lines) + '\n')
        return True
    else:
        print(f"[modify] Pattern not found: {line_pattern}", file=sys.stderr)
        return False


def main():
    parser = argparse.ArgumentParser(description='Modify RTPS config parameters')
    parser.add_argument('--config', type=Path, default='scripts/automation/config.json',
                        help='Path to config.json')
    parser.add_argument('--param', required=True,
                        help='Parameter name (heartbeat_period, history_size, etc.)')
    parser.add_argument('--value', required=True,
                        help='New value (for lease_duration use format: 12,0)')
    parser.add_argument('--backup', action='store_true',
                        help='Create backup before modifying')
    parser.add_argument('--restore', action='store_true',
                        help='Restore from backup')

    args = parser.parse_args()

    # Load configuration
    config = load_config(args.config)
    project_root = Path(config['project_root'])

    # Get parameter configuration
    if args.param not in config['parameters']:
        print(f"[error] Unknown parameter: {args.param}", file=sys.stderr)
        print(f"Available: {', '.join(config['parameters'].keys())}")
        sys.exit(1)

    param_config = config['parameters'][args.param]
    file_path = project_root / param_config['file']

    # Handle restore
    if args.restore:
        restore_file(file_path)
        sys.exit(0)

    # Create backup
    if args.backup:
        backup_file(file_path)

    # Parse value
    if args.param == 'lease_duration':
        # Format: "12,0" -> {"seconds": 12, "nanoseconds": 0}
        parts = args.value.split(',')
        if len(parts) != 2:
            print("[error] lease_duration format: seconds,nanoseconds (e.g., 12,0)", file=sys.stderr)
            sys.exit(1)
        value = {"seconds": int(parts[0]), "nanoseconds": int(parts[1])}
        value_format = param_config.get('format')
    else:
        value = int(args.value)
        value_format = None

    # Modify parameter
    success = modify_parameter(
        file_path,
        param_config['line_pattern'],
        value,
        value_format
    )

    if success:
        print(f"[success] Modified {args.param} = {args.value}")
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == '__main__':
    main()
