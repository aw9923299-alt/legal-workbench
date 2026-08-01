import { Badge, Button, Card, Checkbox, Collapse, Flex, Progress, Space, Tag, Typography } from 'antd';
import { CheckOutlined, CloseOutlined, LinkOutlined, PlusOutlined, QuestionCircleOutlined } from '@ant-design/icons';
import { useState } from 'react';
import { inboxItems } from '../data/mock';
import type { InboxItem } from '../types/domain';
import { PriorityTag, RiskTag } from '../components/StatusTags';

const { Title, Text, Paragraph } = Typography;

export default function InboxPage() {
  const [selected, setSelected] = useState<string[]>([]);
  const toggle = (id: string) => setSelected((current) => current.includes(id) ? current.filter((item) => item !== id) : [...current, id]);

  return (
    <div className="page">
      <div className="page-title-row">
        <div><span className="eyebrow">HUMAN-IN-THE-LOOP</span><Title level={2}>AI 收件箱</Title><Text type="secondary">低置信度与边界不明确消息不会自动创建正式任务。</Text></div>
        <Space><Button disabled={!selected.length}>批量关联</Button><Button disabled={!selected.length}>批量忽略</Button><Button type="primary" disabled={!selected.length}>确认所选</Button></Space>
      </div>
      <div className="inbox-layout">
        <aside className="filter-rail">
          <strong>判断队列</strong>
          {['全部待确认', '明确任务', '可能是工作', '仅供知悉', '信息不足', '已处理'].map((item, index) => <button key={item} className={index === 0 ? 'active' : ''}>{item}<Badge count={index === 0 ? 6 : index === 1 ? 2 : 0} /></button>)}
          <strong>置信度</strong>
          <button>低于 70%</button><button>70%–90%</button><button>高于 90%</button>
        </aside>
        <main className="inbox-stream">
          <div className="batch-bar"><Checkbox checked={selected.length === inboxItems.length} onChange={() => setSelected(selected.length === inboxItems.length ? [] : inboxItems.map((item) => item.id))}>选择本页</Checkbox><span>共 {inboxItems.length} 条待确认</span></div>
          {inboxItems.map((item) => <InboxCard key={item.id} item={item} checked={selected.includes(item.id)} onToggle={() => toggle(item.id)} />)}
        </main>
      </div>
    </div>
  );
}

function InboxCard({ item, checked, onToggle }: { item: InboxItem; checked: boolean; onToggle: () => void }) {
  return (
    <Card className="inbox-card" bordered={false}>
      <div className="inbox-card-grid">
        <Checkbox checked={checked} onChange={onToggle} />
        <div className="inbox-card-main">
          <div className="inbox-card-head"><Tag color={item.aiDecision === '明确交给我的任务' ? 'blue' : item.aiDecision === '可能属于我的工作' ? 'gold' : 'default'}>{item.aiDecision}</Tag><span>{item.speaker.name} · {item.chatName} · {item.sentAt}</span></div>
          <Title level={5}>{item.summary}</Title>
          <Collapse ghost size="small" items={[{ key: 'context', label: '查看相关上下文', children: item.context.map((line) => <Paragraph key={line}>{line}</Paragraph>) }]} />
          <Flex wrap gap={8}><PriorityTag value={item.suggestedPriority} /><RiskTag value={item.suggestedRisk} /><Tag>{item.suggestedType}</Tag>{item.relatedTaskId && <Tag icon={<LinkOutlined />}>关联 {item.relatedTaskId}</Tag>}</Flex>
          <div className="rationale-box"><strong>AI 判断依据</strong>{item.rationale.map((reason) => <span key={reason}>· {reason}</span>)}</div>
        </div>
        <div className="confidence-panel"><Text type="secondary">置信度</Text><Progress type="circle" percent={Math.round(item.confidence * 100)} size={62} strokeWidth={8} /><Text type="secondary">建议人工复核</Text></div>
      </div>
      <div className="inbox-card-actions">
        <Button icon={<PlusOutlined />} type="primary">创建任务</Button>
        <Button icon={<LinkOutlined />}>关联已有任务</Button>
        <Button icon={<CheckOutlined />}>仅记录为信息</Button>
        <Button icon={<QuestionCircleOutlined />}>修改提取结果</Button>
        <Button icon={<CloseOutlined />} danger type="text">忽略</Button>
      </div>
    </Card>
  );
}
