import { useState, useEffect, Fragment } from "react";
import { useOutletContext } from "react-router-dom";
import {
  getBroadcast,
  getBroadcastNowPlaying,
  generateBroadcast,
  deleteBroadcastItem,
  insertBroadcastItem,
  moveBroadcastItem,
  getSongs,
  getNews,
  getWeather,
  getPodcasts,
  getIntros,
  updateSong,
  updateNews,
  updateWeather,
  generateDjTts,
  generateNewsTts,
  generateWeatherTts,
  getTtsVoices,
} from "../../api";
import "./Broadcast.css";

const TYPE_LABELS = {
  song: "Песня",
  dj: "DJ",
  news: "Новости",
  weather: "Погода",
  podcast: "Подкаст",
  intro: "ИНТРО",
  empty: "Пусто",
};

export default function Broadcast() {
  const { selectedDate } = useOutletContext();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [confirmGen, setConfirmGen] = useState(false);
  const [insertSlot, setInsertSlot] = useState(null);
  const [catalog, setCatalog] = useState({ songs: [], news: [], weather: [], podcasts: [], intros: [] });
  const [dragIndex, setDragIndex] = useState(null);
  const [dragOverIndex, setDragOverIndex] = useState(null);
  const [nowPlaying, setNowPlaying] = useState({ entityType: null, entityId: null });
  const [expandedId, setExpandedId] = useState(null);
  const [editingText, setEditingText] = useState("");
  const [savingId, setSavingId] = useState(null);
  const [revoicingId, setRevoicingId] = useState(null);
  const [voices, setVoices] = useState([]);
  const [selectedVoice, setSelectedVoice] = useState("ru-RU-DmitryNeural");

  useEffect(() => {
    load();
  }, [selectedDate]);

  useEffect(() => {
    const today = new Date().toISOString().slice(0, 10);
    if (selectedDate !== today) {
      setNowPlaying({ entityType: null, entityId: null });
      return;
    }
    const poll = () => {
      getBroadcastNowPlaying(selectedDate).then(setNowPlaying).catch(() => {});
    };
    poll();
    const id = setInterval(poll, 5000);
    return () => clearInterval(id);
  }, [selectedDate]);

  useEffect(() => {
    getTtsVoices().then((r) => {
      const v = r.voices || [];
      setVoices(v);
      const firstId = Array.isArray(v[0]) ? v[0][0] : v[0];
      if (firstId && selectedVoice !== firstId) setSelectedVoice(firstId);
    });
  }, []);

  useEffect(() => {
    if (insertSlot) {
      Promise.all([getSongs(), getNews(), getWeather(), getPodcasts(), getIntros()]).then(
        ([songs, news, weather, podcasts, intros]) => {
          const toArr = (x) => (Array.isArray(x) ? x : Array.isArray(x?.items) ? x.items : []);
          setCatalog({
            songs: toArr(songs),
            news: toArr(news),
            weather: toArr(weather),
            podcasts: toArr(podcasts),
            intros: toArr(intros),
          });
        }
      );
    }
  }, [insertSlot]);

  const load = () => {
    setLoading(true);
    getBroadcast(selectedDate)
      .then(setData)
      .catch(() => setData({ items: [] }))
      .finally(() => setLoading(false));
  };

  const handleGenerate = async () => {
    if (!confirmGen) {
      setConfirmGen(true);
      return;
    }
    setGenerating(true);
    try {
      await generateBroadcast(selectedDate);
      setConfirmGen(false);
      load();
    } catch (e) {
      alert(e.message || "Ошибка генерации");
    } finally {
      setGenerating(false);
    }
  };

  const handleDelete = async (item) => {
    if (item.entity_type === "empty") return;
    if (!confirm("Удалить эту позицию? Останется пустой слот.")) return;
    try {
      await deleteBroadcastItem(item.id, selectedDate);
      load();
    } catch (e) {
      alert(e.message || "Ошибка");
    }
  };

  const handleInsert = async (entityType, entityId) => {
    if (!insertSlot) return;
    try {
      await insertBroadcastItem(insertSlot.id, selectedDate, entityType, entityId);
      setInsertSlot(null);
      load();
    } catch (e) {
      alert(e.message || "Ошибка вставки");
    }
  };

  const handleDragStart = (e, idx) => {
    if (e.target.closest("[data-no-drag]")) {
      e.preventDefault();
      return;
    }
    setDragIndex(idx);
  };
  const handleDragOver = (e, idx) => {
    e.preventDefault();
    setDragOverIndex(idx);
  };
  const handleDrop = async (e, toIdx) => {
    e.preventDefault();
    if (dragIndex == null || dragIndex === toIdx) {
      setDragIndex(null);
      return;
    }
    try {
      await moveBroadcastItem(selectedDate, dragIndex, toIdx);
      load();
    } catch (err) {
      alert(err.message || "Ошибка перемещения");
    }
    setDragIndex(null);
    setDragOverIndex(null);
  };
  const handleDragEnd = () => {
    setDragIndex(null);
    setDragOverIndex(null);
  };

  const hasText = (item) => ["dj", "news", "weather"].includes(item.entity_type);
  const toggleExpand = (item, e) => {
    e.stopPropagation();
    if (!hasText(item)) return;
    if (expandedId === item.id) {
      setExpandedId(null);
      setEditingText("");
    } else {
      setExpandedId(item.id);
      setEditingText(item.text || "");
    }
  };

  const handleSaveText = async (item) => {
    if (!editingText.trim()) return;
    setSavingId(item.id);
    try {
      if (item.entity_type === "dj") await updateSong(item.entity_id, { dj_text: editingText.trim() });
      else if (item.entity_type === "news") await updateNews(item.entity_id, editingText.trim());
      else if (item.entity_type === "weather") await updateWeather(item.entity_id, editingText.trim());
      load();
      setExpandedId(null);
      setEditingText("");
    } catch (e) {
      alert(e.message || "Ошибка сохранения");
    } finally {
      setSavingId(null);
    }
  };

  const handleRevoice = async (item) => {
    setRevoicingId(item.id);
    try {
      if (item.entity_type === "dj") await generateDjTts(item.entity_id, selectedVoice);
      else if (item.entity_type === "news") await generateNewsTts(item.entity_id, selectedVoice);
      else if (item.entity_type === "weather") await generateWeatherTts(item.entity_id, selectedVoice);
      load();
    } catch (e) {
      alert(e.message || "Ошибка переозвучки");
    } finally {
      setRevoicingId(null);
    }
  };

  const truncate = (s, n = 30) => (s && s.length > n ? s.slice(0, n) + "…" : s || "—");

  const items = data?.items || [];
  const today = new Date().toISOString().slice(0, 10);
  const isToday = selectedDate === today;
  const isNowPlaying = (item) =>
    isToday &&
    nowPlaying.entityType &&
    nowPlaying.entityId != null &&
    item.entity_type === nowPlaying.entityType &&
    item.entity_id === nowPlaying.entityId;

  return (
    <div className="broadcast-page">
      <h2>Сетка эфира — {selectedDate}</h2>

      <div className="broadcast-actions">
        <button
          className={`primary ${confirmGen ? "confirm" : ""}`}
          onClick={handleGenerate}
          disabled={loading || generating}
        >
          {confirmGen ? "Подтвердить перезапись?" : "Сгенерировать эфир"}
        </button>
        {confirmGen && (
          <button onClick={() => setConfirmGen(false)}>Отмена</button>
        )}
      </div>

      {loading ? (
        <div className="loading">Загрузка...</div>
      ) : (
        <div className="broadcast-grid">
          <table className="broadcast-table">
            <thead>
              <tr>
                <th className="col-expand"></th>
                <th className="col-num">№</th>
                <th>Время</th>
                <th>Тип</th>
                <th className="col-desc">Описание</th>
                <th>Текст</th>
                <th>Длительность</th>
                <th className="col-actions"></th>
              </tr>
            </thead>
            <tbody>
              {items.map((item, idx) => (
                <Fragment key={item.id}>
                  <tr
                    key={item.id}
                    className={`type-${item.entity_type} ${dragIndex === idx ? "dragging" : ""} ${dragOverIndex === idx && dragIndex != null && dragIndex !== idx ? "drag-over" : ""} ${isNowPlaying(item) ? "now-playing" : ""} ${expandedId === item.id ? "expanded" : ""}`}
                    draggable
                    onDragStart={(e) => handleDragStart(e, idx)}
                    onDragOver={(e) => handleDragOver(e, idx)}
                    onDrop={(e) => handleDrop(e, idx)}
                    onDragEnd={handleDragEnd}
                  >
                    <td className="col-expand" data-no-drag onClick={(e) => toggleExpand(item, e)}>
                      {hasText(item) && (
                        <span className={`expand-arrow ${expandedId === item.id ? "expanded" : ""}`} title={expandedId === item.id ? "Свернуть" : "Развернуть"}>
                          ▼
                        </span>
                      )}
                    </td>
                    <td className="col-num">{idx + 1}</td>
                    <td>{item.start_time}</td>
                    <td>{TYPE_LABELS[item.entity_type] || item.entity_type}</td>
                    <td className="col-desc">
                      {item.entity_type === "empty" ? (
                        <button
                          type="button"
                          className="insert-btn"
                          onClick={() => setInsertSlot(item)}
                        >
                          + Вставить
                        </button>
                      ) : (
                        truncate(
                          item.metadata_json
                            ? (() => {
                                try {
                                  const m = JSON.parse(item.metadata_json);
                                  return m.title || "—";
                                } catch {
                                  return "—";
                                }
                              })()
                            : "—"
                        )
                      )}
                    </td>
                    <td className="col-text">{hasText(item) ? truncate(item.text, 60) : "—"}</td>
                    <td>{Math.round(item.duration_seconds)} с</td>
                    <td className="col-actions">
                      {item.entity_type !== "empty" && (
                        <button
                          type="button"
                          className="delete-btn"
                          onClick={() => handleDelete(item)}
                          title="Удалить"
                          aria-label="Удалить"
                        >
                          ✕
                        </button>
                      )}
                    </td>
                  </tr>
                  {expandedId === item.id && hasText(item) && (
                    <tr key={`${item.id}-detail`} className="detail-row">
                      <td colSpan={8}>
                        <div className="expand-panel">
                          <textarea
                            value={editingText}
                            onChange={(e) => setEditingText(e.target.value)}
                            placeholder="Текст для озвучки"
                            rows={4}
                          />
                          <div className="expand-actions">
                            {voices.length > 0 && (
                              <select
                                value={selectedVoice}
                                onChange={(e) => setSelectedVoice(e.target.value)}
                                className="voice-select"
                              >
                                {voices.map((v) => {
                                  const [id, label] = Array.isArray(v) ? v : [v, v];
                                  return <option key={id} value={id}>{label}</option>;
                                })}
                              </select>
                            )}
                            <button
                              type="button"
                              className="save-btn"
                              onClick={() => handleSaveText(item)}
                              disabled={savingId === item.id || editingText.trim() === (item.text || "").trim()}
                            >
                              {savingId === item.id ? "…" : "Сохранить"}
                            </button>
                            <button
                              type="button"
                              className="revoice-btn"
                              onClick={() => handleRevoice(item)}
                              disabled={revoicingId === item.id}
                            >
                              {revoicingId === item.id ? "…" : "Переозвучить"}
                            </button>
                          </div>
                        </div>
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
          {items.length === 0 && (
            <p className="empty-hint">
              Нет данных. Добавьте контент (песни, новости, погоду и т.д.) и нажмите «Сгенерировать эфир».
            </p>
          )}
        </div>
      )}

      {insertSlot && (
        <div className="modal-overlay" onClick={() => setInsertSlot(null)}>
          <div className="modal insert-modal" onClick={(e) => e.stopPropagation()}>
            <h3>Вставить в слот №{items.findIndex((i) => i.id === insertSlot.id) + 1}</h3>
            <div className="insert-catalog">
              {catalog.songs.filter((s) => s.file_path).length > 0 && (
                <section>
                  <h4>Песни</h4>
                  <ul>
                    {catalog.songs
                      .filter((s) => s.file_path)
                      .slice(0, 30)
                      .map((s) => (
                        <li key={s.id}>
                          <button type="button" onClick={() => handleInsert("song", s.id)}>
                            {s.artist} — {s.title}
                          </button>
                        </li>
                      ))}
                  </ul>
                </section>
              )}
              {catalog.songs.filter((s) => s.dj_audio_path).length > 0 && (
                <section>
                  <h4>DJ</h4>
                  <ul>
                    {catalog.songs
                      .filter((s) => s.dj_audio_path)
                      .slice(0, 20)
                      .map((s) => (
                        <li key={`dj-${s.id}`}>
                          <button type="button" onClick={() => handleInsert("dj", s.id)}>
                            {s.artist} — {s.title}
                          </button>
                        </li>
                      ))}
                  </ul>
                </section>
              )}
              {catalog.news.filter((n) => n.audio_path).length > 0 && (
                <section>
                  <h4>Новости</h4>
                  <ul>
                    {catalog.news.filter((n) => n.audio_path).map((n) => (
                      <li key={n.id}>
                        <button type="button" onClick={() => handleInsert("news", n.id)}>
                          #{n.id} — {n.text?.slice(0, 50)}…
                        </button>
                      </li>
                    ))}
                  </ul>
                </section>
              )}
              {catalog.weather.filter((w) => w.audio_path).length > 0 && (
                <section>
                  <h4>Погода</h4>
                  <ul>
                    {catalog.weather.filter((w) => w.audio_path).map((w) => (
                      <li key={w.id}>
                        <button type="button" onClick={() => handleInsert("weather", w.id)}>
                          #{w.id} — {w.text?.slice(0, 50)}…
                        </button>
                      </li>
                    ))}
                  </ul>
                </section>
              )}
              {catalog.podcasts.length > 0 && (
                <section>
                  <h4>Подкасты</h4>
                  <ul>
                    {catalog.podcasts.map((p) => (
                      <li key={p.id}>
                        <button type="button" onClick={() => handleInsert("podcast", p.id)}>
                          {p.title}
                        </button>
                      </li>
                    ))}
                  </ul>
                </section>
              )}
              {catalog.intros.length > 0 && (
                <section>
                  <h4>ИНТРО</h4>
                  <ul>
                    {catalog.intros.map((i) => (
                      <li key={i.id}>
                        <button type="button" onClick={() => handleInsert("intro", i.id)}>
                          {i.title}
                        </button>
                      </li>
                    ))}
                  </ul>
                </section>
              )}
            </div>
            <button type="button" className="modal-close" onClick={() => setInsertSlot(null)}>
              Отмена
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
