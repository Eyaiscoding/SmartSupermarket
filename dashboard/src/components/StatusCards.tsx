import {
  ArrowDownLeft,
  ArrowUpRight,
  BatteryCharging,
  Check,
  X,
  ShieldCheck,
  Zap,
} from 'lucide-react';
import { TEMPERATURE_SENSORS, type TimestepRecord, type TemperatureSensor } from '../api/types';
import { number, dateTime } from '../lib/format';
import { NeonGauge } from './NeonGauge';
const statuses = { NORMAL: 'Normal', AT_RISK: 'À risque', CRITICAL: 'Critique' };
const temperatureLabels: Record<TemperatureSensor, string> = {
  display_freezer_temp: 'Vitrine surgelés',
  freezer_room_temp: 'Chambre de congélation',
  display_refrigerator_temp: 'Vitrine réfrigérée',
  cold_room_temp: 'Chambre froide',
};
const temperatureStatuses = { OK: 'Dans la plage', WARNING: 'Avertissement', CRITICAL: 'Critique' };
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
          {record.tier1Protected
            ? 'Alimentation prioritaire protégée'
            : 'Intervention immédiate requise'}
        </span>
        <div aria-live="polite" className="temperature-monitor">
          <p>
            Températures ·{' '}
            {record.temperatureStatus ? (
              <span
                className={`badge ${record.temperatureStatus === 'OK' ? 'NORMAL' : record.temperatureStatus === 'WARNING' ? 'AT_RISK' : 'CRITICAL'}`}
              >
                {temperatureStatuses[record.temperatureStatus]}
              </span>
            ) : (
              'Mesures indisponibles'
            )}
          </p>
          {record.temperatures && (
            <details>
              <summary>Voir les capteurs ({Object.keys(record.temperatures).length}/4)</summary>
              {TEMPERATURE_SENSORS.map((sensor) => (
                <p key={sensor}>
                  {temperatureLabels[sensor]} :{' '}
                  {record.temperatures?.[sensor] == null
                    ? 'Indisponible'
                    : `${number(record.temperatures[sensor])} °C`}
                </p>
              ))}
              {record.temperatureAlerts?.map((alert) => (
                <p key={alert.sensor}>
                  {temperatureLabels[alert.sensor]} · {temperatureStatuses[alert.status]} depuis{' '}
                  {dateTime(alert.since)}. Plage : {number(alert.limitLow)} à{' '}
                  {number(alert.limitHigh)} °C.
                </p>
              ))}
              <p>Seuils de simulation à valider.</p>
            </details>
          )}
        </div>
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
