/**
 * Shared page header: a small mono eyebrow naming the section the page belongs
 * to, the title, a one-line subtitle, and optional actions on the right.
 */
export default function PageHeader({ eyebrow, title, subtitle, actions }) {
  return (
    <div className="page-header">
      <div className="page-header__text">
        {eyebrow && <p className="eyebrow">{eyebrow}</p>}
        <h1 className="page-title">{title}</h1>
        {subtitle && <p className="page-subtitle">{subtitle}</p>}
      </div>
      {actions && <div className="page-header__actions">{actions}</div>}
    </div>
  );
}
