import { useState, useEffect } from "react";
import { Lock } from "lucide-react";
import { checkAuth, hasStoredAdminKey } from "../../api";
import "./AdminAuthGate.css";

/**
 * Обёртка для админки: при 401 или отсутствии ключа показывает форму входа.
 * ADMIN_API_KEY в .env — если задан, требуется авторизация.
 */
export default function AdminAuthGate({ children }) {
  const [needsAuth, setNeedsAuth] = useState(null);
  const [keyInput, setKeyInput] = useState("");
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const onUnauth = () => {
      localStorage.removeItem("admin_api_key");
      setNeedsAuth(true);
    };
    window.addEventListener("admin-unauth", onUnauth);
    (async () => {
      try {
        const res = await checkAuth("");
        if (res.auth_required === false) {
          setNeedsAuth(false);
          return;
        }
        const stored = localStorage.getItem("admin_api_key");
        if (stored) {
          const verified = await checkAuth(stored);
          if (verified.ok) {
            setNeedsAuth(false);
            return;
          }
          localStorage.removeItem("admin_api_key");
        }
        setNeedsAuth(true);
      } catch {
        setNeedsAuth(true);
      } finally {
        setLoading(false);
      }
    })();
    return () => window.removeEventListener("admin-unauth", onUnauth);
  }, []);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(null);
    try {
      const res = await checkAuth(keyInput);
      if (res.ok && res.auth_required) {
        setNeedsAuth(false);
      } else if (res.ok && !res.auth_required) {
        setNeedsAuth(false);
      } else {
        setError("Неверный ключ");
      }
    } catch (err) {
      const msg = err?.message || "";
      setError(msg.includes("Слишком много") ? "Слишком много попыток. Подождите минуту." : (msg || "Неверный ключ"));
    }
  };

  if (loading) {
    return (
      <div className="admin-auth-loading">
        <div className="admin-auth-spinner" />
        <span>Загрузка...</span>
      </div>
    );
  }

  if (needsAuth) {
    return (
      <div className="admin-auth-gate">
        <div className="admin-auth-card">
          <Lock size={32} className="admin-auth-icon" />
          <h2>Вход в админку</h2>
          <p className="admin-auth-hint">
            Введите API-ключ. Задаётся в ADMIN_API_KEY на сервере.
          </p>
          <form onSubmit={handleSubmit}>
            <input
              type="password"
              value={keyInput}
              onChange={(e) => setKeyInput(e.target.value)}
              placeholder="API-ключ"
              className="admin-auth-input"
              autoFocus
            />
            {error && <p className="admin-auth-error">{error}</p>}
            <button type="submit" className="admin-auth-btn">
              Войти
            </button>
          </form>
        </div>
      </div>
    );
  }

  return children;
}
