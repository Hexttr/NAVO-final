import { useState, useRef, useEffect } from "react";
import { Play, Square } from "lucide-react";
import { getBroadcastNowPlaying, getStreamUrl, moscowDateStr } from "../api";
import "./Player.css";

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
  const [audioReady, setAudioReady] = useState(false);
  const audioRef = useRef(null);
  const audioContextRef = useRef(null);
  const analyserRef = useRef(null);
  const sourceRef = useRef(null);
  const dataArrayRef = useRef(null);
  const rafRef = useRef(null);
  const retryCountRef = useRef(0);
  const useStreamFallbackRef = useRef(false);

  const playStream = async () => {
    if (!audioRef.current) return;
    const audio = audioRef.current;

    try {
      const { icecastUrl, streamUrl } = await getStreamUrl();
      const base = window.location.origin;
      const icecastFull = icecastUrl.startsWith("http") ? icecastUrl : base + icecastUrl;
      const streamFull = streamUrl.startsWith("http") ? streamUrl : base + streamUrl;
      const streamWithCacheBust = streamFull + (streamFull.includes("?") ? "&" : "?") + "t=" + Date.now();

      // Icecast не поддерживает HEAD — пробуем напрямую. При ошибке — fallback на /stream
      if (useStreamFallbackRef.current) {
        audio.src = streamWithCacheBust;
      } else {
        audio.src = icecastFull;
      }

      audio.play().catch((e) => {
        setError("Не удалось воспроизвести. Проверьте эфир в админке.");
        setLoading(false);
      });
    } catch (e) {
      useStreamFallbackRef.current = true;
      const fallback = "http://localhost:8000/stream?t=" + Date.now();
      audio.src = fallback;
      audio.play().catch(() => {
        setError("Не удалось воспроизвести. Проверьте эфир в админке.");
        setLoading(false);
      });
    }
  };

  const unlockAudioContext = () => {
    const ctx = audioContextRef.current;
    if (ctx?.state === "suspended") ctx.resume();
    else if (!ctx) {
      const Ctx = window.AudioContext || window.webkitAudioContext;
      if (Ctx) {
        audioContextRef.current = new Ctx();
        audioContextRef.current.resume();
      }
    }
  };

  const togglePlay = () => {
    setError(null);
    retryCountRef.current = 0;
    unlockAudioContext();
    if (playing) {
      setAudioReady(false);
      useStreamFallbackRef.current = false;
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
    useStreamFallbackRef.current = true;
    if (retryCountRef.current < MAX_RETRIES) {
      retryCountRef.current += 1;
      setError(`Переподключение... (${retryCountRef.current}/${MAX_RETRIES})`);
      setTimeout(() => playStream(), RETRY_DELAY_MS);
    } else {
      setError("Ошибка загрузки. Проверьте эфир в админке.");
      retryCountRef.current = 0;
    }
  };

  useEffect(() => {
    if (!playing) return;
    const poll = () => {
      getBroadcastNowPlaying(moscowDateStr(), null)
        .then((r) => setNowPlayingTitle(r?.title || null))
        .catch(() => setNowPlayingTitle(null));
    };
    poll();
    const id = setInterval(poll, 1000);
    return () => clearInterval(id);
  }, [playing]);

  useEffect(() => {
    const audio = audioRef.current;
    if (!playing || !audioReady || !audio?.src) return;

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

    let cancelled = false;
    const isApple = /iPhone|iPad|iPod|Macintosh|Mac OS X/.test(navigator.userAgent);
    if (isApple) {
      setUseAnalyser(false);
      return;
    }

    const setupAudioContext = async () => {
      const AudioContextClass = window.AudioContext || window.webkitAudioContext;
      if (!AudioContextClass) return;

      let ctx = audioContextRef.current;
      if (!ctx || ctx.state === "closed") {
        ctx = new AudioContextClass();
        audioContextRef.current = ctx;
      }
      if (ctx.state === "suspended") await ctx.resume();
      if (cancelled) return;

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

      let frameCount = 0;
      let hadRealData = false;
      const SAFARI_FALLBACK_FRAMES = 60;

      const animate = () => {
        if (cancelled) return;
        rafRef.current = requestAnimationFrame(animate);
        if (ctx.state === "suspended") ctx.resume();
        if (ctx.state === "running") {
          analyser.getByteFrequencyData(dataArray);
          const maxVal = dataArray.length ? Math.max(...dataArray) : 0;
          if (maxVal > 2) hadRealData = true;
          frameCount++;
          if (!hadRealData && frameCount >= SAFARI_FALLBACK_FRAMES) {
            setUseAnalyser(false);
            return;
          }
          const step = Math.floor(dataArray.length / BAR_COUNT);
          const next = Array(BAR_COUNT)
            .fill(0)
            .map((_, i) => {
              const idx = Math.min(i * step, dataArray.length - 1);
              const v = dataArray[idx] || 0;
              return Math.max(8, Math.min(80, 8 + (v / 255) * 72));
            });
          setBarHeights(next);
        }
      };
      setUseAnalyser(true);
      animate();
    };

    setupAudioContext();

    const onVisibilityChange = () => {
      const ctx = audioContextRef.current;
      if (document.visibilityState === "visible" && ctx?.state === "suspended") {
        ctx.resume();
      }
    };
    document.addEventListener("visibilitychange", onVisibilityChange);

    return () => {
      cancelled = true;
      document.removeEventListener("visibilitychange", onVisibilityChange);
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
  }, [playing, audioReady]);

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
        <p className="player-now-playing">Сейчас в эфире: {nowPlayingTitle || "—"}</p>
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
          setAudioReady(true);
          setLoading(false);
          setError(null);
          retryCountRef.current = 0;
        }}
        onPause={() => {
          setPlaying(false);
          setAudioReady(false);
        }}
        onError={handleAudioError}
        onWaiting={() => setLoading(true)}
        onCanPlay={() => setLoading(false)}
      />
    </div>
  );
}
