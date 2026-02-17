import { useState, useRef } from "react";
import { Link } from "react-router-dom";
import { getBroadcastPlaylistUrls } from "../api";
import "./Player.css";

const API_BASE = "http://localhost:8000";

export default function Player() {
  const [playing, setPlaying] = useState(false);
  const [items, setItems] = useState([]);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);
  const audioRef = useRef(null);

  const togglePlay = async () => {
    setError(null);
    if (playing) {
      audioRef.current?.pause();
      setPlaying(false);
      return;
    }
    if (items.length === 0) {
      setLoading(true);
      try {
        const today = new Date().toISOString().slice(0, 10);
        const { items: fetched, startIndex } = await getBroadcastPlaylistUrls(today, true);
        if (!fetched?.length) {
          setError("Нет эфира на сегодня. Сгенерируйте эфир в админке.");
          setLoading(false);
          return;
        }
        setItems(fetched);
        setCurrentIndex(startIndex);
        const item = fetched[startIndex];
        const fullUrl = item?.url?.startsWith("http") ? item.url : `${API_BASE}${item?.url || ""}`;
        audioRef.current.src = fullUrl;
        audioRef.current.play().catch((e) => setError("Не удалось воспроизвести"));
        setPlaying(true);
      } catch (e) {
        setError(e.message || "Не удалось загрузить плейлист");
      } finally {
        setLoading(false);
      }
      return;
    }
    const item = items[currentIndex];
    if (!item?.url) return;
    const fullUrl = item.url.startsWith("http") ? item.url : `${API_BASE}${item.url}`;
    audioRef.current.src = fullUrl;
    audioRef.current.play().catch((e) => setError("Не удалось воспроизвести"));
    setPlaying(true);
  };

  const handleEnded = () => {
    if (items.length <= 1) {
      setPlaying(false);
      return;
    }
    const nextIndex = currentIndex + 1 >= items.length ? 0 : currentIndex + 1;
    setCurrentIndex(nextIndex);
    const item = items[nextIndex];
    const fullUrl = item?.url?.startsWith("http") ? item.url : `${API_BASE}${item?.url || ""}`;
    audioRef.current.src = fullUrl;
    audioRef.current.play().catch((e) => setError("Не удалось воспроизвести"));
  };

  return (
    <div className="player-page">
      <div className="player-header">
        <h1 className="logo">NAVO RADIO</h1>
        <p className="tagline">Восточная музыка • Душанбе</p>
      </div>
      <div className="player-control">
        <button
          className={`play-btn ${playing ? "playing" : ""}`}
          onClick={togglePlay}
          disabled={loading}
          aria-label={playing ? "Stop" : "Play"}
        >
          {loading ? "…" : playing ? "⏸" : "▶"}
        </button>
      </div>
      <p className="player-hint">
        {playing ? "Слушайте эфир" : "Нажмите Play для прослушивания"}
      </p>
      {error && <p className="player-error">{error}</p>}
      <Link to="/admin" className="admin-link">
        Админ-панель
      </Link>
      <audio
        ref={audioRef}
        onEnded={handleEnded}
        onPlay={() => setPlaying(true)}
        onPause={() => setPlaying(false)}
        onError={() => setError("Ошибка загрузки. Проверьте эфир в админке.")}
      />
    </div>
  );
}
