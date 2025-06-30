#!/usr/bin/env python3
"""
Helper script for running benchmarks and exporting results.

This script provides a convenient way to run benchmarks locally and export
the results for upload to the deployed environment.
"""

import argparse
import os
import sys
import subprocess


def run_command(cmd, description):
    """Run a command and return success status."""
    print(f"\n{'='*60}")
    print(f"Running: {description}")
    print(f"{'='*60}")
    print(f"Command: {' '.join(cmd)}")
    print()
    
    try:
        result = subprocess.run(cmd, check=True, capture_output=False)
        print(f"\n✅ {description} completed successfully!")
        return True
    except subprocess.CalledProcessError as e:
        print(f"\n❌ {description} failed with exit code {e.returncode}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Export benchmark results for upload to deployed environment",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run benchmarks and export results as SQL dump
  python scripts/export_benchmarks.py --run-benchmarks --export
  
  # Only export existing results as SQL dump
  python scripts/export_benchmarks.py --export
  
  # Run benchmarks with fixtures and export as SQL dump
  python scripts/export_benchmarks.py --run-benchmarks --load-fixtures --export
  
  # Export specific company only as SQL dump
  python scripts/export_benchmarks.py --export --company "Kleines Unternehmen"
  
  # Export only data (no schema) for importing into existing database
  python scripts/export_benchmarks.py --export --data-only
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
        help='Export benchmark results as SQL dump'
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
    
    parser.add_argument(
        '--data-only',
        action='store_true',
        help='Export only data, not schema (for importing into existing database)'
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
        cmd = ['python', 'manage.py', 'export_sql_dump']
        if args.include_schedules:
            cmd.append('--include-schedules')
        if args.company:
            cmd.extend(['--company', args.company])
        if args.data_only:
            cmd.append('--data-only')
        cmd.extend(['--output-dir', args.output_dir])
        
        success = run_command(cmd, "Export SQL Dump")
        if not success:
            sys.exit(1)
        
        # Show next steps
        print(f"\n{'='*60}")
        print("EXPORT COMPLETE!")
        print(f"{'='*60}")
        print(f"Export files created in: {args.output_dir}/")
        print(f"SQL dump file: {args.output_dir}/benchmark_dump.sql")
        print(f"ZIP file ready for upload: {args.output_dir}/benchmark_dump.zip")
        print("\nNext steps:")
        print("1. Upload the ZIP file to your deployed environment")
        print("2. Use the web interface: /upload-benchmark")
        print("3. Or use the API: POST /api/upload-benchmark-results/")
        print(f"\nUpload URL: https://your-deployed-domain.com/upload-benchmark")
        print("\nThe SQL dump method is more reliable and faster than the old JSON method!")
    
    if not args.run_benchmarks and not args.export:
        parser.print_help()
        print("\nPlease specify --run-benchmarks and/or --export")


if __name__ == '__main__':
    main() 