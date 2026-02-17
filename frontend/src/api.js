const API = "http://localhost:8000/api";

export async function getStats() {
  const r = await fetch(`${API}/admin/stats`);
  return r.json();
}

export async function getSongs() {
  const r = await fetch(`${API}/songs`);
  return r.json();
}

export async function createSong(data) {
  const r = await fetch(`${API}/songs`, {
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
  const r = await fetch(`${API}/songs/upload/${songId}`, { method: "POST", body: fd });
  return r.json();
}

export async function generateFromJamendo() {
  const r = await fetch(`${API}/songs/jamendo/generate`, { method: "POST" });
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
  const r = await fetch(`${API}/songs/${songId}/generate-dj`, { method: "POST" });
  return r.json();
}

export async function generateDjBatch(songIds) {
  const r = await fetch(`${API}/songs/generate-dj-batch?${songIds.map((id) => `song_ids=${id}`).join("&")}`, {
    method: "POST",
  });
  return r.json();
}

export async function generateDjTts(songId, voice = "ru-RU-DmitryNeural") {
  const r = await fetch(`${API}/songs/${songId}/tts?voice=${encodeURIComponent(voice)}`, { method: "POST" });
  return r.json();
}

export async function updateSong(songId, data) {
  const r = await fetch(`${API}/songs/${songId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  return r.json();
}

export async function deleteSong(songId) {
  const r = await fetch(`${API}/songs/${songId}`, { method: "DELETE" });
  return r.json();
}

export async function getNews() {
  const r = await fetch(`${API}/news`);
  return r.json();
}

export async function createNews(text) {
  const r = await fetch(`${API}/news`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
  return r.json();
}

export async function generateNews() {
  const r = await fetch(`${API}/news/generate`, { method: "POST" });
  return r.json();
}

export async function generateNewsTts(newsId, voice = "ru-RU-DmitryNeural") {
  const r = await fetch(`${API}/news/${newsId}/tts?voice=${encodeURIComponent(voice)}`, { method: "POST" });
  return r.json();
}

export async function updateNews(newsId, text) {
  const r = await fetch(`${API}/news/${newsId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
  return r.json();
}

export async function deleteNews(newsId) {
  const r = await fetch(`${API}/news/${newsId}`, { method: "DELETE" });
  return r.json();
}

export async function getWeather() {
  const r = await fetch(`${API}/weather`);
  return r.json();
}

export async function createWeather(text) {
  const r = await fetch(`${API}/weather`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
  return r.json();
}

export async function generateWeather() {
  const r = await fetch(`${API}/weather/generate`, { method: "POST" });
  return r.json();
}

export async function generateWeatherTts(weatherId, voice = "ru-RU-DmitryNeural") {
  const r = await fetch(`${API}/weather/${weatherId}/tts?voice=${encodeURIComponent(voice)}`, { method: "POST" });
  return r.json();
}

export async function updateWeather(weatherId, text) {
  const r = await fetch(`${API}/weather/${weatherId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
  return r.json();
}

export async function deleteWeather(weatherId) {
  const r = await fetch(`${API}/weather/${weatherId}`, { method: "DELETE" });
  return r.json();
}

export async function getPodcasts() {
  const r = await fetch(`${API}/podcasts`);
  return r.json();
}

export async function createPodcast(title, file) {
  const fd = new FormData();
  fd.append("title", title);
  fd.append("file", file);
  const r = await fetch(`${API}/podcasts`, { method: "POST", body: fd });
  return r.json();
}

export async function deletePodcast(podcastId) {
  const r = await fetch(`${API}/podcasts/${podcastId}`, { method: "DELETE" });
  return r.json();
}

export async function getIntros() {
  const r = await fetch(`${API}/intros`);
  return r.json();
}

export async function createIntro(title, file) {
  const fd = new FormData();
  fd.append("title", title);
  fd.append("file", file);
  const r = await fetch(`${API}/intros`, { method: "POST", body: fd });
  return r.json();
}

export async function deleteIntro(introId) {
  const r = await fetch(`${API}/intros/${introId}`, { method: "DELETE" });
  return r.json();
}

export async function getBroadcast(date) {
  const r = await fetch(`${API}/broadcast?d=${date}`);
  return r.json();
}

export async function generateBroadcast(date) {
  const r = await fetch(`${API}/broadcast/generate?d=${date}`, { method: "POST" });
  return r.json();
}

export async function getTtsVoices() {
  const r = await fetch(`${API}/tts/voices`);
  return r.json();
}
