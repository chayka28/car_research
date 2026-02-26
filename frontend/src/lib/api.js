const apiBase = (import.meta.env.VITE_API_BASE_URL || "").replace(/\/$/, "");

function buildUrl(path) {
  return `${apiBase}${path}`;
}

function translateErrorDetail(detail) {
  if (detail === "Invalid credentials") {
    return "Неверный логин или пароль.";
  }

  if (detail === "Could not validate credentials") {
    return "Токен недействителен. Выполните вход повторно.";
  }

  if (detail === "Listing not found") {
    return "Запись не найдена.";
  }

  return detail;
}

async function parseApiError(response) {
  let message = `Ошибка запроса: ${response.status}`;

  try {
    const data = await response.json();
    if (typeof data?.detail === "string") {
      message = translateErrorDetail(data.detail);
    }
  } catch {
    // Оставляем fallback, если ответ не в JSON.
  }

  const error = new Error(message);
  error.status = response.status;
  return error;
}

export async function login({ username, password }) {
  const response = await fetch(buildUrl("/api/login"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password })
  });

  if (!response.ok) {
    throw await parseApiError(response);
  }

  return response.json();
}

export async function getListings(token, params = {}) {
  const searchParams = new URLSearchParams();

  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") {
      continue;
    }
    searchParams.set(key, String(value));
  }

  const queryString = searchParams.toString();
  const path = queryString ? `/api/listings?${queryString}` : "/api/listings";

  const response = await fetch(buildUrl(path), {
    headers: {
      Authorization: `Bearer ${token}`
    }
  });

  if (!response.ok) {
    throw await parseApiError(response);
  }

  return response.json();
}

export async function deleteListing(token, listingId) {
  const response = await fetch(buildUrl(`/api/listings/${listingId}`), {
    method: "DELETE",
    headers: {
      Authorization: `Bearer ${token}`
    }
  });

  if (!response.ok) {
    throw await parseApiError(response);
  }
}

export async function getCars(token) {
  const response = await fetch(buildUrl("/api/cars"), {
    headers: {
      Authorization: `Bearer ${token}`
    }
  });

  if (!response.ok) {
    throw await parseApiError(response);
  }

  return response.json();
}
