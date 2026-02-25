const TOKEN_STORAGE_KEY = "car_research_access_token";

export function getToken() {
  return window.localStorage.getItem(TOKEN_STORAGE_KEY);
}

export function setToken(token) {
  window.localStorage.setItem(TOKEN_STORAGE_KEY, token);
}

export function clearToken() {
  window.localStorage.removeItem(TOKEN_STORAGE_KEY);
}
