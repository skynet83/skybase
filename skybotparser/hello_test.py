"""Тестовый скрипт для проверки компиляции Nuitka."""
import sys
import os

def main():
    print(f"Hello from Nuitka compiled EXE!")
    print(f"Python: {sys.version}")
    print(f"Platform: {sys.platform}")
    print(f"Current dir: {os.getcwd()}")
    print(f"Executable: {sys.executable}")

if __name__ == "__main__":
    main()
