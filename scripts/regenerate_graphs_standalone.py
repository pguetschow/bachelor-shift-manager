#!/usr/bin/env python3
"""
Standalone script to regenerate benchmark graphs from existing JSON result files.

This version doesn't require Django setup and works directly with JSON data.
It's useful for environments where Django isn't available or when you just
want to regenerate graphs from existing JSON files.

Usage:
    python scripts/regenerate_graphs_standalone.py [--export-dir EXPORT_DIR] [--test-case TEST_CASE]

Examples:
    # Regenerate all graphs from default export directory
    python scripts/regenerate_graphs_standalone.py
    
    # Regenerate graphs from custom export directory
    python scripts/regenerate_graphs_standalone.py --export-dir /path/to/benchmark/results
    
    # Regenerate graphs for specific test case only
    python scripts/regenerate_graphs_standalone.py --test-case small_company
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Any

# Add the project root to the Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Import required libraries for graph generation
try:
    import matplotlib.pyplot as plt
    import numpy as np
    import pandas as pd
except ImportError as e:
    print(f"Error: Required libraries not found. Please install: {e}")
    print("Run: pip install matplotlib numpy pandas")
    sys.exit(1)


def load_benchmark_results(export_dir: str) -> Dict[str, Any]:
    """Load the main benchmark results file."""
    results_file = os.path.join(export_dir, 'benchmark_results.json')
    if not os.path.exists(results_file):
        raise FileNotFoundError(f"Benchmark results file not found: {results_file}")
    
    with open(results_file, 'r', encoding='utf-8') as f:
        return json.load(f)


def generate_runtime_comparison_graph(all_results: Dict[str, Any], export_dir: str):
    """Generate runtime comparison graph across all test cases."""
    print("Generating runtime comparison graph...")
    
    # Extract data for comparison
    test_cases = list(all_results.keys())
    algorithms = set()
    for test_results in all_results.values():
        algorithms.update(test_results['results'].keys())
    algorithms = sorted(list(algorithms))
    
    # Runtime comparison across test cases
    fig, axes = plt.subplots(1, len(test_cases), figsize=(6*len(test_cases), 6))
    if len(test_cases) == 1:
        axes = [axes]
    
    for idx, test_case in enumerate(test_cases):
        ax = axes[idx]
        results = all_results[test_case]['results']
        
        alg_names = []
        runtimes = []
        for alg in algorithms:
            if alg in results and results[alg]['status'] == 'success':
                alg_names.append(alg)
                runtimes.append(results[alg]['runtime'])
        
        bars = ax.bar(alg_names, runtimes)
        ax.set_title(f"{all_results[test_case]['display_name']}")
        ax.set_xlabel('Algorithmus')
        ax.set_ylabel('Laufzeit (s)')
        ax.set_xticks(range(len(alg_names)))
        ax.set_xticklabels(alg_names, rotation=45, ha='right')
        
        # Add values
        for bar, val in zip(bars, runtimes):
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height(),
                   f'{val:.1f}', ha='center', va='bottom', fontsize=8)
    
    plt.suptitle('Laufzeitvergleich über alle Testfälle', fontsize=16)
    plt.tight_layout()
    plt.savefig(os.path.join(export_dir, 'runtime_comparison_all.png'), dpi=300)
    plt.close()
    
    print("✓ Generated runtime comparison graph")


def generate_scalability_analysis(all_results: Dict[str, Any], export_dir: str):
    """Generate scalability analysis graph."""
    print("Generating scalability analysis...")
    
    test_cases = list(all_results.keys())
    algorithms = set()
    for test_results in all_results.values():
        algorithms.update(test_results['results'].keys())
    algorithms = sorted(list(algorithms))
    
    if len(test_cases) <= 1:
        print("Skipping scalability analysis (need multiple test cases)")
        return
    
    plt.figure(figsize=(12, 8))
    
    # Collect scaling exponents for each algorithm
    scaling_exponents: Dict[str, float] = {}
    for alg in algorithms:
        problem_sizes = []
        runtimes_alg = []
        for test_case in test_cases:
            results = all_results[test_case]['results']
            if alg in results and results[alg]['status'] == 'success':
                size = all_results[test_case]['problem_size']['employees']
                problem_sizes.append(size)
                runtimes_alg.append(results[alg]['runtime'])
        
        if problem_sizes:
            # Plot runtime vs problem size
            plt.plot(problem_sizes, runtimes_alg, marker='o', label=alg, linewidth=2)
            
            # Compute scaling exponent using log–log regression if at least two points
            if len(problem_sizes) > 1:
                logs_x = np.log(problem_sizes)
                logs_y = np.log(runtimes_alg)
                # linear fit returns slope (exponent) and intercept
                slope, _ = np.polyfit(logs_x, logs_y, 1)
                scaling_exponents[alg] = float(slope)
    
    plt.xlabel('Anzahl Mitarbeiter')
    plt.ylabel('Laufzeit (Sekunden)')
    plt.title('Skalierbarkeitsanalyse')
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(os.path.join(export_dir, 'scalability_analysis.png'), dpi=300)
    plt.close()
    
    # Persist scaling exponents to JSON for further analysis
    if scaling_exponents:
        try:
            with open(os.path.join(export_dir, 'scaling_exponents.json'), 'w', encoding='utf-8') as f:
                json.dump(scaling_exponents, f, indent=4)
        except Exception as e:
            print(f"Warning: Could not save scaling exponents: {e}")
    
    print("✓ Generated scalability analysis")


def generate_fairness_comparison_graph(test_results: Dict[str, Any], export_dir: str, test_case: str):
    """Generate fairness comparison graph for a test case."""
    print(f"Generating fairness comparison for {test_case}...")
    
    # Filter successful results
    successful = {k: v for k, v in test_results.items() if v['status'] == 'success'}
    if not successful:
        print(f"No successful results for {test_case}, skipping...")
        return
    
    algorithms = list(successful.keys())
    
    # Create test case directory
    test_dir = os.path.join(export_dir, test_case)
    if not os.path.exists(test_dir):
        os.makedirs(test_dir)
    
    # Fairness Comparison across algorithms
    fig, axes = plt.subplots(2, 3, figsize=(18, 12))
    axes = axes.flatten()
    
    # Define metric keys and labels
    fairness_keys = [
        ('jain_index', 'Jain-Fairness-Index'),
        ('gini_overtime', 'Gini-Koeffizient (Überstunden)'),
        ('variance_hours', 'Varianz Arbeitsstunden'),
        ('gini_coefficient', 'Gini-Koeffizient (Arbeitsstunden)'),
        ('hours_std_dev', 'Standardabweichung (Std.)'),
        ('hours_cv', 'Variationskoeffizient (%)'),
    ]
    
    for idx, (key, title) in enumerate(fairness_keys):
        values = []
        for alg in algorithms:
            val = successful[alg]['kpis']['fairness_metrics'].get(key, 0)
            values.append(val)
        
        ax = axes[idx]
        bars = ax.bar(algorithms, values, color='skyblue')
        ax.set_title(title)
        
        # Determine ylabel
        if 'Gini' in title:
            ax.set_ylabel('Index')
        elif 'Jain' in title:
            ax.set_ylabel('Index')
        elif 'Varianz' in title or 'Standard' in title:
            ax.set_ylabel('Stunden²' if 'Varianz' in title else 'Stunden')
        elif 'Variationskoeffizient' in title:
            ax.set_ylabel('CV (%)')
        else:
            ax.set_ylabel('')
        
        ax.set_xticklabels(algorithms, rotation=45, ha='right')
        
        # Annotate values
        for bar, val in zip(bars, values):
            # Format numbers: percentages with one decimal where appropriate
            if 'CV' in title:
                label = f'{val:.1f}%'
            elif 'Gini' in title or 'Jain' in title:
                label = f'{val:.3f}'
            elif 'Varianz' in title:
                label = f'{val:.1f}'
            elif 'Standard' in title:
                label = f'{val:.1f}'
            else:
                label = f'{val:.1f}'
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height(), label,
                    ha='center', va='bottom')
    
    plt.tight_layout()
    plt.savefig(os.path.join(test_dir, 'fairness_comparison.png'), dpi=300)
    plt.close()
    
    print(f"✓ Generated fairness comparison for {test_case}")


def generate_coverage_analysis_graph(test_results: Dict[str, Any], export_dir: str, test_case: str):
    """Generate coverage analysis graph for a test case."""
    print(f"Generating coverage analysis for {test_case}...")
    
    # Filter successful results
    successful = {k: v for k, v in test_results.items() if v['status'] == 'success'}
    if not successful:
        print(f"No successful results for {test_case}, skipping...")
        return
    
    algorithms = list(successful.keys())
    
    # Create test case directory
    test_dir = os.path.join(export_dir, test_case)
    if not os.path.exists(test_dir):
        os.makedirs(test_dir)
    
    # Coverage Analysis across algorithms
    fig, axes = plt.subplots(2, 2, figsize=(15, 12))
    axes = axes.flatten()
    
    for idx, alg in enumerate(algorithms):
        if idx >= 4:  # Limit to 4 subplots
            break
        
        coverage_stats = successful[alg]['kpis']['coverage_stats']
        shift_names = [stat['shift']['name'] for stat in coverage_stats]
        coverage_percentages = [stat['coverage_percentage'] for stat in coverage_stats]
        
        # Coverage percentage
        bars = axes[idx].bar(shift_names, coverage_percentages, color='lightblue')
        axes[idx].set_title(f'Abdeckung - {alg}')
        axes[idx].set_ylabel('Abdeckung (%)')
        axes[idx].set_xticklabels(shift_names, rotation=45, ha='right')
        axes[idx].axhline(y=100, color='red', linestyle='--', alpha=0.7, label='100% Abdeckung')
        axes[idx].legend()
        
        # Add value labels
        for bar, val in zip(bars, coverage_percentages):
            axes[idx].text(bar.get_x() + bar.get_width()/2, bar.get_height(),
                         f'{val:.1f}%', ha='center', va='bottom')
    
    plt.tight_layout()
    plt.savefig(os.path.join(test_dir, 'coverage_analysis.png'), dpi=300)
    plt.close()
    
    print(f"✓ Generated coverage analysis for {test_case}")


def main():
    parser = argparse.ArgumentParser(
        description="Standalone script to regenerate benchmark graphs from JSON files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Regenerate all graphs from default export directory
  python scripts/regenerate_graphs_standalone.py
  
  # Regenerate graphs from custom export directory
  python scripts/regenerate_graphs_standalone.py --export-dir /path/to/benchmark/results
  
  # Regenerate graphs for specific test case only
  python scripts/regenerate_graphs_standalone.py --test-case small_company
        """
    )
    
    parser.add_argument(
        '--export-dir',
        type=str,
        default='export',
        help='Directory containing benchmark results (default: export)'
    )
    
    parser.add_argument(
        '--test-case',
        type=str,
        action='append',
        help='Specific test case(s) to regenerate graphs for (can be specified multiple times)'
    )
    
    parser.add_argument(
        '--skip-cross-comparison',
        action='store_true',
        help='Skip generating cross-test case comparison graphs'
    )
    
    args = parser.parse_args()
    
    # Validate export directory
    if not os.path.exists(args.export_dir):
        print(f"Error: Export directory does not exist: {args.export_dir}")
        sys.exit(1)
    
    try:
        # Load benchmark results
        print(f"Loading benchmark results from: {args.export_dir}")
        all_results = load_benchmark_results(args.export_dir)
        
        # Determine which test cases to process
        if args.test_case:
            test_cases = args.test_case
        else:
            # Process all test cases found in the results
            test_cases = list(all_results.keys())
        
        print(f"Found {len(test_cases)} test case(s) to process: {', '.join(test_cases)}")
        
        # Regenerate graphs for each test case
        for test_case in test_cases:
            if test_case not in all_results:
                print(f"Warning: Test case '{test_case}' not found in benchmark results, skipping...")
                continue
            
            try:
                test_results = all_results[test_case]['results']
                generate_fairness_comparison_graph(test_results, args.export_dir, test_case)
                generate_coverage_analysis_graph(test_results, args.export_dir, test_case)
            except Exception as e:
                print(f"Error regenerating graphs for {test_case}: {e}")
                continue
        
        # Regenerate cross-test case comparison graphs
        if not args.skip_cross_comparison:
            try:
                generate_runtime_comparison_graph(all_results, args.export_dir)
                generate_scalability_analysis(all_results, args.export_dir)
            except Exception as e:
                print(f"Error regenerating cross-test case graphs: {e}")
        
        print("\n✓ Graph regeneration complete!")
        print(f"Results saved to: {args.export_dir}")
        
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main() 