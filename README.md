# Document Converter Benchmark Suite

A comprehensive testing framework to benchmark document conversion tools for **speed** and **accuracy**, with special focus on comparing results against Tesseract OCR baseline.

## 🎯 Features

- **Multiple Converters Tested:**
  - MarkItDown (Microsoft)
  - PyPDF2
  - pdfplumber
  - PyMuPDF (fitz)
  - Apache Tika
  - Tesseract OCR
  - pdfminer.six
  - pypandoc
  - textract
  - unstructured

- **Comprehensive Metrics:**
  - Execution time (speed)
  - Text similarity ratio (accuracy)
  - Character/word/line counts
  - Success/failure rates
  - Error tracking

- **Multiple Output Formats:**
  - JSON reports (machine-readable)
  - Markdown summaries (human-readable)
  - Detailed result logs

## 📋 Prerequisites

### System Requirements

**For Tesseract OCR:**
```bash
# Ubuntu/Debian
sudo apt-get update
sudo apt-get install tesseract-ocr tesseract-ocr-eng poppler-utils

# macOS
brew install tesseract poppler

# Verify installation
tesseract --version
```

**For Apache Tika:**
```bash
# Install Java (required)
# Ubuntu/Debian
sudo apt-get install default-jre

# macOS
brew install openjdk
```

**For Pandoc (optional):**
```bash
# Ubuntu/Debian
sudo apt-get install pandoc

# macOS
brew install pandoc
```

## 🚀 Installation

### Quick Start (Core Converters Only)

```bash
# Clone or download the benchmark suite
git clone <your-repo> && cd <repo-dir>

# Install core Python packages
pip install markitdown[all] PyPDF2 pdfplumber pymupdf pdfminer.six

# For OCR support (after installing tesseract system package)
pip install pytesseract pdf2image Pillow
```

### Full Installation (All Converters)

```bash
# Install from requirements file
pip install -r requirements.txt

# Note: This will attempt to install ALL converters
# Some may fail if system dependencies are missing
```

### Minimal Installation (Framework Only)

```bash
# No external dependencies needed for the framework itself
# Just the three core files:
# - converter_benchmark.py
# - converter_implementations.py
# - run_benchmark.py
```

## 📖 Usage

### Quick Start Example

```bash
# Check which converters are available
python run_benchmark.py --list-converters

# Run benchmark on a single PDF
python run_benchmark.py sample.pdf

# Run on multiple files
python run_benchmark.py file1.pdf file2.pdf file3.pdf

# Test all PDFs in a directory
python run_benchmark.py documents/*.pdf
```

### Advanced Usage

```bash
# Test specific converters only
python run_benchmark.py test.pdf --converters markitdown pypdf2 tesseract

# Use different baseline for accuracy comparison
python run_benchmark.py test.pdf --baseline markitdown

# Extract tables (where supported)
python run_benchmark.py test.pdf --extract-tables

# High-DPI OCR for better accuracy
python run_benchmark.py test.pdf --tesseract-dpi 600

# Custom output directory
python run_benchmark.py test.pdf --output-dir my_results

# Verbose mode (show detailed errors)
python run_benchmark.py test.pdf --verbose
```

### Programmatic Usage

```python
from converter_benchmark import DocumentConverterBenchmark
from converter_implementations import get_available_converters

# Get available converters
converters = get_available_converters(test_imports=True)

# Initialize benchmark
benchmark = DocumentConverterBenchmark(output_dir="my_results")

# Run tests
test_files = ["document1.pdf", "document2.pdf"]
report = benchmark.run_benchmark_suite(
    test_files=test_files,
    converters=converters,
    baseline_converter='tesseract'
)

# Print summary
benchmark.print_summary()

# Access results programmatically
for result in benchmark.results:
    print(f"{result.converter_name}: {result.execution_time:.3f}s")
```

## 📊 Output Files

The benchmark generates three types of output files in the specified output directory:

### 1. JSON Report (`benchmark_report_TIMESTAMP.json`)
Machine-readable summary with:
- Aggregate statistics per converter
- Success/failure rates
- Average execution times
- Comparison metrics vs baseline

### 2. Detailed Results (`detailed_results_TIMESTAMP.json`)
Complete raw data including:
- Full extracted text for each conversion
- Individual execution times
- Error messages
- Metadata from converters

### 3. Markdown Summary (`summary_TIMESTAMP.md`)
Human-readable report with:
- Performance comparison tables
- Accuracy metrics
- Per-file breakdowns
- Success/failure indicators

## 🔍 Understanding the Results

### Speed Metrics
- **Execution Time**: How long the conversion took (in seconds)
- **Speed Ratio**: Relative speed compared to baseline (>1 = faster)

### Accuracy Metrics
- **Similarity Ratio**: 0.0 to 1.0, how similar text is to baseline (1.0 = identical)
- **Character Difference**: Absolute difference in character count
- **Word Difference**: Absolute difference in word count
- **Common Words**: Number of matching words between texts

### Example Output

```
Converter Performance Summary
| Converter    | Success Rate | Avg Time (s) | Avg Chars | Avg Words |
|--------------|--------------|--------------|-----------|----------|
| markitdown   | 100.0%       | 0.234        | 5420      | 892      |
| pypdf2       | 100.0%       | 0.189        | 5398      | 886      |
| tesseract    | 100.0%       | 3.456        | 5445      | 895      |

Accuracy Comparison (vs Tesseract)
| File         | Converter  | Similarity | Speed Ratio | Char Diff |
|--------------|------------|------------|-------------|-----------|
| sample.pdf   | markitdown | 98.5%      | 14.76x      | 25        |
| sample.pdf   | pypdf2     | 97.8%      | 18.29x      | 47        |
```

## 🧪 Testing Strategy

### Recommended Approach

1. **Start with Core Converters**
   ```bash
   python run_benchmark.py test.pdf --converters markitdown pypdf2 pdfplumber
   ```

2. **Add OCR for Scanned Documents**
   ```bash
   python run_benchmark.py scanned.pdf --converters tesseract markitdown
   ```

3. **Comprehensive Testing**
   ```bash
   python run_benchmark.py *.pdf --baseline tesseract
   ```

### Document Types to Test

- **Digital PDFs**: Native text-based PDFs (best with PyPDF2, pdfplumber, MarkItDown)
- **Scanned PDFs**: Image-based PDFs requiring OCR (best with Tesseract)
- **Mixed PDFs**: Combination of text and images
- **Complex Layouts**: Tables, multi-column (best with pdfplumber, MarkItDown)

## 🛠️ Troubleshooting

### "No converters available"
```bash
# Check what's missing
python run_benchmark.py --list-converters

# Install missing packages
pip install <missing-package>
```

### Tesseract Not Found
```bash
# Ubuntu/Debian
sudo apt-get install tesseract-ocr

# macOS
brew install tesseract

# Verify
tesseract --version
```

### "Java not found" (for Tika)
```bash
# Ubuntu/Debian
sudo apt-get install default-jre

# macOS
brew install openjdk

# Verify
java -version
```

### Slow Performance
- Use lower DPI for Tesseract: `--tesseract-dpi 150`
- Test fewer converters: `--converters markitdown pypdf2`
- Process smaller batches of files

### Import Errors
```bash
# Update pip
pip install --upgrade pip

# Reinstall package
pip uninstall <package>
pip install <package>
```

## 🔐 Security Considerations

**✅ All converters in this suite perform LOCAL processing**
- No data sent to external servers
- No cloud dependencies
- Safe for sensitive/confidential documents

**For Production Use:**
- Run in isolated Docker containers
- Implement file size limits
- Validate input files before processing
- Monitor resource usage (CPU, memory)
- Consider timeouts for long-running conversions

## 📈 Performance Tips

1. **For Speed**: Use PyMuPDF or PyPDF2 for digital PDFs
2. **For Accuracy**: Use MarkItDown or pdfplumber for complex layouts
3. **For OCR**: Tesseract with 300+ DPI for best results
4. **For Tables**: pdfplumber or MarkItDown
5. **For Batch Processing**: PyMuPDF (fastest)

## 🤝 Contributing

To add a new converter:

1. Add implementation to `converter_implementations.py`:
```python
@staticmethod
def my_converter(file_path: str, **kwargs) -> Dict:
    # Your implementation
    return {'text': extracted_text}
```

2. Register in `get_available_converters()`:
```python
converters = {
    # ... existing converters
    'my_converter': ConverterImplementations.my_converter,
}
```

3. Add installation instructions to README

## 📝 License

[Your License Here]

## 🙏 Acknowledgments

- Microsoft MarkItDown team
- PyPDF2 maintainers
- Mozilla PDF.js team
- Tesseract OCR project
- All open-source contributors

## 📧 Contact

[Your contact information]

---

**Note**: This benchmark suite is for testing and comparison purposes. Always validate converter output for production use cases.
