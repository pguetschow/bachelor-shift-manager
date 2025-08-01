# Real-Time KPI Calculation in Employee View

## Overview

The employee view has been updated to calculate KPIs in real-time instead of relying on store data. This provides more accurate and up-to-date calculations that reflect the current state of the schedule data.

## Changes Made

### 1. New KPI Calculator Service (`src/services/kpiCalculator.js`)

Created a new service that handles all KPI calculations directly from raw schedule data:

- **Employee Statistics**: Calculates total hours, shifts, utilization percentage, and weekly workload
- **Yearly Statistics**: Calculates yearly totals, utilization, and monthly breakdown
- **Expected Hours**: Calculates expected monthly/yearly hours based on contract and absences
- **Working Days**: Determines working days excluding weekends, holidays, and absences

### 2. Updated Employee View (`src/views/EmployeeView.vue`)

Modified the employee view to:

- Load raw schedule data directly from API endpoints
- Use the KPI calculator service for real-time calculations
- Store calculated results in reactive refs instead of computed properties from store
- Handle errors gracefully with fallback to empty data

### 3. Enhanced Backend API Endpoints

Updated the backend to include additional data needed for frontend calculations:

- **Monthly Schedule Endpoint**: Now includes employee absences
- **Yearly Schedule Endpoint**: Now includes raw schedule data and employee absences

## Key Features

### Real-Time Calculations
- KPIs are calculated fresh each time data is loaded
- No dependency on cached store data
- Immediate reflection of schedule changes

### Accurate Absence Handling
- Considers employee-specific absences when calculating expected hours
- Excludes absences from working day calculations
- Provides more accurate utilization percentages

### Holiday and Weekend Awareness
- Excludes weekends (Saturday/Sunday) from working days
- Excludes German holidays from working days
- Respects company Sunday workday settings

### Error Handling
- Graceful fallback when API calls fail
- Console logging for debugging
- Empty data states when calculations fail

## API Endpoints Used

### Monthly Employee Schedule
```
GET /api/companies/{companyId}/employees/{employeeId}/schedule/
Query params: year, month, algorithm
```

### Yearly Employee Schedule
```
GET /api/companies/{companyId}/employees/{employeeId}/yearly/
Query params: year, algorithm
```

## Data Flow

1. **Load Raw Data**: Fetch schedule data from API endpoints
2. **Calculate KPIs**: Use KPI calculator service to process raw data
3. **Update UI**: Display calculated statistics and charts
4. **Watch Changes**: Recalculate when algorithm or date changes

## Benefits

- **Accuracy**: Calculations are always based on current data
- **Performance**: No need to maintain complex store state
- **Flexibility**: Easy to modify calculation logic
- **Reliability**: Independent of store synchronization issues
- **Debugging**: Clear separation between data loading and calculation

## Future Enhancements

- Add more sophisticated holiday detection
- Implement caching for expensive calculations
- Add more detailed KPI breakdowns
- Support for different calculation algorithms 