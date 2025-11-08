import re

line = '            ((df["RSI_3"] > 3.0) | (df["RSI_3_15m"] > 3.0) | (df["RSI_3_change_pct_1h"] > -50.0))'

def replace_rsi(match):
    var = match.group(1)  # RSI_3, RSI_14, etc.
    op = match.group(2)   # > or <
    val = match.group(3)  # numeric value
    
    print(f"Match found: var={var}, op={op}, val={val}")
    
    try:
        num_val = float(val)
        inverted_val = 100.0 - num_val
        new_op = '<' if op == '>' else '>'
        result = f'{var} {new_op} {inverted_val:.1f}'
        print(f"Returning: {result}")
        return result
    except Exception as e:
        print(f"Error: {e}")
        return match.group(0)

result = re.sub(r'(df\["RSI_[\w_]+"\])\s*([><])\s*(-?\d+\.?\d*)', replace_rsi, line)
print(f"\nOriginal: {line}")
print(f"Result:   {result}")
