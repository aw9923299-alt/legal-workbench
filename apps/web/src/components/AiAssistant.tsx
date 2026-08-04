import { Avatar, List, Typography } from 'antd';
import { RobotOutlined } from '@ant-design/icons';
import { SemanticStatusTag } from './StatusTags';

const suggestions = [
  '优先处理主播解约事项：16:00 前需形成风险口径。',
  '广告合规任务仍缺 3 项材料，建议 13:30 自动催办。',
  '用户抽奖投诉已逾期 22 小时，建议升级至运营负责人。',
];

export default function AiAssistant() {
  return (
    <aside className="assistant-panel">
      <div className="panel-heading">
        <div><span className="eyebrow">演示建议</span><h3><RobotOutlined /> AI 建议（演示）</h3></div>
        <SemanticStatusTag kind="ai">AI 建议 · 需人工核对</SemanticStatusTag>
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
        <Typography.Text strong>依据范围</Typography.Text>
        <Typography.Paragraph>仅基于本地演示任务、待确认消息和期限样例；不代表已执行知识检索或实时系统分析。</Typography.Paragraph>
      </div>
    </aside>
  );
}
