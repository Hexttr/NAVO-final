import { useState, useEffect, useRef } from "react";
import { useOutletContext } from "react-router-dom";
import { Pencil, Play, Square, X } from "lucide-react";
import {
  getWeather,
  createWeather,
  generateWeather,
  generateWeatherTts,
  regenerateWeatherText,
  updateWeather,
  deleteWeather,
  getTtsVoices,
  getWeatherAudioUrl,
} from "../../api";
import "./EntityPage.css";

export default function Weather() {
  const { selectedDate } = useOutletContext();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [voices, setVoices] = useState([]);
  const [newText, setNewText] = useState("");
  const [editingId, setEditingId] = useState(null);
  const [editingText, setEditingText] = useState("");
  const [editBusy, setEditBusy] = useState(false);
  const editTextareaRef = useRef(null);
  const [selectedVoice, setSelectedVoice] = useState("ru-RU-DmitryNeural");
  const [generating, setGenerating] = useState(false);
  const [ttsProgress, setTtsProgress] = useState(null);
  const [playingId, setPlayingId] = useState(null);
  const [expandedId, setExpandedId] = useState(null);
  const audioRef = useRef(null);

  const PREVIEW_LEN = 100;

  useEffect(() => {
    load();
    getTtsVoices().then((r) => {
      const v = r.voices || [];
      setVoices(v);
      if (v.length > 0) {
        setSelectedVoice((prev) => (v.some((x) => x[0] === prev) ? prev : v[0][0]));
      }
    });
  }, [selectedDate]);

  useEffect(() => {
    const ta = editTextareaRef.current;
    if (ta && editingId) {
      ta.style.height = "auto";
      ta.style.height = Math.max(120, ta.scrollHeight) + "px";
    }
  }, [editingText, editingId]);

  const load = () => {
    setLoading(true);
    getWeather(selectedDate).then(setItems).finally(() => setLoading(false));
  };

  const handleAdd = async () => {
    if (!newText.trim()) return;
    await createWeather(newText.trim(), selectedDate);
    setNewText("");
    load();
  };

  const handleGenerate = async () => {
    setGenerating(true);
    try {
      await generateWeather(selectedDate);
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
    setEditBusy(true);
    try {
      await updateWeather(id, text);
      setEditingId(null);
      load();
    } finally {
      setEditBusy(false);
    }
  };

  const handleRegenerateInEdit = async (id) => {
    setEditBusy(true);
    try {
      const updated = await regenerateWeatherText(id);
      setEditingText(updated.text || "");
    } catch (e) {
      alert(e.message || "Ошибка перегенерации");
    } finally {
      setEditBusy(false);
    }
  };

  const handleRevoiceInEdit = async (id) => {
    setEditBusy(true);
    try {
      await generateWeatherTts(id, selectedVoice);
      load();
      setEditingId(null);
    } catch (e) {
      alert(e.message || "Ошибка озвучки");
    } finally {
      setEditBusy(false);
    }
  };

  const handleDelete = async (id) => {
    if (!confirm("Удалить?")) return;
    await deleteWeather(id);
    load();
  };

  if (loading && !items.length) return <div className="loading">Загрузка...</div>;

  const dateLabel = selectedDate
    ? new Date(selectedDate + "T12:00:00").toLocaleDateString("ru-RU", {
        day: "numeric",
        month: "long",
        year: "numeric",
      })
    : "";

  return (
    <div className="entity-page">
      <h2>Погода {dateLabel && `— ${dateLabel}`}</h2>

      <div className="add-manual">
        <textarea
          placeholder="Текст прогноза погоды"
          value={newText}
          onChange={(e) => setNewText(e.target.value)}
          rows={8}
        />
      </div>

      <div className="entity-toolbar">
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
        <button onClick={handleAdd} disabled={!newText.trim()}>
          Добавить вручную
        </button>
        <button
          className="primary"
          onClick={handleGenerate}
          disabled={loading || generating || !!ttsProgress}
        >
          Сгенерировать
        </button>
        <button
          className="tts-all-btn"
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

      <audio ref={audioRef} onEnded={() => setPlayingId(null)} />
      <div className="items-list items-list-compact">
        {items.map((w) => (
          <div
            key={w.id}
            className={`item-card item-card-collapsible ${expandedId === w.id ? "expanded" : ""}`}
          >
            {editingId === w.id ? (
              <div className="item-edit-form">
                <textarea
                  ref={editTextareaRef}
                  value={editingText}
                  onChange={(e) => setEditingText(e.target.value)}
                  rows={4}
                />
                <div className="item-edit-form-actions">
                  <button
                    type="button"
                    onClick={() => handleSave(w.id, editingText)}
                    disabled={editBusy}
                  >
                    Сохранить
                  </button>
                  <button
                    type="button"
                    className="regen-btn"
                    onClick={() => handleRegenerateInEdit(w.id)}
                    disabled={editBusy}
                  >
                    Перегенерировать текст
                  </button>
                  <button
                    type="button"
                    className="revoice-btn"
                    onClick={() => handleRevoiceInEdit(w.id)}
                    disabled={editBusy || !editingText.trim()}
                  >
                    Переозвучить
                  </button>
                </div>
              </div>
            ) : (
              <>
                <div
                  className="item-card-header"
                  onClick={() => setExpandedId(expandedId === w.id ? null : w.id)}
                >
                  <span className="item-preview">
                    {w.text.length > PREVIEW_LEN ? `${w.text.slice(0, PREVIEW_LEN)}...` : w.text}
                  </span>
                  <div className="item-card-header-actions" onClick={(e) => e.stopPropagation()}>
                    <button
                      type="button"
                      className="item-icon-btn edit-btn"
                      onClick={() => {
                        setEditingId(w.id);
                        setEditingText(w.text || "");
                      }}
                      title="Редактировать"
                    >
                      <Pencil size={14} />
                    </button>
                    {w.audio_path && (
                      <button
                        type="button"
                        className={`item-icon-btn play-btn ${playingId === w.id ? "playing" : ""}`}
                        onClick={() => handlePlay(w)}
                        title={playingId === w.id ? "Стоп" : "Воспроизвести"}
                      >
                        {playingId === w.id ? <Square size={14} /> : <Play size={14} />}
                      </button>
                    )}
                    <button
                      type="button"
                      className="item-icon-btn delete-btn"
                      onClick={() => handleDelete(w.id)}
                      title="Удалить"
                    >
                      <X size={14} />
                    </button>
                  </div>
                </div>
                {expandedId === w.id && (
                  <div className="item-card-body">
                    <p className="item-text">{w.text}</p>
                    {w.text && !w.audio_path && (
                      <div className="item-actions">
                        <button onClick={() => handleTts(w.id)}>Озвучить</button>
                      </div>
                    )}
                  </div>
                )}
              </>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
