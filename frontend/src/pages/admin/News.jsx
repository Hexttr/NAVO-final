import { useState, useEffect, useRef } from "react";
import { useOutletContext } from "react-router-dom";
import { Pencil, Play, Square, X } from "lucide-react";
import {
  getNews,
  createNews,
  generateNews,
  generateNewsTts,
  regenerateNewsText,
  updateNews,
  deleteNews,
  getTtsVoices,
  getNewsAudioUrl,
} from "../../api";
import "./EntityPage.css";

export default function News() {
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
    getNews(selectedDate).then(setItems).finally(() => setLoading(false));
  };

  const handleAdd = async () => {
    if (!newText.trim()) return;
    await createNews(newText.trim(), selectedDate);
    setNewText("");
    load();
  };

  const handleGenerate = async () => {
    setGenerating(true);
    try {
      await generateNews(selectedDate);
      load();
    } catch (e) {
      alert(e.message || "Ошибка генерации");
    } finally {
      setGenerating(false);
    }
  };

  const handleTts = async (id) => {
    try {
      await generateNewsTts(id, selectedVoice);
      load();
    } catch (e) {
      alert(e.message || "Ошибка TTS");
    }
  };

  const handleTtsAll = async () => {
    const ids = items.filter((n) => n.text && !n.audio_path).map((n) => n.id);
    if (!ids.length) {
      alert("Нет выпусков для озвучки");
      return;
    }
    setTtsProgress({ current: 0, total: ids.length });
    for (let i = 0; i < ids.length; i++) {
      try {
        const res = await generateNewsTts(ids[i], selectedVoice);
        setItems((prev) =>
          prev.map((n) => (n.id === ids[i] ? { ...n, audio_path: res.audio_path } : n))
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
    const url = getNewsAudioUrl(item.id);
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
      await updateNews(id, text);
      setEditingId(null);
      load();
    } finally {
      setEditBusy(false);
    }
  };

  const handleRegenerateInEdit = async (id) => {
    setEditBusy(true);
    try {
      const updated = await regenerateNewsText(id);
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
      await generateNewsTts(id, selectedVoice);
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
    await deleteNews(id);
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
      <h2>Новости {dateLabel && `— ${dateLabel}`}</h2>

      <div className="add-manual">
        <textarea
          placeholder="Текст выпуска новостей"
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
          disabled={loading || generating || !!ttsProgress || !items.filter((n) => n.text && !n.audio_path).length}
        >
          Озвучить для всех
        </button>
      </div>

      {generating && (
        <div className="jamendo-progress">
          <div className="progress-bar">
            <div className="progress-fill progress-indeterminate" />
          </div>
          <span className="progress-text">Генерация выпуска новостей...</span>
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
        {items.map((n) => (
          <div
            key={n.id}
            className={`item-card item-card-collapsible ${expandedId === n.id ? "expanded" : ""}`}
          >
            {editingId === n.id ? (
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
                    onClick={() => handleSave(n.id, editingText)}
                    disabled={editBusy}
                  >
                    Сохранить
                  </button>
                  <button
                    type="button"
                    className="regen-btn"
                    onClick={() => handleRegenerateInEdit(n.id)}
                    disabled={editBusy}
                  >
                    Перегенерировать текст
                  </button>
                  <button
                    type="button"
                    className="revoice-btn"
                    onClick={() => handleRevoiceInEdit(n.id)}
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
                  onClick={() => setExpandedId(expandedId === n.id ? null : n.id)}
                >
                  <span className="item-preview">
                    {n.text.length > PREVIEW_LEN ? `${n.text.slice(0, PREVIEW_LEN)}...` : n.text}
                  </span>
                  <div className="item-card-header-actions" onClick={(e) => e.stopPropagation()}>
                    <button
                      type="button"
                      className="item-icon-btn edit-btn"
                      onClick={() => {
                        setEditingId(n.id);
                        setEditingText(n.text || "");
                      }}
                      title="Редактировать"
                    >
                      <Pencil size={14} />
                    </button>
                    {n.audio_path && (
                      <button
                        type="button"
                        className={`item-icon-btn play-btn ${playingId === n.id ? "playing" : ""}`}
                        onClick={() => handlePlay(n)}
                        title={playingId === n.id ? "Стоп" : "Воспроизвести"}
                      >
                        {playingId === n.id ? <Square size={14} /> : <Play size={14} />}
                      </button>
                    )}
                    <button
                      type="button"
                      className="item-icon-btn delete-btn"
                      onClick={() => handleDelete(n.id)}
                      title="Удалить"
                    >
                      <X size={14} />
                    </button>
                  </div>
                </div>
                {expandedId === n.id && (
                  <div className="item-card-body">
                    <p className="item-text">{n.text}</p>
                    {n.text && !n.audio_path && (
                      <div className="item-actions">
                        <button onClick={() => handleTts(n.id)}>Озвучить</button>
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
