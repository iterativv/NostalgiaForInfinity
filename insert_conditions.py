#!/usr/bin/env python3
"""
Script to insert generated short conditions into NostalgiaForInfinityX7.py
"""

# Read the generated conditions (skip header lines 1-2)
print("Reading generated conditions...")
with open('generated_short_conditions.txt', 'r', encoding='utf-8') as f:
    lines = f.readlines()
    # Skip first 3 lines (header comment lines 1-2 and blank line 3)
    generated_content = ''.join(lines[3:])

print(f"  Loaded {len(lines)-3} lines of generated content")

# Read the main file
print("Reading main file...")
with open('NostalgiaForInfinityX7.py', 'r', encoding='utf-8') as f:
    main_lines = f.readlines()

print(f"  Main file has {len(main_lines)} lines")

# Find the insertion point - look for the line with "# Condition #641"
insertion_index = None
for i, line in enumerate(main_lines):
    if '# Condition #641 - Top Coins mode (Short).' in line:
        insertion_index = i
        print(f"  Found insertion point at line {i+1}")
        break

if insertion_index is None:
    print("ERROR: Could not find '# Condition #641 - Top Coins mode (Short).' in file")
    exit(1)

# Check if conditions are already inserted by looking for 901 before the insertion point
already_inserted = False
for i in range(max(0, insertion_index-100), insertion_index):
    if 'short_entry_condition_index == 901' in main_lines[i]:
        already_inserted = True
        print(f"  Found condition 901 already at line {i+1}")
        # Find where to insert remaining conditions
        for j in range(i, insertion_index):
            if '# Condition #3 - Normal mode (Long)' in main_lines[j]:
                # This is the end of condition 902, insert after this
                # Find the actual end of condition 902
                for k in range(j, insertion_index):
                    if 'if short_entry_condition_index ==' in main_lines[k] and k > j:
                        insertion_index = k
                        print(f"  Will insert remaining conditions at line {k+1}")
                        break
                break
        break

if already_inserted:
    print("  Conditions 901-902 already inserted, will insert 903 onwards")
    # Extract only conditions 903 onwards from generated content
    generated_lines = generated_content.split('\n')
    start_idx = None
    for idx, line in enumerate(generated_lines):
        if 'short_entry_condition_index == 903' in line:
            start_idx = idx - 1  # Include the comment line before it
            print(f"  Found condition 903 at line {idx} in generated file")
            break
    
    if start_idx is not None:
        generated_content = '\n'.join(generated_lines[start_idx:])
        print(f"  Extracted {len(generated_lines) - start_idx} lines for conditions 903-9120")
    else:
        print("ERROR: Could not find condition 903 in generated file")
        exit(1)

# Insert the generated content
print(f"Inserting at line {insertion_index + 1}...")
new_lines = main_lines[:insertion_index] + [generated_content + '\n'] + main_lines[insertion_index:]

# Write back
print("Writing modified file...")
with open('NostalgiaForInfinityX7.py', 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print(f"✓ Successfully inserted conditions")
print(f"  File now has {len(new_lines)} lines total")
print(f"  Added {len(new_lines) - len(main_lines)} lines")
