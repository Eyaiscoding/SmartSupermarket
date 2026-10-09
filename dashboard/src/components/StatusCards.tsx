import {
  ArrowDownLeft,
  ArrowUpRight,
  BatteryCharging,
  Check,
  X,
  ShieldCheck,
  Zap,
} from 'lucide-react';
import type { TimestepRecord } from '../api/types';
import { number } from '../lib/format';
import { NeonGauge } from './NeonGauge';
const statuses = { NORMAL: 'Normal', AT_RISK: 'À risque', CRITICAL: 'Critique' };
export function StatusCards({ record }: { record: TimestepRecord }) {
  return (
    <section className="kpi-grid" aria-label="État actuel">
      <article className="card metric">
        <div className="card-label">
          <span>Couverture des besoins</span>
          <Zap size={18} />
        </div>
        <div className="gauge-status">
          <span
            className={`badge ${record.coverageStatus}`}
            aria-label={`Couverture : ${statuses[record.coverageStatus]}`}
          >
            {statuses[record.coverageStatus]}
          </span>
        </div>
        <NeonGauge label="Taux de couverture des besoins" value={record.coverageRatio * 100} />
        <p>Objectif de couverture ≥ 95 %</p>
      </article>
      <article className={`card metric protection ${record.tier1Protected ? '' : 'breach'}`}>
        <div className="card-label">
          <span>Charges critiques · Tier 1</span>
          <ShieldCheck size={18} />
        </div>
        <div className="metric-line">
          <span className="check-icon">
            {record.tier1Protected ? <Check size={23} /> : <X size={23} />}
          </span>
          <strong className="word">{record.tier1Protected ? 'Protégées' : 'En danger'}</strong>
        </div>
        <p>Réfrigération · priorité absolue</p>
        <span className="micro-label">
          {record.tier1Protected ? 'Chaîne du froid préservée' : 'Intervention immédiate requise'}
        </span>
      </article>
      <article className="card metric">
        <div className="card-label">
          <span>État de charge batterie</span>
          <BatteryCharging size={18} />
        </div>
        <NeonGauge
          label={`Charge batterie ${number(record.batterySoc)} %, plage sûre de 10 à 95 %`}
          limits
          value={record.batterySoc}
        />
        <div className="meter-limits">
          <span>10 % · réserve</span>
          <span>95 % · limite</span>
        </div>
        {(record.batterySoc < 10 || record.batterySoc > 95) && (
          <p className="danger">Batterie hors plage sûre</p>
        )}
      </article>
      <article className="card metric">
        <div className="card-label">
          <span>Puissance réseau</span>
          {record.gridPower >= 0 ? <ArrowDownLeft size={18} /> : <ArrowUpRight size={18} />}
        </div>
        <strong className={record.gridPower >= 0 ? 'import-text' : 'export-text'}>
          {number(Math.abs(record.gridPower))}
          <small> kW</small>
        </strong>
        <p className={record.gridPower >= 0 ? 'import-text' : 'export-text'}>
          {record.gridPower > 0
            ? '↙ Importation du réseau'
            : record.gridPower < 0
              ? '↗ Exportation vers le réseau'
              : 'Aucun échange réseau'}
        </p>
        <div className="p2p">
          Échange P2P <b>{number(record.p2pPower)} kW</b>
        </div>
      </article>
    </section>
  );
}
