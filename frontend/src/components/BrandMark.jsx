/**
 * NovaLedger brand mark: a square hazard-yellow plate, hard-cornered like a
 * stencilled rack label, carrying a loaded pallet — a case sitting on a deck
 * with three feet.
 *
 * Decorative; the adjacent wordmark carries the accessible name.
 */
export default function BrandMark({ size = 34 }) {
  return (
    <span className="brand-mark" aria-hidden="true" style={size !== 34 ? { width: size, height: size } : undefined}>
      <svg viewBox="0 0 32 32" xmlns="http://www.w3.org/2000/svg">
        <rect x="2" y="2" width="28" height="28" fill="#ffcb05" stroke="#0a0a0a" strokeWidth="2" />
        <g fill="#0a0a0a">
          {/* Case, narrower than the deck so the deck edges read */}
          <rect x="10" y="9" width="12" height="6" />
          {/* Pallet deck */}
          <rect x="7" y="15" width="18" height="3" />
          {/* Feet */}
          <rect x="7" y="18" width="4" height="5" />
          <rect x="14" y="18" width="4" height="5" />
          <rect x="21" y="18" width="4" height="5" />
        </g>
      </svg>
    </span>
  );
}
