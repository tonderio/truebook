/**
 * TrueBook Logo components.
 * Uses the official TrueBook SVG logo from /public/truebook-logo.svg
 */

export function TrueBookLogo({ height = 32, className = '' }) {
  return (
    <img
      src="/truebook-logo.svg"
      alt="TrueBook"
      style={{ height }}
      className={className}
    />
  )
}

export function TrueBookMark({ size = 28 }) {
  return (
    <div
      className="flex items-center justify-center rounded-lg bg-blue-600 text-white font-bold"
      style={{ width: size, height: size, fontSize: size * 0.5 }}
    >
      TB
    </div>
  )
}

// Backward-compatible exports (old code references these)
export const TonderWordmark = TrueBookLogo
export const TonderMark = TrueBookMark
export const TonderBrand = ({ logoHeight = 28 }) => <TrueBookLogo height={logoHeight} />
