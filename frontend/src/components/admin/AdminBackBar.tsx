import './admin-shared.css';

type Props = {
  label: string;
  onBack: () => void;
};

export function AdminBackBar({ label, onBack }: Props) {
  return (
    <div className="admin-view-nav">
      <button
        type="button"
        className="btn btn--ghost admin-view-nav__back"
        onClick={onBack}
      >
        ← {label}
      </button>
    </div>
  );
}
