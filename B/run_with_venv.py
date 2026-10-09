#!/usr/bin/env python3
# run_with_venv.py - Script to run main.py with virtual environment

import os
import sys

# Get the absolute path to the current directory
base_dir = os.path.dirname(os.path.abspath(__file__))

# Path to activate_this.py in the virtual environment
activate_script = os.path.join(base_dir, '.venv', 'Scripts', 'activate_this.py')

# Check if the activate script exists
if not os.path.exists(activate_script):
    print(f"Error: Virtual environment activation script not found at {activate_script}")
    sys.exit(1)

# Execute the activation script
try:
    exec(open(activate_script, encoding='utf-8').read(), {'__file__': activate_script})
except Exception as e:
    print(f"Error activating virtual environment: {e}")
    sys.exit(1)

# Now run the main.py script
main_script = os.path.join(base_dir, 'main.py')
if not os.path.exists(main_script):
    print(f"Error: Main script not found at {main_script}")
    sys.exit(1)

# Pass command line arguments to main script
import argparse

# Execute the main script
try:
    exec(open(main_script, encoding='utf-8').read())
except Exception as e:
    print(f"Error running main script: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)