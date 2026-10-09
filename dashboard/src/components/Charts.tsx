import { useId, useMemo, useState } from 'react';
import {
  Area,
  Bar,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceArea,
  ReferenceDot,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import type { TimestepRecord } from '../api/types';
import { aggregateEnergy, cumulativeBalance, type Aggregation } from '../lib/energy';
import { dateTime, number, shortDate, time } from '../lib/format';
import { CURRENCY } from '../config/market';
import { ChartGradients } from './ChartGradients';
interface HoverProps {
  active?: boolean;
  label?: string | number;
  payload?: ReadonlyArray<{
    name?: string;
    value?: number | string;
    unit?: string;
    color?: string;
  }>;
  records?: TimestepRecord[];
}
function Hover({ active, label, payload, records }: HoverProps) {
  if (!active || !payload?.length) return null;
  const record = records?.find((r) => r.timestamp === Number(label));
  return (
    <div className="chart-tooltip">
      <strong>{dateTime(Number(label))}</strong>
      {payload.map((entry, i) => (
        <div key={i}>
          <span style={{ color: entry.color?.startsWith('url(') ? 'var(--text)' : entry.color }}>
            {entry.name}
          </span>
          <b>
            {typeof entry.value === 'number' ? number(entry.value, 2) : entry.value} {entry.unit}
          </b>
        </div>
      ))}
      {record?.anomalyFlag && (
        <p className="anomaly-text">Anomalie : {record.anomalySource ?? 'Source non précisée'}</p>
      )}
    </div>
  );
}
export function Charts({ records }: { records: TimestepRecord[] }) {
  const gradientId = useId();
  const [aggregation, setAggregation] = useState<Aggregation>('hour');
  const flows = useMemo(
    () =>
      records.map((r) => ({
        ...r,
        importPower: Math.max(r.gridPower, 0),
        exportPower: Math.min(r.gridPower, 0),
      })),
    [records],
  );
  const bars = useMemo(() => aggregateEnergy(records, aggregation), [records, aggregation]);
  const balance = useMemo(() => cumulativeBalance(records), [records]);
  const hasPrice = records.some((r) => r.energyPrice !== undefined);
  const domain: [number, number] = [
    records[0].timestamp,
    Math.max(records.at(-1)!.timestamp, records[0].timestamp + 900000),
  ];
  const tick = (t: number) =>
    domain[1] - domain[0] >= 86400000 ? `${shortDate(t)} ${time(t)}` : time(t);
  const axis = {
    dataKey: 'timestamp',
    type: 'number' as const,
    domain,
    tickFormatter: tick,
    minTickGap: 45,
    tickLine: false,
    axisLine: false,
  };
  const grid = <CartesianGrid strokeDasharray="3 5" vertical={false} stroke="var(--grid-line)" />;
  return (
    <section className="charts-grid" aria-label="Graphiques énergétiques">
      <article className="card chart-card chart-wide">
        <div className="chart-heading">
          <div>
            <h2>Échanges avec le réseau</h2>
            <p>Importation positive · exportation négative</p>
          </div>
          <div className="legend">
            <span>
              <i className="dot import" />
              Import
            </span>
            <span>
              <i className="dot export" />
              Export
            </span>
            <span>
              <i className="dot anomaly" />
              Anomalie
            </span>
          </div>
        </div>
        <div
          className="chart"
          role="img"
          aria-label="Puissance réseau en kW et anomalies au fil du temps"
        >
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart
              data={flows}
              syncId="energy"
              syncMethod="value"
              margin={{ top: 15, right: hasPrice ? 20 : 10, bottom: 5, left: 0 }}
            >
              <ChartGradients id={`${gradientId}-flows`} />
              {grid}
              <XAxis {...axis} />
              <YAxis
                yAxisId="power"
                tickFormatter={(v) => `${v}`}
                unit=" kW"
                width={68}
                axisLine={false}
                tickLine={false}
              />
              {hasPrice && (
                <YAxis
                  yAxisId="price"
                  orientation="right"
                  unit={` ${CURRENCY}/kWh`}
                  width={82}
                  tickFormatter={(v) => number(Number(v), 2)}
                  axisLine={false}
                  tickLine={false}
                />
              )}
              <Tooltip content={<Hover records={records} />} />
              <ReferenceLine yAxisId="power" y={0} stroke="var(--muted)" />
              <Area
                yAxisId="power"
                type="monotone"
                dataKey="importPower"
                name="Import"
                unit="kW"
                className="neon-line"
                stroke="var(--yellow)"
                strokeWidth={2}
                fill={`url(#${gradientId}-flows-import)`}
                fillOpacity={1}
                isAnimationActive={false}
              />
              <Area
                yAxisId="power"
                type="monotone"
                dataKey="exportPower"
                name="Export"
                unit="kW"
                stroke="var(--fuchsia)"
                strokeWidth={2}
                strokeDasharray="6 3"
                fill={`url(#${gradientId}-flows-export)`}
                fillOpacity={1}
                isAnimationActive={false}
              />
              {hasPrice && (
                <Line
                  yAxisId="price"
                  dataKey="energyPrice"
                  name="Prix d’achat"
                  unit={`${CURRENCY}/kWh`}
                  stroke="var(--price-color)"
                  dot={false}
                  strokeDasharray="2 5"
                  connectNulls={false}
                  isAnimationActive={false}
                />
              )}{' '}
              {records
                .filter((r) => r.anomalyFlag)
                .map((r) => (
                  <ReferenceDot
                    key={r.timestamp}
                    yAxisId="power"
                    x={r.timestamp}
                    y={r.gridPower}
                    r={4}
                    className="anomaly-dot"
                    fill="var(--fuchsia)"
                    stroke="var(--card)"
                  />
                ))}
            </ComposedChart>
          </ResponsiveContainer>
        </div>
        <div className="chart-footer">
          <span>Pas de simulation : 15 minutes</span>
          <span>
            {hasPrice
              ? records.some((r) => r.energyPrice === undefined)
                ? 'Prix partiels : tarif par défaut pour les pas manquants'
                : 'Prix d’achat · ligne en pointillés'
              : 'Les prix utilisent les tarifs par défaut'}
          </span>
        </div>
      </article>
      <article className="card chart-card">
        <div className="chart-heading">
          <div>
            <h2>Réserve de la batterie</h2>
            <p>Zone de fonctionnement sûre : 10–95 %</p>
          </div>
          <span className="badge neutral">SOC</span>
        </div>
        <div
          className="chart small"
          role="img"
          aria-label="État de charge de la batterie en pourcentage"
        >
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={records} syncId="energy" syncMethod="value">
              {grid}
              <XAxis {...axis} />
              <YAxis domain={[0, 100]} unit=" %" width={58} tickLine={false} axisLine={false} />
              <Tooltip content={<Hover />} />
              <ReferenceArea y1={10} y2={95} fill="var(--yellow)" fillOpacity={0.035} />
              <ReferenceLine y={10} stroke="var(--yellow-soft)" strokeDasharray="4 4" />
              <ReferenceLine y={95} stroke="var(--yellow-soft)" strokeDasharray="4 4" />
              <Line
                dataKey="batterySoc"
                name="Charge"
                unit="%"
                className="neon-line"
                stroke="var(--yellow)"
                strokeWidth={2.5}
                dot={false}
                isAnimationActive={false}
              />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      </article>
      <article className="card chart-card">
        <div className="chart-heading">
          <div>
            <h2>Énergie achetée & vendue</h2>
            <p>
              <span className="import-text">Jaune : achats</span> ·{' '}
              <span className="export-text">fuchsia : ventes</span>
            </p>
          </div>
          <label className="sr-only" htmlFor="aggregation">
            Agrégation de l’énergie
          </label>
          <select
            id="aggregation"
            value={aggregation}
            onChange={(e) => setAggregation(e.target.value as Aggregation)}
          >
            <option value="step">15 min</option>
            <option value="hour">Heure</option>
            <option value="day">Jour</option>
          </select>
        </div>
        <div
          className="chart small"
          role="img"
          aria-label="Énergie achetée et vendue en kilowattheures"
        >
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={bars}>
              <ChartGradients id={`${gradientId}-bars`} />
              {grid}
              <XAxis
                dataKey="timestamp"
                tickFormatter={(v) =>
                  aggregation === 'day' ? shortDate(Number(v)) : time(Number(v))
                }
                minTickGap={30}
                tickLine={false}
                axisLine={false}
              />
              <YAxis unit=" kWh" width={70} tickLine={false} axisLine={false} />
              <Tooltip content={<Hover />} />
              <Bar
                dataKey="bought"
                name="Achats"
                unit="kWh"
                fill={`url(#${gradientId}-bars-buy-bars)`}
                radius={[4, 4, 0, 0]}
                isAnimationActive={false}
              />
              <Bar
                dataKey="sold"
                name="Ventes"
                unit="kWh"
                fill={`url(#${gradientId}-bars-sell-bars)`}
                radius={[4, 4, 0, 0]}
                isAnimationActive={false}
              />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      </article>
      <article className="card chart-card chart-wide">
        <div className="chart-heading">
          <div>
            <h2>Solde net cumulé</h2>
            <p>Revenus de vente moins coût des achats, sur la période affichée</p>
          </div>
          <span className="badge neutral">{CURRENCY}</span>
        </div>
        <div className="chart small" role="img" aria-label="Solde financier cumulé en euros">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={balance} syncId="energy" syncMethod="value">
              {grid}
              <XAxis {...axis} />
              <YAxis
                unit={` ${CURRENCY}`}
                width={76}
                tickFormatter={(v) => number(Number(v), 0)}
                tickLine={false}
                axisLine={false}
              />
              <Tooltip content={<Hover />} />
              <ReferenceLine y={0} stroke="var(--muted)" />
              <Area
                dataKey="balance"
                name="Solde cumulé"
                unit={CURRENCY}
                stroke={balance.at(-1)!.balance >= 0 ? 'var(--ok)' : 'var(--danger)'}
                fill={balance.at(-1)!.balance >= 0 ? 'var(--ok)' : 'var(--danger)'}
                fillOpacity={0.06}
                strokeWidth={2}
                isAnimationActive={false}
              />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      </article>
    </section>
  );
}
