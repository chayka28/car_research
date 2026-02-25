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

  const [form, setForm] = useState({ username: "admin", password: "admin123" });
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
      setError(apiError.message || "Unable to login. Check credentials and retry.");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <main className="page page-login">
      <section className="auth-shell fade-up">
        <p className="kicker">Car Research Admin</p>
        <h1>Welcome back</h1>
        <p className="auth-subtitle">Sign in to access live car inventory from the protected API.</p>

        <form className="auth-form" onSubmit={onSubmit}>
          <label>
            Username
            <input
              autoComplete="username"
              name="username"
              onChange={onChange}
              value={form.username}
              required
            />
          </label>

          <label>
            Password
            <input
              autoComplete="current-password"
              type="password"
              name="password"
              onChange={onChange}
              value={form.password}
              required
            />
          </label>

          {error ? <p className="form-error">{error}</p> : null}

          <button type="submit" disabled={isSubmitting}>
            {isSubmitting ? "Signing in..." : "Sign in"}
          </button>
        </form>
      </section>
    </main>
  );
}
