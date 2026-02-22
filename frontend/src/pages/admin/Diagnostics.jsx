import { useState, useEffect } from "react";
import { Activity, RefreshCw, CheckCircle, XCircle } from "lucide-react";
import { getDiagnostics, getDiagnosticsNowPlaying } from "../../api";
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

function DiagnosticsNowPlaying() {
  const [np, setNp] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  useEffect(() => {
    let cancelled = false;
    const load = () => {
      setLoading(true);
      setError(null);
      getDiagnosticsNowPlaying()
        .then((d) => { if (!cancelled) { setNp(d); setError(null); } })
        .catch((e) => { if (!cancelled) { setNp(null); setError(e.message || "Ошибка"); } })
        .finally(() => { if (!cancelled) setLoading(false); });
    };
    load();
    const id = setInterval(load, 5000);
    return () => { cancelled = true; clearInterval(id); };
  }, []);
  if (!np) return (
    <div className="diagnostics-card">
      <div className="diagnostics-card-title">Сейчас играет</div>
      <div className="diag-hint">{loading ? "Загрузка…" : (error || "Нет данных")}</div>
    </div>
  );
  const resp = np.now_playing_response || {};
  const sp = np.stream_position_file || {};
  const slotDb = np.slot_by_db || {};
  const slotReal = np.slot_by_real_durations || {};
  return (
    <div className="diagnostics-card diagnostics-now-playing">
      <div className="diagnostics-card-title">Сейчас играет (диагностика)</div>
      {np.error && <div className="diagnostics-error" style={{ marginBottom: 8 }}>Ошибка: {np.error}</div>}
      <ul className="diagnostics-list">
        <li><strong>МСК:</strong> {np.moscow_time} ({np.moscow_sec} сек) <span className="diag-hint">источник: {np.time_source || "?"}</span></li>
        {np.first_slot_start && <li><strong>Начало эфира:</strong> {np.first_slot_start} МСК</li>}
        <li><strong>Позиция:</strong> {np.position_used?.toFixed(0)} сек — {np.position_source}</li>
        <li><strong>stream_position.json:</strong> {sp.exists ? `есть (возраст ${sp.age_sec} сек)` : "НЕТ"}</li>
        {sp.raw && sp.raw.title && <li className="diag-hint">В файле: {sp.raw.title}</li>}
        <li><strong>Пользователь видит:</strong> {resp.title ?? (resp.source ? "—" : "Нет трека (позиция вне расписания?)")} <span className="diag-hint">(источник: {resp.source || "—"})</span></li>
        <li><strong>Позиция по БД:</strong> {slotDb.title || "—"}</li>
        {slotReal.title && <li><strong>По реальным длительностям:</strong> {slotReal.title}</li>}
        {np.icecast && <li>Icecast: {np.icecast}</li>}
      </ul>
    </div>
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
      .then((res) => {
        if (res && typeof res === "object" && "checks" in res) {
          setData(res);
        } else {
          setError("Неверный формат ответа");
        }
      })
      .catch((e) => setError(e.message || "Ошибка загрузки"))
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
          <div className="diagnostics-col diagnostics-col-1">
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
              <div className="diagnostics-card-title">Stream / Icecast</div>
              <ul className="diagnostics-list">
                <li>
                  <StatusBadge ok={checks.stream_ready} label={checks.stream_ready ? "Stream готов" : "Stream не готов"} />
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

          <div className="diagnostics-col diagnostics-col-2">
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
                  <StatusBadge ok={checks.hls_ready} label={checks.hls_ready ? "HLS готов" : "HLS не готов"} />
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
          </div>

          <div className="diagnostics-col diagnostics-col-3">
            <DiagnosticsNowPlaying />
          </div>
        </div>
      )}

      <p className="diagnostics-hint">
        При 404 от Icecast nginx автоматически переключается на backend stream. HLS имеет приоритет при воспроизведении.
      </p>
    </div>
  );
}
