import { Button, Card, Col, Row, Tag, Typography } from 'antd';
import { ArrowRightOutlined, SettingOutlined } from '@ant-design/icons';

const { Title, Text } = Typography;
const categories = [
  ['合同审核','12 个默认字段','6 项风险检查','SLA 1 个工作日'],['主播签约','16 个默认字段','9 项风险检查','SLA 4 小时'],['广告合规','11 个默认字段','14 项风险检查','SLA 4 小时'],['知识产权','15 个默认字段','12 项风险检查','SLA 1 个工作日'],['劳动用工','18 个默认字段','10 项风险检查','SLA 1 个工作日'],['用户投诉','10 个默认字段','7 项风险检查','SLA 8 小时'],['平台处罚','13 个默认字段','9 项风险检查','SLA 2 小时'],['诉讼仲裁','24 个默认字段','18 项风险检查','节点制 SLA'],
];
export default function LibraryPage() { return <div className="page"><div className="page-title-row"><div><span className="eyebrow">LEGAL PLAYBOOK</span><Title level={2}>法务事项库</Title><Text type="secondary">把字段、流程、风险检查、材料清单、SLA 和 Agent 调用固化为专业模板。</Text></div><Button type="primary">新建事项类型</Button></div><Row gutter={[16,16]}>{categories.map(([name,...meta]) => <Col xs={24} md={12} xl={6} key={name}><Card className="library-card" bordered={false}><div className="library-icon">法</div><Title level={4}>{name}</Title>{meta.map((item) => <Text key={item} type="secondary">{item}</Text>)}<div><Tag>标准流程</Tag><Tag>可配置</Tag></div><Button type="link" icon={<SettingOutlined />}>配置模板</Button><Button type="link" icon={<ArrowRightOutlined />}>查看事项</Button></Card></Col>)}</Row></div>; }
