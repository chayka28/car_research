import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { getCars } from "../lib/api";
import { clearToken, getToken } from "../lib/auth";

const PAGE_SIZE = 100;
const THEME_STORAGE_KEY = "car_research_theme";

function formatPrice(value) {
  if (!Number.isFinite(value)) {
    return "-";
  }

  return new Intl.NumberFormat("ru-RU", {
    style: "currency",
    currency: "RUB",
    maximumFractionDigits: 0
  }).format(value);
}

function buildPageWindow(currentPage, totalPages) {
  if (totalPages <= 1) {
    return [1];
  }

  const start = Math.max(1, currentPage - 2);
  const end = Math.min(totalPages, currentPage + 2);
  const pages = [];

  for (let page = start; page <= end; page += 1) {
    pages.push(page);
  }

  if (!pages.includes(1)) {
    pages.unshift(1);
  }
  if (!pages.includes(totalPages)) {
    pages.push(totalPages);
  }

  return [...new Set(pages)];
}

function textValue(value) {
  return String(value || "").toLowerCase();
}

function compareText(left, right) {
  return textValue(left).localeCompare(textValue(right), "ru");
}

function compareNumber(left, right) {
  const a = Number.isFinite(left) ? left : Number.NEGATIVE_INFINITY;
  const b = Number.isFinite(right) ? right : Number.NEGATIVE_INFINITY;
  return a - b;
}

export default function CarsPage() {
  const navigate = useNavigate();

  const [allItems, setAllItems] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");

  const [queryInput, setQueryInput] = useState("");
  const [query, setQuery] = useState("");
  const [sortBy, setSortBy] = useState("brand");
  const [sortOrder, setSortOrder] = useState("asc");
  const [page, setPage] = useState(1);
  const [theme, setTheme] = useState(() => window.localStorage.getItem(THEME_STORAGE_KEY) || "light");

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setPage(1);
      setQuery(queryInput.trim());
    }, 350);

    return () => window.clearTimeout(timer);
  }, [queryInput]);

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    window.localStorage.setItem(THEME_STORAGE_KEY, theme);
  }, [theme]);

  const loadCars = async () => {
    setIsLoading(true);
    setError("");

    const token = getToken();
    if (!token) {
      navigate("/login", { replace: true });
      return;
    }

    try {
      const data = await getCars(token);
      setAllItems(Array.isArray(data) ? data : []);
    } catch (apiError) {
      if (apiError.status === 401) {
        clearToken();
        navigate("/login", { replace: true });
        return;
      }
      setError(apiError.message || "Не удалось загрузить список автомобилей.");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadCars();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const filteredSortedItems = useMemo(() => {
    const term = query.toLowerCase();
    const filtered = term
      ? allItems.filter((item) =>
          [item.brand, item.model, item.color, item.link].some((value) => textValue(value).includes(term))
        )
      : allItems;

    const direction = sortOrder === "asc" ? 1 : -1;

    return [...filtered].sort((left, right) => {
      if (sortBy === "price") {
        return direction * compareNumber(left.price, right.price);
      }
      if (sortBy === "year") {
        return direction * compareNumber(left.year, right.year);
      }
      if (sortBy === "model") {
        return direction * compareText(left.model, right.model);
      }
      if (sortBy === "color") {
        return direction * compareText(left.color, right.color);
      }
      return direction * compareText(left.brand, right.brand);
    });
  }, [allItems, query, sortBy, sortOrder]);

  const total = filteredSortedItems.length;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  useEffect(() => {
    if (page > totalPages) {
      setPage(totalPages);
    }
  }, [page, totalPages]);

  const items = useMemo(() => {
    const start = (page - 1) * PAGE_SIZE;
    return filteredSortedItems.slice(start, start + PAGE_SIZE);
  }, [filteredSortedItems, page]);

  const pageButtons = useMemo(() => buildPageWindow(page, totalPages), [page, totalPages]);

  const onLogout = () => {
    clearToken();
    navigate("/login", { replace: true });
  };

  const toggleTheme = () => {
    setTheme((prev) => (prev === "light" ? "dark" : "light"));
  };

  const onSort = (field) => {
    setPage(1);
    setSortOrder((prev) => {
      if (sortBy === field) {
        return prev === "asc" ? "desc" : "asc";
      }
      return field === "price" || field === "year" ? "desc" : "asc";
    });
    setSortBy(field);
  };

  return (
    <main className="page page-cars">
      <div className="dashboard fade-up">
        <header className="hero">
          <div>
            <p className="kicker">Админ-панель Carsensor</p>
            <h1>Список автомобилей</h1>
            <p className="hero-subtitle">
              Данные загружаются через защищенный API `GET /api/cars`. Доступны поиск, сортировка и пагинация.
            </p>
          </div>

          <div className="hero-actions">
            <button className="secondary" onClick={toggleTheme}>
              {theme === "light" ? "Темная тема" : "Светлая тема"}
            </button>
            <button className="secondary" onClick={loadCars} disabled={isLoading}>
              {isLoading ? "Обновляем..." : "Обновить"}
            </button>
            <button className="danger" onClick={onLogout}>
              Выйти
            </button>
          </div>
        </header>

        <section className="stats-grid">
          <article>
            <span>Всего найдено</span>
            <strong>{total}</strong>
          </article>
          <article>
            <span>На текущей странице</span>
            <strong>{items.length}</strong>
          </article>
          <article>
            <span>Страниц</span>
            <strong>{totalPages}</strong>
          </article>
        </section>

        <section className="table-shell">
          <div className="table-toolbar">
            <div className="controls-row">
              <label htmlFor="search-input">Поиск</label>
              <input
                id="search-input"
                placeholder="Марка, модель, цвет, ссылка"
                value={queryInput}
                onChange={(event) => setQueryInput(event.target.value)}
              />
            </div>

            <div className="controls-row">
              <label htmlFor="sort-by">Сортировка</label>
              <select
                id="sort-by"
                value={sortBy}
                onChange={(event) => {
                  setPage(1);
                  setSortBy(event.target.value);
                }}
              >
                <option value="brand">По марке</option>
                <option value="model">По модели</option>
                <option value="year">По году</option>
                <option value="price">По цене</option>
                <option value="color">По цвету</option>
              </select>
            </div>

            <div className="controls-row">
              <label htmlFor="sort-order">Порядок</label>
              <select
                id="sort-order"
                value={sortOrder}
                onChange={(event) => {
                  setPage(1);
                  setSortOrder(event.target.value);
                }}
              >
                <option value="desc">По убыванию</option>
                <option value="asc">По возрастанию</option>
              </select>
            </div>
          </div>

          {error ? <p className="form-error">{error}</p> : null}

          {isLoading ? <p className="empty-state">Загрузка автомобилей...</p> : null}
          {!isLoading && items.length === 0 ? <p className="empty-state">По текущим условиям ничего не найдено.</p> : null}

          {!isLoading && items.length > 0 ? (
            <>
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>
                        <button className="th-button" onClick={() => onSort("brand")}>
                          Марка
                        </button>
                      </th>
                      <th>
                        <button className="th-button" onClick={() => onSort("model")}>
                          Модель
                        </button>
                      </th>
                      <th>
                        <button className="th-button" onClick={() => onSort("year")}>
                          Год
                        </button>
                      </th>
                      <th>
                        <button className="th-button" onClick={() => onSort("price")}>
                          Цена
                        </button>
                      </th>
                      <th>
                        <button className="th-button" onClick={() => onSort("color")}>
                          Цвет
                        </button>
                      </th>
                      <th>Источник</th>
                    </tr>
                  </thead>
                  <tbody>
                    {items.map((item, index) => (
                      <tr key={item.link || `${item.brand}-${item.model}-${item.year}-${index}`} style={{ animationDelay: `${Math.min(index, 12) * 35}ms` }}>
                        <td>{item.brand || "-"}</td>
                        <td>{item.model || "-"}</td>
                        <td>{item.year || "-"}</td>
                        <td>{formatPrice(item.price)}</td>
                        <td>{item.color || "-"}</td>
                        <td>
                          <a href={item.link} target="_blank" rel="noreferrer">
                            Открыть
                          </a>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div className="pagination">
                <button className="secondary" disabled={page <= 1} onClick={() => setPage((prev) => prev - 1)}>
                  Назад
                </button>

                <div className="page-window">
                  {pageButtons.map((buttonPage) => (
                    <button
                      key={buttonPage}
                      className={buttonPage === page ? "page-btn active" : "page-btn"}
                      onClick={() => setPage(buttonPage)}
                    >
                      {buttonPage}
                    </button>
                  ))}
                </div>

                <button
                  className="secondary"
                  disabled={page >= totalPages}
                  onClick={() => setPage((prev) => prev + 1)}
                >
                  Вперед
                </button>
              </div>
            </>
          ) : null}
        </section>
      </div>
    </main>
  );
}
