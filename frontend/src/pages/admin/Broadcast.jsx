import { useState, useEffect } from "react";
import { useOutletContext } from "react-router-dom";
import { getBroadcast, generateBroadcast } from "../../api";
import "./Broadcast.css";

const TYPE_LABELS = {
  song: "Песня",
  dj: "DJ",
  news: "Новости",
  weather: "Погода",
  podcast: "Подкаст",
  intro: "ИНТРО",
};

export default function Broadcast() {
  const { selectedDate } = useOutletContext();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [confirmGen, setConfirmGen] = useState(false);

  useEffect(() => {
    load();
  }, [selectedDate]);

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

  const items = data?.items || [];

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
                <th>Время</th>
                <th>Тип</th>
                <th>Описание</th>
                <th>Длительность</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.id} className={`type-${item.entity_type}`}>
                  <td>{item.start_time}</td>
                  <td>{TYPE_LABELS[item.entity_type] || item.entity_type}</td>
                  <td>
                    {item.metadata_json
                      ? (() => {
                          try {
                            const m = JSON.parse(item.metadata_json);
                            return m.title || "—";
                          } catch {
                            return "—";
                          }
                        })()
                      : "—"}
                  </td>
                  <td>{Math.round(item.duration_seconds)} с</td>
                </tr>
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
    </div>
  );
}
