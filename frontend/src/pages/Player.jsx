import { useState, useRef, useEffect } from "react";
import { Play, Square } from "lucide-react";
import { getBroadcastPlaylistUrls, getBroadcastNowPlaying } from "../api";
import "./Player.css";

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";
const EQ_BARS = 24;
const BAR_COUNT = EQ_BARS;

export default function Player() {
  const [playing, setPlaying] = useState(false);
  const [items, setItems] = useState([]);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);
  const [barHeights, setBarHeights] = useState(() => Array(BAR_COUNT).fill(15));
  const [useAnalyser, setUseAnalyser] = useState(false);
  const audioRef = useRef(null);
  const audioContextRef = useRef(null);
  const analyserRef = useRef(null);
  const sourceRef = useRef(null);
  const dataArrayRef = useRef(null);
  const rafRef = useRef(null);

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

  useEffect(() => {
    if (!playing || items.length === 0) return;
    const today = new Date().toISOString().slice(0, 10);
    const poll = async () => {
      try {
        const np = await getBroadcastNowPlaying(today);
        if (np?.entityType != null && np?.entityId != null) {
          const idx = items.findIndex(
            (it) => it.type === np.entityType && it.entity_id === np.entityId
          );
          if (idx >= 0 && idx !== currentIndex) {
            setCurrentIndex(idx);
            const item = items[idx];
            const fullUrl = item?.url?.startsWith("http") ? item.url : `${API_BASE}${item?.url || ""}`;
            if (audioRef.current) {
              audioRef.current.src = fullUrl;
              audioRef.current.play().catch(() => {});
            }
          }
        }
      } catch {
        /* ignore */
      }
    };
    const id = setInterval(poll, 60000);
    return () => clearInterval(id);
  }, [playing, items, currentIndex]);

  useEffect(() => {
    const audio = audioRef.current;
    if (!playing || !audio?.src) return;

    try {
      const audioOrigin = new URL(audio.src, window.location.href).origin;
      if (audioOrigin !== window.location.origin) {
        setUseAnalyser(false);
        return;
      }
    } catch {
      setUseAnalyser(false);
      return;
    }

    const setupAudioContext = () => {
      const AudioContextClass = window.AudioContext || window.webkitAudioContext;
      if (!AudioContextClass) return;

      let ctx = audioContextRef.current;
      if (!ctx || ctx.state === "closed") {
        ctx = new AudioContextClass();
        audioContextRef.current = ctx;
      }
      if (ctx.state === "suspended") ctx.resume();

      if (!sourceRef.current) {
        try {
          const source = ctx.createMediaElementSource(audio);
          sourceRef.current = source;
          const analyser = ctx.createAnalyser();
          analyser.fftSize = 256;
          analyser.smoothingTimeConstant = 0.7;
          analyser.minDecibels = -70;
          analyser.maxDecibels = -20;
          source.connect(analyser);
          analyser.connect(ctx.destination);
          analyserRef.current = analyser;
          dataArrayRef.current = new Uint8Array(analyser.frequencyBinCount);
        } catch (e) {
          console.warn("Audio analyser setup failed:", e);
          return;
        }
      }

      const analyser = analyserRef.current;
      const dataArray = dataArrayRef.current;
      if (!analyser || !dataArray) return;

      const animate = () => {
        rafRef.current = requestAnimationFrame(animate);
        analyser.getByteFrequencyData(dataArray);
        const step = Math.floor(dataArray.length / BAR_COUNT);
        const next = Array(BAR_COUNT)
          .fill(0)
          .map((_, i) => {
            const idx = Math.min(i * step, dataArray.length - 1);
            const v = dataArray[idx] || 0;
            return Math.max(8, Math.min(80, 8 + (v / 255) * 72));
          });
        setBarHeights(next);
      };
      setUseAnalyser(true);
      animate();
    };

    setupAudioContext();

    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
  }, [playing]);

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
          {loading ? "…" : playing ? <Square size={40} /> : <Play size={40} />}
        </button>
      </div>
      <p className="player-hint">
        {playing ? "Слушайте эфир" : "Нажмите Play для прослушивания"}
      </p>
      {error && <p className="player-error">{error}</p>}
      {playing && (
        <div className={`equalizer ${!useAnalyser ? "equalizer-fallback" : ""}`} aria-hidden>
          {barHeights.map((h, i) => (
            <div
              key={i}
              className="equalizer-bar"
              style={useAnalyser ? { height: `${h}%` } : undefined}
            />
          ))}
        </div>
      )}
      {playing && items[currentIndex]?.title && (
        <p className="player-now-playing">
          Сейчас играет: {items[currentIndex].title}
        </p>
      )}
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
