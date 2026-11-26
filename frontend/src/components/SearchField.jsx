/**
 * Underlined search field used in the page toolbars: a 2px ink rule to write
 * on rather than a boxed input, with a leading magnifier.
 *
 * The list is expected to refetch as the query settles, so there is no
 * submit button.
 */
export default function SearchField({ value, onChange, label, placeholder }) {
  return (
    <span className="search-field search-field--underline">
      <svg
        className="search-field__icon"
        width="16"
        height="16"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
      >
        <circle cx="11" cy="11" r="7" />
        <path d="m20 20-3.5-3.5" />
      </svg>
      <input
        className="input"
        type="search"
        aria-label={label}
        placeholder={placeholder}
        value={value}
        onChange={e => onChange(e.target.value)}
      />
    </span>
  );
}
