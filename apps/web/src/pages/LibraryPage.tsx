import { Button, Card, List, Tag, Typography } from 'antd';
import { ArrowRightOutlined, SettingOutlined } from '@ant-design/icons';
import DataBoundaryBanner from '../components/DataBoundaryBanner';
import PageHeader from '../components/PageHeader';

const { Text } = Typography;
const categories = [
  { name: '合同审核', category: 'contract', summary: '12 个默认字段 · 6 项风险检查 · 1 个工作日', },
  { name: '主播签约', category: 'employment', summary: '16 个默认字段 · 9 项风险检查 · 4 小时', },
  { name: '广告合规', category: 'copy_review', summary: '11 个默认字段 · 14 项风险检查 · 4 小时', },
  { name: '知识产权', category: 'intellectual_property', summary: '15 个默认字段 · 12 项风险检查 · 1 个工作日', },
  { name: '劳动用工', category: 'employment', summary: '18 个默认字段 · 10 项风险检查 · 1 个工作日', },
  { name: '用户投诉', category: 'dispute', summary: '10 个默认字段 · 7 项风险检查 · 8 小时', },
  { name: '平台处罚', category: 'platform_rules', summary: '13 个默认字段 · 9 项风险检查 · 2 小时', },
  { name: '诉讼仲裁', category: 'dispute', summary: '24 个默认字段 · 18 项风险检查 · 节点制 SLA', },
];

export default function LibraryPage({ onBrowseCategory }: { onBrowseCategory: (category: string) => void }) {
  return (
    <div className="page library-page">
      <PageHeader
        eyebrow="安全演示数据"
        title="事项模板（演示）"
        description="目录仅展示可复核的分类入口；模板新建与配置尚未接入后端。"
        primaryAction={<Button type="primary" disabled>新建事项类型（后端未接入）</Button>}
      />
      <DataBoundaryBanner
        variant="demo"
        title="安全演示数据"
        description="查看事项会打开真实事项中心并保留分类参数；不表示已有模板配置、Agent 调用或 SLA 自动执行能力。"
      />
      <Card className="template-directory" variant="borderless">
        <List
          dataSource={categories}
          renderItem={(template) => (
            <List.Item
              actions={[
                <Button key="configure" type="text" size="small" icon={<SettingOutlined />} disabled>
                  配置{template.name}模板（后端未接入）
                </Button>,
                <Button key="browse" type="link" icon={<ArrowRightOutlined />} onClick={() => onBrowseCategory(template.category)}>
                  查看{template.name}事项
                </Button>,
              ]}
            >
              <List.Item.Meta
                title={<span className="template-title">{template.name}</span>}
                description={<><Text type="secondary">{template.summary}</Text><Tag>演示目录</Tag></>}
              />
            </List.Item>
          )}
        />
      </Card>
    </div>
  );
}
