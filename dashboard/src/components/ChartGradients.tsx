/** SVG paint definitions use the theme variables, including the soft intensity. */
export function ChartGradients({ id }: { id: string }) {
  return (
    <defs>
      <linearGradient id={`${id}-import`} x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stopColor="var(--yellow)" stopOpacity={0.38} />
        <stop offset="100%" stopColor="var(--orange)" stopOpacity={0.04} />
      </linearGradient>
      <linearGradient id={`${id}-export`} x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stopColor="var(--fuchsia)" stopOpacity={0.32} />
        <stop offset="100%" stopColor="var(--fuchsia)" stopOpacity={0.02} />
      </linearGradient>
      <linearGradient id={`${id}-buy-bars`} x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stopColor="var(--yellow)" />
        <stop offset="100%" stopColor="var(--orange)" />
      </linearGradient>
      <linearGradient id={`${id}-sell-bars`} x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stopColor="var(--fuchsia)" />
        <stop offset="100%" stopColor="var(--fuchsia-soft)" />
      </linearGradient>
    </defs>
  );
}
