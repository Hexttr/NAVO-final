import { useState, useEffect, useRef } from "react";
import { getPodcasts, createPodcast, deletePodcast } from "../../api";
import "./EntityPage.css";

export default function Podcasts() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [newTitle, setNewTitle] = useState("");
  const fileRef = useRef(null);

  useEffect(() => {
    load();
  }, []);

  const load = () => {
    setLoading(true);
    getPodcasts().then(setItems).finally(() => setLoading(false));
  };

  const handleAdd = async () => {
    const file = fileRef.current?.files?.[0];
    if (!newTitle.trim() || !file) {
      alert("Введите название и выберите MP3");
      return;
    }
    await createPodcast(newTitle.trim(), file);
    setNewTitle("");
    if (fileRef.current) fileRef.current.value = "";
    load();
  };

  const handleDelete = async (id) => {
    if (!confirm("Удалить?")) return;
    await deletePodcast(id);
    load();
  };

  if (loading && !items.length) return <div className="loading">Загрузка...</div>;

  return (
    <div className="entity-page">
      <h2>Подкасты</h2>

      <div className="entity-actions">
        <div className="add-manual">
          <input
            placeholder="Название"
            value={newTitle}
            onChange={(e) => setNewTitle(e.target.value)}
          />
          <input type="file" ref={fileRef} accept=".mp3" />
          <button onClick={handleAdd} disabled={!newTitle.trim()}>
            Добавить
          </button>
        </div>
      </div>

      <table className="entity-table">
        <thead>
          <tr>
            <th>#</th>
            <th>Название</th>
            <th>Действия</th>
          </tr>
        </thead>
        <tbody>
          {items.map((p, i) => (
            <tr key={p.id}>
              <td>{i + 1}</td>
              <td>{p.title}</td>
              <td>
                <button className="danger" onClick={() => handleDelete(p.id)}>
                  Удалить
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
