# Benchmark Graph Regeneration Scripts

This directory contains scripts to regenerate benchmark graphs from existing JSON result files without needing to rerun the entire benchmark process.

## Scripts Overview

### 1. `regenerate_benchmark_graphs.py` (Full Django Version)
- **Requires**: Django setup and database access
- **Use case**: When you want to regenerate graphs using the full `EnhancedAnalytics` class with all features
- **Features**: 
  - Uses the complete graph generation logic from `EnhancedAnalytics`
  - Can access database models for additional analysis
  - Generates all graph types including individual algorithm graphs

### 2. `regenerate_graphs_standalone.py` (Standalone Version)
- **Requires**: Only matplotlib, numpy, pandas
- **Use case**: When Django isn't available or you just want to regenerate basic graphs from JSON
- **Features**:
  - Works independently of Django
  - Generates core comparison graphs (fairness, coverage, runtime, scalability)
  - Faster execution for basic graph regeneration

## Usage

### Basic Usage (Regenerate All Graphs)

```bash
# Using the full Django version
python scripts/regenerate_benchmark_graphs.py

# Using the standalone version
python scripts/regenerate_graphs_standalone.py
```

### Regenerate Specific Test Cases

```bash
# Regenerate graphs for specific test case(s)
python scripts/regenerate_benchmark_graphs.py --test-case small_company
python scripts/regenerate_benchmark_graphs.py --test-case small_company --test-case medium_company

# Using standalone version
python scripts/regenerate_graphs_standalone.py --test-case small_company
```

### Custom Export Directory

```bash
# Use custom directory containing benchmark results
python scripts/regenerate_benchmark_graphs.py --export-dir /path/to/benchmark/results
```

### Skip Cross-Test Case Comparisons

```bash
# Only regenerate individual test case graphs, skip cross-comparisons
python scripts/regenerate_benchmark_graphs.py --skip-cross-comparison
```

## Expected Directory Structure

The scripts expect the following structure in your export directory:

```
export/
├── benchmark_results.json          # Main results file
├── runtime_comparison_all.png      # Cross-test case runtime comparison
├── scalability_analysis.png        # Scalability analysis
├── scaling_exponents.json          # Scaling exponents data
├── small_company/
│   ├── results.json               # Individual test case results
│   ├── fairness_comparison.png    # Fairness comparison graphs
│   ├── coverage_analysis.png      # Coverage analysis graphs
│   └── ...                        # Other individual graphs
├── medium_company/
│   └── ...
├── large_company/
│   └── ...
└── bigger_company/
    └── ...
```

## Generated Graphs

### Individual Test Case Graphs
- **Fairness Comparison**: Jain index, Gini coefficients, variance, standard deviation, coefficient of variation
- **Coverage Analysis**: Shift coverage percentages across algorithms
- **Additional Metrics**: Runtime, constraint violations, etc. (Django version only)

### Cross-Test Case Graphs
- **Runtime Comparison**: Algorithm runtime comparison across all test cases
- **Scalability Analysis**: Runtime vs problem size with scaling exponents

## When to Use Each Script

### Use `regenerate_benchmark_graphs.py` when:
- You have Django set up and running
- You want to regenerate all graph types including individual algorithm graphs
- You need access to database models for additional analysis
- You're modifying the `EnhancedAnalytics` class and want to test changes

### Use `regenerate_graphs_standalone.py` when:
- Django isn't available or set up
- You only need basic comparison graphs
- You want faster execution
- You're working in a different environment

## Troubleshooting

### Common Issues

1. **"Benchmark results file not found"**
   - Make sure the export directory contains `benchmark_results.json`
   - Check the `--export-dir` path is correct

2. **"Company not found in database"** (Django version)
   - Ensure the database contains the expected companies
   - Check that fixtures have been loaded

3. **Import errors** (Standalone version)
   - Install required packages: `pip install matplotlib numpy pandas`

4. **Permission errors**
   - Ensure write permissions to the export directory

### Getting Help

```bash
# Show help for either script
python scripts/regenerate_benchmark_graphs.py --help
python scripts/regenerate_graphs_standalone.py --help
```

## Integration with Development Workflow

1. **Modify graph generation logic** in `rostering_app/services/enhanced_analytics.py`
2. **Test changes** by regenerating graphs:
   ```bash
   python scripts/regenerate_benchmark_graphs.py --test-case small_company
   ```
3. **Iterate** on the graph generation logic
4. **Regenerate all graphs** when satisfied:
   ```bash
   python scripts/regenerate_benchmark_graphs.py
   ```

This workflow allows you to quickly iterate on graph generation improvements without the overhead of rerunning the entire benchmark process. 