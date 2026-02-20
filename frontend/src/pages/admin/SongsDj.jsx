import { useState, useEffect, useRef } from "react";
import { Loader2, Play, Square, X } from "lucide-react";
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
const TTS_BATCH_KEY = "navo_tts_batch";
const DJ_BATCH_KEY = "navo_dj_batch";

function loadBatch(key) {
  try {
    const raw = localStorage.getItem(key);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function saveBatch(key, data) {
  if (data) localStorage.setItem(key, JSON.stringify(data));
  else localStorage.removeItem(key);
}

import "./EntityPage.css";

export default function SongsDj() {
  const [songs, setSongs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [voices, setVoices] = useState([]);
  const [newTitle, setNewTitle] = useState("");
  const [newArtist, setNewArtist] = useState("");
  const [newAlbum, setNewAlbum] = useState("");
  const [editingDj, setEditingDj] = useState(null);
  const [editingText, setEditingText] = useState("");
  const [regeneratingSongId, setRegeneratingSongId] = useState(null);
  const [revoicingSongId, setRevoicingSongId] = useState(null);
  const editTextareaRef = useRef(null);
  const [selectedVoice, setSelectedVoice] = useState("ru-RU-DmitryNeural");
  const [jamendoProgress, setJamendoProgress] = useState(null);
  const [djBatchProgress, setDjBatchProgress] = useState(null);
  const [ttsBatchProgress, setTtsBatchProgress] = useState(null);
  const [playingId, setPlayingId] = useState(null);
  const [playingDjId, setPlayingDjId] = useState(null);
  const audioRef = useRef(null);

  useEffect(() => {
    const ta = editTextareaRef.current;
    if (ta && editingDj) {
      ta.style.height = "auto";
      ta.style.height = Math.max(80, ta.scrollHeight) + "px";
    }
  }, [editingText, editingDj]);

  useEffect(() => {
    load();
    getTtsVoices().then((r) => {
      const v = r.voices || [];
      setVoices(v);
      if (v.length > 0) {
        setSelectedVoice((prev) => (v.some((x) => x[0] === prev) ? prev : v[0][0]));
      }
    });
  }, []);

  useEffect(() => {
    const batch = loadBatch(TTS_BATCH_KEY);
    if (!batch?.songIds?.length) return;
    const voice = batch.voice || "ru-RU-DmitryNeural";
    const runResume = async () => {
      const songsList = await getSongs();
      const byId = Object.fromEntries((songsList || []).map((s) => [s.id, s]));
      const remaining = batch.songIds.filter((id) => {
        const s = byId[id];
        return s?.dj_text && !s?.dj_audio_path;
      });
      if (remaining.length === 0) {
        saveBatch(TTS_BATCH_KEY, null);
        load();
        return;
      }
      const completed = batch.total - remaining.length;
      setTtsBatchProgress({ current: completed, total: batch.total });
      if (batch.voice) setSelectedVoice(batch.voice);
      for (let i = 0; i < remaining.length; i++) {
        try {
          await generateDjTts(remaining[i], voice);
        } catch (e) {
          console.warn("TTS:", remaining[i], e);
        }
        setTtsBatchProgress({ current: completed + i + 1, total: batch.total });
        if (i < remaining.length - 1) await sleep(300);
      }
      saveBatch(TTS_BATCH_KEY, null);
      setTtsBatchProgress(null);
      load();
    };
    runResume();
  }, []);

  useEffect(() => {
    const batch = loadBatch(DJ_BATCH_KEY);
    if (!batch?.songIds?.length) return;
    const runResume = async () => {
      const songsList = await getSongs();
      const byId = Object.fromEntries((songsList || []).map((s) => [s.id, s]));
      const remaining = batch.songIds.filter((id) => {
        const s = byId[id];
        return s?.file_path && !s?.dj_text;
      });
      if (remaining.length === 0) {
        saveBatch(DJ_BATCH_KEY, null);
        load();
        return;
      }
      const completed = batch.total - remaining.length;
      setDjBatchProgress({ current: completed, total: batch.total });
      for (let i = 0; i < remaining.length; i++) {
        try {
          await generateDj(remaining[i]);
        } catch (e) {
          console.warn("DJ:", remaining[i], e);
        }
        setDjBatchProgress({ current: completed + i + 1, total: batch.total });
        if (i < remaining.length - 1) await sleep(2100);
      }
      saveBatch(DJ_BATCH_KEY, null);
      setDjBatchProgress(null);
      load();
    };
    runResume();
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
    saveBatch(TTS_BATCH_KEY, null);
    saveBatch(DJ_BATCH_KEY, { songIds: ids, total: ids.length });
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
    saveBatch(DJ_BATCH_KEY, null);
    setDjBatchProgress(null);
  };

  const handleTts = async (songId) => {
    setRevoicingSongId(songId);
    try {
      const voiceToUse = selectedVoice.startsWith("ru-RU-") ? voices[0]?.[0] || "dVRDrbP5ULGXB94se4KZ" : selectedVoice;
      await generateDjTts(songId, voiceToUse);
      load();
    } catch (e) {
      alert(e.message || "Ошибка TTS");
    } finally {
      setRevoicingSongId(null);
    }
  };

  const handleTtsAll = async () => {
    const ids = songs.filter((s) => s.dj_text && !s.dj_audio_path).map((s) => s.id);
    if (!ids.length) {
      alert("Нет треков с текстом DJ для озвучки");
      return;
    }
    const voiceToUse = selectedVoice.startsWith("ru-RU-") ? voices[0]?.[0] || "dVRDrbP5ULGXB94se4KZ" : selectedVoice;
    saveBatch(DJ_BATCH_KEY, null);
    saveBatch(TTS_BATCH_KEY, { songIds: ids, total: ids.length, voice: voiceToUse });
    setTtsBatchProgress({ current: 0, total: ids.length });
    for (let i = 0; i < ids.length; i++) {
      try {
        const res = await generateDjTts(ids[i], voiceToUse);
        setSongs((prev) =>
          prev.map((s) => (s.id === ids[i] ? { ...s, dj_audio_path: res.audio_path } : s))
        );
      } catch (e) {
        console.warn(`TTS для ${ids[i]} не выполнен:`, e);
      }
      setTtsBatchProgress({ current: i + 1, total: ids.length });
      if (i < ids.length - 1) await sleep(300);
    }
    saveBatch(TTS_BATCH_KEY, null);
    setTtsBatchProgress(null);
  };

  const handleSaveDj = async (songId, text, close = true) => {
    await updateSong(songId, { dj_text: text });
    if (close) setEditingDj(null);
    setSongs((prev) =>
      prev.map((s) => (s.id === songId ? { ...s, dj_text: text } : s))
    );
  };

  const handleRegenerateInEdit = async (songId) => {
    const song = songs.find((s) => s.id === songId);
    if (!song?.file_path) {
      alert("Сначала загрузите MP3");
      return;
    }
    setRegeneratingSongId(songId);
    try {
      const res = await generateDj(songId);
      setEditingText(res.dj_text || "");
      setSongs((prev) =>
        prev.map((s) => (s.id === songId ? { ...s, dj_text: res.dj_text, dj_audio_path: "" } : s))
      );
    } catch (e) {
      alert(e.message || "Ошибка");
    } finally {
      setRegeneratingSongId(null);
    }
  };

  const handleRevoiceInEdit = async (songId, currentText) => {
    if (!currentText?.trim()) return;
    const voiceToUse = selectedVoice.startsWith("ru-RU-") ? voices[0]?.[0] || "dVRDrbP5ULGXB94se4KZ" : selectedVoice;
    setRevoicingSongId(songId);
    try {
      await updateSong(songId, { dj_text: currentText });
      const res = await generateDjTts(songId, voiceToUse);
      setSongs((prev) =>
        prev.map((s) => (s.id === songId ? { ...s, dj_text: currentText, dj_audio_path: res.audio_path } : s))
      );
    } catch (e) {
      alert(e.message || "Ошибка TTS");
    } finally {
      setRevoicingSongId(null);
    }
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
          Озвучить остатки ({songs.filter((s) => s.dj_text && !s.dj_audio_path).length})
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
                  <div className="item-edit-form">
                    <textarea
                      ref={editTextareaRef}
                      value={editingText}
                      onChange={(e) => setEditingText(e.target.value)}
                      style={{
                        width: "100%",
                        minWidth: 200,
                        minHeight: 80,
                        overflow: "hidden",
                        resize: "none",
                      }}
                      placeholder="Текст DJ..."
                    />
                    <div className="item-edit-form-actions">
                      <button
                        type="button"
                        onClick={() => handleSaveDj(s.id, editingText, true)}
                        disabled={regeneratingSongId === s.id || revoicingSongId === s.id}
                      >
                        Сохранить
                      </button>
                      <button
                        type="button"
                        className="regen-btn"
                        onClick={() => handleRegenerateInEdit(s.id)}
                        disabled={regeneratingSongId === s.id || revoicingSongId === s.id || !s.file_path}
                      >
                        {regeneratingSongId === s.id && <Loader2 size={16} className="spin-icon" />}
                        {regeneratingSongId === s.id
                          ? " Генерация..."
                          : editingText
                            ? "Перегенерировать текст"
                            : "Генерировать текст"}
                      </button>
                      <button
                        type="button"
                        className="revoice-btn"
                        onClick={() => handleRevoiceInEdit(s.id, editingText)}
                        disabled={
                          regeneratingSongId === s.id ||
                          revoicingSongId === s.id ||
                          !editingText.trim()
                        }
                      >
                        {revoicingSongId === s.id && <Loader2 size={16} className="spin-icon" />}
                        {revoicingSongId === s.id ? " Озвучивание..." : s.dj_audio_path ? "Переозвучить" : "Озвучить"}
                      </button>
                    </div>
                  </div>
                ) : (
                  <div className="dj-cell">
                    <span className="dj-text">{s.dj_text || "—"}</span>
                    <div className="dj-actions">
                      <button
                        onClick={() => {
                          setEditingDj(s.id);
                          setEditingText(s.dj_text || "");
                        }}
                      >
                        Редактировать
                      </button>
                      {s.dj_audio_path && (
                        <button onClick={() => handlePlayDj(s)}>
                          {playingDjId === s.id ? "Стоп" : "Воспроизвести"}
                        </button>
                      )}
                      {!s.dj_text && (
                        <button onClick={() => handleGenerateDj(s.id)}>Сгенерировать</button>
                      )}
                      {s.dj_text && !s.dj_audio_path && (
                        <button
                          className="revoice-btn"
                          onClick={() => handleTts(s.id)}
                          disabled={revoicingSongId === s.id}
                        >
                          {revoicingSongId === s.id && <Loader2 size={14} className="spin-icon" />}
                          {revoicingSongId === s.id ? " Озвучивание..." : "Озвучить"}
                        </button>
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
