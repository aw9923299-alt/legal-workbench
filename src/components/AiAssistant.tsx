import { Avatar, Button, Input, List, Typography } from 'antd';
import { RobotOutlined, SendOutlined } from '@ant-design/icons';
import { useState } from 'react';

const suggestions = [
  '优先处理主播解约事项：16:00 前需形成风险口径。',
  '广告合规任务仍缺 3 项材料，建议 13:30 自动催办。',
  '用户抽奖投诉已逾期 22 小时，建议升级至运营负责人。',
];

export default function AiAssistant() {
  const [query, setQuery] = useState('');
  return (
    <aside className="assistant-panel">
      <div className="panel-heading">
        <div><span className="eyebrow">AI LEGAL CONCIERGE</span><h3><RobotOutlined /> 管家今日建议</h3></div>
        <span className="assistant-status">在线</span>
      </div>
      <List
        className="assistant-list"
        dataSource={suggestions}
        renderItem={(item, index) => (
          <List.Item>
            <Avatar size={24}>{index + 1}</Avatar>
            <span>{item}</span>
          </List.Item>
        )}
      />
      <div className="assistant-evidence">
        <Typography.Text strong>回答依据</Typography.Text>
        <Typography.Paragraph>综合 5 个任务、12 条飞书消息与 4 个截止节点。所有建议需人工确认。</Typography.Paragraph>
      </div>
      <Input.TextArea
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        placeholder="例如：哪些任务超过三天没有进展？"
        autoSize={{ minRows: 2, maxRows: 4 }}
      />
      <Button type="primary" block icon={<SendOutlined />} disabled={!query.trim()}>询问 AI 管家</Button>
    </aside>
  );
}
