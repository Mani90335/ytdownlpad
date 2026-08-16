#!/bin/bash
# Move to the directory where this script is located
cd "$(dirname "$0")"

echo "========================================"
echo " Starting Python Server..."
echo "========================================"
echo ""

# Run the python server
python3 server.py

# Keep the terminal window open if the server crashes or exits
echo ""
echo "========================================"
echo "Process completed. Press Enter to exit."
echo "========================================"
read
