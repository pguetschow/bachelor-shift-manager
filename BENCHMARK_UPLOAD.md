# Benchmark Upload System

This system allows you to run benchmarks locally and upload the results to the deployed environment, avoiding the high costs of running benchmarks on the deployed server.

## Overview

The benchmark upload system consists of:

1. **Local Export**: Export benchmark results from your local environment as SQL dumps
2. **Upload Interface**: Web-based upload interface for the deployed environment
3. **API Endpoints**: REST API for programmatic uploads
4. **Helper Scripts**: Easy-to-use scripts for local operations

## Quick Start

### 1. Run Benchmarks Locally

```bash
# Run benchmarks with fixtures and export results as SQL dump
python scripts/export_benchmarks.py --run-benchmarks --load-fixtures --export --include-schedules
```

### 2. Upload to Deployed Environment

1. Navigate to `/upload-benchmark` on your deployed site
2. Drag and drop the generated `benchmark_dump.zip` file
3. Wait for the upload to complete

## Detailed Usage

### Local Export Commands

#### Using the Helper Script (Recommended)

```bash
# Run benchmarks and export as JSON dump
python scripts/export_benchmarks.py --run-benchmarks --export

# Run benchmarks with fixtures and export as JSON dump
python scripts/export_benchmarks.py --run-benchmarks --load-fixtures --export

# Export existing results only as JSON dump
python scripts/export_benchmarks.py --export

# Export with schedule entries (larger file)
python scripts/export_benchmarks.py --export --include-schedules

# Export specific company only
python scripts/export_benchmarks.py --export --company "Kleines Unternehmen"

# Export only data (no schema) for importing into existing database
python scripts/export_benchmarks.py --export --data-only
```

#### Using Django Management Commands

```bash
# Run benchmarks
python manage.py benchmark_algorithms --load-fixtures

# Export results as JSON dump
python manage.py export_sql_dump --include-schedules

# Export only data (no schema)
python manage.py export_sql_dump --data-only

# Export specific company
python manage.py export_sql_dump --company "Kleines Unternehmen"
```

### Import Commands

```bash
# Import JSON dump
python manage.py import_sql_dump --file benchmark_dump.zip --clear-existing

# Dry run to see what would be imported
python manage.py import_sql_dump --file benchmark_dump.zip --dry-run

# Import without clearing existing data
python manage.py import_sql_dump --file benchmark_dump.zip
```

### Upload Methods

#### Web Interface

1. Navigate to `/upload-benchmark` on your deployed site
2. Follow the on-screen instructions
3. Drag and drop or select the ZIP file
4. View import results

#### API Upload

```bash
# Upload via curl
curl -X POST \
  -F "file=@benchmark_dump.zip" \
  https://your-domain.com/api/upload-benchmark-results/
```

#### Python Script Upload

```python
import requests

with open('benchmark_dump.zip', 'rb') as f:
    files = {'file': f}
    response = requests.post(
        'https://your-domain.com/api/upload-benchmark-results/',
        files=files
    )
    print(response.json())
```

## File Structure

The export creates the following structure:

```
benchmark_export/
├── benchmark_dump.json    # JSON dump file
└── benchmark_dump.zip     # Compressed file for upload
```

### Export Format

The system uses JSON dumps for reliable and fast data transfer:

- **Format**: Standard Django JSON dump with all data
- **Advantages**: 
  - More reliable and faster import
  - Preserves data integrity
  - Works with any Django-supported database (now MySQL by default)
  - Smaller file sizes
  - Standard JSON format

## Configuration

### Database

- The default database is now **MySQL**. Ensure your environment variables and Docker Compose are configured for MySQL.
- SQLite is no longer supported.

### Export Options

- `--include-schedules`: Include schedule entries (larger file)
- `--company`: Export specific company only
- `--output-dir`: Custom output directory
- `--data-only`: Export only data, not schema (for importing into existing database)

### Upload Limits

- Maximum file size: 50MB
- Supported format: ZIP files
- Required content: `benchmark_dump.json`

## Troubleshooting

### Common Issues

1. **File too large**
   - Use `--include-schedules` only when needed
   - Export specific companies with `--company`
   - JSON dumps are typically smaller than SQL dumps

2. **Upload fails**
   - Check file format (must be ZIP)
   - Verify file contains `benchmark_dump.json`
   - Check server logs for detailed errors

3. **Import errors**
   - Review import summary for specific errors
   - Check data consistency in export file
   - Try using `--dry-run` to preview import

### Error Handling

The system provides detailed error reporting:

- File validation errors
- Import process errors
- Database constraint violations
- Data format issues

## Performance

### JSON Dump Performance

| Metric | Performance |
|--------|-------------|
| Export Speed | ~2-5 seconds |
| Import Speed | ~5-15 seconds |
| File Size | ~1-5 MB |
| Reliability | High |
| Data Integrity | Preserved |

## Security Considerations

- Upload endpoint validates file format and content
- Files are processed in temporary directories
- Database operations use transactions for consistency
- No persistent file storage on server

## Best Practices

1. **Use JSON dumps** for reliable data transfer
2. **Run benchmarks locally** to save costs
3. **Use fixtures** for consistent test data
4. **Include schedules** only when needed
5. **Test imports** with `--dry-run` before production
6. **Use `--data-only`** when importing into existing database

## Migration from Legacy Methods

If you were previously using other export methods:

1. **Export**: Use `python manage.py export_sql_dump` for all new exports
2. **Import**: The upload system now only accepts JSON dumps
3. **Benefits**: Faster, more reliable, and smaller file sizes

The JSON dump method is the only supported format for all exports and imports. 