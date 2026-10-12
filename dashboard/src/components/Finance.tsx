import type { TimestepRecord } from '../api/types';
import { totalMetrics } from '../lib/energy';
import { money, number } from '../lib/format';
export function Finance({ records }: { records: TimestepRecord[] }) {
  const totals = totalMetrics(records);
  const items = [
    ['Énergie achetée', `${number(totals.bought)} kWh`],
    ['Énergie vendue', `${number(totals.sold)} kWh`],
    ['Échanges P2P', `${number(totals.p2p)} kWh`],
    ['Coût des achats', money(totals.cost)],
    ['Revenus de vente', money(totals.revenue)],
    ['Solde net', money(totals.net)],
  ];
  return (
    <section aria-labelledby="finance-title">
      <div className="section-heading">
        <div>
          <span className="eyebrow">MARCHÉ & FINANCE</span>
          <h2 id="finance-title">Chaque échange compte.</h2>
        </div>
        <span className="muted">Période affichée · estimations tarifaires</span>
      </div>
      <div className="finance-grid">
        {items.map(([label, value], i) => (
          <article className={`card finance-card ${i === 5 ? 'balance-card' : ''}`} key={label}>
            <span>{label}</span>
            <strong className={i === 5 ? (totals.net >= 0 ? 'positive' : 'negative') : ''}>
              {value.slice(0, value.lastIndexOf(' '))}{' '}
              <span className="metric-unit">{value.slice(value.lastIndexOf(' ') + 1)}</span>
            </strong>
            {i === 2 && <small>Valeur estimée : {money(totals.p2pValue)}</small>}
            {i === 5 && <small>Ventes − achats · hors P2P</small>}
          </article>
        ))}
      </div>
    </section>
  );
}
