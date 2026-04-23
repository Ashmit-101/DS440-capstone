import {
  ManualPredictionRequest,
  PredictionResponse,
  SurveySchemaResponse,
} from "./types";

// On web, use relative URLs so the request goes to whatever origin is serving the app.
// On native, fall back to the env var or localhost.
const fallbackBaseUrl =
  typeof window !== "undefined" ? "" : "http://localhost:8000";

export const API_BASE_URL =
  process.env.EXPO_PUBLIC_API_BASE_URL?.replace(/\/$/, "") ?? fallbackBaseUrl;

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
    ...init,
  });

  if (!response.ok) {
    const body = await response.json().catch(() => null);
    const detail =
      typeof body?.detail === "string"
        ? body.detail
        : "Request failed. Check the API base URL and backend status.";
    throw new Error(detail);
  }

  return response.json() as Promise<T>;
}

export function fetchSurveySchema() {
  return request<SurveySchemaResponse>("/survey/schema");
}

export function submitManualPrediction(payload: ManualPredictionRequest) {
  return request<PredictionResponse>("/predict/manual", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}
