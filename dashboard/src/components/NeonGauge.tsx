import { useId } from 'react';
import { number } from '../lib/format';

/** Presentation only: preserves the measured value and the accessible native meter. */
export function NeonGauge({
  value,
  label,
  limits = false,
}: {
  value: number;
  label: string;
  limits?: boolean;
}) {
  const gradient = useId();
  return (
    <div className="neon-gauge">
      <svg viewBox="0 0 200 122" aria-hidden="true" focusable="false">
        <defs>
          <linearGradient id={gradient} x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor="var(--yellow)" />
            <stop offset="65%" stopColor="var(--yellow)" />
            <stop offset="100%" stopColor="var(--orange)" />
          </linearGradient>
        </defs>
        <path className="gauge-track" d="M 18 102 A 82 82 0 0 1 182 102" pathLength={100} />
        <path
          className="gauge-fill"
          d="M 18 102 A 82 82 0 0 1 182 102"
          pathLength={100}
          stroke={`url(#${gradient})`}
          strokeDasharray={`${value} 100`}
        />
        {limits && (
          <g className="gauge-ticks">
            <path d="M 16 102 L 30 102" transform="rotate(18 100 102)" />
            <path d="M 16 102 L 30 102" transform="rotate(171 100 102)" />
          </g>
        )}
      </svg>
      <strong aria-hidden="true">
        {number(value)}
        <small> %</small>
      </strong>
      <meter
        className="sr-only"
        aria-label={label}
        min={0}
        max={100}
        low={limits ? 10 : undefined}
        high={limits ? 95 : undefined}
        optimum={limits ? 60 : undefined}
        value={value}
      />
    </div>
  );
}
