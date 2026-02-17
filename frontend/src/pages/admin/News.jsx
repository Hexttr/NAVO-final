import { useState, useEffect } from "react";
import {
  getNews,
  createNews,
  generateNews,
  generateNewsTts,
  updateNews,
  deleteNews,
  getTtsVoices,
} from "../../api";
import "./EntityPage.css";

export default function News() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [voices, setVoices] = useState([]);
  const [newText, setNewText] = useState("");
  const [editingId, setEditingId] = useState(null);
  const [selectedVoice, setSelectedVoice] = useState("ru-RU-DmitryNeural");

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
    setLoading(true);
    try {
      await generateNews();
      load();
    } finally {
      setLoading(false);
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
        <button className="primary" onClick={handleGenerate} disabled={loading}>
          Сгенерировать
        </button>
      </div>

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

      <div className="items-list">
        {items.map((n) => (
          <div key={n.id} className="item-card">
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
              <div>
                <p className="item-text">{n.text}</p>
                <div className="item-actions">
                  <button onClick={() => setEditingId(n.id)}>Редактировать</button>
                  {n.text && !n.audio_path && (
                    <button onClick={() => handleTts(n.id)}>Озвучить</button>
                  )}
                  {n.audio_path && <span className="ok">✓ Озвучено</span>}
                  <button className="danger" onClick={() => handleDelete(n.id)}>
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
