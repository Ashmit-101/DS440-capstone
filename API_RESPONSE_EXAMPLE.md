# API Response Example - With Mock Health Data

## Endpoint
```
POST /predict/manual
```

## Request
```json
{
  "mood_today": 3,
  "energy_today": 4,
  "stress_today": 2,
  "sleep_quality": 3,
  "social_connection": 4,
  "journal_note": "Had a good day at work, felt productive"
}
```

## Response (Success)
```json
{
  "features_from_date": "2024-04-23",
  "prediction_for_date": "2024-04-24",
  "predicted_happy_score": 3.47,
  "model_cv_mae": 0.68,
  "model_cv_std": 0.12,
  "summary": "Tomorrow looks fairly close to today.",
  "likely_drivers": [
    "stress is pulling the forecast down",
    "energy is a positive signal",
    "connection is giving you some lift"
  ],
  "confidence_note": "Moderate confidence. Treat this as a directional check-in, not a precise score.",
  "health_data": {
    "sleep_hours": 7.5,
    "steps": 8200,
    "calories_burned": 2150
  }
}
```

---

## What Each Field Means

### Core Prediction
- **features_from_date**: Date whose data was used (today)
- **prediction_for_date**: Date being predicted (tomorrow)
- **predicted_happy_score**: Forecast on 1-5 scale

### Model Metrics
- **model_cv_mae**: Cross-validated mean absolute error (~0.68 = ±0.68 points)
- **model_cv_std**: Variation across folds (lower = more stable)

### Interpretation
- **summary**: Plain-English description of direction
- **likely_drivers**: Top 3 factors influencing the prediction
- **confidence_note**: Caveat about how to interpret the forecast

### NEW: Health Data
- **health_data.sleep_hours**: Actual sleep (from mock Apple Health)
- **health_data.steps**: Daily step count (from mock Apple Health)
- **health_data.calories_burned**: Energy expenditure (from mock Apple Health)

---

## Different Response Scenarios

### Scenario 1: High Energy Day (Good Prediction)
```json
{
  "predicted_happy_score": 4.18,
  "summary": "Tomorrow looks a bit better than today.",
  "likely_drivers": [
    "sleep is supporting you",
    "energy is a positive signal",
    "connection is giving you some lift"
  ],
  "confidence_note": "Moderate confidence. Treat this as a directional check-in, not a precise score.",
  "health_data": {
    "sleep_hours": 8.5,
    "steps": 12400,
    "calories_burned": 2650
  }
}
```

### Scenario 2: Stressed Out Day (Watch)
```json
{
  "predicted_happy_score": 2.34,
  "summary": "Tomorrow may feel a bit heavier than today.",
  "likely_drivers": [
    "stress is pulling the forecast down",
    "low connection may be weighing on tomorrow",
    "low energy makes tomorrow less steady"
  ],
  "confidence_note": "Low confidence. This is still an early behavioral estimate, not a clinical signal.",
  "health_data": {
    "sleep_hours": 5.9,
    "steps": 5200,
    "calories_burned": 1750
  }
}
```

### Scenario 3: Mixed Signals
```json
{
  "predicted_happy_score": 3.21,
  "summary": "Tomorrow looks fairly close to today.",
  "likely_drivers": [
    "today looked fairly middle-of-the-road"
  ],
  "confidence_note": "Moderate confidence. Treat this as a directional check-in, not a precise score.",
  "health_data": {
    "sleep_hours": 7.1,
    "steps": 9100,
    "calories_burned": 2200
  }
}
```

---

## Error Responses

### Model Not Trained
```json
{
  "detail": "Model has not been trained yet. POST /train first."
}
```
**Status**: 503 Service Unavailable

**Fix**: Run `POST /train` endpoint first

### Health Data Not Found
```json
{
  "detail": "No health data found for user_demo"
}
```
**Status**: 503 Service Unavailable

**Fix**: Ensure `health_data.csv` exists in `mood_prediction/` directory

---

## How the Mobile App Uses This

### Display Health Data Card
```typescript
if (prediction.health_data && 
    (prediction.health_data.sleep_hours || 
     prediction.health_data.steps || 
     prediction.health_data.calories_burned)) {
  // Show green health data card with metrics
}
```

### Display Prediction Result
```typescript
// Color is determined by predicted_happy_score
if (score >= 4.1) → "High" (green)
if (score >= 3.1) → "Steady" (orange)
else → "Watch" (red)
```

### Show Drivers
```typescript
// List up to 3 top factors
prediction.likely_drivers.map(driver => <Chip>{driver}</Chip>)
```

---

## Testing the Endpoint

### Using curl
```bash
curl -X POST http://localhost:8000/predict/manual \
  -H "Content-Type: application/json" \
  -d '{
    "mood_today": 3,
    "energy_today": 4,
    "stress_today": 2,
    "sleep_quality": 3,
    "social_connection": 4
  }'
```

### Using Python
```python
import requests

response = requests.post(
    "http://localhost:8000/predict/manual",
    json={
        "mood_today": 3,
        "energy_today": 4,
        "stress_today": 2,
        "sleep_quality": 3,
        "social_connection": 4,
        "journal_note": "Had a good day"
    }
)

print(response.json())
# Shows health_data in response
```

---

## Key Insight

The `health_data` field is **new** and **demo-specific**. It shows:
1. What health metrics were used in the prediction
2. That real data improves over survey-only predictions
3. Clear path to real HealthKit integration

When you move to real Apple Health, this field will populate with actual user data instead of CSV data.
