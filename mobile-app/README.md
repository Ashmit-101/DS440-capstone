# Mood Prediction Mobile POC

Expo React Native app for the manual-survey prediction flow.

## Run

1. Start the FastAPI backend on port `8000`.
2. In this folder, install dependencies with `npm install`.
3. Set the API URL for your simulator or device:

```bash
EXPO_PUBLIC_API_BASE_URL=http://127.0.0.1:8000 npm start
```

If you test on a physical device, replace `127.0.0.1` with your machine's LAN IP.

## API contract used

- `GET /survey/schema`
- `POST /predict/manual`
