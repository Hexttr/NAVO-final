import { useState, useEffect, useRef } from "react";
import {
  getNews,
  createNews,
  generateNews,
  generateNewsTts,
  updateNews,
  deleteNews,
  getTtsVoices,
  getNewsAudioUrl,
} from "../../api";
import "./EntityPage.css";

export default function News() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [voices, setVoices] = useState([]);
  const [newText, setNewText] = useState("");
  const [editingId, setEditingId] = useState(null);
  const [selectedVoice, setSelectedVoice] = useState("ru-RU-DmitryNeural");
  const [generating, setGenerating] = useState(false);
  const [ttsProgress, setTtsProgress] = useState(null);
  const [playingId, setPlayingId] = useState(null);
  const [expandedId, setExpandedId] = useState(null);
  const audioRef = useRef(null);

  const PREVIEW_LEN = 100;

  useEffect(() => {
    load();
    getTtsVoices().then((r) => setVoices(r.voices || []));
  }, []);

  const load = () => {
    setLoading(true);
    getNews().then(setItems).finally(() => setLoading(false));
  };

  const handleAdd = async () => {
    if (!newText.trim()) return;
    await createNews(newText.trim());
    setNewText("");
    load();
  };

  const handleGenerate = async () => {
    setGenerating(true);
    try {
      await generateNews();
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
    await updateNews(id, text);
    setEditingId(null);
    load();
  };

  const handleDelete = async (id) => {
    if (!confirm("Удалить?")) return;
    await deleteNews(id);
    load();
  };

  if (loading && !items.length) return <div className="loading">Загрузка...</div>;

  return (
    <div className="entity-page">
      <h2>Новости</h2>

      <div className="entity-actions">
        <div className="add-manual">
          <textarea
            placeholder="Текст выпуска новостей"
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
      <div className="items-list items-list-compact">
        {items.map((n) => (
          <div
            key={n.id}
            className={`item-card item-card-collapsible ${expandedId === n.id ? "expanded" : ""}`}
          >
            {editingId === n.id ? (
              <div>
                <textarea
                  defaultValue={n.text}
                  onBlur={(e) => handleSave(n.id, e.target.value)}
                  rows={6}
                  className="text-block"
                />
                <button onClick={() => setEditingId(null)}>Готово</button>
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
                  <span className="item-expand-icon">{expandedId === n.id ? "▲" : "▼"}</span>
                </div>
                {expandedId === n.id && (
                  <div className="item-card-body">
                    <p className="item-text">{n.text}</p>
                    <div className="item-actions">
                      <button onClick={() => setEditingId(n.id)}>Редактировать</button>
                      {n.audio_path && (
                        <button onClick={() => handlePlay(n)}>
                          {playingId === n.id ? "Стоп" : "Воспроизвести"}
                        </button>
                      )}
                      {n.text && !n.audio_path && (
                        <button onClick={() => handleTts(n.id)}>Озвучить</button>
                      )}
                      <button className="danger" onClick={() => handleDelete(n.id)}>
                        Удалить
                      </button>
                    </div>
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
