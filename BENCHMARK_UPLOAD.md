# Benchmark Upload System

This system allows you to run benchmarks locally and upload the results to the deployed environment, avoiding the high costs of running benchmarks on the deployed server.

## Overview

The benchmark upload system consists of:

1. **Local Export**: Export benchmark results from your local environment
2. **Upload Interface**: Web-based upload interface for the deployed environment
3. **API Endpoints**: REST API for programmatic uploads
4. **Helper Scripts**: Easy-to-use scripts for local operations

## Quick Start

### 1. Run Benchmarks Locally

```bash
# Run benchmarks with fixtures and export results
python scripts/export_benchmarks.py --run-benchmarks --load-fixtures --export --include-schedules
```

### 2. Upload to Deployed Environment

1. Navigate to `/upload-benchmark` on your deployed site
2. Drag and drop the generated `benchmark_export.zip` file
3. Wait for the upload to complete

## Detailed Usage

### Local Export Commands

#### Using the Helper Script (Recommended)

```bash
# Run benchmarks and export
python scripts/export_benchmarks.py --run-benchmarks --export

# Run benchmarks with fixtures and export
python scripts/export_benchmarks.py --run-benchmarks --load-fixtures --export

# Export existing results only
python scripts/export_benchmarks.py --export

# Export with schedule entries (larger file)
python scripts/export_benchmarks.py --export --include-schedules

# Export specific company only
python scripts/export_benchmarks.py --export --company "Kleines Unternehmen"
```

#### Using Django Management Commands

```bash
# Run benchmarks
python manage.py benchmark_algorithms --load-fixtures

# Export results
python manage.py export_benchmark_results --include-schedules
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
  -F "file=@benchmark_export.zip" \
  https://your-domain.com/api/upload-benchmark-results/
```

#### Python Script Upload

```python
import requests

with open('benchmark_export.zip', 'rb') as f:
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
├── benchmark_export.json    # Main export data
└── benchmark_export.zip     # Compressed file for upload
```

### Export Data Format

The JSON export contains:

```json
{
  "metadata": {
    "exported_at": "2025-01-01T12:00:00",
    "benchmark_status": { ... },
    "export_options": { ... }
  },
  "companies": [...],
  "employees": [...],
  "shifts": [...],
  "schedule_entries": [...],
  "company_benchmark_statuses": [...]
}
```

## API Endpoints

### Upload Benchmark Results

**POST** `/api/upload-benchmark-results/`

Upload a ZIP file containing benchmark export data.

**Request:**
- Content-Type: `multipart/form-data`
- Body: ZIP file with key `file`

**Response:**
```json
{
  "status": "success",
  "message": "Benchmark results uploaded successfully",
  "import_summary": {
    "companies_imported": 3,
    "employees_imported": 140,
    "shifts_imported": 9,
    "schedule_entries_imported": 50000,
    "company_statuses_imported": 3,
    "errors": []
  }
}
```

### Upload Status

**GET** `/api/upload-status/`

Get upload endpoint status and instructions.

**Response:**
```json
{
  "status": "ready",
  "message": "Upload endpoint is ready",
  "instructions": {
    "format": "ZIP file containing benchmark_export.json",
    "max_size": "50MB",
    "endpoint": "/api/upload-benchmark-results/",
    "method": "POST",
    "content_type": "multipart/form-data"
  }
}
```

## Configuration

### Export Options

- `--include-schedules`: Include schedule entries (larger file)
- `--company`: Export specific company only
- `--output-dir`: Custom output directory

### Upload Limits

- Maximum file size: 50MB
- Supported format: ZIP files
- Required content: `benchmark_export.json`

## Troubleshooting

### Common Issues

1. **File too large**
   - Use `--include-schedules` only when needed
   - Export specific companies with `--company`

2. **Upload fails**
   - Check file format (must be ZIP)
   - Verify file contains `benchmark_export.json`
   - Check server logs for detailed errors

3. **Import errors**
   - Review import summary for specific errors
   - Check data consistency in export file

### Error Handling

The system provides detailed error reporting:

- File validation errors
- Import process errors
- Database constraint violations
- Data format issues

## Security Considerations

- Upload endpoint validates file format and content
- Files are processed in temporary directories
- Database operations use transactions for consistency
- No persistent file storage on server

## Performance

### Export Performance

- Companies, employees, shifts: ~1-2 seconds
- Schedule entries: ~10-30 seconds (depending on data size)
- ZIP compression: ~1-5 seconds

### Upload Performance

- File validation: ~1-2 seconds
- Data import: ~5-30 seconds (depending on data size)
- Total upload time: ~10-60 seconds

## Best Practices

1. **Run benchmarks locally** to save costs
2. **Use fixtures** for consistent test data
3. **Include schedules** only when needed
4. **Test uploads** with small datasets first
5. **Monitor import results** for errors
6. **Backup data** before large imports

## Support

For issues or questions:

1. Check the error messages in the upload interface
2. Review the import summary for specific problems
3. Check server logs for detailed error information
4. Verify export file format and content 