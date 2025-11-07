# Quick Start Guide

Get started with the Document Converter Benchmark Suite in 5 minutes!

## ⚡ Super Quick Start

```bash
# 1. Run setup
python setup.py

# 2. Check available converters
python run_benchmark.py --list-converters

# 3. Test a PDF
python run_benchmark.py your_file.pdf
```

Done! Results will be in `benchmark_results/`

---

## 📦 Installation Options

### Option A: Minimal (No OCR)
```bash
pip install markitdown[all] PyPDF2 pdfplumber pymupdf pdfminer.six
```

### Option B: With OCR Support
```bash
# Install system packages first:
# Ubuntu: sudo apt-get install tesseract-ocr poppler-utils
# macOS: brew install tesseract poppler

# Then install Python packages:
pip install markitdown[all] PyPDF2 pdfplumber pymupdf pdfminer.six pytesseract pdf2image
```

### Option C: Everything
```bash
pip install -r requirements.txt
```

---

## 🎯 Common Use Cases

### Test a Single PDF
```bash
python run_benchmark.py document.pdf
```

### Compare Specific Converters
```bash
python run_benchmark.py document.pdf --converters markitdown pypdf2 tesseract
```

### Batch Test Multiple Files
```bash
python run_benchmark.py *.pdf
```

### Use Different Baseline
```bash
python run_benchmark.py document.pdf --baseline markitdown
```

### High-Quality OCR
```bash
python run_benchmark.py scanned.pdf --tesseract-dpi 600
```

---

## 📊 Understanding Results

Results are saved in `benchmark_results/` with three files:

1. **`benchmark_report_*.json`** - Summary statistics
2. **`detailed_results_*.json`** - Complete raw data  
3. **`summary_*.md`** - Human-readable report

### Key Metrics

**Speed**: Lower execution time = faster
**Accuracy**: Higher similarity % = more accurate vs baseline
**Speed Ratio**: >1.0x means faster than baseline

---

## 🔧 Troubleshooting

### No converters available?
```bash
python setup.py  # Run interactive setup
```

### Tesseract not found?
```bash
# Ubuntu/Debian
sudo apt-get install tesseract-ocr

# macOS
brew install tesseract

# Verify
tesseract --version
```

### Import errors?
```bash
pip install --upgrade pip
pip install <package-name>
```

---

## 💡 Tips

1. **Start simple**: Test with markitdown and pypdf2 first
2. **Use OCR for scanned docs**: Add tesseract when needed
3. **Batch carefully**: Test on 1-2 files first, then scale up
4. **Check output**: Review the `.md` summary file for easy reading
5. **Adjust DPI**: Higher DPI = better OCR but slower (try 150-600)

---

## 📚 Next Steps

- Read full [README.md](README.md) for detailed documentation
- Check [example_usage.py](example_usage.py) for code examples
- Run `python run_benchmark.py --help` for all options

---

## 🆘 Getting Help

**List available converters:**
```bash
python run_benchmark.py --list-converters
```

**Installation help:**
```bash
python run_benchmark.py --install-help
```

**Verbose output:**
```bash
python run_benchmark.py file.pdf --verbose
```

---

**Happy Benchmarking! 🚀**
