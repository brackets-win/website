import './admin-shared.css';

type Props = {
  title: string;
  countLabel: string;
  search: string;
  onSearchChange: (value: string) => void;
  searchLabel: string;
  createLabel?: string;
  onCreate?: () => void;
};

export function AdminCatalogToolbar({
  title,
  countLabel,
  search,
  onSearchChange,
  searchLabel,
  createLabel,
  onCreate,
}: Props) {
  return (
    <header className="card__header catalog-card__header">
      <div className="catalog-card__toolbar">
        <div className="catalog-card__toolbar-row">
          <div>
            <h2 className="catalog-card__title">{title}</h2>
            <p className="catalog-card__count">{countLabel}</p>
          </div>
          {createLabel && onCreate ? (
            <button type="button" className="btn btn--primary" onClick={onCreate}>
              {createLabel}
            </button>
          ) : null}
        </div>
        <input
          type="search"
          className="input catalog-card__search"
          placeholder="Search…"
          value={search}
          onChange={(e) => onSearchChange(e.target.value)}
          aria-label={searchLabel}
        />
      </div>
    </header>
  );
}
