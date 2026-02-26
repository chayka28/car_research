import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { deleteListing, getListings } from "../lib/api";
import { clearToken, getToken } from "../lib/auth";

const PAGE_SIZE = 100;
const THEME_STORAGE_KEY = "car_research_theme";
const DELETE_CONFIRM_STORAGE_KEY = "car_research_skip_delete_confirm";

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

function formatDate(value) {
  if (!value) {
    return "-";
  }

  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return "-";
  }

  return new Intl.DateTimeFormat("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit"
  }).format(parsed);
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

export default function CarsPage() {
  const navigate = useNavigate();

  const [items, setItems] = useState([]);
  const [meta, setMeta] = useState({ total: 0, page: 1, pages: 1, per_page: PAGE_SIZE });
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");
  const [deletingId, setDeletingId] = useState(null);

  const [queryInput, setQueryInput] = useState("");
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [sortBy, setSortBy] = useState("updated");
  const [sortOrder, setSortOrder] = useState("desc");
  const [page, setPage] = useState(1);
  const [theme, setTheme] = useState(() => window.localStorage.getItem(THEME_STORAGE_KEY) || "light");
  const [pendingDeleteItem, setPendingDeleteItem] = useState(null);
  const [dontShowDeleteConfirm, setDontShowDeleteConfirm] = useState(false);
  const [skipDeleteConfirm, setSkipDeleteConfirm] = useState(
    () => window.localStorage.getItem(DELETE_CONFIRM_STORAGE_KEY) === "1"
  );

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

  useEffect(() => {
    if (!pendingDeleteItem) {
      return undefined;
    }

    const onKeyDown = (event) => {
      if (event.key === "Escape") {
        setPendingDeleteItem(null);
        setDontShowDeleteConfirm(false);
      }
    };

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [pendingDeleteItem]);

  const loadListings = async () => {
    setIsLoading(true);
    setError("");

    const token = getToken();
    if (!token) {
      navigate("/login", { replace: true });
      return;
    }

    try {
      const data = await getListings(token, {
        page,
        per_page: PAGE_SIZE,
        query,
        sort_by: sortBy,
        sort_order: sortOrder,
        is_active: statusFilter === "all" ? undefined : statusFilter === "active"
      });

      setItems(Array.isArray(data?.items) ? data.items : []);
      setMeta({
        total: Number(data?.total || 0),
        page: Number(data?.page || 1),
        pages: Number(data?.pages || 1),
        per_page: Number(data?.per_page || PAGE_SIZE)
      });
    } catch (apiError) {
      if (apiError.status === 401) {
        clearToken();
        navigate("/login", { replace: true });
        return;
      }
      setError(apiError.message || "Не удалось загрузить список объявлений.");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadListings();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page, query, sortBy, sortOrder, statusFilter]);

  const activeCountOnPage = useMemo(() => items.filter((item) => item.is_active).length, [items]);
  const pageButtons = useMemo(() => buildPageWindow(meta.page, meta.pages), [meta.page, meta.pages]);

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
      return field === "updated" ? "desc" : "asc";
    });
    setSortBy(field);
  };

  const deleteListingById = async (listingId) => {
    const token = getToken();
    if (!token) {
      navigate("/login", { replace: true });
      return;
    }

    try {
      setDeletingId(listingId);
      await deleteListing(token, listingId);

      const nextPage = items.length === 1 && page > 1 ? page - 1 : page;
      if (nextPage !== page) {
        setPage(nextPage);
      } else {
        await loadListings();
      }
    } catch (apiError) {
      if (apiError.status === 401) {
        clearToken();
        navigate("/login", { replace: true });
        return;
      }
      setError(apiError.message || "Не удалось удалить запись.");
    } finally {
      setDeletingId(null);
    }
  };

  const onDeleteClick = (item) => {
    if (skipDeleteConfirm) {
      void deleteListingById(item.id);
      return;
    }

    setDontShowDeleteConfirm(false);
    setPendingDeleteItem(item);
  };

  const onCancelDelete = () => {
    setPendingDeleteItem(null);
    setDontShowDeleteConfirm(false);
  };

  const onConfirmDelete = async () => {
    if (!pendingDeleteItem) {
      return;
    }

    if (dontShowDeleteConfirm) {
      window.localStorage.setItem(DELETE_CONFIRM_STORAGE_KEY, "1");
      setSkipDeleteConfirm(true);
    }

    const listingId = pendingDeleteItem.id;
    setPendingDeleteItem(null);
    setDontShowDeleteConfirm(false);
    await deleteListingById(listingId);
  };

  return (
    <main className="page page-cars">
      <div className="dashboard fade-up">
        <header className="hero">
          <div>
            <p className="kicker">Админ-панель Carsensor</p>
            <h1>Управление объявлениями</h1>
            <p className="hero-subtitle">
              Просматривайте активные и неактивные предложения, применяйте фильтры и сортировку, удаляйте записи.
            </p>
          </div>

          <div className="hero-actions">
            <button className="secondary" onClick={toggleTheme}>
              {theme === "light" ? "Тёмная тема" : "Светлая тема"}
            </button>
            <button className="secondary" onClick={loadListings} disabled={isLoading}>
              {isLoading ? "Обновляем..." : "Обновить"}
            </button>
            <button className="danger" onClick={onLogout}>
              Выйти
            </button>
          </div>
        </header>

        <section className="stats-grid">
          <article>
            <span>Всего в базе</span>
            <strong>{meta.total}</strong>
          </article>
          <article>
            <span>На текущей странице</span>
            <strong>{items.length}</strong>
          </article>
          <article>
            <span>Активных на странице</span>
            <strong>{activeCountOnPage}</strong>
          </article>
        </section>

        <section className="table-shell">
          <div className="table-toolbar">
            <div className="controls-row">
              <label htmlFor="search-input">Поиск</label>
              <input
                id="search-input"
                placeholder="Марка, модель, цвет, ID"
                value={queryInput}
                onChange={(event) => setQueryInput(event.target.value)}
              />
            </div>

            <div className="controls-row">
              <label htmlFor="status-filter">Статус</label>
              <select
                id="status-filter"
                value={statusFilter}
                onChange={(event) => {
                  setPage(1);
                  setStatusFilter(event.target.value);
                }}
              >
                <option value="all">Все</option>
                <option value="active">Только активные</option>
                <option value="inactive">Только неактивные</option>
              </select>
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
                <option value="updated">По обновлению</option>
                <option value="brand">По марке</option>
                <option value="model">По модели</option>
                <option value="year">По году</option>
                <option value="price">По цене</option>
                <option value="status">По статусу</option>
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

          {isLoading ? <p className="empty-state">Загрузка объявлений...</p> : null}
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
                      <th>Цвет</th>
                      <th>
                        <button className="th-button" onClick={() => onSort("status")}>
                          Статус
                        </button>
                      </th>
                      <th>
                        <button className="th-button" onClick={() => onSort("updated")}>
                          Обновлено
                        </button>
                      </th>
                      <th>Источник</th>
                      <th>Действия</th>
                    </tr>
                  </thead>
                  <tbody>
                    {items.map((item, index) => (
                      <tr key={item.id} style={{ animationDelay: `${Math.min(index, 12) * 35}ms` }}>
                        <td>{item.brand}</td>
                        <td>{item.model}</td>
                        <td>{item.year || "-"}</td>
                        <td>{item.price_text || formatPrice(item.price)}</td>
                        <td>{item.color || "-"}</td>
                        <td>
                          <span className={`status-pill ${item.is_active ? "active" : "inactive"}`}>
                            {item.is_active ? "Активно" : "Неактивно"}
                          </span>
                        </td>
                        <td>{formatDate(item.last_seen_at)}</td>
                        <td>
                          <a href={item.link} target="_blank" rel="noreferrer">
                            Открыть
                          </a>
                        </td>
                        <td>
                          <button
                            className="danger ghost"
                            onClick={() => onDeleteClick(item)}
                            disabled={deletingId === item.id}
                          >
                            {deletingId === item.id ? "Удаление..." : "Удалить"}
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div className="pagination">
                <button className="secondary" disabled={meta.page <= 1} onClick={() => setPage((prev) => prev - 1)}>
                  Назад
                </button>

                <div className="page-window">
                  {pageButtons.map((buttonPage) => (
                    <button
                      key={buttonPage}
                      className={buttonPage === meta.page ? "page-btn active" : "page-btn"}
                      onClick={() => setPage(buttonPage)}
                    >
                      {buttonPage}
                    </button>
                  ))}
                </div>

                <button
                  className="secondary"
                  disabled={meta.page >= meta.pages}
                  onClick={() => setPage((prev) => prev + 1)}
                >
                  Вперёд
                </button>
              </div>
            </>
          ) : null}
        </section>
      </div>

      {pendingDeleteItem ? (
        <div className="modal-backdrop" role="presentation" onClick={onCancelDelete}>
          <div className="modal" role="dialog" aria-modal="true" aria-labelledby="delete-modal-title" onClick={(event) => event.stopPropagation()}>
            <h2 id="delete-modal-title">Подтвердите удаление</h2>
            <p>
              Вы действительно хотите удалить объявление <strong>{pendingDeleteItem.brand}</strong> <strong>{pendingDeleteItem.model}</strong> ({pendingDeleteItem.external_id})?
            </p>
            <p>Действие необратимо.</p>

            <label className="checkbox-row">
              <input
                type="checkbox"
                checked={dontShowDeleteConfirm}
                onChange={(event) => setDontShowDeleteConfirm(event.target.checked)}
              />
              <span>Не показывать это сообщение снова</span>
            </label>

            <div className="modal-actions">
              <button className="secondary" onClick={onCancelDelete} disabled={deletingId === pendingDeleteItem.id}>
                Отмена
              </button>
              <button className="danger" onClick={onConfirmDelete} disabled={deletingId === pendingDeleteItem.id}>
                {deletingId === pendingDeleteItem.id ? "Удаление..." : "Удалить"}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </main>
  );
}
