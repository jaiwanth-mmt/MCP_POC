#!/usr/bin/env python3
"""MCP Cab Server Entry Point"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src', 'cabs-mcp-server'))

def main():
    print("Starting MCP Cab Server...")
    print("-" * 60)

    from server import mcp
    mcp.run()


if __name__ == "__main__":
    main()
