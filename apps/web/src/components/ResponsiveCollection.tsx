import type { Key, ReactNode } from 'react';

export type ResponsiveCollectionProps<T> = {
  items: readonly T[];
  getKey: (item: T, index: number) => Key;
  renderDesktop: (items: readonly T[]) => ReactNode;
  renderMobile: (item: T, index: number) => ReactNode;
  renderCompact?: (item: T, index: number) => ReactNode;
  className?: string;
};

export default function ResponsiveCollection<T>({ items, getKey, renderDesktop, renderCompact, renderMobile, className }: ResponsiveCollectionProps<T>) {
  const compactRenderer = renderCompact ?? renderMobile;
  return (
    <div className={['responsive-collection', className].filter(Boolean).join(' ')}>
      <div className="responsive-collection__desktop">{renderDesktop(items)}</div>
      <div className="responsive-collection__compact">{items.map((item, index) => <div key={getKey(item, index)}>{compactRenderer(item, index)}</div>)}</div>
      <div className="responsive-collection__mobile">{items.map((item, index) => <div key={getKey(item, index)}>{renderMobile(item, index)}</div>)}</div>
    </div>
  );
}
