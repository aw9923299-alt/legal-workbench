import { Alert, Button, Card, Empty, Input, Space, Spin, Table, Tag, Typography } from 'antd';
import { ReloadOutlined, SearchOutlined } from '@ant-design/icons';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { legalApi } from '../services/api';
import { categoryLabels, riskLabels } from '../services/apiLabels';
import type { LegalMatter } from '../types/api';

const { Title, Text } = Typography;

export default function TaskCenterPage({ onOpenMatter }: { onOpenMatter: (matterId: string) => void }) {
  const [items, setItems] = useState<LegalMatter[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string>();
  const [keyword, setKeyword] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    setError(undefined);
    try {
      setItems(await legalApi.listMatters());
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '加载事项失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const filtered = useMemo(() => {
    const normalized = keyword.trim().toLowerCase();
    if (!normalized) return items;
    return items.filter((item) => `${item.matterNumber} ${item.title} ${item.ownerId}`.toLowerCase().includes(normalized));
  }, [items, keyword]);

  return (
    <div className="page">
      <div className="page-title-row">
        <div>
          <span className="eyebrow">LEGAL MATTERS</span>
          <Title level={2}>法务事项中心</Title>
          <Text type="secondary">事项承载完整法律问题，具体行动由WorkItem跟踪。</Text>
        </div>
        <Button icon={<ReloadOutlined />} onClick={() => void load()}>刷新</Button>
      </div>
      {error && <Alert type="error" showIcon message={error} />}
      <Card bordered={false} className="task-center-card">
        <Space style={{ marginBottom: 16 }}>
          <Input
            value={keyword}
            onChange={(event) => setKeyword(event.target.value)}
            prefix={<SearchOutlined />}
            placeholder="搜索事项编号、标题或负责人"
            style={{ width: 360 }}
          />
          <Text type="secondary">共 {filtered.length} 项</Text>
        </Space>
        <Spin spinning={loading}>
          {!loading && filtered.length === 0 ? <Empty description="暂无事项" /> : (
            <Table
              rowKey="id"
              dataSource={filtered}
              pagination={{ pageSize: 12 }}
              onRow={(record) => ({ onClick: () => onOpenMatter(record.id), style: { cursor: 'pointer' } })}
              columns={[
                { title: '编号', dataIndex: 'matterNumber', width: 170 },
                { title: '事项', dataIndex: 'title', ellipsis: true },
                { title: '分类', dataIndex: 'primaryCategory', render: (value: string) => categoryLabels[value] ?? value },
                { title: '风险', dataIndex: 'legalRisk', render: (value: string) => <Tag color={value === 'critical' ? 'red' : value === 'high' ? 'volcano' : 'gold'}>{riskLabels[value] ?? value}</Tag> },
                { title: '工作状态', dataIndex: 'workStatus', render: (value: string) => <Tag>{value}</Tag> },
                { title: '负责人', dataIndex: 'ownerId' },
                { title: '打开', render: (_: unknown, record: LegalMatter) => <Button type="link" onClick={(event) => { event.stopPropagation(); onOpenMatter(record.id); }}>查看</Button> },
              ]}
            />
          )}
        </Spin>
      </Card>
    </div>
  );
}
