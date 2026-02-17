import { useState, useRef, useMemo } from "react";
import { Link } from "react-router-dom";
import "./Player.css";

const API_BASE = "http://localhost:8000";

export default function Player() {
  const [playing, setPlaying] = useState(false);
  const [streamDate, setStreamDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [fromStart, setFromStart] = useState(false);
  const [useTestStream, setUseTestStream] = useState(true);
  const [error, setError] = useState(null);
  const audioRef = useRef(null);

  const streamUrl = useMemo(() => {
    if (useTestStream) {
      return `${API_BASE}/stream-test?d=${streamDate}`;
    }
    return `${API_BASE}/stream?d=${streamDate}${fromStart ? "&from_start=1" : ""}`;
  }, [streamDate, fromStart, useTestStream]);

  const togglePlay = () => {
    if (!audioRef.current) return;
    setError(null);
    if (playing) {
      audioRef.current.pause();
    } else {
      audioRef.current.play().catch((e) => setError("Не удалось воспроизвести. Проверьте, что эфир сгенерирован."));
    }
    setPlaying(!playing);
  };

  return (
    <div className="player-page">
      <div className="player-header">
        <h1 className="logo">NAVO RADIO</h1>
        <p className="tagline">Восточная музыка • Душанбе</p>
      </div>
      <div className="player-date">
        <label htmlFor="stream-date">Эфир на дату:</label>
        <input
          id="stream-date"
          type="date"
          value={streamDate}
          onChange={(e) => {
            setStreamDate(e.target.value);
            setPlaying(false);
          }}
          className="date-picker"
        />
      </div>
      <div className="player-sync">
        <label>
          <input
            type="checkbox"
            checked={fromStart}
            onChange={(e) => {
              setFromStart(e.target.checked);
              setPlaying(false);
            }}
          />
          С начала дня (иначе — с текущего времени по Москве)
        </label>
      </div>
      <div className="player-control">
        <button
          className={`play-btn ${playing ? "playing" : ""}`}
          onClick={togglePlay}
          aria-label={playing ? "Stop" : "Play"}
        >
          {playing ? "⏸" : "▶"}
        </button>
      </div>
      <div className="player-sync">
        <label>
          <input
            type="checkbox"
            checked={useTestStream}
            onChange={(e) => {
              setUseTestStream(e.target.checked);
              setPlaying(false);
            }}
          />
          Тест (один файл) — пока основной стрим не работает
        </label>
      </div>
      <p className="player-hint">
        {playing ? "Слушайте эфир" : "Нажмите Play для прослушивания"}
      </p>
      {error && <p className="player-error">{error}</p>}
      <Link to="/admin" className="admin-link">
        Админ-панель
      </Link>
      <audio
        key={streamUrl}
        ref={audioRef}
        src={streamUrl}
        onEnded={() => setPlaying(false)}
        onPlay={() => setPlaying(true)}
        onPause={() => setPlaying(false)}
        onError={() => setError("Ошибка загрузки потока. Сгенерируйте эфир в админке.")}
      />
    </div>
  );
}
