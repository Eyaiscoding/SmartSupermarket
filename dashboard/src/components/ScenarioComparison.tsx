import { useMemo } from 'react';
import type { TimestepRecord } from '../api/types';

interface Props {
  records: TimestepRecord[];
  scenario: string;
}

export function ScenarioComparison({ records, scenario }: Props) {
  const stats = useMemo(() => {
    if (records.length === 0) return null;
    
    const avgCoverage = records.reduce((sum, r) => sum + r.coverageRatio, 0) / records.length;
    const avgBattery = records.reduce((sum, r) => sum + r.batterySoc, 0) / records.length;
    const avgGrid = records.reduce((sum, r) => sum + r.gridPower, 0) / records.length;
    const minBattery = Math.min(...records.map(r => r.batterySoc));
    const maxGrid = Math.max(...records.map(r => Math.abs(r.gridPower)));
    const anomalyCount = records.filter(r => r.anomalyFlag).length;
    const tier1Breaches = records.filter(r => !r.tier1Protected).length;
    
    return {
      avgCoverage: (avgCoverage * 100).toFixed(1),
      avgBattery: avgBattery.toFixed(1),
      avgGrid: avgGrid.toFixed(1),
      minBattery: minBattery.toFixed(1),
      maxGrid: maxGrid.toFixed(1),
      anomalyCount,
      tier1Breaches,
      totalRecords: records.length
    };
  }, [records]);
  
  if (!stats) return null;
  
  const getScenarioColor = () => {
    switch (scenario) {
      case 'price_spike': return '#ff9800';
      case 'forced_grid_outage': return '#f44336';
      case 'sensor_corruption': return '#9c27b0';
      default: return '#4caf50';
    }
  };
  
  const getScenarioLabel = () => {
    switch (scenario) {
      case 'price_spike': return 'Pic de Prix';
      case 'forced_grid_outage': return 'Coupure Réseau';
      case 'sensor_corruption': return 'Capteur Défaillant';
      default: return 'Normal';
    }
  };
  
  return (
    <div style={{
      background: 'rgba(0,0,0,0.8)',
      border: `3px solid ${getScenarioColor()}`,
      borderRadius: '12px',
      padding: '20px',
      margin: '20px 0',
      fontFamily: 'monospace'
    }}>
      <h2 style={{ 
        margin: '0 0 15px 0', 
        color: getScenarioColor(),
        fontSize: '24px',
        textTransform: 'uppercase'
      }}>
        📊 Scénario: {getScenarioLabel()}
      </h2>
      
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
        gap: '15px',
        color: '#fff'
      }}>
        <div style={{ padding: '10px', background: 'rgba(255,255,255,0.1)', borderRadius: '8px' }}>
          <div style={{ fontSize: '12px', opacity: 0.7 }}>Couverture Moyenne</div>
          <div style={{ fontSize: '28px', fontWeight: 'bold', color: getScenarioColor() }}>
            {stats.avgCoverage}%
          </div>
        </div>
        
        <div style={{ padding: '10px', background: 'rgba(255,255,255,0.1)', borderRadius: '8px' }}>
          <div style={{ fontSize: '12px', opacity: 0.7 }}>Batterie Moyenne</div>
          <div style={{ fontSize: '28px', fontWeight: 'bold', color: getScenarioColor() }}>
            {stats.avgBattery}%
          </div>
        </div>
        
        <div style={{ padding: '10px', background: 'rgba(255,255,255,0.1)', borderRadius: '8px' }}>
          <div style={{ fontSize: '12px', opacity: 0.7 }}>Réseau Moyen</div>
          <div style={{ fontSize: '28px', fontWeight: 'bold', color: getScenarioColor() }}>
            {stats.avgGrid} kW
          </div>
        </div>
        
        <div style={{ padding: '10px', background: 'rgba(255,255,255,0.1)', borderRadius: '8px' }}>
          <div style={{ fontSize: '12px', opacity: 0.7 }}>Batterie Min</div>
          <div style={{ fontSize: '28px', fontWeight: 'bold', color: stats.minBattery < '20' ? '#f44336' : getScenarioColor() }}>
            {stats.minBattery}%
          </div>
        </div>
        
        <div style={{ padding: '10px', background: 'rgba(255,255,255,0.1)', borderRadius: '8px' }}>
          <div style={{ fontSize: '12px', opacity: 0.7 }}>Réseau Max</div>
          <div style={{ fontSize: '28px', fontWeight: 'bold', color: getScenarioColor() }}>
            {stats.maxGrid} kW
          </div>
        </div>
        
        <div style={{ padding: '10px', background: 'rgba(255,255,255,0.1)', borderRadius: '8px' }}>
          <div style={{ fontSize: '12px', opacity: 0.7 }}>Anomalies Détectées</div>
          <div style={{ fontSize: '28px', fontWeight: 'bold', color: stats.anomalyCount > 0 ? '#f44336' : '#4caf50' }}>
            {stats.anomalyCount}
          </div>
        </div>
        
        {stats.tier1Breaches > 0 && (
          <div style={{ 
            padding: '10px', 
            background: 'rgba(244,67,54,0.3)', 
            borderRadius: '8px',
            border: '2px solid #f44336'
          }}>
            <div style={{ fontSize: '12px', opacity: 0.7 }}>⚠️ Ruptures Tier 1</div>
            <div style={{ fontSize: '28px', fontWeight: 'bold', color: '#f44336' }}>
              {stats.tier1Breaches}
            </div>
          </div>
        )}
      </div>
      
      <div style={{ marginTop: '15px', fontSize: '12px', opacity: 0.6, textAlign: 'right' }}>
        {stats.totalRecords} mesures analysées
      </div>
    </div>
  );
}
