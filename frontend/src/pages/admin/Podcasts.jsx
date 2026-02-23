import { useState, useEffect, useRef } from "react";
import { Play, Square, Volume2 } from "lucide-react";
import { getPodcasts, createPodcast, deletePodcast, getPodcastAudioUrl, applyPodcastVolumeBoost } from "../../api";
import "./EntityPage.css";

export default function Podcasts() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [newTitle, setNewTitle] = useState("");
  const [playingId, setPlayingId] = useState(null);
  const [boostLoading, setBoostLoading] = useState(false);
  const fileRef = useRef(null);
  const audioRef = useRef(null);

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

  const handleBoost = async () => {
    setBoostLoading(true);
    try {
      const res = await applyPodcastVolumeBoost();
      alert(res.message || `Обновлено ${res.updated} подкастов`);
      if (res.updated > 0) load();
    } catch (e) {
      alert(e.message || "Ошибка");
    } finally {
      setBoostLoading(false);
    }
  };

  const handlePlay = (item) => {
    if (!item.file_path) return;
    const audio = audioRef.current;
    const url = getPodcastAudioUrl(item.id);
    if (playingId === item.id && audio && !audio.paused) {
      audio.pause();
      setPlayingId(null);
    } else {
      audio.src = url;
      audio.play();
      setPlayingId(item.id);
    }
  };

  if (loading && !items.length) return <div className="loading">Загрузка...</div>;

  return (
    <div className="entity-page">
      <h2>Подкасты</h2>

      <div className="entity-actions">
        <div className="entity-toolbar">
          <button onClick={handleBoost} disabled={boostLoading || !items.length}>
            <Volume2 size={16} /> Усилить громкость всех
          </button>
        </div>
        <div className="add-manual">
          <input
            placeholder="Название"
            value={newTitle}
            onChange={(e) => setNewTitle(e.target.value)}
          />
          <label className="file-input-btn">
            <input type="file" ref={fileRef} accept=".mp3" />
            <span>Выберите файл</span>
          </label>
          <button className="add-btn" onClick={handleAdd} disabled={!newTitle.trim()}>
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
                <div className="cell-actions">
                  {p.file_path && (
                    <button
                      className={`icon-btn play-btn ${playingId === p.id ? "playing" : ""}`}
                      onClick={() => handlePlay(p)}
                      title="Слушать"
                    >
                      {playingId === p.id ? <Square size={14} /> : <Play size={14} />}
                    </button>
                  )}
                  <button className="danger" onClick={() => handleDelete(p.id)}>
                    Удалить
                  </button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <audio ref={audioRef} onEnded={() => setPlayingId(null)} />
    </div>
  );
}
