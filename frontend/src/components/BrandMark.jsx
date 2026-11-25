/**
 * NovaLedger brand mark: a yellow tile with a thin black border and a bold
 * black "N" built from two uprights and a diagonal. Decorative; the adjacent
 * wordmark carries the accessible name.
 */
export default function BrandMark({ size = 34 }) {
  return (
    <span className="brand-mark" aria-hidden="true" style={size !== 34 ? { width: size, height: size } : undefined}>
      <svg viewBox="0 0 32 32" xmlns="http://www.w3.org/2000/svg">
        <rect x="1.75" y="1.75" width="28.5" height="28.5" rx="5" fill="#ffcb05" stroke="#0a0a0a" strokeWidth="1.5" />
        <path d="M10 23 V9 M22 23 V9 M10 9 L22 23" fill="none" stroke="#0a0a0a" strokeWidth="3.4" strokeLinecap="square" strokeLinejoin="miter" />
      </svg>
    </span>
  );
}
