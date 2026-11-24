import { useCallback, useEffect, useRef, useState } from "react";
import { authFetch } from "../api";
import { useAuth } from "../AuthContext";

const RESULT_PAGE_SIZE = 100;
const EVALUATION_PAGE_SIZE = 100;
const WINDOW_OPTIONS = [7, 14, 30];
const HISTORY_OPTIONS = [90, 180, 365];
const M5_EVALUATION_RUN_MODEL_NAME = "M5 fixed evaluation (4 models)";

function errorMessage(data, fallback) {
  if (typeof data?.detail === "string") return data.detail;
  if (Array.isArray(data?.detail)) {
    return data.detail.map(item => item.msg).filter(Boolean).join("; ") || fallback;
  }
  return fallback;
}

function formatNumber(value) {
  if (value === null || value === undefined || value === "" || !Number.isFinite(Number(value))) return "—";
  return new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 }).format(Number(value));
}

function formatMetric(value, suffix = "") {
  return value === null || value === undefined
    ? "—"
    : `${new Intl.NumberFormat(undefined, { maximumFractionDigits: 4 }).format(value)}${suffix}`;
}

function formatTimestamp(value) {
  if (!value) return "-";
  const parsed = new Date(`${value.replace(" ", "T")}Z`);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString();
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

export default function Forecasting() {
  const { can } = useAuth();
  const canRun = can("reports", "write");
  const [model, setModel] = useState("rolling_average");
  const [source, setSource] = useState("WMS");
  const [windowDays, setWindowDays] = useState(7);
  const [historyDays, setHistoryDays] = useState(365);
  const [seriesLimit, setSeriesLimit] = useState(1000);
  const [maxArimaSeries, setMaxArimaSeries] = useState(100);
  const [horizonDays, setHorizonDays] = useState(1);
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
  const [comparisonHorizonDays, setComparisonHorizonDays] = useState(14);
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
      setSelectedRunId(current => current ?? (selectFirst ? nextRuns[0]?.id ?? null : null));
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
  const selectedM5Experiment = M5_EXPERIMENTS.find(experiment => experiment.key === m5Experiment) || M5_EXPERIMENTS[0];
  const isForecastActionRunning = running || comparing || evaluatingM5;
  const canLoadMoreRuns = runsMeta && runs.length < runsMeta.total;

  return (
    <section>
      <div className="page-header">
        <div>
          <h1 className="page-title">Demand Forecasts</h1>
          <p className="page-subtitle">Estimate daily demand by product and warehouse from historical sales.</p>
        </div>
      </div>

      {notice && (
        <div className={`alert alert-${notice.type}`} role={notice.type === "error" ? "alert" : "status"} style={{ marginBottom: 20 }}>
          <span>{notice.text}</span>
          <button className="btn btn-ghost btn-xs" type="button" aria-label="Dismiss message" onClick={() => setNotice(null)}>&times;</button>
        </div>
      )}

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
                  <span className="input-hint">Days ahead, up to 90. The average is repeated for each day.</span>
                </div>
                <div className="input-group">
                  <label className="input-label" htmlFor="forecast-as-of">Calculate through date</label>
                  <input id="forecast-as-of" className="input" type="date" value={asOfDate} onChange={event => setAsOfDate(event.target.value)} />
                  <span className="input-hint">Leave blank to use the latest date in the selected source.</span>
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

      {runsError && <div className="alert alert-error" role="alert" style={{ marginBottom: 20 }}>{runsError}</div>}

      <div className="grid-2" style={{ alignItems: "start" }}>
        <div>
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
                      <tr key={run.id} style={{ background: selectedRunId === run.id ? "rgba(59, 130, 246, 0.08)" : undefined }}>
                        <td>
                          <button className="btn btn-ghost btn-xs" type="button" aria-pressed={selectedRunId === run.id} onClick={() => selectRun(run.id)}>
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
        </div>

        <div>
          <div className="page-header" style={{ marginBottom: 12 }}>
            <h2 className="section-title" style={{ margin: 0 }}>Predictions</h2>
            {resultMeta && <span className="muted">{formatNumber(resultMeta.total)} total</span>}
          </div>
          {resultsError ? (
            <div className="alert alert-error" role="alert">{resultsError}</div>
          ) : !selectedRunId ? (
            <div className="card"><div className="empty-state"><div className="empty-state-text">Select a completed run to review predictions</div></div></div>
          ) : selectedRun?.status === "failed" ? (
            <div className="alert alert-error" role="alert">
              {selectedRun.error_message || "This forecast run failed before it produced predictions."}
            </div>
          ) : resultsLoading && results.length === 0 ? (
            <div className="card"><div className="empty-state"><div className="empty-state-text">Loading predictions...</div></div></div>
          ) : results.length === 0 ? (
            <div className="card"><div className="empty-state"><div className="empty-state-text">This run has no predictions to display</div></div></div>
          ) : (
            <>
              <div className="table-container">
                <table>
                  <thead>
                    <tr><th>Test date</th><th>Product</th><th>Warehouse</th><th>Model</th><th>Generated at</th><th style={{ textAlign: "right" }}>Daily demand</th></tr>
                  </thead>
                  <tbody>
                    {results.map(result => (
                      <tr key={result.id}>
                        <td style={{ whiteSpace: "nowrap" }}>{result.forecast_date}</td>
                        <td>
                          <div style={{ fontWeight: 600 }}>{result.product_name}</div>
                          <div className="muted" style={{ fontSize: "0.75rem" }}>{result.sku}</div>
                        </td>
                        <td>
                          <div>{result.warehouse_name}</div>
                          <div className="muted" style={{ fontSize: "0.75rem" }}>{result.warehouse_code}</div>
                        </td>
                        <td>
                          <div>{result.model_name}</div>
                          <div className="muted" style={{ fontSize: "0.7rem" }}>{result.model_version}</div>
                        </td>
                        <td style={{ whiteSpace: "nowrap" }}>{formatTimestamp(result.generated_at)}</td>
                        <td style={{ textAlign: "right", fontVariantNumeric: "tabular-nums", fontWeight: 700 }}>{formatNumber(result.predicted_demand)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {resultMeta && resultMeta.total > resultMeta.limit && (
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginTop: 12 }}>
                  <button className="btn btn-ghost btn-sm" type="button" disabled={resultOffset === 0 || resultsLoading} onClick={() => changeResultPage(Math.max(0, resultOffset - RESULT_PAGE_SIZE))}>Previous</button>
                  <span className="muted">Page {currentPage} of {pageCount}</span>
                  <button className="btn btn-ghost btn-sm" type="button" disabled={resultOffset + RESULT_PAGE_SIZE >= resultMeta.total || resultsLoading} onClick={() => changeResultPage(resultOffset + RESULT_PAGE_SIZE)}>Next</button>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </section>
  );
}
