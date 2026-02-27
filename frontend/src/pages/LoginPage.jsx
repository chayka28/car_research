import { useMemo, useState } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";

import { login } from "../lib/api";
import { getToken, setToken } from "../lib/auth";

export default function LoginPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const existingToken = getToken();

  const redirectTarget = useMemo(() => {
    if (location.state && typeof location.state.from?.pathname === "string") {
      return location.state.from.pathname;
    }
    return "/";
  }, [location.state]);

  const [form, setForm] = useState({ username: "", password: "" });
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState("");

  if (existingToken) {
    return <Navigate to="/" replace />;
  }

  const onChange = (event) => {
    const { name, value } = event.target;
    setForm((prev) => ({ ...prev, [name]: value }));
  };

  const onSubmit = async (event) => {
    event.preventDefault();
    setIsSubmitting(true);
    setError("");

    try {
      const data = await login(form);
      setToken(data.access_token);
      navigate(redirectTarget, { replace: true });
    } catch (apiError) {
      setError(apiError.message || "Не удалось выполнить вход. Проверьте логин и пароль.");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <main className="page page-login">
      <section className="auth-shell fade-up">
        <p className="kicker">CAR RESEARCH ADMIN</p>
        <h1>Вход в систему</h1>
        <p className="auth-subtitle">
          Авторизуйтесь, чтобы открыть панель управления объявлениями.
        </p>

        <form className="auth-form" onSubmit={onSubmit}>
          <label>
            Логин
            <input
              autoComplete="username"
              name="username"
              placeholder="Введите логин"
              onChange={onChange}
              value={form.username}
              required
            />
          </label>

          <label>
            Пароль
            <input
              autoComplete="current-password"
              type="password"
              name="password"
              placeholder="Введите пароль"
              onChange={onChange}
              value={form.password}
              required
            />
          </label>

          {error ? <p className="form-error">{error}</p> : null}

          <button type="submit" disabled={isSubmitting}>
            {isSubmitting ? "Выполняем вход..." : "Войти"}
          </button>
        </form>
      </section>
    </main>
  );
}
