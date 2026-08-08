import { ArrowRightOutlined } from '@ant-design/icons';
import type { ReactNode } from 'react';

interface MetricProps {
  label: string;
  value: number;
  hint: string;
  tone: 'critical' | 'warning' | 'neutral' | 'info';
  icon: ReactNode;
  onClick?: () => void;
}

export default function MetricStrip({ items, caption }: { items: MetricProps[]; caption?: string }) {
  return (
    <section className="metric-strip">
      {caption && <p className="metric-strip__caption">{caption}</p>}
      <div className="metric-strip__items">
        {items.map((item) => (
          <button type="button" key={item.label} className={`metric-cell metric-${item.tone}`} onClick={item.onClick}>
            <span className="metric-icon">{item.icon}</span>
            <span className="metric-copy">
              <span className="metric-label">{item.label}</span>
              <strong>{item.value}</strong>
              <span className="metric-hint">{item.hint}</span>
            </span>
            <ArrowRightOutlined className="metric-arrow" />
          </button>
        ))}
      </div>
    </section>
  );
}
