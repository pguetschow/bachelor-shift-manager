#!/usr/bin/env python3
"""
Script to regenerate benchmark graphs from existing JSON result files.

This script allows you to update the graph generation logic and regenerate
all benchmark graphs without having to restart the benchmark process.

Usage:
    python scripts/regenerate_benchmark_graphs.py [--export-dir EXPORT_DIR] [--test-case TEST_CASE]

Examples:
    # Regenerate all graphs from default export directory
    python scripts/regenerate_benchmark_graphs.py
    
    # Regenerate graphs from custom export directory
    python scripts/regenerate_benchmark_graphs.py --export-dir /path/to/benchmark/results
    
    # Regenerate graphs for specific test case only
    python scripts/regenerate_benchmark_graphs.py --test-case small_company
    
    # Regenerate graphs for multiple specific test cases
    python scripts/regenerate_benchmark_graphs.py --test-case small_company --test-case medium_company
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

# Django setup
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rostering_project.settings')
import django
django.setup()

from rostering_app.models import Company, Employee, Shift, ScheduleEntry
from rostering_app.services.enhanced_analytics import EnhancedAnalytics


def load_benchmark_results(export_dir: str) -> Dict[str, Any]:
    """Load the main benchmark results file."""
    results_file = os.path.join(export_dir, 'benchmark_results.json')
    if not os.path.exists(results_file):
        raise FileNotFoundError(f"Benchmark results file not found: {results_file}")
    
    with open(results_file, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_test_case_results(export_dir: str, test_case: str) -> Dict[str, Any]:
    """Load results for a specific test case."""
    results_file = os.path.join(export_dir, test_case, 'results.json')
    if not os.path.exists(results_file):
        raise FileNotFoundError(f"Test case results file not found: {results_file}")
    
    with open(results_file, 'r', encoding='utf-8') as f:
        return json.load(f)


def get_company_from_test_case(test_case: str) -> Company:
    """Get the company object for a given test case."""
    # Map test case names to company names
    test_case_to_company = {
        'small_company': 'Kleines Unternehmen',
        'medium_company': 'Mittleres Unternehmen', 
        'large_company': 'Großes Unternehmen',
        'bigger_company': 'Sehr Großes Unternehmen'
    }
    
    company_name = test_case_to_company.get(test_case)
    if not company_name:
        raise ValueError(f"Unknown test case: {test_case}")
    
    try:
        return Company.objects.get(name=company_name)
    except Company.DoesNotExist:
        raise ValueError(f"Company not found in database: {company_name}")


def regenerate_test_case_graphs(export_dir: str, test_case: str, all_results: Dict[str, Any]):
    """Regenerate graphs for a specific test case."""
    print(f"Regenerating graphs for test case: {test_case}")
    
    # Get the company
    company = get_company_from_test_case(test_case)
    
    # Get all schedule entries for this company
    all_entries = ScheduleEntry.objects.filter(company=company)
    employees = list(Employee.objects.filter(company=company))
    shifts = list(Shift.objects.filter(company=company))
    
    # Create analytics instance
    analytics = EnhancedAnalytics(company, all_entries, employees, shifts)
    
    # Get results for this test case
    test_results = all_results[test_case]['results']
    
    # Generate algorithm comparison graphs
    analytics.generate_algorithm_comparison_graphs(test_results, export_dir, test_case)
    
    print(f"✓ Generated graphs for {test_case}")


def regenerate_cross_test_case_graphs(export_dir: str, all_results: Dict[str, Any]):
    """Regenerate cross-test case comparison graphs."""
    print("Regenerating cross-test case comparison graphs...")
    
    # Generate comparison graphs across all test cases
    EnhancedAnalytics.generate_comparison_graphs_across_test_cases(all_results, export_dir)
    
    print("✓ Generated cross-test case comparison graphs")


def main():
    parser = argparse.ArgumentParser(
        description="Regenerate benchmark graphs from existing JSON result files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Regenerate all graphs from default export directory
  python scripts/regenerate_benchmark_graphs.py
  
  # Regenerate graphs from custom export directory
  python scripts/regenerate_benchmark_graphs.py --export-dir /path/to/benchmark/results
  
  # Regenerate graphs for specific test case only
  python scripts/regenerate_benchmark_graphs.py --test-case small_company
  
  # Regenerate graphs for multiple specific test cases
  python scripts/regenerate_benchmark_graphs.py --test-case small_company --test-case medium_company
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
                regenerate_test_case_graphs(args.export_dir, test_case, all_results)
            except Exception as e:
                print(f"Error regenerating graphs for {test_case}: {e}")
                continue
        
        # Regenerate cross-test case comparison graphs
        if not args.skip_cross_comparison:
            try:
                regenerate_cross_test_case_graphs(args.export_dir, all_results)
            except Exception as e:
                print(f"Error regenerating cross-test case graphs: {e}")
        
        print("\n✓ Graph regeneration complete!")
        print(f"Results saved to: {args.export_dir}")
        
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main() 