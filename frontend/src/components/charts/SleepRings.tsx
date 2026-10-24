import { useEffect, useState } from 'react';

interface SleepRingsProps {
  /** Average sleep efficiency, % of time in bed asleep (its own 0-100 scale). */
  efficiency: number | null;
  /** Average sleep duration in minutes. */
  durationMinutes: number | null;
  deepMinutes: number | null;
  remMinutes: number | null;
  size?: number;
}

const GAP_PX = 3;

function splitDuration(minutes: number): { h: number; m: number } {
  const total = Math.round(minutes);
  return { h: Math.floor(total / 60), m: total % 60 };
}

/**
 * Two concentric rings with separate meanings, labeled in the adjacent legend:
 *  - Outer thin ring: sleep efficiency on its own 0-100% scale.
 *  - Inner segmented ring: how the average sleep duration divides into deep,
 *    REM and the remainder. It is a composition of duration, not a score.
 * The center states the average duration. No target is implied.
 */
export function SleepRings({ efficiency, durationMinutes, deepMinutes, remMinutes, size = 280 }: SleepRingsProps) {
  const [ready, setReady] = useState(false);
  useEffect(() => {
    const id = requestAnimationFrame(() => setReady(true));
    return () => cancelAnimationFrame(id);
  }, []);

  const c = size / 2;
  const outerR = c - 8;
  const outerStroke = 7;
  const innerR = outerR - 26;
  const innerStroke = 24;
  const outerC = 2 * Math.PI * outerR;
  const innerC = 2 * Math.PI * innerR;

  const effFraction = efficiency === null ? 0 : Math.min(Math.max(efficiency / 100, 0), 1);

  // Stage composition only when the parts are consistent with the total.
  let segments: Array<{ id: string; color: string; fraction: number }> = [];
  if (durationMinutes !== null && durationMinutes > 0 && deepMinutes !== null && remMinutes !== null) {
    const other = durationMinutes - deepMinutes - remMinutes;
    if (other >= 0) {
      segments = [
        { id: 'deep', color: 'var(--c-deep)', fraction: deepMinutes / durationMinutes },
        { id: 'rem', color: 'var(--c-rem)', fraction: remMinutes / durationMinutes },
        { id: 'other', color: 'var(--c-other)', fraction: other / durationMinutes },
      ];
    }
  }

  let cursor = 0;
  const arcs = segments.map((s) => {
    const start = cursor * innerC;
    const len = Math.max(s.fraction * innerC - GAP_PX, 0.5);
    cursor += s.fraction;
    return { ...s, start, len };
  });

  const dur = durationMinutes === null ? null : splitDuration(durationMinutes);
  const label =
    `Average sleep duration ${dur ? `${dur.h} hours ${dur.m} minutes` : 'not recorded'}. ` +
    `Sleep efficiency ${efficiency === null ? 'not recorded' : `${Math.round(efficiency)} percent of time in bed`}.`;

  return (
    <div className="rings" style={{ width: size, height: size }} role="img" aria-label={label}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} aria-hidden="true">
        <g transform={`rotate(-90 ${c} ${c})`}>
          {/* Outer: efficiency */}
          <circle cx={c} cy={c} r={outerR} fill="none" stroke="var(--surface-3)" strokeWidth={outerStroke} />
          {efficiency !== null && (
            <circle
              cx={c}
              cy={c}
              r={outerR}
              fill="none"
              stroke="var(--c-efficiency)"
              strokeWidth={outerStroke}
              strokeLinecap="round"
              className="rings__arc"
              style={{ strokeDasharray: ready ? `${effFraction * outerC} ${outerC}` : `0 ${outerC}` }}
            />
          )}

          {/* Inner: composition of average sleep duration */}
          <circle cx={c} cy={c} r={innerR} fill="none" stroke="var(--surface-2)" strokeWidth={innerStroke} />
          {arcs.map((a, i) => (
            <circle
              key={a.id}
              cx={c}
              cy={c}
              r={innerR}
              fill="none"
              stroke={a.color}
              strokeWidth={innerStroke}
              className="rings__arc"
              style={{
                strokeDasharray: ready ? `${a.len} ${innerC}` : `0 ${innerC}`,
                strokeDashoffset: -(a.start + GAP_PX / 2),
                transitionDelay: `${i * 120}ms`,
              }}
            />
          ))}
        </g>
      </svg>

      <div className="rings__center" aria-hidden="true">
        <span className="rings__caption">Avg sleep</span>
        {dur ? (
          <span className="rings__value">
            {dur.h}
            <small>h</small> {String(dur.m).padStart(2, '0')}
            <small>m</small>
          </span>
        ) : (
          <span className="rings__value rings__value--missing">Not recorded</span>
        )}
      </div>
    </div>
  );
}
