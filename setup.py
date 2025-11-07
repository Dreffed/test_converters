#!/usr/bin/env python3
"""
Setup Helper Script
Helps install and verify converter dependencies
"""

import subprocess
import sys
import os
from pathlib import Path


def check_python_version():
    """Check if Python version is compatible"""
    version = sys.version_info
    if version < (3, 8):
        print("❌ Python 3.8 or higher required")
        print(f"   Current version: {version.major}.{version.minor}.{version.micro}")
        return False
    print(f"✅ Python version: {version.major}.{version.minor}.{version.micro}")
    return True


def check_system_command(command, name):
    """Check if a system command is available"""
    try:
        result = subprocess.run(
            [command, "--version"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            print(f"✅ {name} is installed")
            return True
        else:
            print(f"❌ {name} is not installed")
            return False
    except (subprocess.TimeoutExpired, FileNotFoundError):
        print(f"❌ {name} is not installed")
        return False


def install_package(package, display_name=None):
    """Install a Python package via pip"""
    if display_name is None:
        display_name = package
    
    print(f"\n📦 Installing {display_name}...")
    
    try:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", package],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE
        )
        print(f"✅ {display_name} installed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to install {display_name}")
        print(f"   Error: {e.stderr.decode() if e.stderr else 'Unknown error'}")
        return False


def install_core_converters():
    """Install core converter packages"""
    print("\n" + "="*80)
    print("INSTALLING CORE CONVERTERS")
    print("="*80)
    
    packages = [
        ("markitdown[all]", "MarkItDown"),
        ("PyPDF2", "PyPDF2"),
        ("pdfplumber", "pdfplumber"),
        ("pymupdf", "PyMuPDF"),
        ("pdfminer.six", "pdfminer.six"),
    ]
    
    success_count = 0
    for package, name in packages:
        if install_package(package, name):
            success_count += 1
    
    print(f"\n📊 Installed {success_count}/{len(packages)} core converters")
    return success_count


def install_ocr_support():
    """Install OCR-related packages"""
    print("\n" + "="*80)
    print("INSTALLING OCR SUPPORT")
    print("="*80)
    
    # Check for tesseract
    has_tesseract = check_system_command("tesseract", "Tesseract OCR")
    
    if not has_tesseract:
        print("\n⚠️  Tesseract OCR not found!")
        print("\nInstall instructions:")
        print("  Ubuntu/Debian: sudo apt-get install tesseract-ocr poppler-utils")
        print("  macOS:         brew install tesseract poppler")
        print("  Windows:       Download from https://github.com/UB-Mannheim/tesseract/wiki")
        return False
    
    # Install Python bindings
    packages = [
        ("pytesseract", "pytesseract"),
        ("pdf2image", "pdf2image"),
        ("Pillow", "Pillow"),
    ]
    
    success_count = 0
    for package, name in packages:
        if install_package(package, name):
            success_count += 1
    
    print(f"\n📊 Installed {success_count}/{len(packages)} OCR packages")
    return success_count == len(packages)


def install_advanced_converters():
    """Install advanced converter packages"""
    print("\n" + "="*80)
    print("INSTALLING ADVANCED CONVERTERS")
    print("="*80)
    
    # Check for Java (needed for Tika)
    has_java = check_system_command("java", "Java")
    
    packages = []
    
    if has_java:
        packages.append(("tika", "Apache Tika"))
    else:
        print("\n⚠️  Java not found! Apache Tika will not be installed")
        print("  Ubuntu/Debian: sudo apt-get install default-jre")
        print("  macOS:         brew install openjdk")
    
    # Check for Pandoc
    has_pandoc = check_system_command("pandoc", "Pandoc")
    
    if has_pandoc:
        packages.append(("pypandoc", "pypandoc"))
    else:
        print("\n⚠️  Pandoc not found! pypandoc will not be installed")
        print("  Ubuntu/Debian: sudo apt-get install pandoc")
        print("  macOS:         brew install pandoc")
    
    # Optional packages (may have complex dependencies)
    packages.extend([
        ("textract", "textract"),
    ])
    
    success_count = 0
    for package, name in packages:
        if install_package(package, name):
            success_count += 1
    
    print(f"\n📊 Installed {success_count}/{len(packages)} advanced converters")
    return success_count


def verify_installation():
    """Verify what's installed"""
    print("\n" + "="*80)
    print("VERIFYING INSTALLATION")
    print("="*80)
    
    # Import the checker
    try:
        from converter_implementations import get_available_converters
        
        print("\n🔍 Checking available converters...\n")
        available = get_available_converters(test_imports=True)
        
        print(f"\n✅ {len(available)} converters available and ready to use!")
        
        if len(available) == 0:
            print("\n⚠️  No converters available. Please install dependencies.")
            return False
        
        return True
        
    except ImportError as e:
        print(f"❌ Error importing verification module: {e}")
        return False


def create_test_files():
    """Create sample test files"""
    print("\n" + "="*80)
    print("CREATING TEST FILES")
    print("="*80)
    
    # Check if we have test PDFs
    pdf_files = list(Path(".").glob("*.pdf"))
    
    if pdf_files:
        print(f"✅ Found {len(pdf_files)} PDF files for testing")
        return True
    else:
        print("⚠️  No PDF files found for testing")
        print("\nTo test the benchmark suite:")
        print("  1. Place PDF files in the current directory, OR")
        print("  2. Specify file paths when running: python run_benchmark.py path/to/file.pdf")
        return False


def main():
    """Main setup function"""
    print("\n" + "#"*80)
    print("# DOCUMENT CONVERTER BENCHMARK - SETUP")
    print("#"*80)
    
    # Check Python version
    if not check_python_version():
        sys.exit(1)
    
    print("\nSetup Options:")
    print("  1. Install core converters (recommended)")
    print("  2. Install core + OCR support")
    print("  3. Install everything (requires system dependencies)")
    print("  4. Verify current installation")
    print("  5. Exit")
    
    try:
        choice = input("\nSelect option (1-5): ").strip()
    except (KeyboardInterrupt, EOFError):
        print("\n\nSetup cancelled.")
        return
    
    if choice == "1":
        install_core_converters()
        verify_installation()
    
    elif choice == "2":
        install_core_converters()
        install_ocr_support()
        verify_installation()
    
    elif choice == "3":
        install_core_converters()
        install_ocr_support()
        install_advanced_converters()
        verify_installation()
    
    elif choice == "4":
        verify_installation()
    
    elif choice == "5":
        print("Setup cancelled.")
        return
    
    else:
        print("Invalid option selected.")
        return
    
    # Check for test files
    create_test_files()
    
    print("\n" + "="*80)
    print("SETUP COMPLETE")
    print("="*80)
    print("\nNext steps:")
    print("  1. Place PDF files in the current directory")
    print("  2. Run: python run_benchmark.py --list-converters")
    print("  3. Run: python run_benchmark.py your_file.pdf")
    print("\nFor help: python run_benchmark.py --help")
    print("="*80)


if __name__ == "__main__":
    main()
