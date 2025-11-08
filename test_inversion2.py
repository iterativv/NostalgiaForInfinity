import re

def invert_comparison(line):
    result = line
    
    # Handle change_pct comparisons FIRST
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
    def replace_rsi(match):
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
    
    result = re.sub(r'(df\["RSI_[\w_]+"\])\s*([><])\s*(-?\d+\.?\d*)', replace_rsi, result)
    
    return result


# Test line
test_line = '          short_entry_logic.append(\n'
print(f"Input:  {test_line.strip()}")
output = invert_comparison(test_line)
print(f"Output: {output.strip()}")
print()

# Test actual logic line
test_line2 = '            ((df["RSI_3"] > 3.0) | (df["RSI_3_15m"] > 3.0) | (df["RSI_3_change_pct_1h"] > -50.0))\n'
print(f"Input:  {test_line2.strip()}")
output2 = invert_comparison(test_line2)
print(f"Output: {output2.strip()}")
