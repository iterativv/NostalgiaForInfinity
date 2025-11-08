"""
Generate short conditions 9141-9145, 9161-9163 from long conditions 141-145, 161-163
"""

import re

# Read the main strategy file
with open("NostalgiaForInfinityX7.py", "r", encoding="utf-8") as f:
    content = f.read()

# Mapping for the new conditions
MAPPINGS = {
    141: 9141,
    142: 9142,
    143: 9143,
    144: 9144,
    145: 9145,
    161: 9161,
    162: 9162,
    163: 9163,
}

MODE_MAP = {
    141: "Top Coins",
    142: "Top Coins",
    143: "Top Coins",
    144: "Top Coins",
    145: "Top Coins",
    161: "Scalp",
    162: "Scalp",
    163: "Scalp",
}


def invert_rsi(match):
    """Invert RSI comparisons: < becomes >, > becomes <, and value inverts to 100-value"""
    rsi_var = match.group(1)
    operator = match.group(2)
    value = float(match.group(3))
    
    new_op = "<" if operator == ">" else ">"
    new_value = 100 - value
    
    return f"{rsi_var} {new_op} {new_value}"


def invert_aroon(text):
    """Swap AROONU <-> AROOND"""
    # Swap AROONU and AROOND
    text = text.replace("AROONU_", "TEMP_AROON_")
    text = text.replace("AROOND_", "AROONU_")
    text = text.replace("TEMP_AROON_", "AROOND_")
    return text


def invert_stochrsi(match):
    """Invert StochRSI comparisons"""
    stoch_var = match.group(1)
    operator = match.group(2)
    value = float(match.group(3))
    
    new_op = "<" if operator == ">" else ">"
    new_value = 100 - value
    
    return f"{stoch_var} {new_op} {new_value}"


def invert_roc(match):
    """Invert ROC comparisons"""
    roc_var = match.group(1)
    operator = match.group(2)
    value = float(match.group(3))
    
    new_op = "<" if operator == ">" else ">"
    new_value = -value
    
    return f"{roc_var} {new_op} {new_value}"


def invert_cmf(match):
    """Invert CMF comparisons"""
    cmf_var = match.group(1)
    operator = match.group(2)
    value = float(match.group(3))
    
    new_op = "<" if operator == ">" else ">"
    new_value = -value
    
    return f"{cmf_var} {new_op} {new_value}"


def invert_price_comparisons(text):
    """Invert price-based comparisons (close < becomes close >, etc)"""
    # close < X becomes close > X
    text = re.sub(r'\(df\["close"\]\s*<\s*', '(df["close"] > ', text)
    text = re.sub(r'\(df\["close"\]\.([a-z_]+)\s*<\s*', r'(df["close"].\1 > ', text)
    
    # EMA comparisons
    text = re.sub(r'\(df\["EMA_(\d+)"\]\s*>\s*df\["EMA_(\d+)"\]\)', r'(df["EMA_\1"] < df["EMA_\2"])', text)
    
    # SMA comparisons
    text = re.sub(r'\(df\["SMA_(\d+)"\]\s*<\s*df\["SMA_(\d+)"\]', r'(df["SMA_\1"] > df["SMA_\2"]', text)
    text = re.sub(r'\(df\["SMA_(\d+)"\]\.shift\(\d+\)\s*<\s*df\["SMA_(\d+)"\]\.shift', r'(df["SMA_\1"].shift(1) > df["SMA_\2"].shift', text)
    
    # close > EMA_200 becomes close < EMA_200
    text = re.sub(r'\(df\["close"\]\s*>\s*df\["EMA_200', '(df["close"] < df["EMA_200', text)
    
    return text


def invert_bbb_mfi_willr(text):
    """Invert BBB, MFI, WILLR comparisons"""
    # BBB > X becomes BBB < X (Bollinger Bands Width)
    text = re.sub(r'\(df\["BBB_([^"]+)"\]\s*>\s*([0-9.]+)\)', r'(df["BBB_\1"] < \2)', text)
    
    # MFI < X becomes MFI > X (Money Flow Index)
    text = re.sub(r'\(df\["MFI_([^"]+)"\]\s*<\s*([0-9.]+)\)', r'(df["MFI_\1"] > \2)', text)
    
    # WILLR < -X becomes WILLR > -X (Williams %R)
    text = re.sub(r'\(df\["WILLR_(\d+)"\]\s*<\s*(-[0-9.]+)\)', r'(df["WILLR_\1"] > \2)', text)
    
    return text


def invert_change_pct(text):
    """Invert change_pct and related percentage comparisons"""
    # change_pct > -X becomes change_pct < X
    text = re.sub(r'\(df\["change_pct(_[^"]+)?"\]\s*>\s*(-[0-9.]+)\)', r'(df["change_pct\1"] < \2)', text)
    # change_pct < X becomes change_pct > -X
    text = re.sub(r'\(df\["change_pct(_[^"]+)?"\]\s*<\s*([0-9.]+)\)', r'(df["change_pct\1"] > -\2)', text)
    
    # change_pct.shift > X becomes change_pct.shift < -X
    text = re.sub(r'\(df\["change_pct(_[^"]+)?"\]\.shift\((\d+)\)\s*<\s*([0-9.]+)\)', r'(df["change_pct\1"].shift(\2) > -\3)', text)
    
    # top_wick_pct < X becomes top_wick_pct > X
    text = re.sub(r'\(df\["top_wick_pct(_[^"]+)?"\]\s*<\s*([0-9.]+)\)', r'(df["top_wick_pct\1"] > \2)', text)
    
    return text


def invert_max_min(text):
    """Invert close_max and close_min comparisons"""
    # close_max_X >= (close * Y) becomes close_min_X <= (close * (2 - Y))
    text = re.sub(
        r'\(df\["close_max_(\d+)(_\w+)?"\]\s*>=\s*\(df\["close"\]\s*\*\s*([0-9.]+)\)\)',
        r'(df["close_min_\1\2"] <= (df["close"] * (2.0 - \3)))',
        text
    )
    
    # close < (close_min_X * Y) becomes close > (close_max_X * (2 - Y))
    text = re.sub(
        r'\(df\["close"\]\s*<\s*\(df\["close_min_(\d+)(_\w+)?"\]\s*\*\s*([0-9.]+)\)\)',
        r'(df["close"] > (df["close_max_\1\2"] * (2.0 - \3)))',
        text
    )
    
    # close > (high_max_X * Y) becomes close < (low_min_X * (2 - Y))
    text = re.sub(
        r'\(df\["close"\]\s*>\s*\(df\["high_max_(\d+)(_\w+)?"\]\s*\*\s*([0-9.]+)\)\)',
        r'(df["close"] < (df["low_min_\1\2"] * (2.0 - \3)))',
        text
    )
    
    return text


def invert_bbd_bbt(text):
    """Invert BBD (Bollinger Band Delta) and BBT (Bollinger Band Top) comparisons"""
    # BBD.gt(close * X) becomes BBD.lt(close * X)
    text = re.sub(r'\.gt\(df\["close"\]\s*\*\s*([0-9.]+)\)', r'.lt(df["close"] * \1)', text)
    
    # BBT.lt(BBD * X) becomes BBT.gt(BBD * X)
    text = re.sub(r'\.lt\(df\["BBD_([^"]+)"\]\s*\*\s*([0-9.]+)\)', r'.gt(df["BBD_\1"] * \2)', text)
    
    # close.lt(BBL.shift()) becomes close.gt(BBU.shift())
    text = re.sub(r'\.lt\(df\["BBL_([^"]+)"\]\.shift\(\)\)', r'.gt(df["BBU_\1"].shift())', text)
    
    # close.le(close.shift()) becomes close.ge(close.shift())
    text = re.sub(r'\.le\(df\["close"\]\.shift\(\)\)', r'.ge(df["close"].shift())', text)
    
    return text


def invert_cci_change(text):
    """Invert CCI_change_pct comparisons"""
    # CCI_change_pct > -X becomes CCI_change_pct < X
    text = re.sub(r'\(df\["CCI_(\d+)_change_pct(_\w+)?"\]\s*>\s*(-[0-9.]+)\)', r'(df["CCI_\1_change_pct\2"] < \3)', text)
    
    return text


def invert_logic_condition(condition_text):
    """Invert a complete condition block"""
    # First handle RSI inversions
    condition_text = re.sub(
        r'(df\["RSI_\d+(?:_\d+[mhd])?"?\])\s*([<>])\s*([0-9.]+)',
        invert_rsi,
        condition_text
    )
    
    # Handle AROON swaps
    condition_text = invert_aroon(condition_text)
    
    # Handle StochRSI inversions
    condition_text = re.sub(
        r'(df\["STOCHRSIk_[^"]+"\])\s*([<>])\s*([0-9.]+)',
        invert_stochrsi,
        condition_text
    )
    
    # Handle ROC inversions
    condition_text = re.sub(
        r'(df\["ROC_\d+(?:_\d+[mhd])?"?\])\s*([<>])\s*(-?[0-9.]+)',
        invert_roc,
        condition_text
    )
    
    # Handle CMF inversions
    condition_text = re.sub(
        r'(df\["CMF_\d+(?:_\d+[mhd])?"?\])\s*([<>])\s*(-?[0-9.]+)',
        invert_cmf,
        condition_text
    )
    
    # Handle price comparisons
    condition_text = invert_price_comparisons(condition_text)
    
    # Handle BBB, MFI, WILLR
    condition_text = invert_bbb_mfi_willr(condition_text)
    
    # Handle change_pct
    condition_text = invert_change_pct(condition_text)
    
    # Handle max/min
    condition_text = invert_max_min(condition_text)
    
    # Handle BBD/BBT
    condition_text = invert_bbd_bbt(condition_text)
    
    # Handle CCI change
    condition_text = invert_cci_change(condition_text)
    
    # Replace protections
    condition_text = condition_text.replace('protections_long_global', 'protections_short_global')
    condition_text = condition_text.replace('is_pair_long_top_coins_mode', 'is_pair_short_top_coins_mode')
    
    # Replace entry logic variable
    condition_text = condition_text.replace('long_entry_logic', 'short_entry_logic')
    
    return condition_text


def extract_and_invert_condition(long_index):
    """Extract a long condition and invert it to create a short condition"""
    short_index = MAPPINGS[long_index]
    mode = MODE_MAP[long_index]
    
    # Find the condition in the file
    pattern = rf'# Condition #{long_index} -.*?\n.*?if long_entry_condition_index == {long_index}:.*?(?=\n        # Condition #|\n        return long_entry_logic)'
    match = re.search(pattern, content, re.DOTALL)
    
    if not match:
        print(f"Could not find condition {long_index}")
        return None
    
    condition_block = match.group(0)
    
    # Invert the condition
    inverted = invert_logic_condition(condition_block)
    
    # Replace index numbers
    inverted = inverted.replace(f'long_entry_condition_index == {long_index}', f'short_entry_condition_index == {short_index}')
    inverted = inverted.replace(f'# Condition #{long_index}', f'# Condition #{short_index}')
    inverted = inverted.replace('(Long)', '(Short)')
    
    return inverted


# Generate all conditions
output = []
for long_idx in sorted(MAPPINGS.keys()):
    print(f"Generating short condition {MAPPINGS[long_idx]} from long condition {long_idx}...")
    inverted = extract_and_invert_condition(long_idx)
    if inverted:
        output.append(inverted)
        output.append("\n")

# Write to file
with open("generated_new_short_conditions.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(output))

print(f"\nGenerated {len(output) // 2} short conditions")
print("Output written to: generated_new_short_conditions.txt")
