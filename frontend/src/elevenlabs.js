import { getSettings } from "./api.js";

const API = import.meta.env.DEV ? "http://localhost:8000/api" : "/api";

// Replace TTS functions to use ElevenLabs locally if provider is elevenlabs
export async function uploadTTSAudio(entityType, id, audioBlob) {
  const fd = new FormData();
  fd.append("file", audioBlob, "tts.mp3");
  const r = await fetch(`${API}/${entityType}/${id}/upload-tts`, { method: "POST", body: fd });
  if (!r.ok) {
    const data = await r.json().catch(() => ({}));
    throw new Error(data.detail || "Ошибка загрузки аудио");
  }
  return r.json();
}

export async function localElevenLabsTTS(text, voiceId) {
  const settings = await getSettings();
  const apiKey = settings.elevenlabs_api_key_frontend || ""; // We might need to fetch this or pass it
  if (!apiKey) throw new Error("API ключ ElevenLabs не найден на клиенте");

  // Fallback voice ID if an empty string or generic label is passed from our fallback logic
  const actualVoiceId = voiceId && !voiceId.includes('-') && voiceId.length > 5 ? voiceId : "pFZP5JQG7iQjIQuC4Bku"; // default 'Lily' voice ID or any standard one

  const r = await fetch(`https://api.elevenlabs.io/v1/text-to-speech/${actualVoiceId}`, {
    method: "POST",
    headers: {
      "xi-api-key": apiKey,
      "Content-Type": "application/json",
      "Accept": "audio/mpeg",
    },
    body: JSON.stringify({
      text,
      model_id: "eleven_multilingual_v2",
    }),
  });
  if (!r.ok) {
    const text = await r.text();
    throw new Error(`Ошибка ElevenLabs: ${r.status} ${text.slice(0, 100)}`);
  }
  return r.blob();
}
