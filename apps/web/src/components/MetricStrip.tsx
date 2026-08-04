import type { ReactNode } from 'react';

interface MetricProps {
  label: string;
  value: number;
  hint: string;
  tone: 'critical' | 'warning' | 'neutral' | 'info';
  icon: ReactNode;
}

export default function MetricStrip({ items, caption }: { items: MetricProps[]; caption?: string }) {
  return (
    <section className="metric-strip">
      {caption && <p className="metric-strip__caption">{caption}</p>}
      <div className="metric-strip__items">
        {items.map((item) => (
          <div key={item.label} className={`metric-cell metric-${item.tone}`}>
            <span className="metric-icon">{item.icon}</span>
            <span className="metric-copy">
              <span className="metric-label">{item.label}</span>
              <strong>{item.value}</strong>
              <span className="metric-hint">{item.hint}</span>
            </span>
          </div>
        ))}
      </div>
    </section>
  );
}
