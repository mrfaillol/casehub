#!/usr/bin/env python3
"""Fix calendly.js - replace ALL double-quoted strings containing ${process.env with backtick template literals"""
import re, sys

filepath = sys.argv[1] if len(sys.argv) > 1 else "calendly.js"

with open(filepath) as f:
    content = f.read()

original = content
fixed = 0

# Strategy: find any line containing ${process.env inside double quotes
# and convert the outermost double quotes of that string to backticks
lines = content.split('\n')
for i, line in enumerate(lines):
    if '${process.env.' not in line:
        continue
    if '`${process.env.' in line:
        continue  # already fixed

    # Find the double-quoted string containing ${process.env.
    # We need to find the opening " that precedes ${process.env and the closing " after it
    pos = line.find('${process.env.')

    # Walk backwards to find the opening "
    open_q = -1
    for j in range(pos - 1, -1, -1):
        if line[j] == '"':
            open_q = j
            break

    if open_q == -1:
        continue

    # Walk forward from after ${process.env.XXX} to find the pattern end
    # Find the closing } of the template expression first
    brace_depth = 0
    k = pos + 2  # skip ${
    while k < len(line):
        if line[k] == '{':
            brace_depth += 1
        elif line[k] == '}':
            if brace_depth == 0:
                break
            brace_depth -= 1
        k += 1

    # Now find the closing " - it's the last " on the meaningful part of the line
    close_q = -1
    # Search from end of line backwards
    stripped = line.rstrip()
    for j in range(len(stripped) - 1, k, -1):
        if stripped[j] == '"':
            close_q = j
            break
        elif stripped[j] == ',':
            continue

    if close_q == -1:
        continue

    # Replace the quotes with backticks
    chars = list(line)
    chars[open_q] = '`'
    chars[close_q] = '`'
    lines[i] = ''.join(chars)
    fixed += 1
    print(f"  Line {i+1}: {lines[i].strip()}")

content = '\n'.join(lines)
with open(filepath, 'w') as f:
    f.write(content)

print(f"Fixed {fixed} lines total")
