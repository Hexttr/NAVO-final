import { useState, useEffect, useRef } from "react";
import {
  getWeather,
  createWeather,
  generateWeather,
  generateWeatherTts,
  updateWeather,
  deleteWeather,
  getTtsVoices,
  getWeatherAudioUrl,
} from "../../api";
import "./EntityPage.css";

export default function Weather() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [voices, setVoices] = useState([]);
  const [newText, setNewText] = useState("");
  const [editingId, setEditingId] = useState(null);
  const [selectedVoice, setSelectedVoice] = useState("ru-RU-DmitryNeural");
  const [generating, setGenerating] = useState(false);
  const [ttsProgress, setTtsProgress] = useState(null);
  const [playingId, setPlayingId] = useState(null);
  const audioRef = useRef(null);

  useEffect(() => {
    load();
    getTtsVoices().then((r) => setVoices(r.voices || []));
  }, []);

  const load = () => {
    setLoading(true);
    getWeather().then(setItems).finally(() => setLoading(false));
  };

  const handleAdd = async () => {
    if (!newText.trim()) return;
    await createWeather(newText.trim());
    setNewText("");
    load();
  };

  const handleGenerate = async () => {
    setGenerating(true);
    try {
      await generateWeather();
      load();
    } catch (e) {
      alert(e.message || "Ошибка генерации");
    } finally {
      setGenerating(false);
    }
  };

  const handleTts = async (id) => {
    try {
      await generateWeatherTts(id, selectedVoice);
      load();
    } catch (e) {
      alert(e.message || "Ошибка TTS");
    }
  };

  const handleTtsAll = async () => {
    const ids = items.filter((w) => w.text && !w.audio_path).map((w) => w.id);
    if (!ids.length) {
      alert("Нет прогнозов для озвучки");
      return;
    }
    setTtsProgress({ current: 0, total: ids.length });
    for (let i = 0; i < ids.length; i++) {
      try {
        const res = await generateWeatherTts(ids[i], selectedVoice);
        setItems((prev) =>
          prev.map((w) => (w.id === ids[i] ? { ...w, audio_path: res.audio_path } : w))
        );
      } catch (e) {
        console.warn(`TTS для ${ids[i]} не выполнен:`, e);
      }
      setTtsProgress({ current: i + 1, total: ids.length });
    }
    setTtsProgress(null);
  };

  const handlePlay = (item) => {
    if (!item.audio_path) return;
    const audio = audioRef.current;
    const url = getWeatherAudioUrl(item.id);
    if (playingId === item.id && audio && !audio.paused) {
      audio.pause();
      setPlayingId(null);
    } else {
      audio.src = url;
      audio.play();
      setPlayingId(item.id);
    }
  };

  const handleSave = async (id, text) => {
    await updateWeather(id, text);
    setEditingId(null);
    load();
  };

  const handleDelete = async (id) => {
    if (!confirm("Удалить?")) return;
    await deleteWeather(id);
    load();
  };

  if (loading && !items.length) return <div className="loading">Загрузка...</div>;

  return (
    <div className="entity-page">
      <h2>Погода</h2>

      <div className="entity-actions">
        <div className="add-manual">
          <textarea
            placeholder="Текст прогноза погоды"
            value={newText}
            onChange={(e) => setNewText(e.target.value)}
            rows={4}
            style={{ width: 400 }}
          />
          <button onClick={handleAdd} disabled={!newText.trim()}>
            Добавить вручную
          </button>
        </div>
        <button
          className="primary"
          onClick={handleGenerate}
          disabled={loading || generating || !!ttsProgress}
        >
          Сгенерировать
        </button>
        <button
          onClick={handleTtsAll}
          disabled={loading || generating || !!ttsProgress || !items.filter((w) => w.text && !w.audio_path).length}
        >
          Озвучить для всех
        </button>
      </div>

      {generating && (
        <div className="jamendo-progress">
          <div className="progress-bar">
            <div className="progress-fill progress-indeterminate" />
          </div>
          <span className="progress-text">Генерация прогноза погоды...</span>
        </div>
      )}
      {ttsProgress && (
        <div className="jamendo-progress">
          <div className="progress-bar">
            <div
              className="progress-fill"
              style={{ width: `${(ttsProgress.current / ttsProgress.total) * 100}%` }}
            />
          </div>
          <span className="progress-text">
            Озвучивается: {ttsProgress.current}/{ttsProgress.total}
          </span>
        </div>
      )}

      <div className="voice-select">
        <label>Голос TTS:</label>
        <select value={selectedVoice} onChange={(e) => setSelectedVoice(e.target.value)}>
          {voices.map(([id, name]) => (
            <option key={id} value={id}>
              {name}
            </option>
          ))}
        </select>
      </div>

      <audio ref={audioRef} onEnded={() => setPlayingId(null)} />
      <div className="items-list">
        {items.map((w) => (
          <div key={w.id} className="item-card">
            {editingId === w.id ? (
              <div>
                <textarea
                  defaultValue={w.text}
                  onBlur={(e) => handleSave(w.id, e.target.value)}
                  rows={6}
                  className="text-block"
                />
                <button onClick={() => setEditingId(null)}>Готово</button>
              </div>
            ) : (
              <div>
                <p className="item-text">{w.text}</p>
                <div className="item-actions">
                  <button onClick={() => setEditingId(w.id)}>Редактировать</button>
                  {w.audio_path && (
                    <button onClick={() => handlePlay(w)}>
                      {playingId === w.id ? "Стоп" : "Воспроизвести"}
                    </button>
                  )}
                  {w.text && !w.audio_path && (
                    <button onClick={() => handleTts(w.id)}>Озвучить</button>
                  )}
                  <button className="danger" onClick={() => handleDelete(w.id)}>
                    Удалить
                  </button>
                </div>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
