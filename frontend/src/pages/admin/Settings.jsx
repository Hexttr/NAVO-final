import { useState, useEffect } from "react";
import { Settings as SettingsIcon, Save, Plus, X } from "lucide-react";
import { getSettings, saveSettings } from "../../api";
import "./Settings.css";

const SLOT_TYPES = [
  { value: "news", label: "Новости" },
  { value: "weather", label: "Погода" },
  { value: "podcast", label: "Подкаст" },
];

export default function Settings() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    getSettings()
      .then(setData)
      .catch(() => setData({}))
      .finally(() => setLoading(false));
  }, []);

  const handleSave = async () => {
    if (!data) return;
    setSaving(true);
    setSaved(false);
    try {
      const res = await saveSettings(data);
      setData(res);
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch (e) {
      alert(e.message || "Ошибка сохранения");
    } finally {
      setSaving(false);
    }
  };

  const addJamendoTag = () => {
    setData((d) => ({
      ...d,
      jamendo_tags: [...(d.jamendo_tags || []), "новый тэг"],
    }));
  };

  const removeJamendoTag = (idx) => {
    setData((d) => ({
      ...d,
      jamendo_tags: d.jamendo_tags.filter((_, i) => i !== idx),
    }));
  };

  const updateJamendoTag = (idx, val) => {
    setData((d) => ({
      ...d,
      jamendo_tags: d.jamendo_tags.map((t, i) => (i === idx ? val : t)),
    }));
  };

  const addBroadcastSlot = () => {
    setData((d) => ({
      ...d,
      broadcast_slots: [...(d.broadcast_slots || []), [12, 0, "news"]],
    }));
  };

  const removeBroadcastSlot = (idx) => {
    setData((d) => ({
      ...d,
      broadcast_slots: d.broadcast_slots.filter((_, i) => i !== idx),
    }));
  };

  const updateBroadcastSlot = (idx, field, val) => {
    setData((d) => {
      const slots = [...(d.broadcast_slots || [])];
      const s = [...slots[idx]];
      if (field === 0) s[0] = parseInt(val, 10) || 0;
      else if (field === 1) s[1] = parseInt(val, 10) || 0;
      else s[2] = val;
      slots[idx] = s;
      return { ...d, broadcast_slots: slots };
    });
  };

  if (loading) return <div className="settings-loading">Загрузка...</div>;

  return (
    <div className="settings-page">
      <div className="settings-header">
        <h2 className="settings-title">
          <SettingsIcon size={22} />
          Настройки
        </h2>
        <button
          className="settings-save-btn"
          onClick={handleSave}
          disabled={saving}
        >
          <Save size={16} />
          {saving ? "Сохранение…" : saved ? "Сохранено" : "Сохранить"}
        </button>
      </div>

      <div className="settings-sections">
        {/* Jamendo tags */}
        <section className="settings-section">
          <h3>Тэги Jamendo</h3>
          <p className="settings-hint">
            Поисковые запросы для выборки музыки. Каждый тэг — отдельный запрос к API Jamendo.
          </p>
          <div className="jamendo-tags-list">
            {(data.jamendo_tags || []).map((tag, idx) => (
              <div key={idx} className="jamendo-tag-row">
                <input
                  type="text"
                  value={tag}
                  onChange={(e) => updateJamendoTag(idx, e.target.value)}
                  placeholder="например: eastern music"
                  className="jamendo-tag-input"
                />
                <button
                  type="button"
                  className="jamendo-tag-remove"
                  onClick={() => removeJamendoTag(idx)}
                  aria-label="Удалить"
                >
                  <X size={14} />
                </button>
              </div>
            ))}
            <button type="button" className="jamendo-tag-add" onClick={addJamendoTag}>
              <Plus size={14} /> Добавить тэг
            </button>
          </div>
        </section>

        {/* LLM provider */}
        <section className="settings-section">
          <h3>Модель для генерации текстов</h3>
          <p className="settings-hint">
            Groq (бесплатно, ограничения) или ChatGPT (OpenAI, платно). API-ключи в .env на сервере.
          </p>
          <div className="settings-select-row">
            <select
              value={data.llm_provider || "groq"}
              onChange={(e) => setData((d) => ({ ...d, llm_provider: e.target.value }))}
              className="settings-select"
            >
              <option value="groq">Groq (Llama)</option>
              <option value="openai">ChatGPT (OpenAI)</option>
            </select>
          </div>
        </section>

        {/* LLM prompts */}
        <section className="settings-section">
          <h3>Промпты для генерации</h3>
          <p className="settings-hint">
            Системный промпт для ИИ. Подставляются данные: для DJ — автор, название, альбом; для новостей — список из RSS; для погоды — прогноз.
          </p>
          <div className="prompts-grid">
            <div>
              <label>DJ (представление трека)</label>
              <textarea
                value={data.llm_prompt_dj || ""}
                onChange={(e) => setData((d) => ({ ...d, llm_prompt_dj: e.target.value }))}
                rows={6}
                className="settings-textarea"
                placeholder="Промпт для DJ"
              />
            </div>
            <div>
              <label>Новости</label>
              <textarea
                value={data.llm_prompt_news || ""}
                onChange={(e) => setData((d) => ({ ...d, llm_prompt_news: e.target.value }))}
                rows={6}
                className="settings-textarea"
                placeholder="Промпт для новостей"
              />
            </div>
            <div>
              <label>Погода</label>
              <textarea
                value={data.llm_prompt_weather || ""}
                onChange={(e) => setData((d) => ({ ...d, llm_prompt_weather: e.target.value }))}
                rows={6}
                className="settings-textarea"
                placeholder="Промпт для погоды"
              />
            </div>
          </div>
        </section>

        {/* TTS provider */}
        <section className="settings-section">
          <h3>Озвучка (TTS)</h3>
          <p className="settings-hint">
            Edge TTS бесплатный. ElevenLabs — платный, выше качество. Ключ ELEVENLABS_API_KEY в .env.
          </p>
          <div className="settings-select-row">
            <select
              value={data.tts_provider || "edge-tts"}
              onChange={(e) => setData((d) => ({ ...d, tts_provider: e.target.value }))}
              className="settings-select"
            >
              <option value="edge-tts">Edge TTS</option>
              <option value="elevenlabs">ElevenLabs</option>
            </select>
          </div>
        </section>

        {/* Broadcast template */}
        <section className="settings-section">
          <h3>Шаблон эфира</h3>
          <p className="settings-hint">
            Фиксированные слоты: час, минута, тип. Слоты сортируются по времени. Интро — в конце каждого часа.
          </p>
          <div className="broadcast-intro-row">
            <label>Интро в минуту:</label>
            <input
              type="number"
              min={0}
              max={59}
              value={data.broadcast_intro_minute ?? 55}
              onChange={(e) =>
                setData((d) => ({
                  ...d,
                  broadcast_intro_minute: parseInt(e.target.value, 10) || 55,
                }))
              }
              className="settings-number"
            />
          </div>
          <div className="broadcast-slots-table">
            <div className="broadcast-slots-header">
              <span>Час</span>
              <span>Мин</span>
              <span>Тип</span>
              <span></span>
            </div>
            {(data.broadcast_slots || []).map((slot, idx) => (
              <div key={idx} className="broadcast-slot-row">
                <input
                  type="number"
                  min={0}
                  max={23}
                  value={slot[0]}
                  onChange={(e) => updateBroadcastSlot(idx, 0, e.target.value)}
                  className="settings-number small"
                />
                <input
                  type="number"
                  min={0}
                  max={59}
                  value={slot[1]}
                  onChange={(e) => updateBroadcastSlot(idx, 1, e.target.value)}
                  className="settings-number small"
                />
                <select
                  value={slot[2]}
                  onChange={(e) => updateBroadcastSlot(idx, 2, e.target.value)}
                  className="settings-select small"
                >
                  {SLOT_TYPES.map((t) => (
                    <option key={t.value} value={t.value}>
                      {t.label}
                    </option>
                  ))}
                </select>
                <button
                  type="button"
                  className="broadcast-slot-remove"
                  onClick={() => removeBroadcastSlot(idx)}
                  aria-label="Удалить"
                >
                  <X size={14} />
                </button>
              </div>
            ))}
            <button type="button" className="broadcast-slot-add" onClick={addBroadcastSlot}>
              <Plus size={14} /> Добавить слот
            </button>
          </div>
        </section>
      </div>
    </div>
  );
}
