import { useState } from 'react';
import { ArrowDownUp, ShieldCheck } from 'lucide-react';
import { ACTIONS, ACTION_LABELS, type TimestepRecord } from '../api/types';
import { dateTime, number, time, shortDate } from '../lib/format';
import { STEP_HOURS } from '../config/market';
export function Operations({ records }: { records: TimestepRecord[] }) {
  const [sort, setSort] = useState<'timestamp' | 'source'>('timestamp');
  const [ascending, setAscending] = useState(false);
  const [limit, setLimit] = useState(10);
  const anomalies = records
    .filter((r) => r.anomalyFlag)
    .sort(
      (a, b) =>
        (sort === 'timestamp'
          ? a.timestamp - b.timestamp
          : (a.anomalySource ?? '').localeCompare(b.anomalySource ?? '', 'fr')) *
        (ascending ? 1 : -1),
    );
  const start = records[0].timestamp;
  const span = records.at(-1)!.timestamp - start + 900000;
  const axisLabel = (value: number) =>
    span > 86400000 ? `${shortDate(value)} ${time(value)}` : time(value);
  const changeSort = (key: 'timestamp' | 'source') => {
    setSort(key);
    setAscending(sort === key ? !ascending : false);
  };
  return (
    <>
      <div className="operations-grid">
        <section className="card operations">
          <div className="chart-heading">
            <div>
              <h2>Actions de contrôle</h2>
              <p>Décisions MPC + DERMS · un pas = 15 min</p>
            </div>
          </div>
          <div className="timeline">
            {ACTIONS.map((action, index) => {
              const active = records.filter((r) => r.activeActions.includes(action));
              const segments: { start: number; end: number }[] = [];
              for (const record of active) {
                const last = segments.at(-1);
                if (last?.end === record.timestamp) last.end += 900000;
                else segments.push({ start: record.timestamp, end: record.timestamp + 900000 });
              }
              return (
                <div className="timeline-row" key={action}>
                  <div className="timeline-label">
                    <span>
                      <i className={`action-key action-${index}`} aria-hidden="true" />
                      {ACTION_LABELS[action]}
                    </span>
                    <small>
                      {active.length} pas · {number(active.length * STEP_HOURS, 2)} h
                    </small>
                  </div>
                  <div
                    className="track"
                    aria-label={`${ACTION_LABELS[action]} : ${active.length} pas actifs`}
                  >
                    {segments.map((segment) => (
                      <button
                        key={segment.start}
                        className={`segment action-${index}`}
                        style={{
                          left: `${((segment.start - start) / span) * 100}%`,
                          width: `${((segment.end - segment.start) / span) * 100}%`,
                        }}
                        title={`${ACTION_LABELS[action]} · ${dateTime(segment.start)} → ${dateTime(segment.end)}`}
                        aria-label={`${ACTION_LABELS[action]} du ${dateTime(segment.start)} au ${dateTime(segment.end)}`}
                      />
                    ))}
                  </div>
                </div>
              );
            })}
            <div className="timeline-axis">
              <span>{axisLabel(start)}</span>
              <span>{axisLabel(start + span / 2)}</span>
              <span>{axisLabel(start + span)}</span>
            </div>
          </div>
        </section>
        <section className="card operations">
          <div className="chart-heading">
            <div>
              <h2>
                Anomalies récentes <span className="count">{anomalies.length}</span>
              </h2>
              <p>Événements détectés sur la période affichée</p>
            </div>
          </div>
          {anomalies.length === 0 ? (
            <div className="empty compact">Aucune anomalie détectée sur cette période.</div>
          ) : (
            <>
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th
                        aria-sort={
                          sort === 'timestamp' ? (ascending ? 'ascending' : 'descending') : 'none'
                        }
                      >
                        <button onClick={() => changeSort('timestamp')}>
                          Horodatage <ArrowDownUp size={12} />
                        </button>
                      </th>
                      <th
                        aria-sort={
                          sort === 'source' ? (ascending ? 'ascending' : 'descending') : 'none'
                        }
                      >
                        <button onClick={() => changeSort('source')}>
                          Source <ArrowDownUp size={12} />
                        </button>
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {anomalies.slice(0, limit).map((r) => (
                      <tr key={r.timestamp}>
                        <td>{dateTime(r.timestamp)}</td>
                        <td>
                          <span className="anomaly-mark" />
                          {r.anomalySource ?? 'Source non précisée'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {anomalies.length > limit && (
                <button className="text-button" onClick={() => setLimit((n) => n + 20)}>
                  Afficher 20 événements supplémentaires
                </button>
              )}
            </>
          )}
        </section>
      </div>
      <section className="tier-panel" aria-labelledby="tier-title">
        <div>
          <ShieldCheck size={22} />
          <h2 id="tier-title">La chaîne du froid, toujours prioritaire.</h2>
          <p>Ordre de délestage : Tier 4 → Tier 3 → Tier 2. Le Tier 1 n’est jamais délesté.</p>
        </div>
        <div className="tiers">
          <span>
            <b>T1 · Réfrigération</b>
            <small>Protection permanente</small>
          </span>
          <span>
            <b>T2 · Caisses & informatique</b>
            <small>Délestage en dernier</small>
          </span>
          <span>
            <b>T3 · Chauffage & climatisation</b>
            <small>Délestage en deuxième</small>
          </span>
          <span>
            <b>T4 · Éclairage</b>
            <small>Délestage en premier</small>
          </span>
        </div>
      </section>
    </>
  );
}
