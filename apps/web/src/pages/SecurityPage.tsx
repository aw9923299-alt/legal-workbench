import { Card, Tag, Typography } from 'antd';
import DataBoundaryBanner from '../components/DataBoundaryBanner';
import PageHeader from '../components/PageHeader';

const { Paragraph, Text, Title } = Typography;

const codedBoundaries = [
  {
    title: '对外沟通审核门禁',
    evidence: '界面与 API 契约',
    statement: '进入外发队列不等于已发送',
    detail: '界面仅允许已批准审核包请求入队，并继续显示排队状态；真实发送结果需由后端通信记录确认。',
  },
  {
    title: 'Agent 与人工决定分离',
    evidence: '界面语义',
    statement: 'Agent 运行完成不等于法律结论已确认',
    detail: '技术运行状态与审核决定分别展示，Agent 输出只作为待人工核对的结构化材料。',
  },
  {
    title: '接口失败显式呈现',
    evidence: '页面状态',
    statement: '失败不会静默替换为演示结果',
    detail: '接入接口的页面分别呈现加载、空、失败与重试；演示数据页面使用独立来源标识。',
  },
  {
    title: '人工作出的值保持优先',
    evidence: '表单门禁',
    statement: '人工修改不会被后续分析静默覆盖',
    detail: '待确认消息在编辑期间保留人工输入；需要重新分析时冻结确认动作并展示当前依据。',
  },
];

const backendGaps = [
  { title: '连接与授权范围', detail: '需要受控状态接口返回当前身份、授权对象、排除范围与查询时间。' },
  { title: '同步与队列健康度', detail: '需要后端提供最近成功时间、失败原因、积压量与可追溯的 correlation ID。' },
  { title: '审计事件查询', detail: '需要只读审计接口、分页与权限过滤；本页不生成示例事件冒充真实日志。' },
  { title: '留存和删除策略', detail: '需要配置来源、实际生效值、变更记录与操作权限，不能只由前端开关表示。' },
];

export default function SecurityPage() {
  return (
    <div className="page data-boundaries-page">
      <PageHeader
        eyebrow="系统与审计"
        title="数据边界"
        description="区分已经落实的产品约束、尚未接入的运行状态，以及需要后端提供的可验证证据。"
      />
      <DataBoundaryBanner
        className="data-boundary-banner--mobile-detail"
        variant="pending"
        title="未接入运行状态接口"
        description="当前连接、授权范围、同步健康度和审计事件数量均不可从本页面验证。"
      />

      <section className="boundary-section" aria-labelledby="coded-boundaries-title">
        <div className="boundary-section-heading">
          <Title id="coded-boundaries-title" level={3}>已在界面与代码中落实的边界</Title>
          <Text type="secondary">以下是可从当前仓库行为核对的产品约束，不代表生产环境健康度。</Text>
        </div>
        <div className="boundary-capability-grid">
          {codedBoundaries.map((item) => (
            <Card className="boundary-capability-card" variant="borderless" key={item.title}>
              <div className="boundary-card-heading">
                <Title level={4}>{item.title}</Title>
                <Tag color="blue">{item.evidence}</Tag>
              </div>
              <Text strong>{item.statement}</Text>
              <Paragraph>{item.detail}</Paragraph>
            </Card>
          ))}
        </div>
      </section>

      <section className="boundary-section boundary-gap-section" aria-labelledby="backend-gaps-title">
        <div className="boundary-section-heading">
          <Title id="backend-gaps-title" level={3}>尚需后端支持</Title>
          <Text type="secondary">接入前保持只读说明，不展示数量、健康度或成功记录。</Text>
        </div>
        <div className="boundary-gap-list">
          {backendGaps.map((item) => (
            <article className="boundary-gap-row" key={item.title}>
              <div><Text strong>{item.title}</Text><Paragraph>{item.detail}</Paragraph></div>
              <Tag color="gold">待接入</Tag>
            </article>
          ))}
        </div>
      </section>
    </div>
  );
}
