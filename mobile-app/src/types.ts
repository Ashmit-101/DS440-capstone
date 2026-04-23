export type SurveyField = {
  key: string;
  label: string;
  description: string;
  scale_low: string;
  scale_high: string;
};

export type SurveySchemaResponse = {
  fields: SurveyField[];
};

export type ManualPredictionRequest = Record<string, number | string>;

export type HealthData = {
  sleep_hours?: number | null;
  steps?: number | null;
  calories_burned?: number | null;
};

export type PredictionResponse = {
  features_from_date: string;
  prediction_for_date: string;
  predicted_happy_score: number;
  model_cv_mae?: number | null;
  model_cv_std?: number | null;
  summary?: string | null;
  likely_drivers?: string[] | null;
  confidence_note?: string | null;
  health_data?: HealthData | null;
  forecast_descriptor?: string | null;
  forecast_range_low?: number | null;
  forecast_range_high?: number | null;
  forecast_range_label?: string | null;
};
