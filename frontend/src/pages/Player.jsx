import { useState, useRef, useEffect } from "react";
import { Play, Square } from "lucide-react";
import { getBroadcastNowPlaying, moscowDateStr } from "../api";
import "./Player.css";

const STREAM_URL = "/stream";
const EQ_BARS = 24;
const BAR_COUNT = EQ_BARS;
const MAX_RETRIES = 5;
const RETRY_DELAY_MS = 2000;

export default function Player() {
  const [playing, setPlaying] = useState(false);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);
  const [nowPlayingTitle, setNowPlayingTitle] = useState(null);
  const [barHeights, setBarHeights] = useState(() => Array(BAR_COUNT).fill(15));
  const [useAnalyser, setUseAnalyser] = useState(false);
  const audioRef = useRef(null);
  const audioContextRef = useRef(null);
  const analyserRef = useRef(null);
  const sourceRef = useRef(null);
  const dataArrayRef = useRef(null);
  const rafRef = useRef(null);
  const retryCountRef = useRef(0);

  const playStream = () => {
    if (!audioRef.current) return;
    audioRef.current.src = STREAM_URL + "?t=" + Date.now();
    audioRef.current.play().catch((e) => {
      setError("Не удалось воспроизвести. Проверьте эфир в админке.");
      setLoading(false);
    });
  };

  const togglePlay = () => {
    setError(null);
    retryCountRef.current = 0;
    if (playing) {
      audioRef.current?.pause();
      setPlaying(false);
      return;
    }
    setLoading(true);
    playStream();
    setPlaying(true);
    setLoading(false);
  };

  const handleAudioError = () => {
    if (retryCountRef.current < MAX_RETRIES) {
      retryCountRef.current += 1;
      setTimeout(() => playStream(), RETRY_DELAY_MS);
    } else {
      setError("Ошибка загрузки. Проверьте эфир в админке.");
      retryCountRef.current = 0;
    }
  };

  useEffect(() => {
    const poll = () => {
      getBroadcastNowPlaying(moscowDateStr())
        .then((r) => setNowPlayingTitle(r?.title || null))
        .catch(() => setNowPlayingTitle(null));
    };
    poll();
    const id = setInterval(poll, 2000);
    return () => clearInterval(id);
  }, []);

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
      {nowPlayingTitle && (
        <p className="player-now-playing">Сейчас играет: {nowPlayingTitle}</p>
      )}
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
      <audio
        ref={audioRef}
        preload="none"
        onPlay={() => {
          setPlaying(true);
          setLoading(false);
          retryCountRef.current = 0;
        }}
        onPause={() => setPlaying(false)}
        onError={handleAudioError}
        onWaiting={() => setLoading(true)}
        onCanPlay={() => setLoading(false)}
      />
    </div>
  );
}
