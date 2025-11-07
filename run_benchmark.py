#!/usr/bin/env python3
"""
Main Benchmark Runner
Easy-to-use script for running document converter benchmarks
"""

import sys
import argparse
import glob
from pathlib import Path
from converter_benchmark import DocumentConverterBenchmark
from converter_implementations import get_available_converters, install_instructions


def main():
    parser = argparse.ArgumentParser(
        description='Benchmark document converters for speed and accuracy',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Test all available converters on a single PDF
  python run_benchmark.py test.pdf
  
  # Test specific converters
  python run_benchmark.py test.pdf --converters markitdown pypdf2 tesseract
  
  # Test multiple files
  python run_benchmark.py file1.pdf file2.pdf file3.pdf
  
  # Use tesseract as baseline for comparison
  python run_benchmark.py test.pdf --baseline tesseract
  
  # Test all PDFs in a directory
  python run_benchmark.py documents/*.pdf
  
  # Show available converters
  python run_benchmark.py --list-converters
  
  # Show installation instructions
  python run_benchmark.py --install-help
        """
    )
    
    parser.add_argument(
        'files',
        nargs='*',
        help='PDF files to test'
    )
    
    parser.add_argument(
        '--converters',
        nargs='+',
        help='Specific converters to test (default: all available)'
    )
    
    parser.add_argument(
        '--baseline',
        default='tesseract',
        help='Converter to use as accuracy baseline (default: tesseract)'
    )
    
    parser.add_argument(
        '--output-dir',
        default='benchmark_results',
        help='Directory for output files (default: benchmark_results)'
    )
    
    parser.add_argument(
        '--list-converters',
        action='store_true',
        help='List all available converters and exit'
    )
    
    parser.add_argument(
        '--install-help',
        action='store_true',
        help='Show installation instructions and exit'
    )
    
    parser.add_argument(
        '--extract-tables',
        action='store_true',
        help='Extract tables from PDFs (where supported)'
    )
    
    parser.add_argument(
        '--tesseract-dpi',
        type=int,
        default=300,
        help='DPI for Tesseract OCR (default: 300)'
    )
    
    parser.add_argument(
        '--poppler-path',
        default=None,
        help='Path to Poppler bin directory (Windows) for pdf2image'
    )
    
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Verbose output with detailed errors'
    )
    parser.add_argument(
        '--textract-url',
        default=None,
        help='URL for textract_http sidecar (POST /extract)'
    )

    # Visualization flags
    parser.add_argument(
        '--visualize-blocks',
        action='store_true',
        help='Render page images with block overlays and compute coverage metrics'
    )
    parser.add_argument(
        '--viz-output-dir',
        default=None,
        help='Output directory for visual artifacts (default: <output-dir>/visual)'
    )
    parser.add_argument(
        '--viz-dpi',
        type=int,
        default=200,
        help='DPI to render page images for visualization (default: 200)'
    )
    parser.add_argument(
        '--viz-iou-thr',
        type=float,
        default=0.5,
        help='IoU threshold for block coverage matching (default: 0.5)'
    )
    parser.add_argument(
        '--viz-match',
        choices=['greedy', 'bipartite'],
        default='bipartite',
        help='Matching strategy for coverage (default: bipartite)'
    )
    parser.add_argument(
        '--viz-export-blocks',
        action='store_true',
        help='Export canonical union blocks JSON per document for future UI'
    )
    parser.add_argument(
        '--viz-renderer',
        choices=['auto', 'pymupdf', 'pdf2image'],
        default='auto',
        help='Renderer to use for visual page images (default: auto)'
    )
    
    args = parser.parse_args()
    
    # Handle special flags
    if args.install_help:
        install_instructions()
        return 0
    
    if args.list_converters:
        print("\nAvailable Converters:")
        print("=" * 60)
        available = get_available_converters(test_imports=True)
        
        if not available:
            print("\n??  No converters available!")
            print("\nRun with --install-help for installation instructions")
        
        return 0
    
    # Validate input files
    if not args.files:
        parser.print_help()
        print("\n??  Error: No files specified!")
        return 1
    
    # Expand and validate files (supports globs like documents/*.pdf)
    test_files = []
    seen = set()
    for file_pattern in args.files:
        matches = glob.glob(file_pattern, recursive=True)
        if matches:
            for match in matches:
                p = Path(match)
                if p.is_file():
                    sp = str(p)
                    if sp not in seen:
                        seen.add(sp)
                        test_files.append(sp)
            continue
        file_path = Path(file_pattern)
        if file_path.exists():
            test_files.append(str(file_path))
        else:
            print(f"??  Warning: No files matched: {file_pattern}")
    
    if args.verbose and test_files:
        print("\nResolved input files:")
        for f in test_files:
            print(f" - {f}")

    if not test_files:
        print("? Error: No valid files found!")
        return 1
    
    # Get available converters
    print("\nChecking available converters...")
    print("-" * 60)
    available_converters = get_available_converters(test_imports=True)
    
    if not available_converters:
        print("\n? Error: No converters available!")
        print("\nRun with --install-help for installation instructions")
        return 1
    
    # Filter converters if specified
    if args.converters:
        converters_to_test = {}
        for name in args.converters:
            if name in available_converters:
                converters_to_test[name] = available_converters[name]
            else:
                print(f"??  Warning: Converter '{name}' not available")
        
        if not converters_to_test:
            print("? Error: None of the specified converters are available!")
            return 1
    else:
        converters_to_test = available_converters
    
    # Prepare converter kwargs
    converter_kwargs = {
        'verbose': args.verbose,
        'extract_tables': args.extract_tables,
        'dpi': args.tesseract_dpi,
        'poppler_path': args.poppler_path,
        'textract_url': args.textract_url,
    }
    
    # Wrap converters with kwargs
    converters = {}
    for name, func in converters_to_test.items():
        converters[name] = lambda fp, f=func: f(fp, **converter_kwargs)
    
    if args.verbose:
        print("\nConverters to test:")
        for name in converters.keys():
            print(f" - {name}")
    
    # Run benchmark
    print(f"\n{'='*80}")
    print("STARTING BENCHMARK")
    print(f"{'='*80}")
    print(f"Files: {len(test_files)}")
    print(f"Converters: {len(converters)}")
    print(f"Baseline: {args.baseline if args.baseline in converters else 'None'}")
    print(f"Output: {args.output_dir}")
    print(f"{'='*80}\n")
    
    benchmark = DocumentConverterBenchmark(
        output_dir=args.output_dir,
        visualize_blocks=args.visualize_blocks,
        viz_output_dir=args.viz_output_dir,
        viz_dpi=args.viz_dpi,
        viz_iou_thr=args.viz_iou_thr,
        viz_export_blocks=args.viz_export_blocks,
        viz_renderer=args.viz_renderer,
        viz_poppler_path=args.poppler_path,
        viz_match_mode=args.viz_match,
    )
    
    baseline = args.baseline if args.baseline in converters else None
    report = benchmark.run_benchmark_suite(
        test_files=test_files,
        converters=converters,
        baseline_converter=baseline
    )
    
    # Print summary
    benchmark.print_summary()
    
    print("\n? Benchmark complete!")
    print(f"?? Results saved to: {args.output_dir}/")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
