"""
Script to generate short entry conditions from long entry conditions
by inverting the trading logic.

This script reads the long entry conditions and creates inverted short conditions:
- Long conditions look for down moves (low RSI) to buy
- Short conditions look for up moves (high RSI) to sell short

Mapping:
- Long conditions: 1, 2, 3, 4, 5, 6, 21, 41, 42, 43, 44, 45, 46, 61, 62, 63, 101, 102, 103, 104, 120
- Short conditions: 901, 902, 903, 904, 905, 906, 921, 941, 942, 943, 944, 945, 946, 961, 962, 963, 9101, 9102, 9103, 9104, 9120
"""

import re

# Mapping of long to short condition indexes
CONDITION_MAPPING = {
    1: 901, 2: 902, 3: 903, 4: 904, 5: 905, 6: 906,
    21: 921,
    41: 941, 42: 942, 43: 943, 44: 944, 45: 945, 46: 946,
    61: 961, 62: 962, 63: 963,
    101: 9101, 102: 9102, 103: 9103, 104: 9104,
    120: 9120
}

# Mode name mapping
MODE_MAPPING = {
    1: "Normal", 2: "Normal", 3: "Normal", 4: "Normal", 5: "Normal", 6: "Normal",
    21: "Pump",
    41: "Quick", 42: "Quick", 43: "Quick", 44: "Quick", 45: "Quick", 46: "Quick",
    61: "Rebuy", 62: "Rebuy", 63: "Rebuy",
    101: "Rapid", 102: "Rapid", 103: "Rapid", 104: "Rapid",
    120: "Grind"
}


def invert_comparison(line):
    """
    Invert comparison operators and values for short conditions.
    
    Rules:
    1. RSI_X > Y becomes RSI_X < (100 - Y)
    2. RSI_X < Y becomes RSI_X > (100 - Y)
    3. AROONU (Aroon Up) becomes AROOND (Aroon Down)
    4. AROOND (Aroon Down) becomes AROONU (Aroon Up) 
    5. STOCHRSIk < Y becomes STOCHRSIk > (100 - Y)
    6. STOCHRSIk > Y becomes STOCHRSIk < (100 - Y)
    7. ROC < Y becomes ROC > -Y
    8. ROC > -Y becomes ROC < Y
    9. CMF > -Y becomes CMF < Y
    10. CMF < Y becomes CMF > -Y
    11. close < X becomes close > X
    12. close > X becomes close < X
    13. EMA_A > EMA_B becomes EMA_A < EMA_B
    14. change_pct < Y becomes change_pct > -Y (for positive values)
    15. change_pct > -Y becomes change_pct < Y
    16. top_wick_pct (keep similar logic but inverted context)
    """
    
    result = line
    
    # Skip comment-only lines
    if result.strip().startswith('#') and 'append(' not in result:
        # Just invert the comment text
        return invert_comment(result)
    
    # Replace AROONU with AROOND and vice versa
    result = result.replace('AROONU_', 'TEMP_AROON_UP_')
    result = result.replace('AROOND_', 'AROONU_')
    result = result.replace('TEMP_AROON_UP_', 'AROOND_')
    
    # Handle change_pct comparisons FIRST (before RSI, since some have names like RSI_3_change_pct_1h)
    def replace_change_pct(match):
        var = match.group(1)
        op = match.group(2)
        val = match.group(3)
        
        try:
            num_val = float(val)
            inverted_val = -num_val
            new_op = '<' if op == '>' else '>'
            return f'{var} {new_op} {inverted_val:.1f}'
        except:
            return match.group(0)
    
    result = re.sub(r'(df\["[\w_]*change_pct[\w_]*"\])\s*([><])\s*(-?\d+\.?\d*)', replace_change_pct, result)
    
    # Handle RSI comparisons
    # Pattern: RSI_X > Y.0 or RSI_X < Y.0
    def replace_rsi(match):
        var = match.group(1)  # RSI_3, RSI_14, etc.
        op = match.group(2)   # > or <
        val = match.group(3)  # numeric value
        
        try:
            num_val = float(val)
            inverted_val = 100.0 - num_val
            new_op = '<' if op == '>' else '>'
            return f'{var} {new_op} {inverted_val:.1f}'
        except:
            return match.group(0)
    
    result = re.sub(r'(df\["RSI_[\w_]+"\])\s*([><])\s*(-?\d+\.?\d*)', replace_rsi, result)
    
    # Handle STOCHRSIk comparisons
    def replace_stoch(match):
        var = match.group(1)
        op = match.group(2)
        val = match.group(3)
        
        try:
            num_val = float(val)
            inverted_val = 100.0 - num_val
            new_op = '<' if op == '>' else '>'
            return f'{var} {new_op} {inverted_val:.1f}'
        except:
            return match.group(0)
    
    result = re.sub(r'(df\["STOCHRSIk_[\w_]+"\])\s*([><])\s*(-?\d+\.?\d*)', replace_stoch, result)
    
    # Handle ROC comparisons (invert sign)
    def replace_roc(match):
        var = match.group(1)
        op = match.group(2)
        val = match.group(3)
        
        try:
            num_val = float(val)
            inverted_val = -num_val
            new_op = '<' if op == '>' else '>'
            return f'{var} {new_op} {inverted_val:.1f}'
        except:
            return match.group(0)
    
    result = re.sub(r'(df\["ROC_[\w_]+"\])\s*([><])\s*(-?\d+\.?\d*)', replace_roc, result)
    
    # Handle CMF comparisons (invert sign)
    def replace_cmf(match):
        var = match.group(1)
        op = match.group(2)
        val = match.group(3)
        
        try:
            num_val = float(val)
            inverted_val = -num_val
            new_op = '<' if op == '>' else '>'
            return f'{var} {new_op} {inverted_val:.1f}'
        except:
            return match.group(0)
    
    result = re.sub(r'(df\["CMF_[\w_]+"\])\s*([><])\s*(-?\d+\.?\d*)', replace_cmf, result)
    
    # Handle CCI comparisons (invert sign)
    def replace_cci(match):
        var = match.group(1)
        op = match.group(2)
        val = match.group(3)
        
        try:
            num_val = float(val)
            inverted_val = -num_val
            new_op = '<' if op == '>' else '>'
            return f'{var} {new_op} {inverted_val:.1f}'
        except:
            return match.group(0)
    
    result = re.sub(r'(df\["CCI_[\w_]+"\])\s*([><])\s*(-?\d+\.?\d*)', replace_cci, result)
    
    # Handle close comparisons with multipliers
    # close < (XXX * Y.YYY) becomes close > (XXX * Y.YYY)
    result = re.sub(r'df\["close"\]\s*<\s*\(', 'df["close"] > (', result)
    result = re.sub(r'df\["close"\]\s*>\s*\(', 'df["close"] < (', result)
    
    # Handle EMA/SMA comparisons
    # EMA_26 > EMA_12 becomes EMA_26 < EMA_12
    def replace_ema_comparison(match):
        ema1 = match.group(1)
        op = match.group(2)
        ema2 = match.group(3)
        new_op = '<' if op == '>' else '>'
        return f'{ema1} {new_op} {ema2}'
    
    result = re.sub(r'(df\["(?:EMA|SMA)_[\w_]+"\])\s*([><])\s*(df\["(?:EMA|SMA)_[\w_]+"\])', replace_ema_comparison, result)
    
    # Handle BBL/BBU references - for shorts, we look at upper band instead of lower
    result = result.replace('"BBL_20_2.0"', '"TEMP_BBL"')
    result = result.replace('"BBU_20_2.0"', '"BBL_20_2.0"')
    result = result.replace('"TEMP_BBL"', '"BBU_20_2.0"')
    
    # Handle high_max/close_max to low_min/close_min for shorts
    result = result.replace('"high_max_', '"TEMP_high_max_')
    result = result.replace('"low_min_', '"high_max_')
    result = result.replace('"TEMP_high_max_', '"low_min_')
    
    result = result.replace('"close_max_', '"TEMP_close_max_')
    result = result.replace('"close_min_', '"close_max_')
    result = result.replace('"TEMP_close_max_', '"close_min_')
    
    return result


def invert_comment(comment):
    """Invert direction words in comments."""
    comment = comment.replace(' down move', ' up move')
    comment = comment.replace(' high', ' low')
    comment = comment.replace(' low', ' high')
    comment = comment.replace(' overbought', ' oversold')
    comment = comment.replace(' oversold', ' overbought')
    comment = comment.replace(' downtrend', ' uptrend')
    comment = comment.replace(' uptrend', ' downtrend')
    comment = comment.replace('big drop', 'big pump')
    comment = comment.replace(' green', ' red')
    comment = comment.replace(' red', ' green')
    comment = comment.replace('top wick', 'bottom wick')
    comment = comment.replace('P&D', 'D&P')
    return comment


def extract_long_condition(file_path, condition_index):
    """Extract a long entry condition from the file."""
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    start_pattern = f'if long_entry_condition_index == {condition_index}:'
    
    # Find start line
    start_idx = None
    for i, line in enumerate(lines):
        if start_pattern in line:
            start_idx = i
            break
    
    if start_idx is None:
        print(f"Could not find condition {condition_index}")
        return None
    
    # Find end line (next condition or section end)
    end_idx = None
    for i in range(start_idx + 1, len(lines)):
        if 'if long_entry_condition_index ==' in lines[i]:
            end_idx = i
            break
        if '# Condition #' in lines[i] and 'if long_entry_condition_index' in lines[i]:
            end_idx = i
            break
        if 'SHORT ENTRY CONDITIONS STARTS HERE' in lines[i]:
            end_idx = i
            break
    
    if end_idx is None:
        # Look for the long entry conditions end marker
        for i in range(start_idx + 1, len(lines)):
            if '# LONG ENTRY CONDITIONS ENDS HERE' in lines[i] or \
               'for enabled_short_entry_signal in self.short_entry_signal_params:' in lines[i]:
                end_idx = i
                break
    
    if end_idx is None:
        end_idx = len(lines)
    
    return lines[start_idx:end_idx]


def generate_short_condition(long_lines, long_idx, short_idx):
    """Generate short condition from long condition."""
    if not long_lines:
        return None
    
    short_lines = []
    mode_name = MODE_MAPPING.get(long_idx, "Unknown")
    
    for line in long_lines:
        # Replace condition index reference
        if f'long_entry_condition_index == {long_idx}:' in line:
            new_line = line.replace(f'long_entry_condition_index == {long_idx}:', 
                                   f'short_entry_condition_index == {short_idx}:')
            short_lines.append(new_line)
            continue
        
        # Replace comment header
        if f'# Condition #{long_idx} -' in line:
            new_line = line.replace(f'# Condition #{long_idx} - ', 
                                   f'# Condition #{short_idx} - ')
            new_line = new_line.replace('(Long)', '(Short)')
            short_lines.append(new_line)
            continue
        
        # Replace protections
        if 'protections_long_global' in line:
            new_line = line.replace('protections_long_global', 'protections_short_global')
            new_line = new_line.replace('long_entry_logic.append', 'short_entry_logic.append')
            short_lines.append(new_line)
            # Add additional short protections
            if '== True' in new_line:
                indent = len(line) - len(line.lstrip())
                short_lines.append(' ' * indent + 'short_entry_logic.append(df["global_protections_short_pump"] == True)\n')
                short_lines.append(' ' * indent + 'short_entry_logic.append(df["global_protections_short_dump"] == True)\n')
            continue
        
        # Replace logic variable
        if 'long_entry_logic.append' in line:
            new_line = line.replace('long_entry_logic.append', 'short_entry_logic.append')
        else:
            new_line = line
        
        # Invert the actual logic in ANY line that has code (not just append lines)
        # This catches the multi-line conditions
        if '(' in new_line or 'df[' in new_line or '&' in new_line or '|' in new_line:
            # Invert comments if present
            if '# ' in new_line:
                # Extract and invert comment
                code_part = new_line[:new_line.index('#')]
                comment_part = new_line[new_line.index('#'):]
                comment_part = invert_comment(comment_part)
                new_line = code_part + comment_part
            
            # Apply the inversion transformations to the code part
            new_line = invert_comparison(new_line)
        
        short_lines.append(new_line)
    
    return short_lines


def main():
    file_path = r'c:\Users\Nhat\testbot\NostalgiaForInfinityX7.py'
    output_file = r'c:\Users\Nhat\testbot\generated_short_conditions.txt'
    
    all_short_conditions = []
    all_short_conditions.append("# Generated Short Entry Conditions\n")
    all_short_conditions.append("# Insert these before 'Condition #641 - Top Coins mode (Short).'\n\n")
    
    for long_idx, short_idx in CONDITION_MAPPING.items():
        print(f"Processing Long Condition {long_idx} -> Short Condition {short_idx}")
        
        # Extract long condition
        long_lines = extract_long_condition(file_path, long_idx)
        
        if long_lines:
            # Generate short condition
            short_lines = generate_short_condition(long_lines, long_idx, short_idx)
            
            if short_lines:
                all_short_conditions.extend(short_lines)
                all_short_conditions.append('\n')
                print(f"  ✓ Generated Short Condition {short_idx} ({len(short_lines)} lines)")
            else:
                print(f"  ✗ Failed to generate Short Condition {short_idx}")
        else:
            print(f"  ✗ Could not find Long Condition {long_idx}")
    
    # Write to output file
    with open(output_file, 'w', encoding='utf-8') as f:
        f.writelines(all_short_conditions)
    
    print(f"\n✓ All conditions generated and saved to: {output_file}")
    print(f"Total lines generated: {len(all_short_conditions)}")
    print("\nNext steps:")
    print("1. Review the generated conditions in generated_short_conditions.txt")
    print("2. Insert them into NostalgiaForInfinityX7.py before line containing 'Condition #641'")


if __name__ == '__main__':
    main()
