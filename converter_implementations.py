#!/usr/bin/env python3
"""
Converter Implementations
Wrappers for various PDF/document converters
"""

import os
import tempfile
from typing import Dict, Optional
from pathlib import Path


class ConverterImplementations:
    """Collection of converter wrapper functions"""
    
    @staticmethod
    def markitdown_converter(file_path: str, **kwargs) -> Dict:
        """Convert using Microsoft MarkItDown"""
        from markitdown import MarkItDown
        
        md = MarkItDown(enable_plugins=kwargs.get('enable_plugins', False))
        result = md.convert(file_path)
        
        return {
            'text': result.text_content,
            'title': getattr(result, 'title', None)
        }
    
    @staticmethod
    def pypdf2_converter(file_path: str, **kwargs) -> Dict:
        """Convert using PyPDF2"""
        import PyPDF2
        
        text_parts = []
        metadata = {}
        
        with open(file_path, 'rb') as file:
            reader = PyPDF2.PdfReader(file)
            
            # Extract metadata
            if reader.metadata:
                metadata = {
                    'title': reader.metadata.get('/Title', ''),
                    'author': reader.metadata.get('/Author', ''),
                    'pages': len(reader.pages)
                }
            
            # Extract text from all pages
            for page_num, page in enumerate(reader.pages):
                try:
                    text = page.extract_text()
                    if text:
                        text_parts.append(text)
                except Exception as e:
                    if kwargs.get('verbose'):
                        print(f"Warning: Failed to extract page {page_num}: {e}")
        
        return {
            'text': '\n\n'.join(text_parts),
            **metadata
        }
    
    @staticmethod
    def pdfplumber_converter(file_path: str, **kwargs) -> Dict:
        """Convert using pdfplumber"""
        import pdfplumber

        text_parts = []
        table_count = 0

        with pdfplumber.open(file_path) as pdf:
            metadata = {
                'pages': len(pdf.pages)
            }
            
            blocks_per_page = {}
            for page_num, page in enumerate(pdf.pages):
                try:
                    # Extract text
                    text = page.extract_text()
                    if text:
                        text_parts.append(text)
                    
                    # Extract tables if requested
                    if kwargs.get('extract_tables', False):
                        tables = page.extract_tables()
                        if tables:
                            table_count += len(tables)
                            for table in tables:
                                # Convert table to text representation
                                table_text = '\n'.join(['\t'.join(str(cell) for cell in row) for row in table])
                                text_parts.append(f"\n[TABLE]\n{table_text}\n[/TABLE]\n")
                
                except Exception as e:
                    if kwargs.get('verbose'):
                        print(f"Warning: Failed to extract page {page_num}: {e}")

                # Attempt word-level extraction and group to line blocks
                try:
                    words = page.extract_words()
                    if words:
                        # Group by line proximity (top within tolerance)
                        tol = 3.0
                        lines = {}
                        for w in words:
                            top = float(w.get('top', 0.0))
                            assigned = False
                            for key in list(lines.keys()):
                                if abs(key - top) <= tol:
                                    lines[key].append(w)
                                    assigned = True
                                    break
                            if not assigned:
                                lines[top] = [w]
                        rects = []
                        pw, ph = page.width, page.height
                        for _, ws in lines.items():
                            x0 = min(float(w['x0']) for w in ws)
                            y0 = min(float(w.get('top', 0.0)) for w in ws)
                            x1 = max(float(w['x1']) for w in ws)
                            y1 = max(float(w.get('bottom', float(w.get('top', 0.0)))) for w in ws)
                            if pw and ph and x1 > x0 and y1 > y0:
                                rects.append({
                                    'x0': max(0.0, min(1.0, x0 / pw)),
                                    'y0': max(0.0, min(1.0, y0 / ph)),
                                    'x1': max(0.0, min(1.0, x1 / pw)),
                                    'y1': max(0.0, min(1.0, y1 / ph)),
                                })
                        if rects:
                            blocks_per_page[page_num] = rects
                except Exception:
                    pass

        result = {
            'text': '\n\n'.join(text_parts),
            'table_count': table_count,
            **metadata
        }
        if blocks_per_page:
            result['blocks_per_page'] = blocks_per_page
        return result
    
    @staticmethod
    def pymupdf_converter(file_path: str, **kwargs) -> Dict:
        """Convert using PyMuPDF (fitz)"""
        import fitz  # PyMuPDF

        text_parts = []

        doc = fitz.open(file_path)

        metadata = {
            'pages': doc.page_count,
            'title': doc.metadata.get('title', ''),
            'author': doc.metadata.get('author', '')
        }

        try:
            blocks_per_page = {}
            for page_num in range(doc.page_count):
                try:
                    page = doc[page_num]
                    text = page.get_text()
                    if text:
                        text_parts.append(text)
                    # Extract blocks and normalize to page size (0..1)
                    try:
                        blks = page.get_text("blocks") or []
                        rects = []
                        pw, ph = page.rect.width, page.rect.height
                        if pw and ph:
                            for b in blks:
                                if len(b) >= 4:
                                    x0, y0, x1, y1 = float(b[0]), float(b[1]), float(b[2]), float(b[3])
                                    # normalize
                                    rects.append({
                                        'x0': max(0.0, min(1.0, x0 / pw)),
                                        'y0': max(0.0, min(1.0, y0 / ph)),
                                        'x1': max(0.0, min(1.0, x1 / pw)),
                                        'y1': max(0.0, min(1.0, y1 / ph)),
                                    })
                        if rects:
                            blocks_per_page[page_num] = rects
                    except Exception:
                        pass
                except Exception as e:
                    if kwargs.get('verbose'):
                        print(f"Warning: Failed to extract page {page_num}: {e}")
        finally:
            doc.close()

        result = {
            'text': '\n\n'.join(text_parts),
            **metadata
        }
        if blocks_per_page:
            result['blocks_per_page'] = blocks_per_page
        return result
    
    @staticmethod
    def tika_converter(file_path: str, **kwargs) -> Dict:
        """Convert using Apache Tika"""
        from tika import parser
        import tika
        
        # Initialize Tika (downloads JAR on first run)
        if not kwargs.get('tika_initialized', False):
            tika.initVM()
        
        parsed = parser.from_file(file_path)
        
        return {
            'text': parsed.get('content', ''),
            'metadata': parsed.get('metadata', {})
        }
    
    @staticmethod
    def tesseract_converter(file_path: str, **kwargs) -> Dict:
        """Convert using Tesseract OCR (requires image conversion first)"""
        import pytesseract
        from pdf2image import convert_from_path

        # Convert PDF to images
        try:
            images = convert_from_path(
                file_path,
                dpi=kwargs.get('dpi', 300),
                fmt=kwargs.get('fmt', 'png'),
                poppler_path=kwargs.get('poppler_path', None)
            )
        except Exception as e:
            raise RuntimeError(
                "pdf2image failed to convert PDF to images. "
                "On Windows, ensure Poppler is installed and pass --poppler-path to run_benchmark.py. "
                f"Original error: {e}"
            )

        text_parts = []
        lang = kwargs.get('lang', 'eng')
        blocks_per_page = {}

        for i, image in enumerate(images):
            try:
                # Perform OCR
                text = pytesseract.image_to_string(image, lang=lang)
                if text:
                    text_parts.append(text)
                # Extract line-level boxes via TSV
                try:
                    data = pytesseract.image_to_data(image, lang=lang, output_type=pytesseract.Output.DICT)
                    n = len(data.get('level', []))
                    rects = []
                    iw, ih = image.size
                    # Aggregate words into lines by (block_num, par_num, line_num)
                    groups = {}
                    for idx in range(n):
                        level = int(data['level'][idx])
                        if level != 5:  # word level
                            continue
                        key = (int(data.get('block_num', [0])[idx]), int(data.get('par_num', [0])[idx]), int(data.get('line_num', [0])[idx]))
                        left = int(data['left'][idx])
                        top = int(data['top'][idx])
                        width = int(data['width'][idx])
                        height = int(data['height'][idx])
                        groups.setdefault(key, []).append((left, top, left+width, top+height))
                    for _, boxes in groups.items():
                        x0 = min(b[0] for b in boxes); y0 = min(b[1] for b in boxes)
                        x1 = max(b[2] for b in boxes); y1 = max(b[3] for b in boxes)
                        if iw and ih and x1 > x0 and y1 > y0:
                            rects.append({
                                'x0': max(0.0, min(1.0, x0 / iw)),
                                'y0': max(0.0, min(1.0, y0 / ih)),
                                'x1': max(0.0, min(1.0, x1 / iw)),
                                'y1': max(0.0, min(1.0, y1 / ih)),
                            })
                    if rects:
                        blocks_per_page[i] = rects
                except Exception:
                    pass
            except Exception as e:
                if kwargs.get('verbose'):
                    print(f"Warning: OCR failed on page {i}: {e}")

        result = {
            'text': '\n\n'.join(text_parts),
            'pages_processed': len(images),
            'dpi': kwargs.get('dpi', 300)
        }
        if blocks_per_page:
            result['blocks_per_page'] = blocks_per_page
        return result
    
    @staticmethod
    def pdfminer_converter(file_path: str, **kwargs) -> Dict:
        """Convert using pdfminer.six"""
        from pdfminer.high_level import extract_text
        from pdfminer.layout import LAParams
        
        # Configure layout parameters
        laparams = LAParams(
            line_margin=kwargs.get('line_margin', 0.5),
            word_margin=kwargs.get('word_margin', 0.1),
            char_margin=kwargs.get('char_margin', 2.0)
        )
        
        text = extract_text(file_path, laparams=laparams)
        
        return {
            'text': text
        }
    
    @staticmethod
    def pypandoc_converter(file_path: str, **kwargs) -> Dict:
        """Convert using pypandoc (Pandoc wrapper)"""
        import pypandoc
        
        # Convert to plain text
        output = pypandoc.convert_file(
            file_path,
            'plain',
            format='pdf',
            extra_args=kwargs.get('extra_args', [])
        )
        
        return {
            'text': output
        }
    
    @staticmethod
    def textract_converter(file_path: str, **kwargs) -> Dict:
        """Convert using textract (multi-format extractor)"""
        import textract
        
        # textract returns bytes
        text = textract.process(file_path).decode('utf-8', errors='ignore')
        
        return {
            'text': text
        }
    
    @staticmethod
    def unstructured_converter(file_path: str, **kwargs) -> Dict:
        """Convert using unstructured library"""
        from unstructured.partition.auto import partition
        
        # Partition the document
        elements = partition(filename=file_path)
        
        # Extract text from elements
        text_parts = []
        element_types = {}
        
        for element in elements:
            text_parts.append(str(element))
            element_type = type(element).__name__
            element_types[element_type] = element_types.get(element_type, 0) + 1
        
        return {
            'text': '\n\n'.join(text_parts),
            'element_types': element_types,
            'element_count': len(elements)
        }


def get_available_converters(test_imports: bool = True) -> Dict:
    """
    Get dictionary of available converters
    
    Args:
        test_imports: If True, only return converters whose dependencies are installed
    
    Returns:
        Dictionary mapping converter names to functions
    """
    converters = {
        'markitdown': ConverterImplementations.markitdown_converter,
        'pypdf2': ConverterImplementations.pypdf2_converter,
        'pdfplumber': ConverterImplementations.pdfplumber_converter,
        'pymupdf': ConverterImplementations.pymupdf_converter,
        'tika': ConverterImplementations.tika_converter,
        'tesseract': ConverterImplementations.tesseract_converter,
        'pdfminer': ConverterImplementations.pdfminer_converter,
        'pypandoc': ConverterImplementations.pypandoc_converter,
        'textract': ConverterImplementations.textract_converter,
        'unstructured': ConverterImplementations.unstructured_converter,
    }
    
    if not test_imports:
        return converters
    
    # Test which converters are available
    available = {}
    
    for name, func in converters.items():
        try:
            # Try to import the required module
            if name == 'markitdown':
                import markitdown
            elif name == 'pypdf2':
                import PyPDF2
            elif name == 'pdfplumber':
                import pdfplumber
            elif name == 'pymupdf':
                import fitz
            elif name == 'tika':
                import tika
            elif name == 'tesseract':
                import pytesseract
                import pdf2image
            elif name == 'pdfminer':
                import pdfminer
            elif name == 'pypandoc':
                import pypandoc
            elif name == 'textract':
                import textract
            elif name == 'unstructured':
                import unstructured
            
            available[name] = func
            print(f"[OK] {name:15} - Available")
            
        except Exception as e:
            err_type = type(e).__name__
            err_msg = getattr(e, 'name', None) or str(e).splitlines()[0]
            print(f"[X] {name:15} - Unavailable ({err_type}: {err_msg})")
    
    return available


def install_instructions():
    """Print installation instructions for all converters"""
    instructions = """
    INSTALLATION INSTRUCTIONS
    =========================
    
    Core Converters:
    ----------------
    pip install markitdown[all]              # Microsoft MarkItDown
    pip install PyPDF2                        # PyPDF2
    pip install pdfplumber                    # pdfplumber
    pip install pymupdf                       # PyMuPDF/fitz
    pip install pdfminer.six                  # pdfminer
    
    OCR & Advanced:
    ---------------
    # Tesseract (requires system package)
    # Ubuntu/Debian: sudo apt-get install tesseract-ocr
    # macOS: brew install tesseract
    pip install pytesseract pdf2image
    
    # Apache Tika (requires Java)
    pip install tika
    
    # Pandoc (requires system package)
    # Ubuntu/Debian: sudo apt-get install pandoc
    # macOS: brew install pandoc
    pip install pypandoc
    
    # Textract (system dependencies may vary)
    pip install textract
    
    # Unstructured
    pip install unstructured[all-docs]
    
    Quick Install (most common):
    ----------------------------
    pip install markitdown[all] PyPDF2 pdfplumber pymupdf pdfminer.six pytesseract pdf2image
    """
    print(instructions)


if __name__ == "__main__":
    print("Converter Implementations")
    print("=" * 60)
    print("\nChecking available converters...")
    print("-" * 60)
    
    available = get_available_converters(test_imports=True)
    
    print(f"\n{len(available)} converters available")
    
    if len(available) < 5:
        print("\n" + "="*60)
        print("Not many converters found. See installation instructions:")
        print("="*60)
        install_instructions()
