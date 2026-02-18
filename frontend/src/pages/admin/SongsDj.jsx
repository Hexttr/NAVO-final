import { useState, useEffect, useRef } from "react";
import { Play, Square, X } from "lucide-react";
import {
  getSongs,
  createSong,
  uploadSongFile,
  generateFromJamendoStream,
  generateDj,
  generateDjTts,
  updateSong,
  deleteSong,
  getTtsVoices,
  getSongAudioUrl,
  getSongDjAudioUrl,
} from "../../api";

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
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
  const [jamendoProgress, setJamendoProgress] = useState(null);
  const [djBatchProgress, setDjBatchProgress] = useState(null);
  const [ttsBatchProgress, setTtsBatchProgress] = useState(null);
  const [playingId, setPlayingId] = useState(null);
  const [playingDjId, setPlayingDjId] = useState(null);
  const audioRef = useRef(null);

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

  const handleJamendo = () => {
    setJamendoProgress({ progress: 0, current: 0, total: 0, created: 0 });
    const cancel = generateFromJamendoStream((data) => {
      setJamendoProgress(data);
      if (data.done || data.error) {
        setJamendoProgress(null);
        load();
        if (data.error) alert(data.error);
        else if (data.created === 0) alert("Треки не загрузились.");
      }
    });
    return cancel;
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
    setDjBatchProgress({ current: 0, total: ids.length });
    for (let i = 0; i < ids.length; i++) {
      try {
        const res = await generateDj(ids[i]);
        setSongs((prev) =>
          prev.map((s) => (s.id === ids[i] ? { ...s, dj_text: res.dj_text, dj_audio_path: "" } : s))
        );
      } catch (e) {
        console.warn(`DJ для ${ids[i]} не сгенерирован:`, e);
      }
      setDjBatchProgress({ current: i + 1, total: ids.length });
      if (i < ids.length - 1) await sleep(2100);
    }
    setDjBatchProgress(null);
  };

  const handleTts = async (songId) => {
    try {
      await generateDjTts(songId, selectedVoice);
      load();
    } catch (e) {
      alert(e.message || "Ошибка TTS");
    }
  };

  const handleTtsAll = async () => {
    const ids = songs.filter((s) => s.dj_text && !s.dj_audio_path).map((s) => s.id);
    if (!ids.length) {
      alert("Нет треков с текстом DJ для озвучки");
      return;
    }
    setTtsBatchProgress({ current: 0, total: ids.length });
    for (let i = 0; i < ids.length; i++) {
      try {
        const res = await generateDjTts(ids[i], selectedVoice);
        setSongs((prev) =>
          prev.map((s) => (s.id === ids[i] ? { ...s, dj_audio_path: res.audio_path } : s))
        );
      } catch (e) {
        console.warn(`TTS для ${ids[i]} не выполнен:`, e);
      }
      setTtsBatchProgress({ current: i + 1, total: ids.length });
    }
    setTtsBatchProgress(null);
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

  const handlePlay = (song) => {
    if (!song.file_path) return;
    const audio = audioRef.current;
    const url = getSongAudioUrl(song.id);
    if (playingId === song.id && audio && !audio.paused) {
      audio.pause();
      setPlayingId(null);
    } else {
      setPlayingDjId(null);
      audio.src = url;
      audio.play();
      setPlayingId(song.id);
    }
  };

  const handlePlayDj = (song) => {
    if (!song.dj_audio_path) return;
    const audio = audioRef.current;
    let url = getSongDjAudioUrl(song.id);
    if (playingDjId === song.id && audio && !audio.paused) {
      audio.pause();
      setPlayingDjId(null);
    } else {
      setPlayingId(null);
      url += (url.includes("?") ? "&" : "?") + "t=" + Date.now();
      audio.src = url;
      audio.play();
      setPlayingDjId(song.id);
    }
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
      </div>
      <div className="entity-actions entity-actions-row2">
        <button className="primary" onClick={handleJamendo} disabled={!!jamendoProgress}>
          Сгенерировать из Jamendo
        </button>
        <button
          onClick={handleGenerateDjAll}
          disabled={loading || !!jamendoProgress || !!djBatchProgress || !!ttsBatchProgress || !songs.length}
        >
          Сгенерировать DJ для всех
        </button>
        <button
          onClick={handleTtsAll}
          disabled={loading || !!jamendoProgress || !!djBatchProgress || !!ttsBatchProgress || !songs.filter((s) => s.dj_text && !s.dj_audio_path).length}
        >
          Озвучить DJ для всех
        </button>
      </div>
      {djBatchProgress && (
        <div className="jamendo-progress">
          <div className="progress-bar">
            <div
              className="progress-fill"
              style={{ width: `${(djBatchProgress.current / djBatchProgress.total) * 100}%` }}
            />
          </div>
          <span className="progress-text">
            Генерируется DJ: {djBatchProgress.current}/{djBatchProgress.total}
          </span>
        </div>
      )}
      {ttsBatchProgress && (
        <div className="jamendo-progress">
          <div className="progress-bar">
            <div
              className="progress-fill"
              style={{ width: `${(ttsBatchProgress.current / ttsBatchProgress.total) * 100}%` }}
            />
          </div>
          <span className="progress-text">
            Озвучивается DJ: {ttsBatchProgress.current}/{ttsBatchProgress.total}
          </span>
        </div>
      )}
      {jamendoProgress && (
        <div className="jamendo-progress">
          <div className="progress-bar">
            <div className="progress-fill" style={{ width: `${jamendoProgress.progress || 0}%` }} />
          </div>
          <span className="progress-text">
            {jamendoProgress.total
              ? `${jamendoProgress.current}/${jamendoProgress.total} — загружено ${jamendoProgress.created} треков`
              : "Поиск треков..."}
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

      <audio ref={audioRef} onEnded={() => { setPlayingId(null); setPlayingDjId(null); }} />
      <table className="entity-table">
        <thead>
          <tr>
            <th></th>
            <th>#</th>
            <th>Автор</th>
            <th>Название</th>
            <th>Альбом</th>
            <th className="col-dj-text">Текст DJ</th>
            <th>Действия</th>
          </tr>
        </thead>
        <tbody>
          {songs.map((s, i) => (
            <tr key={s.id}>
              <td>
                {s.file_path && (
                  <button
                    className="play-btn-small"
                    onClick={() => handlePlay(s)}
                    title={playingId === s.id ? "Стоп" : "Слушать"}
                  >
                    {playingId === s.id ? <Square size={14} /> : <Play size={14} />}
                  </button>
                )}
              </td>
              <td>{i + 1}</td>
              <td>{s.artist}</td>
              <td>{s.title}</td>
              <td>{s.album || "—"}</td>
              <td className="col-dj-text">
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
                      {s.dj_audio_path && (
                        <button onClick={() => handlePlayDj(s)}>
                          {playingDjId === s.id ? "Стоп" : "Воспроизвести"}
                        </button>
                      )}
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
                <div className="cell-actions">
                  {!s.file_path && (
                    <label className="upload-btn">
                      Загрузить MP3
                      <input
                        type="file"
                        accept=".mp3"
                        hidden
                        onChange={(e) => e.target.files[0] && handleFileUpload(s.id, e.target.files[0])}
                      />
                    </label>
                  )}
                  <button
                    type="button"
                    className="icon-btn delete-btn"
                    onClick={() => handleDelete(s.id)}
                    title="Удалить"
                    aria-label="Удалить"
                  >
                    <X size={14} />
                  </button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
