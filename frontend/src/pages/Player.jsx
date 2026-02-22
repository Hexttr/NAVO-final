import { useState, useRef, useEffect } from "react";
import { Play, Square } from "lucide-react";
import Hls from "hls.js";
import { getBroadcastNowPlaying, getHlsUrl, moscowDateStr } from "../api";
import "./Player.css";

const STREAM_URL = "/stream";
const HLS_CANPLAY_TIMEOUT_MS = 20000; // Если HLS не даёт canplay за 20 сек — fallback на /stream
const EQ_BARS = 24;
const BAR_COUNT = EQ_BARS;
const MAX_RETRIES = 5;
const RETRY_DELAY_MS = 2000;

/** Текущая секунда дня по Москве (UTC+3) */
function moscowSecondsNow() {
  const d = new Date();
  const moscowMs = d.getTime() + 3 * 3600 * 1000;
  const m = new Date(moscowMs);
  return m.getUTCHours() * 3600 + m.getUTCMinutes() * 60 + m.getUTCSeconds();
}

export default function Player() {
  const [playing, setPlaying] = useState(false);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);
  const [nowPlayingTitle, setNowPlayingTitle] = useState(null);
  const [barHeights, setBarHeights] = useState(() => Array(BAR_COUNT).fill(15));
  const [useAnalyser, setUseAnalyser] = useState(false);
  const [audioReady, setAudioReady] = useState(false); // true когда audio реально играет (onPlay) — для Safari
  const audioRef = useRef(null);
  const hlsRef = useRef(null);
  const audioContextRef = useRef(null);
  const analyserRef = useRef(null);
  const sourceRef = useRef(null);
  const dataArrayRef = useRef(null);
  const rafRef = useRef(null);
  const retryCountRef = useRef(0);
  const positionGetterRef = useRef(null);
  const useStreamFallbackRef = useRef(false); // true = /stream, API использует stream_position

  const playStream = async () => {
    if (!audioRef.current) return;
    const today = moscowDateStr();
    let { url: hlsUrl, startPosition: serverStartSec } = await getHlsUrl(today);
    const audio = audioRef.current;
    const startSec = serverStartSec != null ? serverStartSec : moscowSecondsNow();

    if (hlsUrl) {
      try {
        const base = window.location.origin;
        const fullUrl = hlsUrl.startsWith("http") ? hlsUrl : base + hlsUrl;
        const ac = new AbortController();
        const t = setTimeout(() => ac.abort(), 5000);
        try {
          const probe = await fetch(fullUrl, { method: "HEAD", signal: ac.signal });
          if (!probe.ok) hlsUrl = null;
        } finally {
          clearTimeout(t);
        }
      } catch {
        hlsUrl = null;
      }
    }

    if (hlsUrl) {
      useStreamFallbackRef.current = false;
      if (Hls.isSupported()) {
        if (hlsRef.current) {
          hlsRef.current.destroy();
          hlsRef.current = null;
        }
        audio.removeAttribute("src");
        const hlsConfig = {
          startPosition: startSec,
          maxBufferLength: 60,
          maxMaxBufferLength: 120,
        };
        const hls = new Hls(hlsConfig);
        hlsRef.current = hls;
        hls.loadSource(hlsUrl);
        hls.attachMedia(audio);
        positionGetterRef.current = () => audioRef.current?.currentTime ?? 0;
        const hlsCanplayTimeout = setTimeout(() => {
          if (hlsRef.current && audio.readyState < 2) {
            hlsRef.current.destroy();
            hlsRef.current = null;
            playStreamFallback(serverStartSec);
          }
        }, HLS_CANPLAY_TIMEOUT_MS);
        const clearCanplayTimeout = () => {
          clearTimeout(hlsCanplayTimeout);
        };
        audio.addEventListener("canplay", clearCanplayTimeout, { once: true });
        audio.addEventListener("playing", clearCanplayTimeout, { once: true });
        audio.addEventListener("error", clearCanplayTimeout, { once: true });
        hls.on(Hls.Events.ERROR, (_, data) => {
          clearTimeout(hlsCanplayTimeout);
          if (data.fatal) {
            hls.destroy();
            hlsRef.current = null;
            if (startSec > 0) {
              const retry = new Hls({ ...hlsConfig, startPosition: 0 });
              hlsRef.current = retry;
              retry.loadSource(hlsUrl);
              retry.attachMedia(audio);
              retry.on(Hls.Events.ERROR, (__, d2) => {
                if (d2.fatal) {
                  retry.destroy();
                  hlsRef.current = null;
                  playStreamFallback(serverStartSec);
                }
              });
              audio.play().catch(() => {});
            } else {
              playStreamFallback(serverStartSec);
            }
          }
        });
        audio.play().catch((e) => {
          setError("Не удалось воспроизвести. Проверьте эфир в админке.");
          setLoading(false);
        });
      } else if (audio.canPlayType("application/vnd.apple.mpegurl")) {
        audio.src = hlsUrl;
        positionGetterRef.current = () => audioRef.current?.currentTime ?? 0;
        const seekToMoscow = () => {
          if (audio.duration && isFinite(audio.duration)) {
            audio.currentTime = Math.min(startSec, audio.duration);
          }
        };
        const nativeHlsTimeout = setTimeout(() => {
          if (audio.readyState < 2) playStreamFallback(serverStartSec);
        }, HLS_CANPLAY_TIMEOUT_MS);
        const onCanplay = () => { clearTimeout(nativeHlsTimeout); seekToMoscow(); };
        audio.addEventListener("loadedmetadata", seekToMoscow, { once: true });
        audio.addEventListener("canplay", onCanplay, { once: true });
        audio.addEventListener("error", () => clearTimeout(nativeHlsTimeout), { once: true });
        audio.play().catch((e) => {
          setError("Не удалось воспроизвести.");
          setLoading(false);
        });
      } else {
        playStreamFallback(serverStartSec);
      }
    } else {
      playStreamFallback(serverStartSec);
    }
  };

  const playStreamFallback = (serverStartSec) => {
    if (!audioRef.current) return;
    useStreamFallbackRef.current = true;
    if (hlsRef.current) {
      hlsRef.current.destroy();
      hlsRef.current = null;
    }
    const startSec = serverStartSec ?? moscowSecondsNow();
    const playStartTime = Date.now();
    positionGetterRef.current = () => startSec + (Date.now() - playStartTime) / 1000;
    audioRef.current.src = STREAM_URL + "?t=" + Date.now();
    audioRef.current.play().catch((e) => {
      setError("Не удалось воспроизвести. Проверьте эфир в админке.");
      setLoading(false);
    });
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
      positionGetterRef.current = null;
      useStreamFallbackRef.current = false;
      if (hlsRef.current) {
        hlsRef.current.destroy();
        hlsRef.current = null;
      }
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
      setError(`Переподключение... (${retryCountRef.current}/${MAX_RETRIES})`);
      setTimeout(() => playStream(), RETRY_DELAY_MS);
    } else {
      setError("Ошибка загрузки. Проверьте эфир в админке.");
      retryCountRef.current = 0;
    }
  };

  useEffect(() => {
    const poll = () => {
      const pos = positionGetterRef.current?.();
      // HLS: currentTime = позиция в потоке (сек от полуночи). Передаём в API.
      // /stream: не передаём position — API использует stream_position (пишет backend).
      const apiPos = useStreamFallbackRef.current ? null : (typeof pos === "number" && isFinite(pos) && pos >= 0 ? pos : null);
      getBroadcastNowPlaying(moscowDateStr(), apiPos)
        .then((r) => setNowPlayingTitle(r?.title || null))
        .catch(() => setNowPlayingTitle(null));
    };
    poll();
    const id = setInterval(poll, 1000);
    return () => clearInterval(id);
  }, []);

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

    // Apple: iOS — все браузеры используют WebKit. Mac — Safari и др. getByteFrequencyData
    // возвращает нули для live stream в WebKit. Fallback для всех Apple-устройств.
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
      if (ctx.state === "suspended") {
        await ctx.resume();
      }
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
      const SAFARI_FALLBACK_FRAMES = 60; // ~1 сек: если нет данных — Safari (getByteFrequencyData=0 для live stream)

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
