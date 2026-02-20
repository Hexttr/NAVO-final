import { useState, useEffect } from "react";
import { Activity, RefreshCw, CheckCircle, XCircle } from "lucide-react";
import { getDiagnostics } from "../../api";
import "./Diagnostics.css";

function HlsClientTest({ url }) {
  const [status, setStatus] = useState(null);
  const [testing, setTesting] = useState(false);
  useEffect(() => {
    if (!url) return;
    setTesting(true);
    const fullUrl = url.startsWith("http") ? url : window.location.origin + url;
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), 8000);
    fetch(fullUrl, { method: "HEAD", signal: ctrl.signal })
      .then((r) => { clearTimeout(t); setStatus(r.status); })
      .catch((e) => { clearTimeout(t); setStatus(e.name || "err"); })
      .finally(() => setTesting(false));
  }, [url]);
  if (testing) return <span className="diag-hint">Проверка доступа…</span>;
  if (status === null) return null;
  const ok = status === 200;
  return (
    <StatusBadge ok={ok} label={ok ? "Доступен с браузера" : `Браузер: ${status}`} />
  );
}

function StatusBadge({ ok, label }) {
  return (
    <span className={`diag-badge ${ok ? "ok" : "fail"}`}>
      {ok ? <CheckCircle size={14} /> : <XCircle size={14} />}
      {label}
    </span>
  );
}

export default function Diagnostics() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchDiagnostics = () => {
    setLoading(true);
    setError(null);
    getDiagnostics()
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    fetchDiagnostics();
    const id = setInterval(fetchDiagnostics, 15000);
    return () => clearInterval(id);
  }, []);

  if (loading && !data) {
    return (
      <div className="diagnostics-page">
        <div className="diagnostics-loading">Загрузка диагностики...</div>
      </div>
    );
  }

  const checks = data?.checks || {};
  const allOk = data?.ok && checks.broadcast_ready && (checks.hls_ready || checks.stream_ready);

  return (
    <div className="diagnostics-page">
      <div className="diagnostics-header">
        <h2>
          <Activity size={22} />
          Диагностика эфира
        </h2>
        <button
          type="button"
          className="diagnostics-refresh"
          onClick={fetchDiagnostics}
          disabled={loading}
          title="Обновить"
        >
          <RefreshCw size={16} className={loading ? "spin" : ""} />
          Обновить
        </button>
      </div>

      {error && <p className="diagnostics-error">Ошибка: {error}</p>}

      {data && (
        <div className="diagnostics-grid">
          <div className={`diagnostics-card ${allOk ? "success" : "warning"}`}>
            <div className="diagnostics-card-title">Общий статус</div>
            <div className="diagnostics-summary">
              <StatusBadge ok={data.ok} label={data.ok ? "Система в порядке" : "Есть проблемы"} />
            </div>
            <div className="diagnostics-meta">
              Дата эфира: {data.moscow_date || "—"} | {data.ts ? new Date(data.ts).toLocaleTimeString("ru") : ""}
            </div>
          </div>

          <div className="diagnostics-card">
            <div className="diagnostics-card-title">Эфир</div>
            <ul className="diagnostics-list">
              <li>
                <StatusBadge ok={checks.broadcast_ready} label="Сетка готова" />
              </li>
              <li>Элементов: {checks.broadcast_items ?? "—"}</li>
              {checks.broadcast_copied && <li className="diag-hint">Эфир скопирован с предыдущего дня</li>}
            </ul>
          </div>

          <div className="diagnostics-card">
            <div className="diagnostics-card-title">HLS</div>
            <ul className="diagnostics-list">
              <li>
                <StatusBadge ok={checks.hls_ready} label="HLS готов" />
              </li>
              {checks.hls_url && (
                <li className="diag-url" title={checks.hls_url}>
                  {checks.hls_url}
                </li>
              )}
              {checks.hls_url && (
                <li>
                  <HlsClientTest url={checks.hls_url} />
                </li>
              )}
            </ul>
          </div>

          <div className="diagnostics-card">
            <div className="diagnostics-card-title">Stream / Icecast</div>
            <ul className="diagnostics-list">
              <li>
                <StatusBadge ok={checks.stream_ready} label="Stream готов" />
              </li>
              <li>
                Icecast /live:{" "}
                {typeof checks.icecast_live === "number" ? (
                  checks.icecast_live === 200 ? (
                    <StatusBadge ok={true} label="200 OK" />
                  ) : (
                    <StatusBadge ok={false} label={`HTTP ${checks.icecast_live}`} />
                  )
                ) : (
                  <StatusBadge ok={false} label={String(checks.icecast_live || "?")} />
                )}
              </li>
            </ul>
          </div>
        </div>
      )}

      <p className="diagnostics-hint">
        При 404 от Icecast nginx автоматически переключается на backend stream. HLS имеет приоритет при воспроизведении.
      </p>
    </div>
  );
}
