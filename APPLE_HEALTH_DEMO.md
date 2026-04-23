# Mock Apple Health Integration (Demo)

This document explains how the mock Apple Health data flows through the mood prediction system.

## Overview

For the demo, we simulate Apple Health data (sleep hours, steps, calories burned) using a CSV file. This data is integrated into the prediction model to show how real behavioral signals would improve mood predictions.

**Real implementation roadmap:** Replace this with actual HealthKit API integration later.

---

## Architecture

### 1. Dummy Health Data (`health_data.csv`)

Located at: `mood_prediction/health_data.csv`

Contains realistic daily metrics for a demo user:
- **user_id**: "user_demo" (the demo user)
- **date**: Calendar date (YYYY-MM-DD)
- **sleep_hours**: Hours of sleep (typically 5-9 hours)
- **steps**: Daily step count (typically 4,000-12,000)
- **calories_burned**: Daily caloric expenditure (typically 1,500-3,000)

Example row:
```
2024-01-15,user_demo,7.5,8200,2150
```

### 2. Backend Changes

#### `mood_prediction/model/predictor.py`

**New functions:**
- `load_health_data()` - Loads the health_data.csv file
- `get_today_health_data(user_id)` - Retrieves the most recent health data for a user

**Updated function:**
- `_build_manual_feature_values()` - Now accepts optional `health_data` dict parameter
  - If health data is available, uses **real** sleep hours instead of mapping from sleep_quality survey
  - Maps **steps** to activity intensity (4k steps ≈ 1, 20k steps ≈ 5)
  - Maps **calories_burned** to exercise intensity (1500 cal ≈ 1, 3000 cal ≈ 5)

**Updated endpoint:**
- `predict_mood_from_survey()` - Now loads health data and includes it in the response

#### `mood_prediction/api/main.py`

**New response types:**
- `HealthDataResponse` - Schema for health data in API response
- Updated `PredictResponse` to include optional `health_data` field

### 3. Frontend Changes

#### `mobile-app/src/types.ts`

Added:
```typescript
export type HealthData = {
  sleep_hours?: number | null;
  steps?: number | null;
  calories_burned?: number | null;
};
```

Updated `PredictionResponse` to include `health_data?: HealthData | null`

#### `mobile-app/App.tsx`

**New UI card:**
- After prediction is returned, displays a "Health data used" card
- Shows sleep hours, steps, and calories burned
- Styled with green accent (to differentiate from prediction colors)
- Badges as "Apple Health (demo)" to clarify this is mock data

---

## How It Works (Flow)

1. **User fills survey** → mood, energy, stress, sleep_quality, social_connection
2. **User taps "Generate forecast"**
3. **Mobile app calls POST /predict/manual** with survey responses
4. **Backend:**
   - Loads health_data.csv (latests entry for "user_demo")
   - Builds features using:
     - Survey responses (for happy, sad, stress_level, etc.)
     - **Real** health data (sleep_hours, activity metrics from steps, exercise from calories)
   - Makes prediction with combined features
   - Returns prediction **with** health_data object
5. **Mobile app displays:**
   - Health data card (green, showing sleep, steps, calories)
   - Prediction result card (colored by mood forecast)
   - Drivers and confidence note

---

## Feature Engineering Details

### Sleep
- **Survey-only (current):** Maps sleep_quality (1-5) to hours using fixed mapping
- **With health data:** Uses actual `sleep_hours` from Apple Health

### Activity (Walk Amount, Activity Mean)
- **Survey-only:** Derived from energy_today (1-5) and calmness
- **With health data:** Mapped from `steps` using formula: `activity_level = min(5, max(1, steps / 4000))`
  - 4,000 steps = activity level ~1
  - 20,000 steps = activity level ~5

### Exercise Intensity
- **Survey-only:** Averaged from energy + calmness
- **With health data:** Mapped from `calories_burned` using formula: `exercise_intensity = min(5, max(1, (calories - 1000) / 400))`
  - 1,500 calories = exercise intensity ~1.25
  - 3,000 calories = exercise intensity ~5

---

## Demo Data Tips

The CSV includes 10 days of realistic variation:
- Varies sleep (5.9–8.5 hours) to show impact on prediction
- Varies steps (4,800–12,400) to show activity patterns
- Correlates calories with steps (more activity = more calories)

**To add more demo days:**
1. Open `health_data.csv`
2. Add rows with new dates and realistic metrics
3. Restart the API server

**To modify demo user:**
- Change the `user_demo` string in `get_today_health_data()` to use a different user ID
- Add that user ID to health_data.csv

---

## Real Apple Health Integration (Future)

When you implement actual HealthKit:

1. **On iOS**, request HealthKit permissions
2. **Query actual data**: `HKHealthStore.execute(query)` for sleep, steps, workouts
3. **Pass to API** as part of prediction request (or compute on-device)
4. **Update feature engineering** to use real ranges (you'll calibrate against real data distribution)

The current code structure makes this straightforward—just replace `load_health_data()` and `get_today_health_data()` with HealthKit queries.

---

## Testing

### Test with the demo data:
```bash
# 1. Start the API
cd mood_prediction
python -m uvicorn api.main:app --reload

# 2. Call the endpoint
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

Response will include:
```json
{
  "predicted_happy_score": 3.45,
  "health_data": {
    "sleep_hours": 7.5,
    "steps": 8200,
    "calories_burned": 2150
  },
  "summary": "Tomorrow looks fairly close to today.",
  "likely_drivers": [...]
}
```

---

## Files Modified

- ✅ Created: `mood_prediction/health_data.csv`
- ✅ Updated: `mood_prediction/model/predictor.py`
- ✅ Updated: `mood_prediction/api/main.py`
- ✅ Updated: `mobile-app/src/types.ts`
- ✅ Updated: `mobile-app/App.tsx`

---

## Visual Flow

```
┌─────────────────────────────────────────┐
│  User fills survey + optional note      │
└────────────────┬────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────┐
│  POST /predict/manual                   │
└────────────────┬────────────────────────┘
                 │
        ┌────────┴────────┐
        ▼                 ▼
   [Survey]         [Health Data CSV]
   (5 fields)       (sleep, steps, cal)
        │                 │
        └────────┬────────┘
                 ▼
         [Feature Engineering]
         • Use real sleep hours
         • Map steps → activity
         • Map calories → exercise
                 │
                 ▼
         [GradientBoosting Model]
                 │
                 ▼
         [Prediction Result]
         + health_data object
                 │
        ┌────────┴────────┐
        ▼                 ▼
   [Health Data Card]  [Mood Card]
   (green, demo badge) (colored by score)
```

---

## Next Steps

1. **Validate** the feature mappings (steps→activity, calories→exercise) against real HealthKit ranges
2. **Collect** actual user survey + health data pairs to evaluate improvement
3. **Implement** real HealthKit integration when ready
4. **Calibrate** the feature mappings if needed based on real data distribution
