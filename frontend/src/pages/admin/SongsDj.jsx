import { useState, useEffect } from "react";
import {
  getSongs,
  createSong,
  uploadSongFile,
  generateFromJamendo,
  generateDj,
  generateDjBatch,
  generateDjTts,
  updateSong,
  deleteSong,
  getTtsVoices,
} from "../../api";
import "./EntityPage.css";

export default function SongsDj() {
  const [songs, setSongs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [voices, setVoices] = useState([]);
  const [newTitle, setNewTitle] = useState("");
  const [newArtist, setNewArtist] = useState("");
  const [newAlbum, setNewAlbum] = useState("");
  const [editingDj, setEditingDj] = useState(null);
  const [selectedVoice, setSelectedVoice] = useState("ru-RU-DmitryNeural");

  useEffect(() => {
    load();
    getTtsVoices().then((r) => setVoices(r.voices || []));
  }, []);

  const load = () => {
    setLoading(true);
    getSongs().then(setSongs).finally(() => setLoading(false));
  };

  const handleAddManual = async () => {
    if (!newTitle.trim()) return;
    await createSong({
      title: newTitle.trim(),
      artist: newArtist.trim() || "Неизвестен",
      album: newAlbum.trim(),
    });
    setNewTitle("");
    setNewArtist("");
    setNewAlbum("");
    load();
  };

  const handleFileUpload = async (songId, file) => {
    await uploadSongFile(songId, file);
    load();
  };

  const handleJamendo = async () => {
    setLoading(true);
    try {
      const res = await generateFromJamendo();
      await load();
      if (res.created === 0) {
        alert("Треки не загрузились. Возможно, Jamendo временно недоступен или формат изменился.");
      }
    } catch (e) {
      alert(e.message || "Ошибка при загрузке из Jamendo");
    } finally {
      setLoading(false);
    }
  };

  const handleGenerateDj = async (songId) => {
    try {
      await generateDj(songId);
      load();
    } catch (e) {
      alert(e.message || "Ошибка");
    }
  };

  const handleGenerateDjAll = async () => {
    const ids = songs.filter((s) => s.file_path).map((s) => s.id);
    if (!ids.length) {
      alert("Нет песен с загруженным файлом");
      return;
    }
    setLoading(true);
    try {
      await generateDjBatch(ids);
      load();
    } finally {
      setLoading(false);
    }
  };

  const handleTts = async (songId) => {
    try {
      await generateDjTts(songId, selectedVoice);
      load();
    } catch (e) {
      alert(e.message || "Ошибка TTS");
    }
  };

  const handleSaveDj = async (songId, text) => {
    await updateSong(songId, { dj_text: text });
    setEditingDj(null);
    load();
  };

  const handleDelete = async (songId) => {
    if (!confirm("Удалить?")) return;
    await deleteSong(songId);
    load();
  };

  if (loading && !songs.length) return <div className="loading">Загрузка...</div>;

  return (
    <div className="entity-page">
      <h2>Песни / DJ</h2>

      <div className="entity-actions">
        <div className="add-manual">
          <input placeholder="Название" value={newTitle} onChange={(e) => setNewTitle(e.target.value)} />
          <input placeholder="Автор" value={newArtist} onChange={(e) => setNewArtist(e.target.value)} />
          <input placeholder="Альбом" value={newAlbum} onChange={(e) => setNewAlbum(e.target.value)} />
          <button onClick={handleAddManual} disabled={!newTitle.trim()}>
            Добавить вручную
          </button>
        </div>
        <button className="primary" onClick={handleJamendo} disabled={loading}>
          Сгенерировать из Jamendo
        </button>
        <button onClick={handleGenerateDjAll} disabled={loading || !songs.length}>
          Сгенерировать DJ для всех
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

      <table className="entity-table">
        <thead>
          <tr>
            <th>#</th>
            <th>Автор</th>
            <th>Название</th>
            <th>Альбом</th>
            <th>Текст DJ</th>
            <th>Действия</th>
          </tr>
        </thead>
        <tbody>
          {songs.map((s, i) => (
            <tr key={s.id}>
              <td>{i + 1}</td>
              <td>{s.artist}</td>
              <td>{s.title}</td>
              <td>{s.album || "—"}</td>
              <td>
                {editingDj === s.id ? (
                  <div>
                    <textarea
                      defaultValue={s.dj_text}
                      onBlur={(e) => handleSaveDj(s.id, e.target.value)}
                      rows={3}
                      style={{ width: "100%", minWidth: 200 }}
                    />
                    <button onClick={() => setEditingDj(null)}>Готово</button>
                  </div>
                ) : (
                  <div className="dj-cell">
                    <span className="dj-text">{s.dj_text || "—"}</span>
                    <div className="dj-actions">
                      <button onClick={() => setEditingDj(s.id)}>Редактировать</button>
                      {!s.dj_text && (
                        <button onClick={() => handleGenerateDj(s.id)}>Сгенерировать</button>
                      )}
                      {s.dj_text && !s.dj_audio_path && (
                        <button onClick={() => handleTts(s.id)}>Озвучить</button>
                      )}
                    </div>
                  </div>
                )}
              </td>
              <td>
                {!s.file_path ? (
                  <label className="upload-btn">
                    Загрузить MP3
                    <input
                      type="file"
                      accept=".mp3"
                      hidden
                      onChange={(e) => e.target.files[0] && handleFileUpload(s.id, e.target.files[0])}
                    />
                  </label>
                ) : (
                  <span className="ok">✓</span>
                )}
                <button className="danger" onClick={() => handleDelete(s.id)}>
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
