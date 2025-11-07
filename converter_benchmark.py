#!/usr/bin/env python3
"""
Document Converter Benchmark Suite
Tests multiple PDF/document converters for speed and accuracy
Compares against Tesseract OCR baseline
"""

import os
import time
import json
import traceback
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, asdict
from datetime import datetime

# Text similarity metrics
from difflib import SequenceMatcher
import re


@dataclass
class ConversionResult:
    """Stores results from a single conversion attempt"""
    converter_name: str
    file_path: str
    success: bool
    execution_time: float
    text_content: str
    char_count: int
    word_count: int
    line_count: int
    error_message: Optional[str] = None
    metadata: Optional[Dict] = None


@dataclass
class ComparisonMetrics:
    """Metrics comparing two conversion results"""
    similarity_ratio: float  # 0.0 to 1.0
    char_difference: int
    word_difference: int
    line_difference: int
    unique_to_baseline: int
    unique_to_compared: int
    common_words: int


class DocumentConverterBenchmark:
    """Main benchmark class for testing document converters"""
    
    def __init__(self, output_dir: str = "benchmark_results",
                 visualize_blocks: bool = False,
                 viz_output_dir: Optional[str] = None,
                 viz_dpi: int = 200,
                 viz_iou_thr: float = 0.5,
                 viz_export_blocks: bool = False):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        self.results: List[ConversionResult] = []
        # Visualization config
        self.visualize_blocks = visualize_blocks
        self.viz_output_dir = Path(viz_output_dir) if viz_output_dir else self.output_dir / 'visual'
        self.viz_dpi = viz_dpi
        self.viz_iou_thr = viz_iou_thr
        self.viz_export_blocks = viz_export_blocks
        
    def _calculate_text_metrics(self, text: str) -> Tuple[int, int, int]:
        """Calculate basic text metrics"""
        if not text:
            return 0, 0, 0
        
        char_count = len(text)
        word_count = len(text.split())
        line_count = len(text.splitlines())
        
        return char_count, word_count, line_count
    
    def _compare_texts(self, baseline: str, compared: str) -> ComparisonMetrics:
        """Compare two text strings and return similarity metrics"""
        # Calculate similarity ratio using SequenceMatcher
        similarity = SequenceMatcher(None, baseline, compared).ratio()
        
        # Basic metrics
        char_diff = abs(len(baseline) - len(compared))
        
        # Word-level comparison
        baseline_words = set(re.findall(r'\w+', baseline.lower()))
        compared_words = set(re.findall(r'\w+', compared.lower()))
        
        common_words = len(baseline_words & compared_words)
        unique_baseline = len(baseline_words - compared_words)
        unique_compared = len(compared_words - baseline_words)
        
        word_diff = abs(len(baseline.split()) - len(compared.split()))
        line_diff = abs(len(baseline.splitlines()) - len(compared.splitlines()))
        
        return ComparisonMetrics(
            similarity_ratio=similarity,
            char_difference=char_diff,
            word_difference=word_diff,
            line_difference=line_diff,
            unique_to_baseline=unique_baseline,
            unique_to_compared=unique_compared,
            common_words=common_words
        )
    
    def test_converter(self, converter_func, converter_name: str, 
                      file_path: str, **kwargs) -> ConversionResult:
        """Test a single converter on a file"""
        print(f"\n{'='*60}")
        print(f"Testing: {converter_name}")
        print(f"File: {file_path}")
        print(f"{'='*60}")
        
        start_time = time.time()
        success = False
        text_content = ""
        error_msg = None
        metadata = {}
        
        try:
            result = converter_func(file_path, **kwargs)
            
            # Handle different return types
            if isinstance(result, dict):
                text_content = result.get('text', result.get('content', ''))
                metadata = {k: v for k, v in result.items() if k not in ['text', 'content']}
            else:
                text_content = str(result)
            
            success = True
            print(f"[OK] Success")
            
        except Exception as e:
            error_msg = f"{type(e).__name__}: {str(e)}"
            print(f"[X] Failed: {error_msg}")
            if kwargs.get('verbose'):
                traceback.print_exc()
        
        execution_time = time.time() - start_time
        char_count, word_count, line_count = self._calculate_text_metrics(text_content)
        
        print(f"⏱️  Time: {execution_time:.3f}s")
        print(f"📊 Stats: {char_count} chars, {word_count} words, {line_count} lines")
        
        result = ConversionResult(
            converter_name=converter_name,
            file_path=file_path,
            success=success,
            execution_time=execution_time,
            text_content=text_content,
            char_count=char_count,
            word_count=word_count,
            line_count=line_count,
            error_message=error_msg,
            metadata=metadata
        )
        
        self.results.append(result)
        return result
    
    def run_benchmark_suite(self, test_files: List[str], 
                           converters: Dict, 
                           baseline_converter: str = None) -> Dict:
        """Run full benchmark suite on multiple files"""
        print("\n" + "="*80)
        print("DOCUMENT CONVERTER BENCHMARK SUITE")
        print("="*80)
        print(f"Test files: {len(test_files)}")
        print(f"Converters: {len(converters)}")
        print(f"Timestamp: {datetime.now().isoformat()}")
        print("="*80)
        
        # Test all converters on all files
        for file_path in test_files:
            if not os.path.exists(file_path):
                print(f"⚠️  File not found: {file_path}")
                continue
            
            print(f"\n{'#'*80}")
            print(f"📄 Processing: {os.path.basename(file_path)}")
            print(f"   Size: {os.path.getsize(file_path) / 1024:.2f} KB")
            print(f"{'#'*80}")
            
            for conv_name, conv_func in converters.items():
                self.test_converter(conv_func, conv_name, file_path)
        
        # Generate comparison report
        report = self._generate_report(baseline_converter)

        # Save results
        self._save_results(report)

        # Optional visualization
        if self.visualize_blocks:
            try:
                self._run_visualization()
            except Exception as e:
                print(f"[X] Visualization failed: {e}")
        
        return report
    
    def _generate_report(self, baseline_name: Optional[str] = None) -> Dict:
        """Generate comprehensive comparison report"""
        report = {
            'timestamp': datetime.now().isoformat(),
            'total_tests': len(self.results),
            'converters': {},
            'files': {},
            'comparisons': []
        }
        
        # Aggregate by converter
        for result in self.results:
            if result.converter_name not in report['converters']:
                report['converters'][result.converter_name] = {
                    'total_tests': 0,
                    'successes': 0,
                    'failures': 0,
                    'avg_time': 0,
                    'total_time': 0,
                    'avg_chars': 0,
                    'avg_words': 0
                }
            
            conv_stats = report['converters'][result.converter_name]
            conv_stats['total_tests'] += 1
            
            if result.success:
                conv_stats['successes'] += 1
                conv_stats['total_time'] += result.execution_time
                conv_stats['avg_chars'] += result.char_count
                conv_stats['avg_words'] += result.word_count
            else:
                conv_stats['failures'] += 1
        
        # Calculate averages
        for conv_name, stats in report['converters'].items():
            if stats['successes'] > 0:
                stats['avg_time'] = stats['total_time'] / stats['successes']
                stats['avg_chars'] = stats['avg_chars'] / stats['successes']
                stats['avg_words'] = stats['avg_words'] / stats['successes']
        
        # Aggregate by file
        for result in self.results:
            if result.file_path not in report['files']:
                report['files'][result.file_path] = []
            report['files'][result.file_path].append({
                'converter': result.converter_name,
                'success': result.success,
                'time': result.execution_time,
                'chars': result.char_count,
                'words': result.word_count,
                'error': result.error_message
            })
        
        # Compare against baseline if specified
        if baseline_name:
            baseline_results = [r for r in self.results if r.converter_name == baseline_name]
            
            for baseline in baseline_results:
                if not baseline.success:
                    continue
                
                # Compare all other converters for same file
                comparisons = []
                for result in self.results:
                    if (result.file_path == baseline.file_path and 
                        result.converter_name != baseline_name and 
                        result.success):
                        
                        metrics = self._compare_texts(baseline.text_content, 
                                                     result.text_content)
                        
                        comparisons.append({
                            'file': os.path.basename(result.file_path),
                            'baseline': baseline_name,
                            'compared': result.converter_name,
                            'similarity': metrics.similarity_ratio,
                            'char_diff': metrics.char_difference,
                            'word_diff': metrics.word_difference,
                            'time_diff': result.execution_time - baseline.execution_time,
                            'speed_ratio': baseline.execution_time / result.execution_time if result.execution_time > 0 else 0
                        })
                
                if comparisons:
                    report['comparisons'].extend(comparisons)
        
        return report
    
    def _save_results(self, report: Dict):
        """Save results to disk"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Save JSON report
        json_path = self.output_dir / f"benchmark_report_{timestamp}.json"
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2)
        print(f"\n[i] Report saved: {json_path}")
        
        # Save detailed results
        detailed_path = self.output_dir / f"detailed_results_{timestamp}.json"
        detailed_results = [asdict(r) for r in self.results]
        with open(detailed_path, 'w', encoding='utf-8') as f:
            json.dump(detailed_results, f, indent=2)
        print(f"[i] Detailed results saved: {detailed_path}")
        
        # Generate markdown summary
        md_path = self.output_dir / f"summary_{timestamp}.md"
        self._generate_markdown_summary(report, md_path)
        print(f"[i] Markdown summary saved: {md_path}")
    
    def _generate_markdown_summary(self, report: Dict, output_path: Path):
        """Generate human-readable markdown summary"""
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write("# Document Converter Benchmark Report\n\n")
            f.write(f"**Generated:** {report['timestamp']}\n\n")
            f.write(f"**Total Tests:** {report['total_tests']}\n\n")
            
            # Converter summary
            f.write("## Converter Performance Summary\n\n")
            f.write("| Converter | Success Rate | Avg Time (s) | Avg Chars | Avg Words |\n")
            f.write("|-----------|--------------|--------------|-----------|----------|\n")
            
            for name, stats in sorted(report['converters'].items()):
                success_rate = (stats['successes'] / stats['total_tests'] * 100) if stats['total_tests'] > 0 else 0
                f.write(f"| {name} | {success_rate:.1f}% | {stats['avg_time']:.3f} | {stats['avg_chars']:.0f} | {stats['avg_words']:.0f} |\n")
            
            # Comparison results
            if report['comparisons']:
                f.write("\n## Accuracy Comparison (vs Baseline)\n\n")
                f.write("| File | Converter | Similarity | Speed Ratio | Char Diff | Word Diff |\n")
                f.write("|------|-----------|------------|-------------|-----------|----------|\n")
                
                for comp in report['comparisons']:
                    f.write(f"| {comp['file']} | {comp['compared']} | "
                           f"{comp['similarity']:.2%} | {comp['speed_ratio']:.2f}x | "
                           f"{comp['char_diff']} | {comp['word_diff']} |\n")
            
            # File-by-file results
            f.write("\n## Results by File\n\n")
            for file_path, results in report['files'].items():
                f.write(f"### {os.path.basename(file_path)}\n\n")
                f.write("| Converter | Success | Time (s) | Characters | Words |\n")
                f.write("|-----------|---------|----------|------------|-------|\n")
                
                for r in results:
                    status = "OK" if r['success'] else "FAIL"
                    f.write(f"| {r['converter']} | {status} | {r['time']:.3f} | "
                           f"{r['chars']} | {r['words']} |\n")
                f.write("\n")
            
            if self.visualize_blocks:
                f.write("\n## Visual Coverage\n\n")
                f.write("Visual overlays and metrics generated. See the 'visual' output folder for images and JSON.\n")
                f.write("\n")

    def _run_visualization(self):
        """Generate visual overlays and coverage metrics per document."""
        from visualizer import Visualizer
        # Group block data by file and engine
        per_file: Dict[str, Dict[str, Dict[int, List[Dict]]]] = {}
        for r in self.results:
            if not r.success:
                continue
            if r.metadata and isinstance(r.metadata, dict):
                blocks = r.metadata.get('blocks_per_page')
                if blocks:
                    per_file.setdefault(r.file_path, {})[r.converter_name] = blocks
        if not per_file:
            print("[i] No block data available for visualization.")
            return
        for file_path, engines_pages in per_file.items():
            out_dir = self.viz_output_dir / os.path.splitext(os.path.basename(file_path))[0]
            out_dir.mkdir(parents=True, exist_ok=True)
            viz = Visualizer(output_dir=out_dir, dpi=self.viz_dpi, iou_thr=self.viz_iou_thr)
            metrics = viz.process_document(
                pdf_path=file_path,
                per_engine_blocks_norm=engines_pages,
                export_blocks_json=self.viz_export_blocks,
            )
            print(f"[i] Visual metrics saved to: {metrics['output_dir']}/visual_metrics.json")
    
    def print_summary(self):
        """Print summary to console"""
        print("\n" + "="*80)
        print("BENCHMARK SUMMARY")
        print("="*80)
        
        # Group by converter
        converter_stats = {}
        for result in self.results:
            if result.converter_name not in converter_stats:
                converter_stats[result.converter_name] = {
                    'total': 0, 'success': 0, 'failed': 0, 'total_time': 0
                }
            
            stats = converter_stats[result.converter_name]
            stats['total'] += 1
            if result.success:
                stats['success'] += 1
                stats['total_time'] += result.execution_time
            else:
                stats['failed'] += 1
        
        print(f"\n{'Converter':<20} {'Success':<10} {'Failed':<10} {'Avg Time':<12}")
        print("-" * 80)
        
        for name, stats in sorted(converter_stats.items()):
            avg_time = stats['total_time'] / stats['success'] if stats['success'] > 0 else 0
            print(f"{name:<20} {stats['success']:<10} {stats['failed']:<10} {avg_time:<12.3f}s")
        
        print("="*80)


if __name__ == "__main__":
    print("Document Converter Benchmark Framework")
    print("Import this module and use the DocumentConverterBenchmark class")
    print("\nExample:")
    print("  from converter_benchmark import DocumentConverterBenchmark")
    print("  benchmark = DocumentConverterBenchmark()")
    print("  results = benchmark.run_benchmark_suite(files, converters)")
