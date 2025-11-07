#!/usr/bin/env python3
"""
Example Test Script
Demonstrates how to use the benchmark framework programmatically
"""

from converter_benchmark import DocumentConverterBenchmark
from converter_implementations import (
    get_available_converters, 
    ConverterImplementations,
    install_instructions
)
from pathlib import Path


def example_basic_usage():
    """Example 1: Basic usage with all available converters"""
    print("\n" + "="*80)
    print("EXAMPLE 1: Basic Usage")
    print("="*80)
    
    # Get available converters
    converters = get_available_converters(test_imports=True)
    
    if not converters:
        print("No converters available. Installing dependencies...")
        install_instructions()
        return
    
    # Initialize benchmark
    benchmark = DocumentConverterBenchmark(output_dir="example_results")
    
    # Test files (replace with your actual PDFs)
    test_files = [
        "sample.pdf",
        # Add more test files here
    ]
    
    # Check if files exist
    existing_files = [f for f in test_files if Path(f).exists()]
    
    if not existing_files:
        print("⚠️  No test files found. Create or specify PDF files to test.")
        return
    
    # Run benchmark
    report = benchmark.run_benchmark_suite(
        test_files=existing_files,
        converters=converters,
        baseline_converter='tesseract'  # Use tesseract as baseline
    )
    
    # Print summary
    benchmark.print_summary()


def example_custom_converters():
    """Example 2: Test specific converters only"""
    print("\n" + "="*80)
    print("EXAMPLE 2: Custom Converter Selection")
    print("="*80)
    
    # Define which converters to test
    selected_converters = {
        'markitdown': ConverterImplementations.markitdown_converter,
        'pypdf2': ConverterImplementations.pypdf2_converter,
        'pdfplumber': ConverterImplementations.pdfplumber_converter,
    }
    
    # Initialize
    benchmark = DocumentConverterBenchmark(output_dir="custom_results")
    
    # Test file
    test_file = "test.pdf"
    
    if not Path(test_file).exists():
        print(f"⚠️  Test file not found: {test_file}")
        return
    
    # Run tests
    for name, converter in selected_converters.items():
        result = benchmark.test_converter(
            converter_func=converter,
            converter_name=name,
            file_path=test_file,
            verbose=True
        )
        
        if result.success:
            print(f"\n✅ {name} extracted {result.word_count} words in {result.execution_time:.3f}s")
        else:
            print(f"\n❌ {name} failed: {result.error_message}")


def example_compare_two_converters():
    """Example 3: Direct comparison between two converters"""
    print("\n" + "="*80)
    print("EXAMPLE 3: Direct Converter Comparison")
    print("="*80)
    
    benchmark = DocumentConverterBenchmark(output_dir="comparison_results")
    
    test_file = "document.pdf"
    
    if not Path(test_file).exists():
        print(f"⚠️  Test file not found: {test_file}")
        return
    
    # Test two converters
    result1 = benchmark.test_converter(
        ConverterImplementations.markitdown_converter,
        "markitdown",
        test_file
    )
    
    result2 = benchmark.test_converter(
        ConverterImplementations.pypdf2_converter,
        "pypdf2",
        test_file
    )
    
    # Compare results
    if result1.success and result2.success:
        metrics = benchmark._compare_texts(result1.text_content, result2.text_content)
        
        print(f"\n📊 Comparison Results:")
        print(f"   Similarity: {metrics.similarity_ratio:.2%}")
        print(f"   Speed: markitdown {result1.execution_time:.3f}s vs pypdf2 {result2.execution_time:.3f}s")
        print(f"   Speed ratio: {result2.execution_time / result1.execution_time:.2f}x")
        print(f"   Word difference: {metrics.word_difference}")
        print(f"   Common words: {metrics.common_words}")


def example_ocr_comparison():
    """Example 4: Compare OCR vs native extraction"""
    print("\n" + "="*80)
    print("EXAMPLE 4: OCR vs Native Extraction")
    print("="*80)
    
    benchmark = DocumentConverterBenchmark(output_dir="ocr_comparison")
    
    test_file = "sample.pdf"
    
    if not Path(test_file).exists():
        print(f"⚠️  Test file not found: {test_file}")
        return
    
    # Test native extraction (fast)
    native_converters = {
        'markitdown': ConverterImplementations.markitdown_converter,
        'pypdf2': ConverterImplementations.pypdf2_converter,
    }
    
    # Test OCR (slower but works on scanned docs)
    try:
        import pytesseract
        ocr_result = benchmark.test_converter(
            ConverterImplementations.tesseract_converter,
            "tesseract_ocr",
            test_file,
            dpi=300
        )
    except ImportError:
        print("⚠️  Tesseract not available for OCR comparison")
        ocr_result = None
    
    # Test native
    for name, converter in native_converters.items():
        native_result = benchmark.test_converter(
            converter,
            name,
            test_file
        )
        
        # Compare with OCR if available
        if ocr_result and ocr_result.success and native_result.success:
            metrics = benchmark._compare_texts(ocr_result.text_content, 
                                              native_result.text_content)
            
            print(f"\n{name} vs OCR:")
            print(f"  Similarity: {metrics.similarity_ratio:.2%}")
            print(f"  Speed advantage: {ocr_result.execution_time / native_result.execution_time:.1f}x faster")


def example_batch_processing():
    """Example 5: Batch process multiple files"""
    print("\n" + "="*80)
    print("EXAMPLE 5: Batch Processing")
    print("="*80)
    
    # Find all PDFs in current directory
    pdf_files = list(Path(".").glob("*.pdf"))
    
    if not pdf_files:
        print("⚠️  No PDF files found in current directory")
        return
    
    print(f"Found {len(pdf_files)} PDF files")
    
    # Use fastest converters for batch processing
    fast_converters = {
        'pymupdf': ConverterImplementations.pymupdf_converter,
        'pypdf2': ConverterImplementations.pypdf2_converter,
    }
    
    # Get only available ones
    available_converters = {}
    for name, func in fast_converters.items():
        try:
            if name == 'pymupdf':
                import fitz
            elif name == 'pypdf2':
                import PyPDF2
            available_converters[name] = func
        except ImportError:
            pass
    
    if not available_converters:
        print("⚠️  No fast converters available")
        return
    
    benchmark = DocumentConverterBenchmark(output_dir="batch_results")
    
    # Process all files
    report = benchmark.run_benchmark_suite(
        test_files=[str(f) for f in pdf_files[:5]],  # Limit to 5 for demo
        converters=available_converters
    )
    
    benchmark.print_summary()


def example_with_tables():
    """Example 6: Extract tables from PDFs"""
    print("\n" + "="*80)
    print("EXAMPLE 6: Table Extraction")
    print("="*80)
    
    try:
        import pdfplumber
    except ImportError:
        print("⚠️  pdfplumber required for table extraction")
        print("   Install: pip install pdfplumber")
        return
    
    benchmark = DocumentConverterBenchmark(output_dir="table_results")
    
    test_file = "document_with_tables.pdf"
    
    if not Path(test_file).exists():
        print(f"⚠️  Test file not found: {test_file}")
        print("   This example requires a PDF with tables")
        return
    
    # Test with table extraction enabled
    result = benchmark.test_converter(
        ConverterImplementations.pdfplumber_converter,
        "pdfplumber_with_tables",
        test_file,
        extract_tables=True
    )
    
    if result.success and result.metadata:
        print(f"\n📊 Extracted {result.metadata.get('table_count', 0)} tables")
        print(f"   Total text length: {result.char_count} characters")


def main():
    """Run all examples"""
    print("\n" + "#"*80)
    print("# DOCUMENT CONVERTER BENCHMARK - EXAMPLES")
    print("#"*80)
    
    # Check what's available
    print("\nChecking available converters...")
    available = get_available_converters(test_imports=True)
    print(f"\n{len(available)} converters available\n")
    
    if len(available) == 0:
        print("⚠️  No converters installed!")
        install_instructions()
        return
    
    # Run examples (comment out ones you don't want to run)
    
    # example_basic_usage()
    # example_custom_converters()
    # example_compare_two_converters()
    # example_ocr_comparison()
    # example_batch_processing()
    # example_with_tables()
    
    print("\n" + "="*80)
    print("Examples complete!")
    print("Uncomment the examples you want to run in example_usage.py")
    print("="*80)


if __name__ == "__main__":
    main()
