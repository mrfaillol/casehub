#!/usr/bin/env python3
"""Fix calendly.js line 96 - the message string with embedded template literal"""
import sys

filepath = sys.argv[1] if len(sys.argv) > 1 else "calendly.js"

with open(filepath) as f:
    lines = f.readlines()

line = lines[95]  # line 96, 0-indexed
print(f"BEFORE: {repr(line.strip())}")

# Find 'message: "' and replace the opening " with `
idx_start = line.index('message: "') + len('message: ')

# Find the closing " before the trailing comma
stripped = line.rstrip()
if stripped.endswith('",'):
    idx_end = len(stripped) - 2  # position of the closing "
elif stripped.endswith('"'):
    idx_end = len(stripped) - 1
else:
    print("ERROR: unexpected line ending")
    sys.exit(1)

chars = list(line)
chars[idx_start] = '`'
chars[idx_end] = '`'
lines[95] = ''.join(chars)
print(f"AFTER:  {repr(lines[95].strip())}")

with open(filepath, 'w') as f:
    f.writelines(lines)

print("Done")
