#!/usr/bin/env python3
"""Test script for sandbox validation"""

def greet(name):
    return f"Hello, {name}!"

if __name__ == "__main__":
    print(greet("Sandbox User"))
    print("Python version test successful")
    import sys
    print(f"Python executable: {sys.executable}")
    print(f"System platform: {sys.platform}")
    print("Sandbox bash tool working correctly!")
