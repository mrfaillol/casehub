#!/usr/bin/env python3
"""Fix ALL JS files with broken template literals (double-quoted ${process.env...} patterns)"""
import os, sys, glob

basedir = sys.argv[1] if len(sys.argv) > 1 else "."

# Find all .js files (excluding node_modules and .bak)
js_files = []
for root, dirs, files in os.walk(basedir):
    dirs[:] = [d for d in dirs if d != 'node_modules']
    for f in files:
        if f.endswith('.js') and not f.endswith('.bak'):
            js_files.append(os.path.join(root, f))

total_fixed = 0
for filepath in js_files:
    with open(filepath) as f:
        lines = f.readlines()

    changed = False
    for i, line in enumerate(lines):
        if '${process.env.' not in line:
            continue
        if '`${process.env.' in line or '`' in line.split('${process.env.')[0].split('"')[-1:][0] if '"' in line.split('${process.env.')[0] else '':
            # Might already have backticks, skip complex cases
            pass

        # Check if there's a "${process.env." pattern (double-quoted template)
        if '"${process.env.' not in line:
            continue

        # Could have multiple ${} in one line
        # Strategy: find the opening " before each ${process.env and the matching closing "
        # Replace outermost quotes containing template expressions with backticks

        # Find all positions of "${process.env.
        result = list(line)
        positions = []
        search_from = 0
        while True:
            idx = line.find('"${process.env.', search_from)
            if idx == -1:
                break
            positions.append(idx)
            search_from = idx + 1

        if not positions:
            continue

        # For the first occurrence, find its opening " (that's positions[0])
        open_q = positions[0]

        # Find the closing " - walk from end of stripped line
        stripped = line.rstrip()
        close_q = -1
        for j in range(len(stripped) - 1, open_q, -1):
            if stripped[j] == '"':
                close_q = j
                break
            elif stripped[j] in ',;':
                continue

        if close_q == -1 or close_q <= open_q:
            continue

        result[open_q] = '`'
        result[close_q] = '`'
        new_line = ''.join(result)

        if new_line != line:
            lines[i] = new_line
            changed = True
            total_fixed += 1
            relpath = os.path.relpath(filepath, basedir)
            print(f"  {relpath}:{i+1}: {new_line.strip()}")

    if changed:
        # Backup
        bak = filepath + '.bak'
        if not os.path.exists(bak):
            with open(filepath) as f:
                orig = f.read()
            # Only backup if no .bak exists
        with open(filepath, 'w') as f:
            f.writelines(lines)

print(f"\nTotal fixed: {total_fixed} lines across all files")
