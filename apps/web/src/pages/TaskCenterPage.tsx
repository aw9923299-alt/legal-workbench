import { Button, Card, Input, Pagination, Select, Table, Tag, Typography } from 'antd';
import { CloseOutlined, ReloadOutlined, SearchOutlined } from '@ant-design/icons';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import ResponsiveCollection from '../components/ResponsiveCollection';
import StatePanel from '../components/StatePanel';
import { RiskTag, type LegalRiskLabel as DisplayLegalRisk } from '../components/StatusTags';
import { navigate } from '../navigation';
import { legalApi } from '../services/api';
import { classifyApiFailure, type ApiFailureState } from '../services/apiFailure';
import { categoryLabels, matterWorkStatusLabels, riskLabels } from '../services/apiLabels';
import type { LegalMatter, LegalRisk, MatterCategory } from '../types/api';

const { Title, Text } = Typography;

type FilterKey = 'q' | 'category' | 'risk' | 'status' | 'owner';
type MatterSort = 'opened_desc' | 'opened_asc' | 'risk_desc' | 'title_asc';

const riskOptions: LegalRisk[] = ['critical', 'high', 'medium', 'low', 'pending'];
const statusOptions: LegalMatter['workStatus'][] = ['ready', 'in_progress', 'waiting', 'blocked', 'done'];
const matterPageSize = 12;
const matterSortOptions: Array<{ value: MatterSort; label: string }> = [
  { value: 'opened_desc', label: '最近开启' },
  { value: 'opened_asc', label: '最早开启' },
  { value: 'risk_desc', label: '风险从高到低' },
  { value: 'title_asc', label: '标题 A–Z' },
];
const riskRank: Record<LegalRisk, number> = { critical: 5, high: 4, medium: 3, low: 2, pending: 1 };

function matterRiskTag(risk: LegalRisk) {
  return <RiskTag value={riskLabels[risk] as DisplayLegalRisk} />;
}

function matterTitleButton(matter: LegalMatter, onOpenMatter: (matterId: string) => void) {
  return (
    <button
      type="button"
      className="matter-title-button"
      aria-label={`打开事项：${matter.title}`}
      onClick={() => onOpenMatter(matter.id)}
    >
      {matter.title}
    </button>
  );
}

function MatterCompactRecord({ matter, onOpenMatter }: { matter: LegalMatter; onOpenMatter: (matterId: string) => void }) {
  return (
    <article className="matter-compact-record" aria-label={`事项：${matter.title}`}>
      <div className="matter-record-identity">
        <span>{matter.matterNumber}</span>
        {matterTitleButton(matter, onOpenMatter)}
      </div>
      <div className="matter-record-tags">
        {matterRiskTag(matter.legalRisk)}
        <Tag>{matterWorkStatusLabels[matter.workStatus] ?? matter.workStatus}</Tag>
      </div>
      <dl>
        <div><dt>分类</dt><dd>{categoryLabels[matter.primaryCategory] ?? matter.primaryCategory}</dd></div>
        <div><dt>负责人</dt><dd>{matter.ownerId}</dd></div>
        <div><dt>开启时间</dt><dd>{new Date(matter.openedAt).toLocaleDateString()}</dd></div>
      </dl>
    </article>
  );
}

function MatterCard({ matter, onOpenMatter }: { matter: LegalMatter; onOpenMatter: (matterId: string) => void }) {
  return (
    <article className="matter-card" aria-label={`事项：${matter.title}`}>
      <div className="matter-record-identity">
        <span>{matter.matterNumber}</span>
        {matterTitleButton(matter, onOpenMatter)}
      </div>
      <div className="matter-record-tags">
        {matterRiskTag(matter.legalRisk)}
        <Tag>{matterWorkStatusLabels[matter.workStatus] ?? matter.workStatus}</Tag>
      </div>
      <dl>
        <div><dt>分类</dt><dd>{categoryLabels[matter.primaryCategory] ?? matter.primaryCategory}</dd></div>
        <div><dt>负责人</dt><dd>{matter.ownerId}</dd></div>
        <div><dt>开启时间</dt><dd>{new Date(matter.openedAt).toLocaleDateString()}</dd></div>
      </dl>
    </article>
  );
}

export default function TaskCenterPage({
  keyword,
  onKeywordChange,
  onOpenMatter,
}: {
  keyword: string;
  onKeywordChange: (keyword: string) => void;
  onOpenMatter: (matterId: string) => void;
}) {
  const [items, setItems] = useState<LegalMatter[]>([]);
  const [loading, setLoading] = useState(true);
  const [failure, setFailure] = useState<ApiFailureState>();
  const restoredScroll = useRef(false);
  const query = new URLSearchParams(window.location.search);
  const category = query.get('category') ?? '';
  const risk = query.get('risk') ?? '';
  const status = query.get('status') ?? '';
  const owner = query.get('owner') ?? '';
  const requestedSort = query.get('sort');
  const sort: MatterSort = matterSortOptions.some((option) => option.value === requestedSort)
    ? requestedSort as MatterSort
    : 'opened_desc';
  const requestedPage = Number.parseInt(query.get('page') ?? '1', 10);
  const page = Number.isFinite(requestedPage) && requestedPage > 0 ? requestedPage : 1;

  const load = useCallback(async () => {
    setLoading(true);
    setFailure(undefined);
    try {
      setItems(await legalApi.listMatters());
    } catch (reason) {
      setItems([]);
      setFailure(classifyApiFailure(reason, '法务事项', '法务事项加载失败', '加载事项失败'));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const owners = useMemo(
    () => [...new Set(items.map((item) => item.ownerId))].sort((left, right) => left.localeCompare(right)),
    [items],
  );

  const filtered = useMemo(() => {
    const normalized = keyword.trim().toLocaleLowerCase();
    return items.filter((item) => {
      const searchableMatterFields = [
        item.matterNumber,
        item.title,
        item.ownerId,
      ].join(' ').toLocaleLowerCase();
      const matchesKeyword = !normalized || searchableMatterFields.includes(normalized);
      const matchesCategory = !category
        || item.primaryCategory === category
        || item.secondaryCategories.includes(category as MatterCategory);
      return matchesKeyword
        && matchesCategory
        && (!risk || item.legalRisk === risk)
        && (!status || item.workStatus === status)
        && (!owner || item.ownerId === owner);
    });
  }, [items, keyword, category, risk, status, owner]);

  const sorted = useMemo(() => filtered
    .map((matter, index) => ({ matter, index }))
    .sort((left, right) => {
      let compared = 0;
      if (sort === 'opened_desc') compared = Date.parse(right.matter.openedAt) - Date.parse(left.matter.openedAt);
      if (sort === 'opened_asc') compared = Date.parse(left.matter.openedAt) - Date.parse(right.matter.openedAt);
      if (sort === 'risk_desc') compared = riskRank[right.matter.legalRisk] - riskRank[left.matter.legalRisk];
      if (sort === 'title_asc') compared = left.matter.title.localeCompare(right.matter.title, 'zh-CN');
      return compared || left.index - right.index || left.matter.id.localeCompare(right.matter.id);
    })
    .map(({ matter }) => matter), [filtered, sort]);

  const totalPages = Math.max(1, Math.ceil(sorted.length / matterPageSize));
  const currentPage = Math.min(page, totalPages);
  const paged = useMemo(
    () => sorted.slice((currentPage - 1) * matterPageSize, currentPage * matterPageSize),
    [currentPage, sorted],
  );

  const replaceQuery = (nextQuery: URLSearchParams) => {
    navigate(`/matters${nextQuery.size ? `?${nextQuery.toString()}` : ''}`, { replace: true });
  };

  const updateFilter = (key: Exclude<FilterKey, 'q'>, value?: string) => {
    const nextQuery = new URLSearchParams(window.location.search);
    if (value) nextQuery.set(key, value);
    else nextQuery.delete(key);
    nextQuery.delete('page');
    replaceQuery(nextQuery);
  };

  const updateSort = (value: MatterSort) => {
    const nextQuery = new URLSearchParams(window.location.search);
    if (value === 'opened_desc') nextQuery.delete('sort');
    else nextQuery.set('sort', value);
    nextQuery.delete('page');
    replaceQuery(nextQuery);
  };

  const updatePage = (value: number) => {
    const nextQuery = new URLSearchParams(window.location.search);
    if (value <= 1) nextQuery.delete('page');
    else nextQuery.set('page', String(value));
    replaceQuery(nextQuery);
    window.scrollTo({ top: 0, behavior: 'auto' });
  };

  const clearFilter = (key: FilterKey) => {
    if (key === 'q') {
      onKeywordChange('');
      return;
    }
    updateFilter(key);
  };

  const clearAllFilters = () => {
    const nextQuery = new URLSearchParams(window.location.search);
    for (const key of ['q', 'category', 'risk', 'status', 'owner']) nextQuery.delete(key);
    nextQuery.delete('page');
    replaceQuery(nextQuery);
  };

  useEffect(() => {
    if (loading || failure || restoredScroll.current) return;
    const restoreScrollY = (window.history.state as { restoreScrollY?: unknown } | null)?.restoreScrollY;
    if (typeof restoreScrollY !== 'number' || restoreScrollY < 0) return;
    restoredScroll.current = true;
    window.requestAnimationFrame(() => {
      window.requestAnimationFrame(() => window.scrollTo({ top: restoreScrollY, behavior: 'auto' }));
    });
  }, [failure, loading, paged.length]);

  const activeFilters = [
    keyword ? { key: 'q' as const, label: `关键词：${keyword}` } : undefined,
    category ? { key: 'category' as const, label: `分类：${categoryLabels[category] ?? category}` } : undefined,
    risk ? { key: 'risk' as const, label: `风险：${riskLabels[risk] ?? risk}风险` } : undefined,
    status ? { key: 'status' as const, label: `状态：${matterWorkStatusLabels[status] ?? status}` } : undefined,
    owner ? { key: 'owner' as const, label: `负责人：${owner}` } : undefined,
  ].filter((value): value is { key: FilterKey; label: string } => Boolean(value));

  return (
    <div className="page task-center-page">
      <div className="page-title-row">
        <div>
          <span className="eyebrow">LEGAL MATTERS</span>
          <Title level={2}>法务事项中心</Title>
          <Text type="secondary">检索已确认的法律事项，并进入详情继续处理。</Text>
        </div>
        <Button icon={<ReloadOutlined />} onClick={() => void load()}>刷新</Button>
      </div>

      <Card variant="borderless" className="task-center-card">
        <div className="matter-filter-toolbar">
          <Input
            className="matter-filter-search"
            role="searchbox"
            aria-label="搜索法务事项队列"
            value={keyword}
            allowClear
            onChange={(event) => onKeywordChange(event.target.value)}
            prefix={<SearchOutlined />}
            placeholder="搜索事项编号、标题或负责人"
          />
          <Select
            aria-label="事项分类"
            value={category || undefined}
            allowClear
            placeholder="全部分类"
            onChange={(value) => updateFilter('category', value)}
            options={Object.entries(categoryLabels).map(([value, label]) => ({ value, label }))}
          />
          <Select
            aria-label="法律风险"
            value={risk || undefined}
            allowClear
            placeholder="全部风险"
            onChange={(value) => updateFilter('risk', value)}
            options={riskOptions.map((value) => ({ value, label: `${riskLabels[value]}风险` }))}
          />
          <Select
            aria-label="工作状态"
            value={status || undefined}
            allowClear
            placeholder="全部状态"
            onChange={(value) => updateFilter('status', value)}
            options={statusOptions.map((value) => ({ value, label: matterWorkStatusLabels[value] }))}
          />
          <Select
            aria-label="负责人"
            value={owner || undefined}
            allowClear
            showSearch
            optionFilterProp="label"
            placeholder="全部负责人"
            onChange={(value) => updateFilter('owner', value)}
            options={owners.map((value) => ({ value, label: value }))}
          />
          <Select
            aria-label="事项排序"
            value={sort}
            onChange={updateSort}
            options={matterSortOptions}
          />
          <div className="matter-result-count">
            <Text type="secondary">共 {filtered.length} 项</Text>
            <Text type="secondary">当前仅在服务返回的前 100 项内排序和分页</Text>
          </div>
        </div>

        {activeFilters.length > 0 && (
          <section className="active-filter-bar" aria-label="已启用筛选">
            <span className="active-filter-bar__label">已启用</span>
            <div className="active-filter-bar__items">
              {activeFilters.map((filter) => (
                <span className="active-filter" key={filter.key}>
                  {filter.label}
                  <Button
                    type="text"
                    size="small"
                    icon={<CloseOutlined />}
                    aria-label={`清除${filter.key === 'q' ? '关键词' : filter.key === 'category' ? '分类' : filter.key === 'risk' ? '风险' : filter.key === 'status' ? '状态' : '负责人'}筛选`}
                    onClick={() => clearFilter(filter.key)}
                  />
                </span>
              ))}
            </div>
            <Button type="link" onClick={clearAllFilters}>清除全部筛选</Button>
          </section>
        )}

        <div className="matter-collection-state">
          {loading ? (
            <StatePanel variant="loading" title="正在加载法务事项" description="正在从事项服务读取已确认事项。" />
          ) : failure ? (
            <StatePanel
              variant={failure.variant}
              title={failure.title}
              description={failure.description}
              correlationId={failure.correlationId}
              action={<Button aria-label="重试" onClick={() => void load()}>重试</Button>}
            />
          ) : items.length === 0 ? (
            <StatePanel
              variant="empty"
              title="暂无法务事项"
              description="当前服务没有返回已确认事项。"
              action={<Button onClick={() => void load()}>刷新</Button>}
            />
          ) : filtered.length === 0 ? (
            <StatePanel
              variant="filtered-empty"
              title="没有符合筛选条件的事项"
              description="调整关键词或筛选条件后再试。"
              action={<Button onClick={clearAllFilters}>清除全部筛选</Button>}
            />
          ) : (
            <>
              <ResponsiveCollection
                className="matters-collection"
                items={paged}
                getKey={(matter) => matter.id}
                renderDesktop={(desktopItems) => (
                  <Table
                    rowKey="id"
                    dataSource={[...desktopItems]}
                    pagination={false}
                    columns={[
                      { title: '编号', dataIndex: 'matterNumber', width: 170 },
                      { title: '事项', dataIndex: 'title', ellipsis: true, render: (_: string, matter: LegalMatter) => matterTitleButton(matter, onOpenMatter) },
                      { title: '分类', dataIndex: 'primaryCategory', render: (value: string) => categoryLabels[value] ?? value },
                      { title: '风险', dataIndex: 'legalRisk', render: (value: LegalRisk) => matterRiskTag(value) },
                      { title: '工作状态', dataIndex: 'workStatus', render: (value: string) => <Tag>{matterWorkStatusLabels[value] ?? value}</Tag> },
                      { title: '负责人', dataIndex: 'ownerId' },
                    ]}
                  />
                )}
                renderCompact={(matter) => <MatterCompactRecord matter={matter} onOpenMatter={onOpenMatter} />}
                renderMobile={(matter) => <MatterCard matter={matter} onOpenMatter={onOpenMatter} />}
              />
              {filtered.length > matterPageSize && (
                <Pagination
                  className="matter-pagination"
                  aria-label="事项分页"
                  current={currentPage}
                  pageSize={matterPageSize}
                  total={filtered.length}
                  showSizeChanger={false}
                  onChange={updatePage}
                />
              )}
            </>
          )}
        </div>
      </Card>
    </div>
  );
}
