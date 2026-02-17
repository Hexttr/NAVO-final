import { useState, useEffect } from "react";
import {
  getWeather,
  createWeather,
  generateWeather,
  generateWeatherTts,
  updateWeather,
  deleteWeather,
  getTtsVoices,
} from "../../api";
import "./EntityPage.css";

export default function Weather() {
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
    getWeather().then(setItems).finally(() => setLoading(false));
  };

  const handleAdd = async () => {
    if (!newText.trim()) return;
    await createWeather(newText.trim());
    setNewText("");
    load();
  };

  const handleGenerate = async () => {
    setLoading(true);
    try {
      await generateWeather();
      load();
    } finally {
      setLoading(false);
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
                  {w.text && !w.audio_path && (
                    <button onClick={() => handleTts(w.id)}>Озвучить</button>
                  )}
                  {w.audio_path && <span className="ok">✓ Озвучено</span>}
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
