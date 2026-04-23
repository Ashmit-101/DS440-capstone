# Apple Health Demo Integration Checklist

## ✅ What's Been Done

### Backend
- [x] Created `mood_prediction/health_data.csv` with 10 days of demo data for "user_demo"
- [x] Updated `mood_prediction/model/predictor.py`:
  - [x] Added `load_health_data()` function
  - [x] Added `get_today_health_data()` function
  - [x] Updated `_build_manual_feature_values()` to accept and use health data
  - [x] Updated `predict_mood_from_survey()` to load and return health data
- [x] Updated `mood_prediction/api/main.py`:
  - [x] Added `HealthDataResponse` model
  - [x] Updated `PredictResponse` to include health_data field

### Frontend
- [x] Updated `mobile-app/src/types.ts`:
  - [x] Added `HealthData` type
  - [x] Updated `PredictionResponse` to include health_data
- [x] Updated `mobile-app/App.tsx`:
  - [x] Added health data card display in results
  - [x] Added styling for health data card
  - [x] Conditionally shows sleep, steps, calories when available

### Documentation
- [x] Created `APPLE_HEALTH_DEMO.md` (comprehensive guide)
- [x] Created `INTEGRATION_CHECKLIST.md` (this file)

---

## 🚀 How to Test

### 1. Start the API Server
```bash
cd mood_prediction
python -m uvicorn api.main:app --reload
```

### 2. Build & Run Mobile App
```bash
cd mobile-app
npx expo start
```

### 3. Fill Out the Survey
- Answer all 5 questions (mood, energy, stress, sleep quality, connection)
- Optionally add a journal note
- Tap "Generate forecast"

### 4. See the Results
You should now see:
1. **Health Data Card** (green) showing:
   - Sleep: 7.5 hrs (or whatever is in the CSV)
   - Steps: 8,200 (or whatever is in the CSV)
   - Calories: 2,150 (or whatever is in the CSV)
2. **Mood Prediction Card** showing the forecast + drivers

---

## 📊 How the Data Flows

```
Survey Answers          Health Data CSV
    ↓                        ↓
    └────────┬───────────────┘
             ↓
    Feature Engineering
    (real sleep, mapped steps/calories)
             ↓
    Gradient Boosting Model
             ↓
    Prediction Score + Health Data
             ↓
    Mobile App displays both
```

---

## 🎯 Demo Data in CSV

The `health_data.csv` has 10 example days:
- **Low activity days**: 4,800-6,500 steps, 5.9-6.8 hrs sleep → should predict lower mood
- **High activity days**: 10,300-12,400 steps, 7.8-8.5 hrs sleep → should predict higher mood

When demoing, try different survey combinations and watch how the actual health data influences the prediction.

---

## 📝 Customizing Demo Data

### Add more days:
```csv
date,user_id,sleep_hours,steps,calories_burned
2024-01-25,user_demo,7.2,9500,2250
2024-01-26,user_demo,8.1,11000,2550
```

### Change demo user:
In `predictor.py`, line with `get_today_health_data()`, change:
```python
def get_today_health_data(user_id: str = "user_demo") -> dict:
```
to:
```python
def get_today_health_data(user_id: str = "your_custom_user") -> dict:
```

Then add that user to health_data.csv.

---

## 🔧 Feature Mappings (Technical Reference)

These are the transformations applied when health data is available:

### Sleep Hours
- **Without health data**: Map survey sleep_quality (1-5) → hours using fixed table
- **With health data**: Use actual sleep_hours directly

### Activity Metrics (Walk Amount, Activity Mean)
- **Without health data**: Average of energy_today + calmness
- **With health data**: `min(5, max(1, steps / 4000))`
  - Example: 8,000 steps → activity level ~2

### Exercise Intensity
- **Without health data**: Average of energy + stress
- **With health data**: `min(5, max(1, (calories - 1000) / 400))`
  - Example: 2,150 calories → exercise intensity ~2.9

### Other Features
These still come from survey (not affected by health data):
- happy, sad, sadornot (from mood_today)
- stress_level (from stress_today)
- conversation_duration, conversation_count (from social_connection)
- phq9_score (calculated from stress + inverse mood)
- phone_locked_duration, phone_lock_events, screen_off_* (from sleep_quality)

---

## ⚠️ Important Notes

1. **This is demo mode**: The health data comes from a CSV, not real Apple Health
2. **User is "user_demo"**: The code always loads data for this user ID
3. **Latest data is used**: If multiple dates exist, the most recent entry is used
4. **Feature scaling**: The mappings (steps → activity, calories → exercise) are rough approximations. Real HealthKit data ranges may need recalibration.

---

## 🔮 Next Steps for Real Integration

When you're ready to implement actual Apple Health:

1. **Remove** the CSV-based system
2. **Add** HealthKit query in iOS
3. **Pass** health data from the app to the API
4. **Update** feature mappings based on real data ranges
5. **Retrain** the model if needed to calibrate against actual HealthKit metrics

The current implementation is structured to make this swap straightforward.

---

## 🐛 Troubleshooting

### Health data card doesn't appear
- Check that `health_data.csv` exists in `mood_prediction/`
- Check that the user ID matches ("user_demo")
- Check API logs to see if health data was loaded

### Predictions don't change with different survey answers
- This is expected initially—the model may need more training data
- Try extreme answers (all 1s vs all 5s) to see if the effect is large

### "Model has not been trained yet" error
- Run: `POST http://localhost:8000/train` to train the model first

---

## 📞 Questions?

Refer to `APPLE_HEALTH_DEMO.md` for detailed architecture and feature engineering explanations.
