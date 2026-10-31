/** Panna's mark: प (pa) on an accent tile, its headline across the top as in the script. Same as public/panna.svg. */
const PannaMark = ({ size = 24 }: { size?: number }) => (
  <svg width={size} height={size} viewBox="0 0 48 48" aria-hidden>
    <rect width="48" height="48" rx="11" fill="var(--color-accent)" />
    <path d="M10 14h28M31 14v24M16 14v8a6 6 0 0 0 6 6h9" fill="none" stroke="var(--color-surface)" strokeWidth="5" strokeLinejoin="round" />
  </svg>
)

export default PannaMark
