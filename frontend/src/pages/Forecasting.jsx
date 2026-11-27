import { useCallback, useEffect, useRef, useState } from "react";
import { authFetch } from "../api";
import { useAuth } from "../AuthContext";
// The shared helpers are behaviourally identical to the local copies this page
// used to define; the aliases keep the call sites unchanged.
import { formatQuantity as formatNumber, formatDateTime as formatTimestamp } from "../format";
import PageHeader from "../components/PageHeader";

const RESULT_PAGE_SIZE = 100;
const EVALUATION_PAGE_SIZE = 100;
const WINDOW_OPTIONS = [7, 14, 30];
const HISTORY_OPTIONS = [90, 180, 365];
const M5_EVALUATION_RUN_MODEL_NAME = "M5 fixed evaluation (4 models)";

const FORECAST_TABS = [
  { id: "forecast", title: "Forecast" },
  { id: "evaluation", title: "Evaluate" },
  { id: "stockout", title: "Stockout" },
  { id: "runs", title: "Runs" },
  { id: "predictions", title: "Predictions" },
];

function errorMessage(data, fallback) {
  if (typeof data?.detail === "string") return data.detail;
  if (Array.isArray(data?.detail)) {
    return data.detail.map(item => item.msg).filter(Boolean).join("; ") || fallback;
  }
  if (data?.detail && typeof data.detail === "object") {
    const message = data.detail.message || data.detail.error;
    const available = Array.isArray(data.detail.available_model_names)
      ? data.detail.available_model_names.filter(Boolean)
      : [];
    if (message && available.length) return `${message} Available: ${available.join(", ")}.`;
    if (typeof message === "string") return message;
  }
  return fallback;
}

function formatMetric(value, suffix = "") {
  return value === null || value === undefined
    ? "—"
    : `${new Intl.NumberFormat(undefined, { maximumFractionDigits: 4 }).format(value)}${suffix}`;
}

function statusClass(status) {
  if (status === "success") return "badge-success";
  if (status === "failed") return "badge-danger";
  return "badge-warning";
}

function parseRunParameters(value) {
  if (!value) return {};
  if (typeof value === "object") return value;
  try {
    return JSON.parse(value);
  } catch {
    return {};
  }
}

function comparisonModelLabel(model) {
  if (model === "rolling_average_7d") return "7-day rolling average";
  if (model === "rolling_average_14d") return "14-day rolling average";
  if (model === "rolling_average_30d") return "30-day rolling average";
  if (model === "arima_with_fallback") return "ARIMA(1,1,1) + 7-day fallback";
  if (model === "tie") return "Tie";
  return "Unavailable";
}

const COMPARISON_MODELS = [
  { key: "rolling_average_7d", label: "7-day rolling average" },
  { key: "rolling_average_14d", label: "14-day rolling average" },
  { key: "rolling_average_30d", label: "30-day rolling average" },
  { key: "arima_with_fallback", label: "ARIMA(1,1,1) + 7-day fallback" },
];

const M5_EXPERIMENTS = [
  {
    key: "development",
    label: "Development validation",
    training: "d_1–d_1885 (1,885 days)",
    holdout: "d_1886–d_1913 (28 days)",
  },
  {
    key: "final",
    label: "Final validation",
    training: "d_1–d_1913 (1,913 days)",
    holdout: "d_1914–d_1941 (28 days)",
  },
];

const STOCKOUT_COMPARISON_MODELS = [
  { value: "7-day rolling average", label: "7-day rolling average" },
  { value: "14-day rolling average", label: "14-day rolling average" },
  { value: "30-day rolling average", label: "30-day rolling average" },
  { value: "ARIMA(1,1,1) + rolling fallback", label: "ARIMA with 7-day fallback" },
];

function stockoutModelOptions(run) {
  if (!run) return [];
  if (run.model_name === "Forecast comparison (4 models)" || run.model_name === M5_EVALUATION_RUN_MODEL_NAME) {
    return STOCKOUT_COMPARISON_MODELS;
  }
  if (run.model_name === "ARIMA(1,1,1)") {
    return [{ value: "ARIMA(1,1,1) + rolling fallback", label: "ARIMA with rolling fallback" }];
  }
  return [{ value: run.model_name, label: run.model_name }];
}

function stockoutRiskClass(risk) {
  if (risk === "critical") return "badge-danger";
  if (risk === "high" || risk === "warning") return "badge-warning";
  if (risk === "healthy") return "badge-success";
  return "badge-neutral";
}

function isIntegerInRange(value, minimum, maximum) {
  return value !== "" && Number.isInteger(Number(value)) && Number(value) >= minimum && Number(value) <= maximum;
}

function isNumberInRange(value, minimum, maximum) {
  return value !== "" && Number.isFinite(Number(value)) && Number(value) >= minimum && Number(value) <= maximum;
}

function compactIdentity(name, code) {
  const title = name || code || "—";
  if (!code || !name) return { title, detail: "" };
  const normalize = value => value.replace(/[^a-z0-9]/gi, "").toLowerCase();
  const nameKey = normalize(name);
  const codeKey = normalize(code);
  const trailingKey = normalize(code.split("::").pop());
  if (
    !codeKey
    || nameKey === codeKey
    || nameKey.includes(codeKey)
    || codeKey.includes(nameKey)
    || (trailingKey && nameKey.includes(trailingKey))
  ) {
    return { title, detail: "" };
  }
  return { title, detail: code };
}

function PredictionTable({ results, resultMeta, resultOffset, resultsLoading, currentPage, pageCount, onPrevious, onNext }) {
  const models = [...new Set(results.map(result => result.model_name).filter(Boolean))];
  const showModel = models.length > 1;
  const generatedAt = results.find(result => result.generated_at)?.generated_at;

  return (
    <>
      <p className="muted" style={{ margin: "0 0 12px" }}>
        {showModel ? `${models.length} models` : models[0]}
        {generatedAt ? ` · generated ${formatTimestamp(generatedAt)}` : ""}
      </p>
      <div className="table-container">
        <table aria-label="Saved forecast predictions">
          <thead>
            <tr>
              <th>Date</th>
              <th>Product</th>
              <th>Warehouse</th>
              {showModel && <th>Model</th>}
              <th style={{ textAlign: "right" }}>Daily demand</th>
            </tr>
          </thead>
          <tbody>
            {results.map(result => {
              const product = compactIdentity(result.product_name, result.sku);
              const warehouse = compactIdentity(result.warehouse_name, result.warehouse_code);
              return (
                <tr key={result.id}>
                  <td style={{ whiteSpace: "nowrap" }}>{result.forecast_date}</td>
                  <td>
                    <div style={{ fontWeight: 600 }}>{product.title}</div>
                    {product.detail && <div className="muted" style={{ fontSize: "0.75rem" }}>{product.detail}</div>}
                  </td>
                  <td>
                    <div>{warehouse.title}</div>
                    {warehouse.detail && <div className="muted" style={{ fontSize: "0.75rem" }}>{warehouse.detail}</div>}
                  </td>
                  {showModel && <td>{result.model_name}</td>}
                  <td style={{ textAlign: "right", fontVariantNumeric: "tabular-nums", fontWeight: 700 }}>{formatNumber(result.predicted_demand)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {resultMeta && resultMeta.total > resultMeta.limit && (
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginTop: 12 }}>
          <button className="btn btn-ghost btn-sm" type="button" disabled={resultOffset === 0 || resultsLoading} onClick={onPrevious}>Previous</button>
          <span className="muted">Page {currentPage} of {pageCount}</span>
          <button className="btn btn-ghost btn-sm" type="button" disabled={resultOffset + resultMeta.limit >= resultMeta.total || resultsLoading} onClick={onNext}>Next</button>
        </div>
      )}
    </>
  );
}

export default function Forecasting() {
  const { can } = useAuth();
  const canRun = can("reports", "write");
  const [activeSection, setActiveSection] = useState(canRun ? "forecast" : "runs");
  const [model, setModel] = useState("rolling_average");
  const [source, setSource] = useState("WMS");
  const [windowDays, setWindowDays] = useState(7);
  const [historyDays, setHistoryDays] = useState(365);
  const [seriesLimit, setSeriesLimit] = useState(1000);
  const [maxArimaSeries, setMaxArimaSeries] = useState(100);
  const [horizonDays, setHorizonDays] = useState(28);
  const [asOfDate, setAsOfDate] = useState("");
  const [running, setRunning] = useState(false);
  const [notice, setNotice] = useState(null);
  const [runs, setRuns] = useState([]);
  const [runsMeta, setRunsMeta] = useState(null);
  const [runsLoading, setRunsLoading] = useState(true);
  const [runsError, setRunsError] = useState("");
  const [selectedRunId, setSelectedRunId] = useState(null);
  const [resultOffset, setResultOffset] = useState(0);
  const [results, setResults] = useState([]);
  const [resultMeta, setResultMeta] = useState(null);
  const [resultsLoading, setResultsLoading] = useState(false);
  const [resultsError, setResultsError] = useState("");
  const [comparisonSource, setComparisonSource] = useState("WMS");
  const [comparisonHistoryDays, setComparisonHistoryDays] = useState(365);
  const [comparisonHorizonDays, setComparisonHorizonDays] = useState(28);
  const [comparisonSeriesLimit, setComparisonSeriesLimit] = useState(100);
  const [comparisonArimaLimit, setComparisonArimaLimit] = useState(100);
  const [comparisonAsOfDate, setComparisonAsOfDate] = useState("");
  const [comparing, setComparing] = useState(false);
  const [comparison, setComparison] = useState(null);
  const [comparisonError, setComparisonError] = useState("");
  const [m5Experiment, setM5Experiment] = useState("development");
  const [m5SeriesLimit, setM5SeriesLimit] = useState(100);
  const [m5ArimaLimit, setM5ArimaLimit] = useState(100);
  const [evaluatingM5, setEvaluatingM5] = useState(false);
  const [m5Evaluation, setM5Evaluation] = useState(null);
  const [m5EvaluationError, setM5EvaluationError] = useState("");
  const [m5EvaluationRunId, setM5EvaluationRunId] = useState(null);
  const [m5EvaluationOffset, setM5EvaluationOffset] = useState(0);
  const [m5EvaluationRows, setM5EvaluationRows] = useState([]);
  const [m5EvaluationMeta, setM5EvaluationMeta] = useState(null);
  const [m5EvaluationLoading, setM5EvaluationLoading] = useState(false);
  const [m5EvaluationRowsError, setM5EvaluationRowsError] = useState("");
  const [stockoutModel, setStockoutModel] = useState("");
  const [simulatedStartingStock, setSimulatedStartingStock] = useState("");
  const [defaultLeadTimeDays, setDefaultLeadTimeDays] = useState(5);
  const [defaultSafetyStock, setDefaultSafetyStock] = useState(30);
  const [criticalMaxDays, setCriticalMaxDays] = useState(3);
  const [highMaxDays, setHighMaxDays] = useState(7);
  const [warningMaxDays, setWarningMaxDays] = useState(14);
  const [receiptDraft, setReceiptDraft] = useState({ productId: "", warehouseId: "", arrivalDate: "", quantity: "", reference: "" });
  const [stockoutReceipts, setStockoutReceipts] = useState([]);
  const [stockoutRequest, setStockoutRequest] = useState(null);
  const [stockoutResult, setStockoutResult] = useState(null);
  const [stockoutOffset, setStockoutOffset] = useState(0);
  const [stockoutLoading, setStockoutLoading] = useState(false);
  const [stockoutError, setStockoutError] = useState("");
  const runsRequestRef = useRef(0);
  const runsAbortRef = useRef(null);
  const forecastActionRef = useRef(false);

  const loadRuns = useCallback(async ({ offset = 0, append = false, selectFirst = true } = {}) => {
    runsAbortRef.current?.abort();
    const controller = new AbortController();
    runsAbortRef.current = controller;
    const requestId = ++runsRequestRef.current;
    setRunsLoading(true);
    setRunsError("");
    try {
      const params = new URLSearchParams({ limit: "50", offset: String(offset) });
      const response = await authFetch(`/forecasts/runs?${params}`, { signal: controller.signal });
      const data = await response.json();
      if (!response.ok) throw new Error(errorMessage(data, "Could not load forecast runs."));
      if (requestId !== runsRequestRef.current) return;
      const nextRuns = data.data || [];
      setRuns(current => append ? [...current, ...nextRuns] : nextRuns);
      setRunsMeta(data.meta || null);
      setSelectedRunId(current => {
        if (append || !selectFirst) return current;
        if (nextRuns.some(run => run.id === current)) return current;
        return nextRuns.find(run => run.status === "success")?.id ?? nextRuns[0]?.id ?? null;
      });
    } catch (error) {
      if (error.name === "AbortError" || requestId !== runsRequestRef.current) return;
      setRunsError(error.message || "Could not load forecast runs.");
    } finally {
      if (requestId === runsRequestRef.current) setRunsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadRuns();
    return () => runsAbortRef.current?.abort();
  }, [loadRuns]);

  useEffect(() => {
    setComparison(null);
    setComparisonError("");
  }, [
    comparisonAsOfDate,
    comparisonArimaLimit,
    comparisonHistoryDays,
    comparisonHorizonDays,
    comparisonSeriesLimit,
    comparisonSource,
  ]);

  useEffect(() => {
    setM5EvaluationError("");
  }, [m5ArimaLimit, m5Experiment, m5SeriesLimit]);

  useEffect(() => {
    setStockoutResult(null);
    setStockoutRequest(null);
    setStockoutError("");
    setStockoutReceipts([]);
    setReceiptDraft({ productId: "", warehouseId: "", arrivalDate: "", quantity: "", reference: "" });
  }, [selectedRunId]);

  useEffect(() => {
    setStockoutResult(null);
    setStockoutRequest(null);
  }, [
    criticalMaxDays,
    defaultLeadTimeDays,
    defaultSafetyStock,
    highMaxDays,
    simulatedStartingStock,
    stockoutModel,
    stockoutReceipts,
    warningMaxDays,
  ]);

  useEffect(() => {
    if (!selectedRunId) {
      setResults([]);
      setResultMeta(null);
      setResultsError("");
      return undefined;
    }

    let active = true;
    const controller = new AbortController();
    const loadResults = async () => {
      setResultsLoading(true);
      setResultsError("");
      try {
        const params = new URLSearchParams({ limit: String(RESULT_PAGE_SIZE), offset: String(resultOffset) });
        const response = await authFetch(`/forecasts/runs/${selectedRunId}/results?${params}`, { signal: controller.signal });
        const data = await response.json();
        if (!response.ok) throw new Error(errorMessage(data, "Could not load forecast results."));
        if (active) {
          setResults(data.data || []);
          setResultMeta(data.meta || null);
        }
      } catch (error) {
        if (active && error.name !== "AbortError") setResultsError(error.message || "Could not load forecast results.");
      } finally {
        if (active) setResultsLoading(false);
      }
    };

    loadResults();
    return () => {
      active = false;
      controller.abort();
    };
  }, [resultOffset, selectedRunId]);

  useEffect(() => {
    if (!m5EvaluationRunId) {
      setM5EvaluationRows([]);
      setM5EvaluationMeta(null);
      setM5EvaluationRowsError("");
      return undefined;
    }

    let active = true;
    const controller = new AbortController();
    const loadEvaluationRows = async () => {
      setM5EvaluationLoading(true);
      setM5EvaluationRowsError("");
      try {
        const params = new URLSearchParams({
          limit: String(EVALUATION_PAGE_SIZE),
          offset: String(m5EvaluationOffset),
        });
        const response = await authFetch(`/forecasts/runs/${m5EvaluationRunId}/evaluation?${params}`, { signal: controller.signal });
        const data = await response.json();
        if (!response.ok) throw new Error(errorMessage(data, "Could not load the M5 evaluation report."));
        if (!active) return;
        const parameters = parseRunParameters(data.run?.parameters);
        setM5EvaluationRows(data.data || []);
        setM5EvaluationMeta(data.meta || null);
        setM5Evaluation(current => ({
          ...(current?.run_id === m5EvaluationRunId ? current : { run_id: m5EvaluationRunId }),
          protocol: data.protocol || parameters.evaluation_protocol || current?.protocol || null,
          metrics: data.summary || current?.metrics || null,
          better_by: data.better_by || current?.better_by || null,
          sampled_series: parameters.series_processed ?? current?.sampled_series,
          series_limit: parameters.series_limit ?? current?.series_limit,
          sample_truncated: parameters.series_sample_truncated ?? current?.sample_truncated,
          predictions_written: parameters.predictions_written ?? current?.predictions_written,
          evaluation_report_rows: parameters.evaluation_report_rows ?? current?.evaluation_report_rows,
          arima_series_processed: parameters.arima_series_processed ?? current?.arima_series_processed,
          fallback_series_processed: parameters.fallback_series_processed ?? current?.fallback_series_processed,
          fallback_reasons: parameters.fallback_reasons ?? current?.fallback_reasons,
        }));
      } catch (error) {
        if (active && error.name !== "AbortError") setM5EvaluationRowsError(error.message || "Could not load the M5 evaluation report.");
      } finally {
        if (active) setM5EvaluationLoading(false);
      }
    };

    loadEvaluationRows();
    return () => {
      active = false;
      controller.abort();
    };
  }, [m5EvaluationOffset, m5EvaluationRunId]);

  useEffect(() => {
    const selectedRun = runs.find(run => run.id === selectedRunId);
    if (selectedRun?.model_name === M5_EVALUATION_RUN_MODEL_NAME && selectedRun.id !== m5EvaluationRunId) {
      setM5Evaluation(null);
      setM5EvaluationRows([]);
      setM5EvaluationMeta(null);
      setM5EvaluationOffset(0);
      setM5EvaluationRunId(selectedRun.id);
    }
  }, [m5EvaluationRunId, runs, selectedRunId]);

  const runForecast = async (event) => {
    event.preventDefault();
    if (forecastActionRef.current) return;
    forecastActionRef.current = true;
    setRunning(true);
    setNotice(null);
    try {
      const payload = { source, horizon_days: Number(horizonDays), series_limit: Number(seriesLimit) };
      if (model === "arima") {
        payload.history_days = Number(historyDays);
        payload.fallback_window_days = Number(windowDays);
        payload.max_arima_series = Number(Math.min(maxArimaSeries, seriesLimit));
      } else {
        payload.window_days = Number(windowDays);
      }
      if (asOfDate) payload.as_of_date = asOfDate;
      const endpoint = model === "arima" ? "/forecasts/arima" : "/forecasts/rolling-average";
      const response = await authFetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(errorMessage(data, "Could not generate the forecast."));

      const modelSummary = model === "arima"
        ? ` ARIMA fit ${formatNumber(data.arima_series_processed)} series; rolling average handled ${formatNumber(data.fallback_series_processed)} fallback series${data.arima_sample_truncated ? ` (fit cap: ${formatNumber(data.max_arima_series)} series)` : ""}.`
        : "";
      setNotice({
        type: "success",
        text: `Generated ${formatNumber(data.predictions_written)} predictions for ${formatNumber(data.series_processed)} product and warehouse series through ${data.forecast_dates?.at(-1) || "the selected horizon"}.${modelSummary}`,
      });
      setM5Evaluation(null);
      setM5EvaluationRunId(null);
      setM5EvaluationRows([]);
      setM5EvaluationMeta(null);
      setM5EvaluationOffset(0);
      setResults([]);
      setResultMeta(null);
      setSelectedRunId(data.run_id);
      setResultOffset(0);
      await loadRuns({ offset: 0 });
      setSelectedRunId(data.run_id);
      setActiveSection("predictions");
    } catch (error) {
      setNotice({ type: "error", text: error.message || "Could not reach the API." });
      void loadRuns({ offset: 0 });
    } finally {
      setRunning(false);
      forecastActionRef.current = false;
    }
  };

  const compareModels = async (event) => {
    event.preventDefault();
    if (forecastActionRef.current) return;
    forecastActionRef.current = true;
    setComparing(true);
    setComparisonError("");
    setComparison(null);
    try {
      const payload = {
        source: comparisonSource,
        history_days: Number(comparisonHistoryDays),
        horizon_days: Number(comparisonHorizonDays),
        series_limit: Number(comparisonSeriesLimit),
        max_arima_series: Number(comparisonArimaLimit),
      };
      if (comparisonAsOfDate) payload.as_of_date = comparisonAsOfDate;
      const response = await authFetch("/forecasts/compare", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(errorMessage(data, "Could not compare the models."));
      setComparison(data);
      setM5Evaluation(null);
      setM5EvaluationRunId(null);
      setM5EvaluationRows([]);
      setM5EvaluationMeta(null);
      setM5EvaluationOffset(0);
      setResults([]);
      setResultMeta(null);
      setResultOffset(0);
      setSelectedRunId(data.run_id);
      await loadRuns({ offset: 0 });
      setSelectedRunId(data.run_id);
    } catch (error) {
      setComparisonError(error.message || "Could not reach the API.");
      void loadRuns({ offset: 0 });
    } finally {
      setComparing(false);
      forecastActionRef.current = false;
    }
  };

  const runM5Evaluation = async (event) => {
    event.preventDefault();
    if (forecastActionRef.current) return;
    forecastActionRef.current = true;
    setEvaluatingM5(true);
    setM5EvaluationError("");
    setM5Evaluation(null);
    setM5EvaluationRunId(null);
    setM5EvaluationRows([]);
    setM5EvaluationMeta(null);
    setM5EvaluationOffset(0);
    setM5EvaluationRowsError("");
    setResults([]);
    setResultMeta(null);
    setResultOffset(0);
    setSelectedRunId(null);
    try {
      const response = await authFetch("/forecasts/m5-evaluations", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          experiment: m5Experiment,
          series_limit: Number(m5SeriesLimit),
          max_arima_series: Number(m5ArimaLimit),
        }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(errorMessage(data, "Could not run the fixed M5 evaluation."));
      setM5Evaluation(data);
      setM5EvaluationRows([]);
      setM5EvaluationMeta(null);
      setM5EvaluationOffset(0);
      setM5EvaluationRunId(data.run_id);
      setResults([]);
      setResultMeta(null);
      setResultOffset(0);
      setSelectedRunId(data.run_id);
      await loadRuns({ offset: 0 });
      setSelectedRunId(data.run_id);
    } catch (error) {
      setM5EvaluationError(error.message || "Could not reach the API.");
      void loadRuns({ offset: 0, selectFirst: false });
    } finally {
      setEvaluatingM5(false);
      forecastActionRef.current = false;
    }
  };

  const selectRun = (runId) => {
    const run = runs.find(item => item.id === runId);
    setResults([]);
    setResultMeta(null);
    setResultOffset(0);
    setSelectedRunId(runId);
    if (run?.model_name === M5_EVALUATION_RUN_MODEL_NAME) {
      setM5Evaluation(null);
      setM5EvaluationRows([]);
      setM5EvaluationMeta(null);
      setM5EvaluationOffset(0);
      setM5EvaluationRunId(runId);
    } else {
      setM5Evaluation(null);
      setM5EvaluationRunId(null);
    }
  };

  const changeResultPage = (offset) => {
    setResults([]);
    setResultOffset(offset);
  };

  const changeM5EvaluationPage = (offset) => {
    setM5EvaluationRows([]);
    setM5EvaluationOffset(offset);
  };

  const currentPage = resultMeta ? Math.floor(resultMeta.offset / resultMeta.limit) + 1 : 1;
  const pageCount = resultMeta ? Math.max(1, Math.ceil(resultMeta.total / resultMeta.limit)) : 1;
  const m5EvaluationCurrentPage = m5EvaluationMeta ? Math.floor(m5EvaluationMeta.offset / m5EvaluationMeta.limit) + 1 : 1;
  const m5EvaluationPageCount = m5EvaluationMeta ? Math.max(1, Math.ceil(m5EvaluationMeta.total / m5EvaluationMeta.limit)) : 1;
  const selectedRun = runs.find(run => run.id === selectedRunId);
  const availableStockoutModels = stockoutModelOptions(selectedRun);
  const selectedStockoutModel = availableStockoutModels.some(option => option.value === stockoutModel)
    ? stockoutModel
    : availableStockoutModels[0]?.value || "";
  const selectedM5Experiment = M5_EXPERIMENTS.find(experiment => experiment.key === m5Experiment) || M5_EXPERIMENTS[0];
  const isForecastActionRunning = running || comparing || evaluatingM5 || stockoutLoading;
  const canLoadMoreRuns = runsMeta && runs.length < runsMeta.total;
  const riskThresholdsValid = (
    isIntegerInRange(criticalMaxDays, 0, 87)
    && isIntegerInRange(highMaxDays, 1, 88)
    && isIntegerInRange(warningMaxDays, 2, 89)
    && Number(criticalMaxDays) < Number(highMaxDays)
    && Number(highMaxDays) < Number(warningMaxDays)
  );
  const stockoutInputsValid = (
    isIntegerInRange(defaultLeadTimeDays, 0, 365)
    && isNumberInRange(defaultSafetyStock, 0, 1_000_000_000)
    && riskThresholdsValid
    && (selectedRun?.source !== "M5" || isNumberInRange(simulatedStartingStock, 0, 1_000_000_000))
  );
  const receiptDraftValid = (
    isIntegerInRange(receiptDraft.productId, 1, 2_147_483_647)
    && (!receiptDraft.warehouseId || isIntegerInRange(receiptDraft.warehouseId, 1, 2_147_483_647))
    && Boolean(receiptDraft.arrivalDate)
    && isNumberInRange(receiptDraft.quantity, 0.01, 1_000_000_000)
  );

  const requestStockoutPage = async (payload, offset) => {
    const params = new URLSearchParams({ limit: String(RESULT_PAGE_SIZE), offset: String(offset) });
    const response = await authFetch(`/forecasts/runs/${selectedRunId}/stockout-predictions?${params}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(errorMessage(data, "Could not calculate stockout risk."));
    return data;
  };

  const calculateStockoutRisk = async (event) => {
    event.preventDefault();
    if (!selectedRun || selectedRun.status !== "success") return;
    setStockoutLoading(true);
    setStockoutError("");
    setStockoutResult(null);
    const payload = {
      model_name: selectedStockoutModel,
      default_lead_time_days: Number(defaultLeadTimeDays),
      default_safety_stock: Number(defaultSafetyStock),
      critical_max_days: Number(criticalMaxDays),
      high_max_days: Number(highMaxDays),
      warning_max_days: Number(warningMaxDays),
      replenishments: stockoutReceipts.map(receipt => ({
        product_id: Number(receipt.productId),
        warehouse_id: receipt.warehouseId ? Number(receipt.warehouseId) : null,
        arrival_date: receipt.arrivalDate,
        quantity: Number(receipt.quantity),
        reference: receipt.reference,
      })),
    };
    if (selectedRun.source === "M5") payload.simulated_starting_stock = Number(simulatedStartingStock);
    try {
      const data = await requestStockoutPage(payload, 0);
      setStockoutRequest(payload);
      setStockoutResult(data);
      setStockoutOffset(0);
    } catch (error) {
      setStockoutError(error.message || "Could not calculate stockout risk.");
    } finally {
      setStockoutLoading(false);
    }
  };

  const changeStockoutPage = async (offset) => {
    if (!stockoutRequest || stockoutLoading) return;
    setStockoutLoading(true);
    setStockoutError("");
    try {
      const data = await requestStockoutPage(stockoutRequest, offset);
      setStockoutResult(data);
      setStockoutOffset(offset);
    } catch (error) {
      setStockoutError(error.message || "Could not load the next stockout page.");
    } finally {
      setStockoutLoading(false);
    }
  };

  const addStockoutReceipt = (event) => {
    event.preventDefault();
    if (!receiptDraftValid) return;
    setStockoutReceipts(current => [...current, { ...receiptDraft, key: `${Date.now()}-${current.length}` }]);
    setReceiptDraft({ productId: "", warehouseId: "", arrivalDate: "", quantity: "", reference: "" });
    setStockoutResult(null);
    setStockoutRequest(null);
  };

  const tabRefs = useRef([]);

  // Proper tablist keyboard model: arrow keys (and Home/End) move focus and
  // selection together. Switching tabs only changes which panel is visible; the
  // data effects key off the selected run, so nothing refetches here.
  const onTabKeyDown = (event) => {
    const deltas = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 };
    const currentIndex = Math.max(0, FORECAST_TABS.findIndex(tab => tab.id === activeSection));
    let nextIndex = null;
    if (event.key in deltas) nextIndex = (currentIndex + deltas[event.key] + FORECAST_TABS.length) % FORECAST_TABS.length;
    else if (event.key === "Home") nextIndex = 0;
    else if (event.key === "End") nextIndex = FORECAST_TABS.length - 1;
    if (nextIndex === null) return;
    event.preventDefault();
    setActiveSection(FORECAST_TABS[nextIndex].id);
    tabRefs.current[nextIndex]?.focus();
  };

  return (
    <section>
      <PageHeader
        eyebrow="Reports"
        title="Demand Forecasts"
        subtitle="Estimated daily demand by product and warehouse, from recorded sales"
      />

      {notice && (
        <div className={`alert alert-${notice.type}`} role={notice.type === "error" ? "alert" : "status"} style={{ marginBottom: 20 }}>
          <span>{notice.text}</span>
          <button className="btn btn-ghost btn-xs" type="button" aria-label="Dismiss message" onClick={() => setNotice(null)}>&times;</button>
        </div>
      )}

      <div className="forecast-nav" role="tablist" aria-label="Forecast workspace" onKeyDown={onTabKeyDown}>
        {FORECAST_TABS.map((item, index) => (
          <button
            key={item.id}
            ref={el => { tabRefs.current[index] = el; }}
            id={`forecast-tab-${item.id}`}
            className="forecast-nav-item"
            type="button"
            role="tab"
            aria-selected={activeSection === item.id}
            aria-controls={`forecast-panel-${item.id}`}
            tabIndex={activeSection === item.id ? 0 : -1}
            onClick={() => setActiveSection(item.id)}
          >
            {item.title}
          </button>
        ))}
      </div>

      <section
        id="forecast-panel-forecast"
        role="tabpanel"
        aria-labelledby="forecast-tab-forecast"
        tabIndex={0}
        hidden={activeSection !== "forecast"}
      >
      {canRun && (
        <div className="card" style={{ marginBottom: 24 }} aria-busy={isForecastActionRunning}>
          <div className="card-body">
            <h2 className="section-title">Generate a forecast</h2>
            <p className="muted" style={{ margin: "-6px 0 18px" }}>
              {model === "arima"
                ? "ARIMA(1,1,1) uses daily history with zero-sales days retained. Sparse histories, convergence problems, invalid predictions, and series outside the deterministic fit cap use the rolling-average fallback."
                : "The rolling average divides demand across every calendar day in the window. Dates without recorded demand count as zero."}
            </p>
            <form onSubmit={runForecast}>
              <fieldset disabled={isForecastActionRunning} style={{ border: 0, padding: 0, margin: 0 }}>
              <div className="form-grid" style={{ marginBottom: 18 }}>
                <div className="input-group">
                  <label className="input-label" htmlFor="forecast-model">Forecast model</label>
                  <select id="forecast-model" className="select" value={model} onChange={event => setModel(event.target.value)}>
                    <option value="rolling_average">Rolling average (Model A)</option>
                    <option value="arima">ARIMA(1,1,1) (Model B)</option>
                  </select>
                </div>
                <div className="input-group">
                  <label className="input-label" htmlFor="forecast-source">Demand source</label>
                  <select id="forecast-source" className="select" value={source} onChange={event => setSource(event.target.value)}>
                    <option value="WMS">Operational WMS demand</option>
                    <option value="M5">M5 sample data</option>
                  </select>
                  <span className="input-hint">
                    {source === "M5"
                      ? "Uses the isolated sample catalog; it does not change live stock."
                      : "Uses outbound demand recorded against active operational warehouses."}
                  </span>
                </div>
                <div className="input-group">
                  <label className="input-label" htmlFor="forecast-series-limit">Maximum forecast series</label>
                  <select id="forecast-series-limit" className="select" value={seriesLimit} onChange={event => {
                    const nextLimit = Number(event.target.value);
                    setSeriesLimit(nextLimit);
                    setMaxArimaSeries(current => Math.min(current, nextLimit));
                  }}>
                    {[100, 250, 500, 1000].map(size => <option key={size} value={size}>{size} series</option>)}
                  </select>
                  <span className="input-hint">A deterministic sample is used when more series are eligible.</span>
                </div>
                <div className="input-group">
                  <label className="input-label" htmlFor="forecast-window">{model === "arima" ? "Fallback window" : "History window"}</label>
                  <select id="forecast-window" className="select" value={windowDays} onChange={event => setWindowDays(Number(event.target.value))}>
                    {WINDOW_OPTIONS.map(days => <option key={days} value={days}>{days} days</option>)}
                  </select>
                  {model === "arima" && <span className="input-hint">Used only for series that need fallback.</span>}
                </div>
                {model === "arima" && (
                  <div className="input-group">
                    <label className="input-label" htmlFor="forecast-history">ARIMA training history</label>
                    <select id="forecast-history" className="select" value={historyDays} onChange={event => setHistoryDays(Number(event.target.value))}>
                      {HISTORY_OPTIONS.map(days => <option key={days} value={days}>{days} days</option>)}
                    </select>
                    <span className="input-hint">Uses at most the selected trailing calendar days.</span>
                  </div>
                )}
                {model === "arima" && (
                  <div className="input-group">
                    <label className="input-label" htmlFor="forecast-arima-limit">Maximum ARIMA fits</label>
                    <select id="forecast-arima-limit" className="select" value={maxArimaSeries} onChange={event => setMaxArimaSeries(Number(event.target.value))}>
                      {[25, 50, 100, 250].filter(size => size <= seriesLimit).map(size => <option key={size} value={size}>{size} series</option>)}
                    </select>
                    <span className="input-hint">Remaining eligible series use the rolling-average fallback.</span>
                  </div>
                )}
                <div className="input-group">
                  <label className="input-label" htmlFor="forecast-horizon">Forecast horizon</label>
                  <input id="forecast-horizon" className="input" type="number" min="1" max="90" step="1" value={horizonDays} onChange={event => setHorizonDays(event.target.value)} required />
                  <span className="input-hint">Number of days to predict after the cutoff, up to 90. Use at least 15 days for the default stockout risk bands.</span>
                </div>
                <div className="input-group">
                  <label className="input-label" htmlFor="forecast-as-of">Historical demand cutoff (optional)</label>
                  <input id="forecast-as-of" className="input" type="date" value={asOfDate} onChange={event => setAsOfDate(event.target.value)} />
                  <span className="input-hint">Use demand through this date; leave blank to use the latest available date.</span>
                </div>
              </div>
              </fieldset>
              <div style={{ display: "flex", justifyContent: "flex-end" }}>
                <button className="btn btn-primary" type="submit" disabled={isForecastActionRunning || Number(horizonDays) < 1 || Number(horizonDays) > 90}>
                  {running ? "Generating..." : "Generate Forecast"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
      </section>

      <section
        id="forecast-panel-evaluation"
        role="tabpanel"
        aria-labelledby="forecast-tab-evaluation"
        tabIndex={0}
        hidden={activeSection !== "evaluation"}
      >
      {canRun ? (
        <div className="card" style={{ marginBottom: 24 }} aria-busy={isForecastActionRunning}>
          <div className="card-body">
            <h2 className="section-title">M5 benchmark evaluation</h2>
            <p className="muted" style={{ margin: "-6px 0 18px" }}>
              Uses the fixed M5 28-day competition horizon. Training and holdout dates are locked so future demand cannot enter the model.
            </p>
            <form onSubmit={runM5Evaluation}>
              <fieldset disabled={isForecastActionRunning} style={{ border: 0, padding: 0, margin: 0 }}>
                <div className="form-grid" style={{ marginBottom: 18 }}>
                  <div className="input-group">
                    <label className="input-label" htmlFor="m5-experiment">Experiment</label>
                    <select id="m5-experiment" className="select" value={m5Experiment} onChange={event => setM5Experiment(event.target.value)}>
                      {M5_EXPERIMENTS.map(experiment => <option key={experiment.key} value={experiment.key}>{experiment.label}</option>)}
                    </select>
                    <span className="input-hint">Training: {selectedM5Experiment.training}. Holdout: {selectedM5Experiment.holdout}.</span>
                  </div>
                  <div className="input-group">
                    <label className="input-label" htmlFor="m5-series-limit">Maximum series</label>
                    <select id="m5-series-limit" className="select" value={m5SeriesLimit} onChange={event => {
                      const nextLimit = Number(event.target.value);
                      setM5SeriesLimit(nextLimit);
                      setM5ArimaLimit(current => Math.min(current, nextLimit));
                    }}>
                      {[50, 100, 250].map(size => <option key={size} value={size}>{size} series</option>)}
                    </select>
                    <span className="input-hint">A deterministic sample is disclosed in the saved report.</span>
                  </div>
                  <div className="input-group">
                    <label className="input-label" htmlFor="m5-arima-limit">Maximum ARIMA fits</label>
                    <select id="m5-arima-limit" className="select" value={m5ArimaLimit} onChange={event => setM5ArimaLimit(Number(event.target.value))}>
                      {[25, 50, 100, 250].filter(size => size <= m5SeriesLimit).map(size => <option key={size} value={size}>{size} series</option>)}
                    </select>
                    <span className="input-hint">Sparse, capped, or failed fits use a clearly labeled 7-day fallback.</span>
                  </div>
                </div>
              </fieldset>
              {m5EvaluationError && <div className="alert alert-error" role="alert" style={{ marginBottom: 16 }}>{m5EvaluationError}</div>}
              <div style={{ display: "flex", justifyContent: "flex-end" }}>
                <button className="btn btn-primary" type="submit" disabled={isForecastActionRunning}>
                  {evaluatingM5 ? "Evaluating models..." : "Run M5 Evaluation"}
                </button>
              </div>
            </form>
          </div>
        </div>
      ) : (
        <div className="card" style={{ marginBottom: 24 }}>
          <div className="card-body">
            <h2 className="section-title">M5 benchmark evaluation</h2>
            <p className="muted" style={{ margin: 0 }}>M5 benchmark evaluation requires reports write permission.</p>
          </div>
        </div>
      )}

      {canRun ? (
      <div className="card" style={{ marginBottom: 24 }} aria-busy={isForecastActionRunning}>
        <div className="card-body">
          <h2 className="section-title">Compare models on historical demand</h2>
          <p className="muted" style={{ margin: "-6px 0 18px" }}>
            All four models use the same training cutoff and holdout dates. Their per-product predictions are saved with model names and generation timestamps.
          </p>
          <form onSubmit={compareModels}>
          <fieldset disabled={isForecastActionRunning} style={{ border: 0, padding: 0, margin: 0 }}>
          <div className="form-grid" style={{ marginBottom: 18 }}>
            <div className="input-group">
              <label className="input-label" htmlFor="compare-source">Demand source</label>
              <select id="compare-source" className="select" value={comparisonSource} onChange={event => setComparisonSource(event.target.value)}>
                <option value="WMS">Operational WMS demand</option>
                <option value="M5">M5 sample data</option>
              </select>
            </div>
            <div className="input-group">
              <label className="input-label" htmlFor="compare-history">Training history</label>
              <select id="compare-history" className="select" value={comparisonHistoryDays} onChange={event => setComparisonHistoryDays(Number(event.target.value))}>
                {HISTORY_OPTIONS.map(days => <option key={days} value={days}>{days} days</option>)}
              </select>
            </div>
            <div className="input-group">
              <label className="input-label" htmlFor="compare-horizon">Holdout horizon</label>
              <input id="compare-horizon" className="input" type="number" min="1" max="90" step="1" value={comparisonHorizonDays} onChange={event => setComparisonHorizonDays(event.target.value)} required />
              <span className="input-hint">Historical days to predict and score.</span>
            </div>
            <div className="input-group">
              <label className="input-label" htmlFor="compare-limit">Maximum series</label>
              <select id="compare-limit" className="select" value={comparisonSeriesLimit} onChange={event => {
                const nextLimit = Number(event.target.value);
                setComparisonSeriesLimit(nextLimit);
                setComparisonArimaLimit(current => Math.min(current, nextLimit));
              }}>
                {[50, 100, 250].map(size => <option key={size} value={size}>{size} series</option>)}
              </select>
              <span className="input-hint">A stable sample keeps M5 comparisons responsive.</span>
            </div>
            <div className="input-group">
              <label className="input-label" htmlFor="compare-arima-limit">Maximum ARIMA fits</label>
              <select id="compare-arima-limit" className="select" value={comparisonArimaLimit} onChange={event => setComparisonArimaLimit(Number(event.target.value))}>
                {[25, 50, 100, 250].filter(size => size <= comparisonSeriesLimit).map(size => <option key={size} value={size}>{size} series</option>)}
              </select>
              <span className="input-hint">Other series receive an explicitly labeled 7-day fallback prediction.</span>
            </div>
            <div className="input-group">
              <label className="input-label" htmlFor="compare-cutoff">Holdout end date</label>
              <input id="compare-cutoff" className="input" type="date" value={comparisonAsOfDate} onChange={event => setComparisonAsOfDate(event.target.value)} />
              <span className="input-hint">Leave blank to score the latest available dates.</span>
            </div>
          </div>
          </fieldset>
          {comparisonError && <div className="alert alert-error" role="alert" style={{ marginBottom: 16 }}>{comparisonError}</div>}
          <div style={{ display: "flex", justifyContent: "flex-end" }}>
            <button className="btn btn-secondary" type="submit" disabled={isForecastActionRunning || Number(comparisonHorizonDays) < 1 || Number(comparisonHorizonDays) > 90}>
              {comparing ? "Scoring models..." : "Compare Models"}
            </button>
          </div>
          </form>
        </div>
      </div>
      ) : (
        <div className="card" style={{ marginBottom: 24 }}>
          <div className="card-body">
            <h2 className="section-title">Compare models on historical demand</h2>
            <p className="muted" style={{ margin: 0 }}>Model comparisons require reports write permission because they run ARIMA fits against historical demand.</p>
          </div>
        </div>
      )}

      {comparison && (
        <div className="card" style={{ marginBottom: 24 }}>
          <div className="card-body">
            <div className="page-header" style={{ marginBottom: 8 }}>
              <div>
                <h2 className="section-title" style={{ margin: 0 }}>Holdout results</h2>
                <p className="muted" style={{ marginTop: 4 }}>
                  {comparison.source} · {comparison.sampled_series} series · training {comparison.training_start} to {comparison.training_end} · holdout {comparison.holdout_start} to {comparison.holdout_end}
                </p>
              </div>
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                <span className="badge badge-neutral">{formatNumber(comparison.observations_scored)} daily observations</span>
                <span className="badge badge-neutral">{formatNumber(comparison.predictions_written)} saved predictions</span>
              </div>
            </div>
            {comparison.sample_truncated && (
              <div className="alert alert-warning" role="status" style={{ margin: "12px 0" }}>
                Used a deterministic sample of up to {comparison.series_limit} product and warehouse series.
              </div>
            )}
            <div className="table-container">
              <table>
                <thead><tr><th>Model</th><th>MAE ↓</th><th>RMSE ↓</th><th>WAPE ↓</th><th>Series handled</th></tr></thead>
                <tbody>
                  {COMPARISON_MODELS.map(({ key, label }) => (
                    <tr key={key}>
                      <td style={{ fontWeight: 600 }}>
                        {label}
                        {comparison.better_by.mae === key && <span className="badge badge-success" style={{ marginLeft: 8 }}>Lowest MAE</span>}
                      </td>
                      <td>{formatMetric(comparison.metrics[key].mae)}</td>
                      <td>{formatMetric(comparison.metrics[key].rmse)}</td>
                      <td>{formatMetric(comparison.metrics[key].wape_pct, "%")}</td>
                      <td>{key === "arima_with_fallback"
                        ? `${formatNumber(comparison.arima_series_processed)} ARIMA · ${formatNumber(comparison.fallback_series_processed)} fallback`
                        : formatNumber(comparison.sampled_series)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="muted" style={{ margin: "12px 0 0", fontSize: "0.75rem" }}>
              Lower error is better. MAE and RMSE are measured in units per day; WAPE is undefined when the holdout contains no demand. The saved comparison run is selected below so its per-product test-period predictions are visible.
            </p>
            <p className="muted" style={{ margin: "6px 0 0", fontSize: "0.75rem" }}>
              Lower error by metric: MAE {comparisonModelLabel(comparison.better_by.mae)} · RMSE {comparisonModelLabel(comparison.better_by.rmse)} · WAPE {comparisonModelLabel(comparison.better_by.wape_pct)}
              {Object.keys(comparison.fallback_reasons || {}).length > 0 && ` · Fallbacks: ${Object.entries(comparison.fallback_reasons).map(([reason, count]) => `${reason.replaceAll("_", " ")} ${count}`).join(", ")}`}
            </p>
          </div>
        </div>
      )}

      {m5EvaluationRunId && (
        <div className="card" style={{ marginBottom: 24 }} aria-busy={m5EvaluationLoading}>
          <div className="card-body">
            <div className="page-header" style={{ marginBottom: 8 }}>
              <div>
                <h2 className="section-title" style={{ margin: 0 }}>M5 evaluation report</h2>
                {m5Evaluation?.protocol && (
                  <p className="muted" style={{ marginTop: 4 }}>
                    Run #{m5EvaluationRunId} · {m5Evaluation.protocol.label} · training {m5Evaluation.protocol.training_day_range} ({m5Evaluation.protocol.training_start} to {m5Evaluation.protocol.training_end}) · holdout {m5Evaluation.protocol.test_day_range} ({m5Evaluation.protocol.test_start} to {m5Evaluation.protocol.test_end})
                  </p>
                )}
              </div>
              {m5Evaluation?.predictions_written !== undefined && (
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                  <span className="badge badge-neutral">{formatNumber(m5Evaluation.predictions_written)} saved predictions</span>
                  <span className="badge badge-neutral">{formatNumber(m5Evaluation.evaluation_report_rows)} report rows</span>
                </div>
              )}
            </div>
            {m5Evaluation?.sample_truncated && (
              <div className="alert alert-warning" role="status" style={{ margin: "12px 0" }}>
                This report uses a deterministic sample of up to {m5Evaluation.series_limit} product and warehouse series.
              </div>
            )}
            {m5Evaluation?.metrics ? (
              <div className="table-container">
                <table>
                  <thead><tr><th>Model</th><th>MAE ↓</th><th>RMSE ↓</th><th>WAPE ↓</th><th>Bias</th><th>MASE ↓</th><th>Zero-demand holdouts</th></tr></thead>
                  <tbody>
                    {COMPARISON_MODELS.map(({ key, label }) => {
                      const metrics = m5Evaluation.metrics[key];
                      if (!metrics) return null;
                      return (
                        <tr key={key}>
                          <td style={{ fontWeight: 600 }}>
                            {label}
                            {m5Evaluation.better_by?.mae === key && <span className="badge badge-success" style={{ marginLeft: 8 }}>Lowest MAE</span>}
                          </td>
                          <td>{formatMetric(metrics.mae)}</td>
                          <td>{formatMetric(metrics.rmse)}</td>
                          <td>{formatMetric(metrics.wape_pct, "%")}</td>
                          <td>{formatMetric(metrics.bias)}</td>
                          <td>{formatMetric(metrics.mase)}</td>
                          <td>{formatNumber(metrics.zero_demand_series)}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            ) : m5EvaluationLoading ? (
              <div className="empty-state"><div className="empty-state-text">Loading evaluation summary...</div></div>
            ) : null}
            {m5Evaluation?.metrics && (
              <p className="muted" style={{ margin: "12px 0 0", fontSize: "0.75rem" }}>
                WAPE is pooled across the report; each product with no holdout demand is shown separately below with WAPE unavailable. Bias is mean prediction minus actual, so positive values overpredict. MASE is the average defined per-series score against a one-step naïve in-sample baseline.
              </p>
            )}
            {m5Evaluation?.fallback_reasons && Object.keys(m5Evaluation.fallback_reasons).length > 0 && (
              <p className="muted" style={{ margin: "6px 0 0", fontSize: "0.75rem" }}>
                ARIMA: {formatNumber(m5Evaluation.arima_series_processed)} fitted · {formatNumber(m5Evaluation.fallback_series_processed)} fallback · {Object.entries(m5Evaluation.fallback_reasons).map(([reason, count]) => `${reason.replaceAll("_", " ")} ${count}`).join(", ")}
              </p>
            )}

            <div className="page-header" style={{ margin: "22px 0 12px" }}>
              <div>
                <h3 className="section-title" style={{ margin: 0 }}>Per-product report</h3>
                {m5EvaluationMeta && <div className="muted" style={{ fontSize: "0.75rem", marginTop: 4 }}>{formatNumber(m5EvaluationMeta.total)} product, warehouse, and model rows</div>}
              </div>
            </div>
            {m5EvaluationRowsError ? (
              <div className="alert alert-error" role="alert">{m5EvaluationRowsError}</div>
            ) : m5EvaluationLoading && m5EvaluationRows.length === 0 ? (
              <div className="empty-state"><div className="empty-state-text">Loading per-product metrics...</div></div>
            ) : m5EvaluationRows.length === 0 ? (
              <div className="empty-state"><div className="empty-state-text">No saved evaluation metrics are available for this run</div></div>
            ) : (
              <>
                <div className="table-container">
                  <table>
                    <thead><tr><th>Product</th><th>Warehouse</th><th>Model</th><th>Actual demand</th><th>MAE</th><th>RMSE</th><th>WAPE</th><th>Bias</th><th>MASE</th><th>Holdout</th><th>Generated</th></tr></thead>
                    <tbody>
                      {m5EvaluationRows.map(row => (
                        <tr key={row.id}>
                          <td>
                            <div style={{ fontWeight: 600 }}>{row.product_name}</div>
                            <div className="muted" style={{ fontSize: "0.75rem" }}>{row.sku}</div>
                          </td>
                          <td>
                            <div>{row.warehouse_name}</div>
                            <div className="muted" style={{ fontSize: "0.75rem" }}>{row.warehouse_code}</div>
                          </td>
                          <td>
                            <div>{row.model_name}</div>
                            <div className="muted" style={{ fontSize: "0.7rem" }}>{row.model_version}</div>
                          </td>
                          <td style={{ textAlign: "right", fontVariantNumeric: "tabular-nums" }}>{formatNumber(row.actual_demand_total)}</td>
                          <td>{formatMetric(row.mae)}</td>
                          <td>{formatMetric(row.rmse)}</td>
                          <td>{row.zero_demand_holdout
                            ? <span title="WAPE is unavailable because the holdout had no actual demand">Unavailable</span>
                            : formatMetric(row.wape_pct, "%")}</td>
                          <td>{formatMetric(row.bias)}</td>
                          <td>{formatMetric(row.mase)}</td>
                          <td>{row.zero_demand_holdout ? <span className="badge badge-warning">No test demand</span> : <span className="badge badge-success">Scored</span>}</td>
                          <td style={{ whiteSpace: "nowrap" }}>{formatTimestamp(row.generated_at)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {m5EvaluationMeta && m5EvaluationMeta.total > m5EvaluationMeta.limit && (
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginTop: 12 }}>
                    <button className="btn btn-ghost btn-sm" type="button" disabled={m5EvaluationOffset === 0 || m5EvaluationLoading} onClick={() => changeM5EvaluationPage(Math.max(0, m5EvaluationOffset - EVALUATION_PAGE_SIZE))}>Previous</button>
                    <span className="muted">Page {m5EvaluationCurrentPage} of {m5EvaluationPageCount}</span>
                    <button className="btn btn-ghost btn-sm" type="button" disabled={m5EvaluationOffset + EVALUATION_PAGE_SIZE >= m5EvaluationMeta.total || m5EvaluationLoading} onClick={() => changeM5EvaluationPage(m5EvaluationOffset + EVALUATION_PAGE_SIZE)}>Next</button>
                  </div>
                )}
              </>
            )}
          </div>
        </div>
      )}
      </section>

      <section
        id="forecast-panel-stockout"
        role="tabpanel"
        aria-labelledby="forecast-tab-stockout"
        tabIndex={0}
        hidden={activeSection !== "stockout"}
      >
      <section aria-label="Stockout risk projection">
      <div className="card" style={{ marginBottom: 24 }} aria-busy={stockoutLoading}>
        <div className="card-body">
          <div className="page-header" style={{ marginBottom: 8 }}>
            <div>
              <h2 className="section-title" style={{ margin: 0 }}>Stockout risk projection</h2>
              <p className="muted" style={{ margin: "4px 0 0" }}>
                Uses the selected run’s day-by-day demand. WMS uses current product stock and saved reorder settings; M5 requires a simulated balance.
              </p>
            </div>
          </div>

          {runs.length > 0 && (
            <div className="input-group" style={{ maxWidth: 420, marginBottom: 16 }}>
              <label className="input-label" htmlFor="stockout-run">Forecast run</label>
              <select id="stockout-run" className="select" value={selectedRunId || ""} onChange={event => selectRun(Number(event.target.value))}>
                {runs.map(run => (
                  <option key={run.id} value={run.id} disabled={run.status !== "success"}>
                    #{run.id} · {run.model_name} · {run.source} · {run.status}
                  </option>
                ))}
              </select>
            </div>
          )}

          {!selectedRun ? (
            <div className="empty-state"><div className="empty-state-text">Select a completed forecast run to project stockout risk</div></div>
          ) : selectedRun.status !== "success" ? (
            <div className="alert alert-warning" role="status">Stockout risk is available after this forecast run succeeds.</div>
          ) : (
            <>
              <form onSubmit={calculateStockoutRisk}>
                <fieldset disabled={stockoutLoading} style={{ border: 0, padding: 0, margin: 0 }}>
                  <div className="form-grid" style={{ marginBottom: 16 }}>
                    {availableStockoutModels.length > 1 && (
                      <div className="input-group">
                        <label className="input-label" htmlFor="stockout-model">Forecast model</label>
                        <select id="stockout-model" className="select" value={selectedStockoutModel} onChange={event => setStockoutModel(event.target.value)}>
                          {availableStockoutModels.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}
                        </select>
                      </div>
                    )}
                    {selectedRun.source === "M5" && (
                      <div className="input-group">
                        <label className="input-label" htmlFor="stockout-simulated-stock">Simulated starting stock</label>
                        <input id="stockout-simulated-stock" className="input" type="number" min="0" max="1000000000" step="0.01" value={simulatedStartingStock} onChange={event => setSimulatedStartingStock(event.target.value)} placeholder="e.g. 120" required />
                        <span className="input-hint">M5 contains demand only. This balance is a development scenario.</span>
                      </div>
                    )}
                    <div className="input-group">
                      <label className="input-label" htmlFor="stockout-default-lead">Fallback supplier lead time</label>
                      <input id="stockout-default-lead" className="input" type="number" min="0" max="365" step="1" value={defaultLeadTimeDays} onChange={event => setDefaultLeadTimeDays(event.target.value)} required />
                      <span className="input-hint">Saved product/warehouse settings take precedence when present.</span>
                    </div>
                    <div className="input-group">
                      <label className="input-label" htmlFor="stockout-default-safety">Fallback safety stock</label>
                      <input id="stockout-default-safety" className="input" type="number" min="0" max="1000000000" step="0.01" value={defaultSafetyStock} onChange={event => setDefaultSafetyStock(event.target.value)} required />
                      <span className="input-hint">Used for each forecast warehouse without a saved safety stock.</span>
                    </div>
                    <div className="input-group">
                      <label className="input-label" htmlFor="stockout-critical-days">Critical through (days)</label>
                        <input id="stockout-critical-days" className="input" type="number" min="0" max="87" step="1" value={criticalMaxDays} onChange={event => setCriticalMaxDays(event.target.value)} required />
                    </div>
                    <div className="input-group">
                      <label className="input-label" htmlFor="stockout-high-days">High through (days)</label>
                        <input id="stockout-high-days" className="input" type="number" min="1" max="88" step="1" value={highMaxDays} onChange={event => setHighMaxDays(event.target.value)} required />
                    </div>
                    <div className="input-group">
                      <label className="input-label" htmlFor="stockout-warning-days">Warning through (days)</label>
                        <input id="stockout-warning-days" className="input" type="number" min="2" max="89" step="1" value={warningMaxDays} onChange={event => setWarningMaxDays(event.target.value)} required />
                      <span className="input-hint">Healthy requires forecast coverage beyond this threshold.</span>
                    </div>
                  </div>

                  <div style={{ borderTop: "1px solid var(--border)", paddingTop: 14, marginBottom: 14 }}>
                    <div style={{ fontWeight: 600, marginBottom: 4 }}>Incoming receipts to include (optional)</div>
                    <p className="muted" style={{ margin: "0 0 12px", fontSize: "0.75rem" }}>
                      Add confirmed quantities and expected dates for this projection. Open purchase orders are not currently stored in NovaLedger, so these entries are not saved as orders.
                    </p>
                    <div className="form-grid" style={{ alignItems: "end" }}>
                      <div className="input-group">
                        <label className="input-label" htmlFor="stockout-receipt-product">Product ID</label>
                        <input id="stockout-receipt-product" className="input" type="number" min="1" max="2147483647" step="1" value={receiptDraft.productId} onChange={event => setReceiptDraft(current => ({ ...current, productId: event.target.value }))} placeholder="From product record" />
                      </div>
                      <div className="input-group">
                        <label className="input-label" htmlFor="stockout-receipt-warehouse">Warehouse ID (optional)</label>
                        <input id="stockout-receipt-warehouse" className="input" type="number" min="1" max="2147483647" step="1" value={receiptDraft.warehouseId} onChange={event => setReceiptDraft(current => ({ ...current, warehouseId: event.target.value }))} />
                      </div>
                      <div className="input-group">
                        <label className="input-label" htmlFor="stockout-receipt-date">Expected arrival</label>
                        <input id="stockout-receipt-date" className="input" type="date" value={receiptDraft.arrivalDate} onChange={event => setReceiptDraft(current => ({ ...current, arrivalDate: event.target.value }))} />
                      </div>
                      <div className="input-group">
                        <label className="input-label" htmlFor="stockout-receipt-quantity">Quantity</label>
                        <input id="stockout-receipt-quantity" className="input" type="number" min="0.01" max="1000000000" step="0.01" value={receiptDraft.quantity} onChange={event => setReceiptDraft(current => ({ ...current, quantity: event.target.value }))} />
                      </div>
                      <div className="input-group">
                        <label className="input-label" htmlFor="stockout-receipt-reference">PO reference (optional)</label>
                        <input id="stockout-receipt-reference" className="input" maxLength="128" value={receiptDraft.reference} onChange={event => setReceiptDraft(current => ({ ...current, reference: event.target.value }))} />
                      </div>
                      <div>
                        <button className="btn btn-secondary" type="button" disabled={!receiptDraftValid} onClick={addStockoutReceipt}>Add receipt</button>
                      </div>
                    </div>
                    {stockoutReceipts.length > 0 && (
                      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 12 }}>
                        {stockoutReceipts.map(receipt => (
                          <span className="badge badge-neutral" key={receipt.key}>
                            Product #{receipt.productId}{receipt.warehouseId ? ` · warehouse #${receipt.warehouseId}` : ""} · {formatNumber(receipt.quantity)} on {receipt.arrivalDate}{receipt.reference ? ` · ${receipt.reference}` : ""}
                            <button className="btn btn-ghost btn-xs" type="button" aria-label={`Remove receipt for product ${receipt.productId}`} onClick={() => {
                              setStockoutReceipts(current => current.filter(item => item.key !== receipt.key));
                              setStockoutResult(null);
                              setStockoutRequest(null);
                            }}>×</button>
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                </fieldset>
                {!riskThresholdsValid && <div className="alert alert-warning" role="status" style={{ marginBottom: 14 }}>Risk thresholds must increase from critical to high to warning.</div>}
                {stockoutError && <div className="alert alert-error" role="alert" style={{ marginBottom: 14 }}>{stockoutError}</div>}
                <div style={{ display: "flex", justifyContent: "flex-end" }}>
                  <button className="btn btn-primary" type="submit" disabled={stockoutLoading || !stockoutInputsValid}>
                    {stockoutLoading ? "Projecting..." : "Calculate Stockout Risk"}
                  </button>
                </div>
              </form>

              {stockoutResult && (
                <div style={{ marginTop: 22 }}>
                  <p className="muted" style={{ margin: "0 0 12px", fontSize: "0.8rem" }}>
                    {stockoutResult.source} · {stockoutResult.model_name} · as of {stockoutResult.as_of_date} · forecast {stockoutResult.forecast_start} to {stockoutResult.forecast_end}
                  </p>
                  {stockoutResult.assumptions.series_sample_truncated && (
                    <div className="alert alert-warning" role="status" style={{ marginBottom: 14 }}>
                      This forecast used a deterministic series sample. Demand from excluded product/warehouse series is not included in the stockout projection.
                    </div>
                  )}
                  {stockoutResult.source === "WMS" && (
                    <div className="alert alert-warning" role="status" style={{ marginBottom: 14 }}>
                      WMS on-hand quantity is stored per product, not per warehouse. Demand is aggregated across the listed forecast warehouses and compared with the product-wide balance.
                    </div>
                  )}
                  <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 14 }}>
                    <span className="badge badge-danger">Critical {formatNumber(stockoutResult.summary.critical)}</span>
                    <span className="badge badge-warning">High {formatNumber(stockoutResult.summary.high)}</span>
                    <span className="badge badge-warning">Warning {formatNumber(stockoutResult.summary.warning)}</span>
                    <span className="badge badge-success">Healthy {formatNumber(stockoutResult.summary.healthy)}</span>
                    {stockoutResult.summary.unrated > 0 && <span className="badge badge-neutral">Unrated {formatNumber(stockoutResult.summary.unrated)}</span>}
                    <span className="badge badge-neutral">Reorder required {formatNumber(stockoutResult.summary.reorder_required)}</span>
                  </div>
                  <div className="table-container">
                    <table aria-label="Stockout risk projections">
                      <thead><tr><th>Product</th><th>Warehouses</th><th>Available stock</th><th>Stockout estimate</th><th>Risk</th><th>Reorder point</th><th>Inventory position</th><th>Ending stock</th></tr></thead>
                      <tbody>
                        {stockoutResult.data.map(row => (
                          <tr key={row.product_id}>
                            <td>
                              <div style={{ fontWeight: 600 }}>{row.product_name}</div>
                              <div className="muted" style={{ fontSize: "0.75rem" }}>{row.sku} · ID {row.product_id}</div>
                            </td>
                            <td>
                              <div>{row.warehouses.map(warehouse => warehouse.warehouse_code).join(", ")}</div>
                              <div className="muted" style={{ fontSize: "0.7rem" }}>Lead time {row.lead_time_days}d · safety {formatNumber(row.safety_stock)} · settings {row.reorder_settings_coverage.configured_warehouses}/{row.reorder_settings_coverage.total_warehouses}</div>
                            </td>
                            <td>{formatNumber(row.available_stock)}<div className="muted" style={{ fontSize: "0.7rem" }}>{row.inventory_source === "simulated" ? "simulated" : row.inventory_source === "available batch stock" ? "usable lot balance" : "live product balance"} · avg {formatNumber(row.average_daily_demand)}/day</div></td>
                            <td>{row.stockout_date ? <><div>{row.stockout_date}</div><div className="muted" style={{ fontSize: "0.75rem" }}>{row.days_remaining} days</div></> : <span className="muted">Beyond forecast window</span>}</td>
                            <td><span className={`badge ${stockoutRiskClass(row.risk)}`}>{row.risk}</span><div className="muted" style={{ fontSize: "0.7rem" }}>{row.reorder_required === null ? "Lead-time demand not covered" : row.reorder_required ? "Reorder now" : "Above reorder point"}</div></td>
                            <td>{formatNumber(row.reorder_point)}</td>
                            <td>{formatNumber(row.inventory_position)}</td>
                            <td>
                              {formatNumber(row.ending_stock)}
                              <details style={{ marginTop: 6 }}>
                                <summary className="muted" style={{ cursor: "pointer", fontSize: "0.75rem" }}>Daily stock path</summary>
                                <div className="table-container" style={{ marginTop: 8 }}>
                                  <table aria-label={`Daily stock path for ${row.product_name}`}>
                                    <thead><tr><th>Date</th><th>Opening</th><th>Demand</th><th>Receipts</th><th>Unmet</th><th>Remaining</th></tr></thead>
                                    <tbody>{row.daily_projection.map(day => (
                                      <tr key={day.date}>
                                        <td>{day.date}</td><td>{formatNumber(day.opening_stock)}</td><td>{formatNumber(day.predicted_demand)}</td><td>{formatNumber(day.replenishment_received)}</td><td>{formatNumber(day.unmet_demand)}</td><td>{formatNumber(day.ending_stock)}</td>
                                      </tr>
                                    ))}</tbody>
                                  </table>
                                </div>
                              </details>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  {stockoutResult.meta.total > stockoutResult.meta.limit && (
                    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginTop: 12 }}>
                      <button className="btn btn-ghost btn-sm" type="button" disabled={stockoutOffset === 0 || stockoutLoading} onClick={() => changeStockoutPage(Math.max(0, stockoutOffset - RESULT_PAGE_SIZE))}>Previous</button>
                      <span className="muted">Page {Math.floor(stockoutOffset / RESULT_PAGE_SIZE) + 1} of {Math.ceil(stockoutResult.meta.total / RESULT_PAGE_SIZE)}</span>
                      <button className="btn btn-ghost btn-sm" type="button" disabled={stockoutOffset + RESULT_PAGE_SIZE >= stockoutResult.meta.total || stockoutLoading} onClick={() => changeStockoutPage(stockoutOffset + RESULT_PAGE_SIZE)}>Next</button>
                    </div>
                  )}
                </div>
              )}
            </>
          )}
        </div>
      </div>
      </section>
      </section>

      <section
        id="forecast-panel-runs"
        role="tabpanel"
        aria-labelledby="forecast-tab-runs"
        tabIndex={0}
        hidden={activeSection !== "runs"}
      >
      {runsError && <div className="alert alert-error" role="alert" style={{ marginBottom: 20 }}>{runsError}</div>}

      <div className="page-header" style={{ marginBottom: 12 }}>
        <div>
          <h2 className="section-title" style={{ margin: 0 }}>Run history</h2>
          {runsMeta && <div className="muted" style={{ fontSize: "0.75rem", marginTop: 4 }}>{formatNumber(runs.length)} of {formatNumber(runsMeta.total)} runs loaded</div>}
        </div>
        <button className="btn btn-ghost btn-sm" type="button" onClick={() => loadRuns({ offset: 0 })} disabled={runsLoading}>
          {runsLoading ? "Refreshing..." : "Refresh"}
        </button>
      </div>
      <div className="table-container">
        {runsLoading && runs.length === 0 ? (
          <div className="empty-state"><div className="empty-state-text">Loading forecast runs...</div></div>
        ) : runs.length === 0 ? (
          <div className="empty-state"><div className="empty-state-text">No forecast runs yet</div></div>
        ) : (
          <table>
            <thead><tr><th>Run</th><th>Source</th><th>Status</th></tr></thead>
            <tbody>
              {runs.map(run => {
                const parameters = parseRunParameters(run.parameters);
                const cutoff = parameters.resolved_as_of_date || parameters.as_of_date;
                const horizon = parameters.horizon_days;
                const history = parameters.history_days;
                const window = parameters.window_days || parameters.fallback_window_days;
                const fallbackCount = parameters.fallback_series_processed;
                const arimaLimit = parameters.max_arima_series;
                const evaluationProtocol = parameters.evaluation_protocol;
                const runSummary = [
                  evaluationProtocol ? `${evaluationProtocol.label} · ${evaluationProtocol.test_day_range}` : null,
                  cutoff ? `as of ${cutoff}` : null,
                  horizon ? `${horizon}-day horizon` : null,
                  history ? `${history}-day history` : null,
                  window ? `${window}-day window` : null,
                  arimaLimit ? `ARIMA cap ${arimaLimit}` : null,
                  parameters.models?.length ? `${parameters.models.length}-model comparison` : null,
                  fallbackCount !== undefined ? `${fallbackCount} fallbacks` : null,
                  parameters.arima_sample_truncated || parameters.series_sample_truncated ? "sample capped" : null,
                ].filter(Boolean).join(" · ");
                return (
                  <tr key={run.id} style={{ background: selectedRunId === run.id ? "var(--nav-active-bg)" : undefined }}>
                    <td>
                      <button
                        className="btn btn-ghost btn-xs"
                        type="button"
                        aria-label={`View predictions for run ${run.id}: ${run.model_name}`}
                        aria-pressed={selectedRunId === run.id}
                        onClick={() => {
                          selectRun(run.id);
                          setActiveSection("predictions");
                        }}
                      >
                        #{run.id} · {run.model_name}
                      </button>
                      <div className="muted" style={{ fontSize: "0.75rem", marginTop: 4 }}>{formatTimestamp(run.started_at)}</div>
                      {runSummary && <div className="muted" style={{ fontSize: "0.7rem", marginTop: 4 }}>{runSummary}</div>}
                    </td>
                    <td><span className="badge badge-neutral">{run.source}</span></td>
                    <td>
                      <span className={`badge ${statusClass(run.status)}`}>{run.status}</span>
                      <div className="muted" style={{ fontSize: "0.75rem", marginTop: 4 }}>{formatNumber(run.products_processed)} products</div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
      {canLoadMoreRuns && (
        <div style={{ display: "flex", justifyContent: "center", marginTop: 12 }}>
          <button className="btn btn-ghost btn-sm" type="button" onClick={() => loadRuns({ offset: runs.length, append: true })} disabled={runsLoading}>
            {runsLoading ? "Loading..." : "Load more runs"}
          </button>
        </div>
      )}
      </section>

      <section
        id="forecast-panel-predictions"
        role="tabpanel"
        aria-labelledby="forecast-tab-predictions"
        tabIndex={0}
        hidden={activeSection !== "predictions"}
      >
        <div className="page-header" style={{ marginBottom: 16 }}>
          <div>
            <h2 className="section-title" style={{ margin: 0 }}>Predictions</h2>
            <p className="muted" style={{ margin: "4px 0 0" }}>
              {selectedRun
                ? `Run #${selectedRun.id} · ${selectedRun.model_name} · ${selectedRun.source}`
                : "Choose a completed run to review its saved demand predictions."}
            </p>
          </div>
          {resultMeta && <span className="badge badge-neutral">{formatNumber(resultMeta.total)} predictions</span>}
        </div>
        {runs.length > 0 && (
          <div className="input-group" style={{ maxWidth: 460, marginBottom: 16 }}>
            <label className="input-label" htmlFor="predictions-run">Forecast run</label>
            <select id="predictions-run" className="select" value={selectedRunId || ""} onChange={event => selectRun(Number(event.target.value))}>
              {runs.map(run => (
                <option key={run.id} value={run.id}>
                  #{run.id} · {run.model_name} · {run.source} · {run.status}
                </option>
              ))}
            </select>
          </div>
        )}
        {resultsError ? (
          <div className="alert alert-error" role="alert">{resultsError}</div>
        ) : !selectedRunId ? (
          <div className="card"><div className="empty-state"><div className="empty-state-text">No forecast run selected</div></div></div>
        ) : selectedRun?.status === "failed" ? (
          <div className="alert alert-error" role="alert">
            {selectedRun.error_message || "This forecast run failed before it produced predictions."}
          </div>
        ) : selectedRun?.status === "running" ? (
          <div className="alert alert-warning" role="status">This forecast is still running. Predictions will appear here when it completes.</div>
        ) : resultsLoading && results.length === 0 ? (
          <div className="card"><div className="empty-state"><div className="empty-state-text">Loading predictions...</div></div></div>
        ) : results.length === 0 ? (
          <div className="card"><div className="empty-state"><div className="empty-state-text">This run has no predictions to display</div></div></div>
        ) : (
          <PredictionTable
            results={results}
            resultMeta={resultMeta}
            resultOffset={resultOffset}
            resultsLoading={resultsLoading}
            currentPage={currentPage}
            pageCount={pageCount}
            onPrevious={() => changeResultPage(Math.max(0, resultOffset - RESULT_PAGE_SIZE))}
            onNext={() => changeResultPage(resultOffset + RESULT_PAGE_SIZE)}
          />
        )}
      </section>
    </section>
  );
}
