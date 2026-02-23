const API =
  import.meta.env.DEV ? "http://localhost:8000/api" : "/api";
const BASE = import.meta.env.DEV ? "http://localhost:8000" : "";

/** Заголовки авторизации для админки (X-Admin-Key) */
function authHeaders() {
  const k = sessionStorage.getItem("admin_api_key");
  return k ? { "X-Admin-Key": k } : {};
}

/** Обёртка fetch с auth для админ-API */
async function apiFetch(url, opts = {}) {
  const r = await fetch(url, { ...opts, headers: { ...opts.headers, ...authHeaders() } });
  if (r.status === 401) {
    sessionStorage.removeItem("admin_api_key");
    window.dispatchEvent(new CustomEvent("admin-unauth"));
  }
  return r;
}

export async function checkAuth(key = "") {
  const r = await fetch(`${BASE || ""}/api/auth/check`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ key: key.trim() }),
  });
  const data = await r.json();
  if (r.ok && data.ok && key.trim()) {
    sessionStorage.setItem("admin_api_key", key.trim());
  }
  return data;
}

export function hasStoredAdminKey() {
  return !!sessionStorage.getItem("admin_api_key");
}

/** Текущая дата по Москве (UTC+3) в формате YYYY-MM-DD */
export function moscowDateStr() {
  return new Date(Date.now() + 3 * 3600 * 1000).toISOString().slice(0, 10);
}

export async function getStats() {
  const r = await apiFetch(`${API}/admin/stats`);
  return r.json();
}

export async function getDiagnostics() {
  const r = await apiFetch(`${BASE || ""}/api/diagnostics`, { cache: "no-store" });
  return r.json();
}

/** Диагностика «Сейчас играет» — для отладки рассинхрона */
export async function getDiagnosticsNowPlaying(date = null) {
  const d = date || moscowDateStr();
  const r = await apiFetch(`${BASE || ""}/api/broadcast/diagnostics/now-playing?d=${d}`, { cache: "no-store" });
  const data = await r.json();
  if (!r.ok) {
    throw new Error(data.detail || data.error || `HTTP ${r.status}`);
  }
  return data;
}

export async function getSongs() {
  const r = await apiFetch(`${API}/songs`);
  return r.json();
}

export async function getSong(songId) {
  const r = await apiFetch(`${API}/songs/${songId}`);
  if (!r.ok) throw new Error("Песня не найдена");
  return r.json();
}

export function getSongAudioUrl(songId) {
  return `${API.replace("/api", "")}/api/songs/${songId}/audio`;
}

export function getSongDjAudioUrl(songId) {
  return `${API.replace("/api", "")}/api/songs/${songId}/dj-audio`;
}
export function getPodcastAudioUrl(podcastId) {
  return `${API.replace("/api", "")}/api/podcasts/${podcastId}/audio`;
}
export function getIntroAudioUrl(introId) {
  return `${API.replace("/api", "")}/api/intros/${introId}/audio`;
}

export async function createSong(data) {
  const r = await apiFetch(`${API}/songs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  const res = await r.json();
  if (!r.ok) throw new Error(res.detail || "Ошибка создания");
  return res;
}

export async function uploadSongFile(songId, file) {
  const fd = new FormData();
  fd.append("file", file);
  const r = await apiFetch(`${API}/songs/upload/${songId}`, { method: "POST", body: fd });
  return r.json();
}

export async function generateFromJamendo() {
  const r = await apiFetch(`${API}/songs/jamendo/generate`, { method: "POST" });
  const data = await r.json();
  if (!r.ok) throw new Error(data.detail || "Ошибка Jamendo");
  return data;
}

/** Stream Jamendo generation with progress. onProgress({ progress, current, total, created }) */
export function generateFromJamendoStream(onProgress) {
  const base = API.replace("/api", "");
  const eventSource = new EventSource(`${base}/api/songs/jamendo/generate-stream`);
  eventSource.onmessage = (e) => {
    try {
      const data = JSON.parse(e.data);
      onProgress(data);
      if (data.done || data.error) eventSource.close();
    } catch (_) {}
  };
  eventSource.onerror = () => eventSource.close();
  return () => eventSource.close();
}

export async function generateDj(songId) {
  const r = await apiFetch(`${API}/songs/${songId}/generate-dj`, { method: "POST" });
  const data = await r.json();
  if (!r.ok) throw new Error(data.detail || "Ошибка");
  return data;
}

export async function generateDjBatch(songIds) {
  const r = await apiFetch(`${API}/songs/generate-dj-batch?${songIds.map((id) => `song_ids=${id}`).join("&")}`, {
    method: "POST",
  });
  return r.json();
}

export async function generateDjTts(songId, voice = "ru-RU-DmitryNeural") {
  const settings = await getSettings();
  if (settings.tts_provider === "elevenlabs") {
    const r = await apiFetch(`${API}/songs/${songId}`);
    const item = await r.json();
    const { localElevenLabsTTS, uploadTTSAudio } = await import("./elevenlabs.js");
    const blob = await localElevenLabsTTS(item.dj_text, voice);
    return uploadTTSAudio("songs", songId, blob);
  }
  const r = await apiFetch(`${API}/songs/${songId}/tts?voice=${encodeURIComponent(voice)}`, { method: "POST" });
  if (!r.ok) {
    const err = await r.json().catch(() => ({}));
    throw new Error(err.detail || "Ошибка TTS");
  }
  return r.json();
}

export async function updateSong(songId, data) {
  const r = await apiFetch(`${API}/songs/${songId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  return r.json();
}

export async function deleteSong(songId) {
  const r = await apiFetch(`${API}/songs/${songId}`, { method: "DELETE" });
  return r.json();
}

export async function getNews(date) {
  const url = date ? `${API}/news?d=${date}` : `${API}/news`;
  const r = await apiFetch(url);
  return r.json();
}

export async function createNews(text, broadcastDate) {
  const r = await apiFetch(`${API}/news`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, broadcast_date: broadcastDate || null }),
  });
  return r.json();
}

export async function generateNews(broadcastDate) {
  const url = broadcastDate ? `${API}/news/generate?d=${broadcastDate}` : `${API}/news/generate`;
  const r = await apiFetch(url, { method: "POST" });
  const text = await r.text();
  if (!r.ok) {
    try {
      const data = JSON.parse(text);
      const msg = Array.isArray(data.detail) ? data.detail[0]?.msg : (data.detail || data.message);
      throw new Error(msg || "Ошибка генерации");
    } catch (e) {
      if (e instanceof SyntaxError) throw new Error(text.slice(0, 150) || "Ошибка генерации");
      throw e;
    }
  }
  return JSON.parse(text);
}

export async function regenerateNewsText(newsId, broadcastDate, broadcastItemId) {
  let url = `${API}/news/${newsId}/regenerate`;
  const params = [];
  if (broadcastDate) params.push(`d=${broadcastDate}`);
  if (broadcastItemId != null) params.push(`broadcast_item_id=${broadcastItemId}`);
  if (params.length) url += "?" + params.join("&");
  const r = await apiFetch(url, { method: "POST" });
  const data = await r.json();
  if (!r.ok) throw new Error(data.detail || "Ошибка");
  return data;
}

export async function generateNewsTts(newsId, voice = "ru-RU-DmitryNeural") {
  const settings = await getSettings();
  if (settings.tts_provider === "elevenlabs") {
    const r = await apiFetch(`${API}/news/${newsId}`);
    const item = await r.json();
    const { localElevenLabsTTS, uploadTTSAudio } = await import("./elevenlabs.js");
    const blob = await localElevenLabsTTS(item.text, voice);
    return uploadTTSAudio("news", newsId, blob);
  }
  const r = await apiFetch(`${API}/news/${newsId}/tts?voice=${encodeURIComponent(voice)}`, { method: "POST" });
  if (!r.ok) {
    const err = await r.json().catch(() => ({}));
    throw new Error(err.detail || "Ошибка TTS");
  }
  return r.json();
}

export function getNewsAudioUrl(newsId) {
  return `${API.replace("/api", "")}/api/news/${newsId}/audio`;
}

export async function updateNews(newsId, text) {
  const r = await apiFetch(`${API}/news/${newsId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
  return r.json();
}

export async function getNewsOldCount() {
  const r = await apiFetch(`${API}/news/old-count`);
  return r.json();
}

export async function clearOldNews() {
  const r = await apiFetch(`${API}/news/clear-old`, { method: "DELETE" });
  return r.json();
}

export async function deleteNews(newsId) {
  const r = await apiFetch(`${API}/news/${newsId}`, { method: "DELETE" });
  return r.json();
}

export async function getWeather(date) {
  const url = date ? `${API}/weather?d=${date}` : `${API}/weather`;
  const r = await apiFetch(url);
  return r.json();
}

export async function createWeather(text, broadcastDate) {
  const r = await apiFetch(`${API}/weather`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, broadcast_date: broadcastDate || null }),
  });
  return r.json();
}

export async function generateWeather(broadcastDate) {
  const url = broadcastDate ? `${API}/weather/generate?d=${broadcastDate}` : `${API}/weather/generate`;
  const r = await apiFetch(url, { method: "POST" });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.detail || data.message || `Ошибка ${r.status}`);
  return data;
}

export async function regenerateWeatherText(weatherId, broadcastDate, broadcastItemId) {
  let url = `${API}/weather/${weatherId}/regenerate`;
  const params = [];
  if (broadcastDate) params.push(`d=${broadcastDate}`);
  if (broadcastItemId != null) params.push(`broadcast_item_id=${broadcastItemId}`);
  if (params.length) url += "?" + params.join("&");
  const r = await apiFetch(url, { method: "POST" });
  const data = await r.json();
  if (!r.ok) throw new Error(data.detail || "Ошибка");
  return data;
}

export async function generateWeatherTts(weatherId, voice = "ru-RU-DmitryNeural") {
  const settings = await getSettings();
  if (settings.tts_provider === "elevenlabs") {
    const r = await apiFetch(`${API}/weather/${weatherId}`);
    const item = await r.json();
    const { localElevenLabsTTS, uploadTTSAudio } = await import("./elevenlabs.js");
    const blob = await localElevenLabsTTS(item.text, voice);
    return uploadTTSAudio("weather", weatherId, blob);
  }
  const r = await apiFetch(`${API}/weather/${weatherId}/tts?voice=${encodeURIComponent(voice)}`, { method: "POST" });
  if (!r.ok) {
    const err = await r.json().catch(() => ({}));
    throw new Error(err.detail || "Ошибка TTS");
  }
  return r.json();
}

export function getWeatherAudioUrl(weatherId) {
  return `${API.replace("/api", "")}/api/weather/${weatherId}/audio`;
}

export async function updateWeather(weatherId, text) {
  const r = await apiFetch(`${API}/weather/${weatherId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
  return r.json();
}

export async function getWeatherOldCount() {
  const r = await apiFetch(`${API}/weather/old-count`);
  return r.json();
}

export async function clearOldWeather() {
  const r = await apiFetch(`${API}/weather/clear-old`, { method: "DELETE" });
  return r.json();
}

export async function deleteWeather(weatherId) {
  const r = await apiFetch(`${API}/weather/${weatherId}`, { method: "DELETE" });
  return r.json();
}

export async function getPodcasts() {
  const r = await apiFetch(`${API}/podcasts`);
  return r.json();
}

export async function createPodcast(title, file) {
  const fd = new FormData();
  fd.append("title", title);
  fd.append("file", file);
  const r = await apiFetch(`${API}/podcasts`, { method: "POST", body: fd });
  return r.json();
}

export async function deletePodcast(podcastId) {
  const r = await apiFetch(`${API}/podcasts/${podcastId}`, { method: "DELETE" });
  return r.json();
}

export async function getIntros() {
  const r = await apiFetch(`${API}/intros`);
  return r.json();
}

export async function createIntro(title, file) {
  const fd = new FormData();
  fd.append("title", title);
  fd.append("file", file);
  const r = await apiFetch(`${API}/intros`, { method: "POST", body: fd });
  return r.json();
}

export async function deleteIntro(introId) {
  const r = await apiFetch(`${API}/intros/${introId}`, { method: "DELETE" });
  return r.json();
}

export async function getBroadcast(date) {
  const r = await apiFetch(`${API}/broadcast?d=${date}`);
  return r.json();
}

export async function deleteBroadcast(date) {
  const r = await apiFetch(`${API}/broadcast?d=${date}`, { method: "DELETE" });
  const data = await r.json();
  if (!r.ok) throw new Error(data.detail || "Ошибка");
  return data;
}

export async function getBroadcastPlaylistUrls(date, sync = true) {
  const r = await apiFetch(`${API}/broadcast/playlist-urls?d=${date}&sync=${sync}`);
  if (!r.ok) throw new Error("Нет эфира на эту дату");
  return r.json();
}

/** URL для плеера: Icecast (приоритет) и /stream (fallback). */
export async function getStreamUrl() {
  const base = API.replace("/api", "") || "";
  const r = await apiFetch(`${base}/api/broadcast/stream-url`, { cache: "no-store" });
  const data = await r.json();
  return {
    icecastUrl: data?.icecastUrl || "http://localhost:8001/live",
    streamUrl: data?.streamUrl || base + "/stream",
  };
}

export async function getBroadcastNowPlaying(date, positionSec = null) {
  let url = `${API}/broadcast/now-playing?d=${date}&_=${Date.now()}`;
  if (positionSec != null && positionSec >= 0) {
    url += `&position=${Math.floor(positionSec)}`;
  }
  const r = await apiFetch(url, {
    cache: "no-store",
    headers: { "Cache-Control": "no-cache", Pragma: "no-cache" },
  });
  return r.json();
}

export async function generateBroadcast(date) {
  const r = await apiFetch(`${API}/broadcast/generate?d=${date}`, { method: "POST" });
  const text = await r.text();
  try {
    const data = JSON.parse(text);
    if (!r.ok) throw new Error(data.detail || data.message || "Ошибка генерации");
    return data;
  } catch (e) {
    if (e instanceof SyntaxError) throw new Error(r.status >= 500 ? "Ошибка сервера. Проверьте логи на сервере." : (text || "Ошибка генерации"));
    throw e;
  }
}

/** Скопировать эфир с fromDate на toDate. toDate: YYYY-MM-DD или "tomorrow" */
export async function copyBroadcastToDate(fromDate, toDate) {
  if (toDate === "tomorrow") {
    const d = new Date(fromDate + "T12:00:00Z");
    d.setUTCDate(d.getUTCDate() + 1);
    toDate = d.toISOString().slice(0, 10);
  }
  const r = await apiFetch(`${API}/broadcast/copy?from=${fromDate}&to=${toDate}`, { method: "POST" });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.detail || data.message || `Ошибка ${r.status}`);
  return data;
}

export async function deleteBroadcastItem(itemId, date) {
  const r = await apiFetch(`${API}/broadcast/items/${itemId}?d=${date}`, { method: "DELETE" });
  if (!r.ok) {
    const err = await r.json().catch(() => ({}));
    throw new Error(err.detail || "Ошибка удаления");
  }
  return r.json();
}

export async function insertBroadcastItem(itemId, date, entityType, entityId) {
  const r = await apiFetch(`${API}/broadcast/items/${itemId}/insert?d=${date}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ entity_type: entityType, entity_id: entityId }),
  });
  if (!r.ok) {
    const err = await r.json().catch(() => ({}));
    throw new Error(err.detail || "Ошибка вставки");
  }
  return r.json();
}

export async function moveBroadcastItem(date, fromIndex, toIndex) {
  const r = await apiFetch(
    `${API}/broadcast/move?d=${date}&from_index=${fromIndex}&to_index=${toIndex}`,
    { method: "POST" }
  );
  if (!r.ok) throw new Error("Ошибка перемещения");
  return r.json();
}

export async function swapBroadcastItems(date, fromIndex, toIndex) {
  const r = await apiFetch(
    `${API}/broadcast/swap?d=${date}&from_index=${fromIndex}&to_index=${toIndex}`,
    { method: "POST" }
  );
  if (!r.ok) throw new Error("Ошибка обмена");
  return r.json();
}

export async function getTtsVoices() {
  // Always use backend proxy — for ElevenLabs it avoids CORS; for Edge TTS it returns Edge voices.
  const r = await apiFetch(`${API}/tts/voices`);
  return r.json();
}

export async function getSettings() {
  const r = await apiFetch(`${API}/settings`);
  return r.json();
}

export async function saveSettings(data) {
  const r = await apiFetch(`${API}/settings`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  const res = await r.json();
  if (!r.ok) throw new Error(res.detail || "Ошибка сохранения");
  return res;
}
