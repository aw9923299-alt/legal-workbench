import { Alert, List, Typography } from 'antd';
import type { MessageJudgementResult } from '../types/api';

const { Text } = Typography;

export function EvidencePanels({ result }: { result: MessageJudgementResult }) {
  return <div className="evidence-panels">
    <section className="evidence-panel confirmed-facts" aria-label="已确认事实">
      <strong>已确认事实（来自原文）</strong>
      <List
        size="small"
        dataSource={result.confirmedFacts}
        locale={{ emptyText: '无' }}
        renderItem={(fact) => {
          const citation = fact.attachmentCitation;
          const source = citation
            ? `${citation.fileName} · ${citation.pageNumber ? `第${citation.pageNumber}页` : '无页码'} · 第${citation.paragraphNumber}段`
            : `消息 ${fact.sourceMessageId}`;
          return <List.Item>
            <Text>{fact.statement}</Text>
            {citation
              ? <Typography.Link href={`#attachment-${citation.attachmentId}`}>来源 {source}</Typography.Link>
              : <Text type="secondary">来源 {source}</Text>}
          </List.Item>;
        }}
      />
    </section>
    <section className="evidence-panel inferred-facts" aria-label="AI推断">
      <strong>AI 推断（未经人工确认）</strong>
      <List size="small" dataSource={result.inferredFacts} locale={{ emptyText: '无' }} renderItem={(fact) => <List.Item><Text>{fact.statement}</Text><Text type="warning">{fact.basis} · {Math.round(fact.confidence * 100)}%</Text></List.Item>} />
    </section>
    {result.missingInformation.length > 0 && <Alert type="warning" showIcon message="缺失信息" description={result.missingInformation.join('；')} />}
  </div>;
}
