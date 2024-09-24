#!/bin/bash

# Check if an argument is provided
if [ "$#" -ne 1 ]; then
    echo "Usage: $0 <input_file.py>"
    exit 1
fi

# Input Python file (first argument)
input_file="$1"

# Extract base name without extension
base_name=$(basename "$input_file" .py)

# Define output file names for Short and Long Entry conditions
short_entry_conditions_output_file="${base_name}-Short-Entry-Conditions.py"
long_entry_conditions_output_file="${base_name}-Long-Entry-Conditions.py"

# Define output file names for Short and Long Exit conditions
short_exit_conditions_output_file="${base_name}-Short-Exit-Conditions.py"
long_exit_conditions_output_file="${base_name}-Long-Exit-Conditions.py"

# Extract the Short Entry Conditions block
sed -n '/# SHORT ENTRY CONDITIONS STARTS HERE/,/# SHORT ENTRY CONDITIONS ENDS HERE/p' "$input_file" > "$short_entry_conditions_output_file"

# Extract the Long Entry Conditions block
sed -n '/# LONG ENTRY CONDITIONS STARTS HERE/,/# LONG ENTRY CONDITIONS ENDS HERE/p' "$input_file" > "$long_entry_conditions_output_file"


# Extract the Short Exit Conditions block
sed -n '/# SHORT EXIT FUNCTIONS STARTS HERE/,/# SHORT GRIND FUNCTIONS ENDS HERE/p' "$input_file" > "$short_exit_conditions_output_file"

# Extract the Long Exit Conditions block
sed -n '/# LONG EXIT FUNCTIONS STARTS HERE/,/# LONG GRIND FUNCTIONS ENDS HERE/p' "$input_file" > "$long_exit_conditions_output_file"


# Inform the user
echo "Short Entry Conditions block has been saved to $short_entry_conditions_output_file."
echo "Long Entry Conditions block has been saved to $long_entry_conditions_output_file."


# Inform the user
echo "Short Exit Conditions block has been saved to $short_exit_conditions_output_file."
echo "Long Exit Conditions block has been saved to $long_exit_conditions_output_file."
