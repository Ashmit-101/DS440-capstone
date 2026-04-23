import { useEffect, useMemo, useState } from "react";
import {
  ActivityIndicator,
  Pressable,
  SafeAreaView,
  ScrollView,
  StatusBar,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";

import { API_BASE_URL, fetchSurveySchema, submitManualPrediction } from "./src/api";
import { PredictionResponse, SurveyField } from "./src/types";

const LIKERT_OPTIONS = [1, 2, 3, 4, 5];

function buildScoreTone(score: number) {
  if (score >= 4.1) {
    return { label: "High", accent: "#166534", panel: "#dcfce7" };
  }
  if (score >= 3.1) {
    return { label: "Steady", accent: "#9a3412", panel: "#ffedd5" };
  }
  return { label: "Watch", accent: "#991b1b", panel: "#fee2e2" };
}

export default function App() {
  const [fields, setFields] = useState<SurveyField[]>([]);
  const [responses, setResponses] = useState<Record<string, number>>({});
  const [journalNote, setJournalNote] = useState("");
  const [activeStep, setActiveStep] = useState(0);
  const [prediction, setPrediction] = useState<PredictionResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;

    async function loadSchema() {
      try {
        setLoading(true);
        const schema = await fetchSurveySchema();
        if (!active) {
          return;
        }
        setFields(schema.fields);
        setActiveStep(0);
      } catch (loadError) {
        if (!active) {
          return;
        }
        setError(
          loadError instanceof Error
            ? loadError.message
            : "Unable to load survey schema.",
        );
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    }

    loadSchema();

    return () => {
      active = false;
    };
  }, []);

  const answeredCount = useMemo(
    () => fields.filter((field) => responses[field.key] !== undefined).length,
    [fields, responses],
  );

  const currentStep = Math.min(activeStep, Math.max(fields.length - 1, 0));
  const currentField = fields[currentStep] ?? null;
  const allQuestionsAnswered = fields.length > 0 && answeredCount === fields.length;
  const scoreTone = prediction ? buildScoreTone(prediction.predicted_happy_score) : null;

  function setAnswer(fieldKey: string, value: number) {
    setResponses((current) => ({
      ...current,
      [fieldKey]: value,
    }));
    if (currentStep < fields.length - 1) {
      setActiveStep(currentStep + 1);
    }
    setPrediction(null);
    setError(null);
  }

  function goToPreviousQuestion() {
    if (currentStep === 0) {
      return;
    }
    setActiveStep(currentStep - 1);
    setPrediction(null);
  }

  async function handleSubmit() {
    try {
      setSubmitting(true);
      setError(null);
      const result = await submitManualPrediction({
        ...responses,
        journal_note: journalNote.trim(),
      });
      setPrediction(result);
    } catch (submitError) {
      setError(
        submitError instanceof Error
          ? submitError.message
          : "Unable to get a prediction.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <SafeAreaView style={styles.safeArea}>
      <StatusBar barStyle="dark-content" />
      <ScrollView contentContainerStyle={styles.container}>
        <View style={styles.hero}>
          <Text style={styles.kicker}>Daily mood check-in</Text>
          <Text style={styles.title}>A shorter check-in with a more usable result.</Text>
          <Text style={styles.subtitle}>
            Fewer questions, clearer language, and a forecast that reads like a product instead
            of a raw model dump.
          </Text>
          <Text style={styles.baseUrl}>API: {API_BASE_URL}</Text>
        </View>

        <View style={styles.infoCard}>
          <Text style={styles.infoTitle}>How this works</Text>
          <Text style={styles.infoText}>
            Fill out your daily check-in below. When you generate a forecast, we'll combine your
            survey answers into a forecast band for tomorrow instead of showing a raw model score.
          </Text>
        </View>

        {loading ? (
          <View style={styles.centerState}>
            <ActivityIndicator size="large" color="#0f766e" />
            <Text style={styles.stateText}>Loading your check-in...</Text>
          </View>
        ) : (
          <View style={styles.formShell}>
            <View style={styles.progressRow}>
              <Text style={styles.progressLabel}>
                {answeredCount} of {fields.length} answered
              </Text>
              <Text style={styles.progressLabel}>
                {Math.round((answeredCount / Math.max(fields.length, 1)) * 100)}%
              </Text>
            </View>
            <View style={styles.progressTrack}>
              <View
                style={[
                  styles.progressFill,
                  { width: `${(answeredCount / Math.max(fields.length, 1)) * 100}%` },
                ]}
              />
            </View>

            {currentField ? (
              <View style={styles.questionCard}>
                <Text style={styles.questionStep}>
                  Question {Math.min(currentStep + 1, fields.length)} of {fields.length}
                </Text>
                <Text style={styles.questionTitle}>{currentField.label}</Text>
                <Text style={styles.questionDescription}>{currentField.description}</Text>
                <View style={styles.scaleLegend}>
                  <Text style={styles.scaleLegendText}>{currentField.scale_low}</Text>
                  <Text style={styles.scaleLegendText}>{currentField.scale_high}</Text>
                </View>
                <View style={styles.scaleRow}>
                  {LIKERT_OPTIONS.map((value) => {
                    const selected = responses[currentField.key] === value;
                    return (
                      <Pressable
                        key={`${currentField.key}-${value}`}
                        onPress={() => setAnswer(currentField.key, value)}
                        style={[styles.scaleButton, selected && styles.scaleButtonSelected]}
                      >
                        <Text
                          style={[
                            styles.scaleButtonText,
                            selected && styles.scaleButtonTextSelected,
                          ]}
                        >
                          {value}
                        </Text>
                      </Pressable>
                    );
                  })}
                </View>

                <View style={styles.navRow}>
                  <Pressable
                    onPress={goToPreviousQuestion}
                    disabled={currentStep === 0}
                    style={[
                      styles.secondaryButton,
                      currentStep === 0 && styles.secondaryButtonDisabled,
                    ]}
                  >
                    <Text style={styles.secondaryButtonText}>Back</Text>
                  </Pressable>
                  <Text style={styles.navHint}>
                    Tap a score to move this answer into your daily check-in.
                  </Text>
                </View>
              </View>
            ) : null}

            <View style={styles.notesCard}>
              <Text style={styles.notesTitle}>Optional note</Text>
              <Text style={styles.notesDescription}>
                Keep a short sentence here for the future text-analysis version. It is not used by
                the model yet.
              </Text>
              <TextInput
                multiline
                numberOfLines={4}
                maxLength={280}
                onChangeText={setJournalNote}
                placeholder="Today felt scattered, but a long walk helped."
                placeholderTextColor="#94a3b8"
                style={styles.notesInput}
                value={journalNote}
              />
            </View>

            <Pressable
              disabled={!allQuestionsAnswered || submitting}
              onPress={handleSubmit}
              style={[
                styles.submitButton,
                (!allQuestionsAnswered || submitting) && styles.submitButtonDisabled,
              ]}
            >
              {submitting ? (
                <ActivityIndicator color="#ffffff" />
              ) : (
                <Text style={styles.submitButtonText}>Generate forecast</Text>
              )}
            </Pressable>
          </View>
        )}

        {error ? (
          <View style={styles.errorBox}>
            <Text style={styles.errorText}>{error}</Text>
          </View>
        ) : null}

        {prediction && scoreTone ? (
          <View>
            {/* Show actual health data used in prediction */}
            {prediction.health_data && (
              prediction.health_data.sleep_hours != null ||
              prediction.health_data.steps != null ||
              prediction.health_data.calories_burned != null
            ) ? (
              <View style={styles.healthDataCard}>
                <View style={styles.healthDataHeaderRow}>
                  <Text style={styles.healthDataTitle}>Health data used</Text>
                  <Text style={styles.healthDataBadge}>Apple Health (demo)</Text>
                </View>
                <View style={styles.healthMetricsRow}>
                  {prediction.health_data.sleep_hours != null ? (
                    <View style={styles.healthMetricChip}>
                      <Text style={styles.healthMetricLabel}>Sleep</Text>
                      <Text style={styles.healthMetricValue}>
                        {prediction.health_data.sleep_hours.toFixed(1)} hrs
                      </Text>
                    </View>
                  ) : null}
                  {prediction.health_data.steps != null ? (
                    <View style={styles.healthMetricChip}>
                      <Text style={styles.healthMetricLabel}>Steps</Text>
                      <Text style={styles.healthMetricValue}>
                        {Math.round(prediction.health_data.steps).toLocaleString()}
                      </Text>
                    </View>
                  ) : null}
                  {prediction.health_data.calories_burned != null ? (
                    <View style={styles.healthMetricChip}>
                      <Text style={styles.healthMetricLabel}>Calories</Text>
                      <Text style={styles.healthMetricValue}>
                        {Math.round(prediction.health_data.calories_burned)}
                      </Text>
                    </View>
                  ) : null}
                </View>
              </View>
            ) : null}

            <View style={[styles.resultCard, { backgroundColor: scoreTone.panel }]}>
              <View style={styles.resultHeaderRow}>
                <Text style={[styles.resultTitle, { color: scoreTone.accent }]}>Tomorrow</Text>
                <View style={[styles.resultBadge, { borderColor: scoreTone.accent }]}>
                  <Text style={[styles.resultBadgeText, { color: scoreTone.accent }]}>
                    {scoreTone.label}
                  </Text>
                </View>
              </View>

              <Text style={styles.resultValue}>
                {prediction.forecast_descriptor ?? "Forecast Ready"}
              </Text>
              {prediction.forecast_range_label ? (
                <Text style={styles.resultRange}>
                  Range: {prediction.forecast_range_label}
                </Text>
              ) : null}
              <Text style={styles.resultSummary}>
                {prediction.summary ?? "The forecast is ready."}
              </Text>

              {prediction.likely_drivers?.length ? (
                <View style={styles.driverList}>
                  {prediction.likely_drivers.map((driver) => (
                    <View key={driver} style={styles.driverChip}>
                      <Text style={styles.driverChipText}>{driver}</Text>
                    </View>
                  ))}
                </View>
              ) : null}

              <View style={styles.resultMetaBlock}>
                <Text style={styles.resultMeta}>
                  Forecast for {prediction.prediction_for_date}
                </Text>
                {prediction.confidence_note ? (
                  <Text style={styles.resultMeta}>{prediction.confidence_note}</Text>
                ) : null}
                {prediction.model_cv_mae !== null && prediction.model_cv_mae !== undefined ? (
                  <Text style={styles.resultMeta}>
                    Model MAE: {prediction.model_cv_mae.toFixed(2)}
                    {prediction.model_cv_std !== null && prediction.model_cv_std !== undefined
                      ? ` (+/- ${prediction.model_cv_std.toFixed(2)})`
                      : ""}
                  </Text>
                ) : null}
              </View>
            </View>
          </View>
        ) : null}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: {
    flex: 1,
    backgroundColor: "#f6f4ee",
  },
  container: {
    paddingHorizontal: 18,
    paddingTop: 18,
    paddingBottom: 42,
    gap: 18,
  },
  hero: {
    backgroundColor: "#fb7185",
    borderRadius: 28,
    padding: 20,
    gap: 8,
  },
  kicker: {
    color: "#4c0519",
    fontSize: 12,
    fontWeight: "700",
    letterSpacing: 1.1,
    textTransform: "uppercase",
  },
  title: {
    color: "#fff7ed",
    fontSize: 30,
    lineHeight: 35,
    fontWeight: "800",
  },
  subtitle: {
    color: "#fff1f2",
    fontSize: 15,
    lineHeight: 22,
  },
  baseUrl: {
    color: "#ffe4e6",
    fontSize: 12,
  },
  infoCard: {
    backgroundColor: "#ecfdf5",
    borderRadius: 20,
    padding: 18,
    gap: 10,
    borderWidth: 1,
    borderColor: "#a7f3d0",
  },
  infoTitle: {
    color: "#065f46",
    fontSize: 16,
    fontWeight: "700",
  },
  infoText: {
    color: "#047857",
    fontSize: 14,
    lineHeight: 20,
  },
  centerState: {
    alignItems: "center",
    justifyContent: "center",
    paddingVertical: 48,
    gap: 12,
  },
  stateText: {
    color: "#334155",
    fontSize: 15,
  },
  formShell: {
    gap: 14,
  },
  progressRow: {
    flexDirection: "row",
    justifyContent: "space-between",
  },
  progressLabel: {
    color: "#475569",
    fontSize: 13,
    fontWeight: "600",
  },
  progressTrack: {
    height: 10,
    borderRadius: 999,
    backgroundColor: "#e2e8f0",
    overflow: "hidden",
  },
  progressFill: {
    height: "100%",
    borderRadius: 999,
    backgroundColor: "#0f766e",
  },
  questionCard: {
    backgroundColor: "#fffdf8",
    borderRadius: 24,
    padding: 18,
    borderWidth: 1,
    borderColor: "#e7e5e4",
    gap: 14,
  },
  questionStep: {
    color: "#0f766e",
    fontSize: 12,
    fontWeight: "700",
    textTransform: "uppercase",
    letterSpacing: 1,
  },
  questionTitle: {
    color: "#111827",
    fontSize: 26,
    lineHeight: 30,
    fontWeight: "800",
  },
  questionDescription: {
    color: "#475569",
    fontSize: 15,
    lineHeight: 22,
  },
  scaleLegend: {
    flexDirection: "row",
    justifyContent: "space-between",
  },
  scaleLegendText: {
    color: "#64748b",
    fontSize: 12,
    fontWeight: "600",
  },
  scaleRow: {
    flexDirection: "row",
    gap: 8,
  },
  scaleButton: {
    flex: 1,
    minHeight: 54,
    borderRadius: 16,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "#fff7ed",
    borderWidth: 1,
    borderColor: "#fdba74",
  },
  scaleButtonSelected: {
    backgroundColor: "#0f766e",
    borderColor: "#0f766e",
    transform: [{ translateY: -2 }],
  },
  scaleButtonText: {
    color: "#9a3412",
    fontSize: 18,
    fontWeight: "800",
  },
  scaleButtonTextSelected: {
    color: "#ecfeff",
  },
  navRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
  },
  navHint: {
    flex: 1,
    color: "#64748b",
    fontSize: 13,
    lineHeight: 18,
  },
  secondaryButton: {
    minHeight: 42,
    paddingHorizontal: 16,
    borderRadius: 999,
    borderWidth: 1,
    borderColor: "#cbd5e1",
    justifyContent: "center",
    backgroundColor: "#ffffff",
  },
  secondaryButtonDisabled: {
    opacity: 0.4,
  },
  secondaryButtonText: {
    color: "#334155",
    fontSize: 14,
    fontWeight: "700",
  },
  notesCard: {
    backgroundColor: "#fffdf8",
    borderRadius: 24,
    padding: 18,
    borderWidth: 1,
    borderColor: "#e7e5e4",
    gap: 10,
  },
  notesTitle: {
    color: "#111827",
    fontSize: 18,
    fontWeight: "700",
  },
  notesDescription: {
    color: "#64748b",
    fontSize: 14,
    lineHeight: 20,
  },
  notesInput: {
    minHeight: 94,
    borderRadius: 18,
    padding: 14,
    backgroundColor: "#f8fafc",
    borderWidth: 1,
    borderColor: "#cbd5e1",
    color: "#0f172a",
    fontSize: 15,
    lineHeight: 21,
    textAlignVertical: "top",
  },
  submitButton: {
    minHeight: 56,
    borderRadius: 18,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "#111827",
  },
  submitButtonDisabled: {
    opacity: 0.45,
  },
  submitButtonText: {
    color: "#ffffff",
    fontSize: 16,
    fontWeight: "800",
  },
  errorBox: {
    backgroundColor: "#fff1f2",
    borderRadius: 18,
    padding: 14,
    borderWidth: 1,
    borderColor: "#fecdd3",
  },
  errorText: {
    color: "#9f1239",
    fontSize: 14,
    lineHeight: 20,
  },
  resultCard: {
    borderRadius: 24,
    padding: 18,
    gap: 12,
  },
  resultHeaderRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
  },
  resultTitle: {
    fontSize: 22,
    fontWeight: "800",
  },
  resultBadge: {
    borderWidth: 1,
    borderRadius: 999,
    paddingHorizontal: 12,
    paddingVertical: 6,
  },
  resultBadgeText: {
    fontSize: 12,
    fontWeight: "800",
    textTransform: "uppercase",
  },
  resultValue: {
    color: "#111827",
    fontSize: 34,
    fontWeight: "900",
  },
  resultRange: {
    color: "#475569",
    fontSize: 14,
    lineHeight: 20,
  },
  resultSummary: {
    color: "#1f2937",
    fontSize: 16,
    lineHeight: 23,
  },
  driverList: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 8,
  },
  driverChip: {
    borderRadius: 999,
    backgroundColor: "rgba(255,255,255,0.55)",
    paddingHorizontal: 12,
    paddingVertical: 8,
  },
  driverChipText: {
    color: "#1f2937",
    fontSize: 13,
    fontWeight: "600",
  },
  resultMetaBlock: {
    gap: 6,
  },
  resultMeta: {
    color: "#374151",
    fontSize: 13,
    lineHeight: 18,
  },
  healthDataCard: {
    backgroundColor: "#f0fdf4",
    borderRadius: 20,
    padding: 16,
    borderWidth: 1,
    borderColor: "#bbf7d0",
    gap: 12,
    marginBottom: 8,
  },
  healthDataHeaderRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
  },
  healthDataTitle: {
    color: "#15803d",
    fontSize: 16,
    fontWeight: "700",
  },
  healthDataBadge: {
    color: "#16a34a",
    fontSize: 11,
    fontWeight: "600",
    textTransform: "uppercase",
  },
  healthMetricsRow: {
    flexDirection: "row",
    gap: 10,
  },
  healthMetricChip: {
    flex: 1,
    borderRadius: 14,
    padding: 10,
    backgroundColor: "#fff",
    borderWidth: 1,
    borderColor: "#bbf7d0",
    gap: 3,
  },
  healthMetricLabel: {
    color: "#65a30d",
    fontSize: 11,
    fontWeight: "700",
    textTransform: "uppercase",
  },
  healthMetricValue: {
    color: "#166534",
    fontSize: 14,
    fontWeight: "700",
  },
});
