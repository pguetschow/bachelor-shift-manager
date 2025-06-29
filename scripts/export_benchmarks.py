#!/usr/bin/env python3
"""
Helper script to export benchmark results for upload to deployed environment.
This script makes it easy to run benchmarks locally and export the results.
"""

import os
import sys
import subprocess
import argparse
from pathlib import Path

def run_command(cmd, description):
    """Run a command and handle errors."""
    print(f"\n{'='*60}")
    print(f"Running: {description}")
    print(f"Command: {' '.join(cmd)}")
    print(f"{'='*60}")
    
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        print("✓ Success!")
        if result.stdout:
            print(result.stdout)
        return True
    except subprocess.CalledProcessError as e:
        print(f"✗ Failed: {e}")
        if e.stdout:
            print("STDOUT:", e.stdout)
        if e.stderr:
            print("STDERR:", e.stderr)
        return False

def main():
    parser = argparse.ArgumentParser(
        description="Export benchmark results for upload to deployed environment",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run benchmarks and export results
  python scripts/export_benchmarks.py --run-benchmarks --export
  
  # Only export existing results
  python scripts/export_benchmarks.py --export
  
  # Run benchmarks with fixtures and export
  python scripts/export_benchmarks.py --run-benchmarks --load-fixtures --export
  
  # Export specific company only
  python scripts/export_benchmarks.py --export --company "Kleines Unternehmen"
        """
    )
    
    parser.add_argument(
        '--run-benchmarks',
        action='store_true',
        help='Run benchmark algorithms before exporting'
    )
    
    parser.add_argument(
        '--load-fixtures',
        action='store_true',
        help='Load fixtures before running benchmarks'
    )
    
    parser.add_argument(
        '--export',
        action='store_true',
        help='Export benchmark results'
    )
    
    parser.add_argument(
        '--include-schedules',
        action='store_true',
        help='Include schedule entries in export (can be large)'
    )
    
    parser.add_argument(
        '--company',
        type=str,
        help='Export only specific company (by name)'
    )
    
    parser.add_argument(
        '--output-dir',
        type=str,
        default='benchmark_export',
        help='Output directory for export files (default: benchmark_export)'
    )
    
    parser.add_argument(
        '--force',
        action='store_true',
        help='Force benchmark to run even if already in progress'
    )
    
    args = parser.parse_args()
    
    # Check if we're in the right directory
    if not os.path.exists('manage.py'):
        print("Error: manage.py not found. Please run this script from the project root directory.")
        sys.exit(1)
    
    success = True
    
    # Step 1: Run benchmarks if requested
    if args.run_benchmarks:
        cmd = ['python', 'manage.py', 'benchmark_algorithms']
        if args.load_fixtures:
            cmd.append('--load-fixtures')
        if args.force:
            cmd.append('--force')
        
        success = run_command(cmd, "Benchmark Algorithms")
        if not success:
            print("\nBenchmark failed. You can still export existing results with --export")
            if not args.export:
                sys.exit(1)
    
    # Step 2: Export results if requested
    if args.export:
        cmd = ['python', 'manage.py', 'export_benchmark_results']
        if args.include_schedules:
            cmd.append('--include-schedules')
        if args.company:
            cmd.extend(['--company', args.company])
        cmd.extend(['--output-dir', args.output_dir])
        
        success = run_command(cmd, "Export Benchmark Results")
        if not success:
            sys.exit(1)
        
        # Show next steps
        print(f"\n{'='*60}")
        print("EXPORT COMPLETE!")
        print(f"{'='*60}")
        print(f"Export files created in: {args.output_dir}/")
        print(f"ZIP file ready for upload: {args.output_dir}/benchmark_export.zip")
        print("\nNext steps:")
        print("1. Upload the ZIP file to your deployed environment")
        print("2. Use the web interface: /upload-benchmark")
        print("3. Or use the API: POST /api/upload-benchmark-results/")
        print(f"\nUpload URL: https://your-deployed-domain.com/upload-benchmark")
    
    if not args.run_benchmarks and not args.export:
        parser.print_help()
        print("\nPlease specify --run-benchmarks and/or --export")

if __name__ == '__main__':
    main() 