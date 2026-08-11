from __future__ import annotations

from pathlib import Path

PATH = Path("apps/web/src/pages/MessageDetailPage.tsx")


def replace_once(old: str, new: str) -> None:
    text = PATH.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"expected one replacement, found {count}: {old[:120]!r}")
    PATH.write_text(text.replace(old, new, 1), encoding="utf-8")


replace_once(
    """interface HumanForm {\n  title: string;\n  category: MatterCategory;\n  priority: Priority;\n  deadline?: { toISOString(): string };\n  ownerId: string;\n  nextAction: string;\n}\n\nexport default function MessageDetailPage() {\n""",
    """interface HumanForm {\n  title: string;\n  category: MatterCategory;\n  priority: Priority;\n  deadline?: { toISOString(): string };\n  ownerId: string;\n  nextAction: string;\n}\n\ninterface RelatedMatterProposal {\n  matterId: string;\n  matterNumber: string;\n  title: string;\n  confidence: number;\n  signals: string[];\n  evidenceRefs: string[];\n}\n\nconst continuitySignalLabels: Record<string, string> = {\n  reply_to_communication: '回复自已发送沟通',\n  same_thread_confirmed_link: '同一会话已有人工关联',\n};\n\nfunction relatedMatterProposals(values: Array<Record<string, unknown>> | undefined): RelatedMatterProposal[] {\n  if (!values) return [];\n  return values.flatMap((value) => {\n    const matterId = typeof value.matterId === 'string' ? value.matterId : '';\n    const matterNumber = typeof value.matterNumber === 'string' ? value.matterNumber : '';\n    const title = typeof value.title === 'string' ? value.title : '';\n    const confidence = typeof value.confidence === 'number' ? value.confidence : 0;\n    if (!matterId || !matterNumber || !title) return [];\n    return [{\n      matterId,\n      matterNumber,\n      title,\n      confidence,\n      signals: Array.isArray(value.signals) ? value.signals.filter((item): item is string => typeof item === 'string') : [],\n      evidenceRefs: Array.isArray(value.evidenceRefs) ? value.evidenceRefs.filter((item): item is string => typeof item === 'string') : [],\n    }];\n  });\n}\n\nexport default function MessageDetailPage() {\n""",
)

replace_once(
    """  const openCreate = () => {\n    const result = analysis.data?.analysisResult;\n    const proposedCategory = result?.categoryCandidates[0]?.category;\n    form.setFieldsValue({\n      title: candidate.data?.titleProposal ?? result?.suggestedTitle ?? '待确认法务事项',\n      category: (proposedCategory === 'general' ? 'general_consultation' : proposedCategory) ?? 'general_consultation',\n      priority: 'medium', ownerId: 'local-legal-user', nextAction: '核实事实、材料和完成时间',\n    });\n    setCreateOpen(true);\n  };\n\n  const result = analysis.data?.analysisResult as MessageJudgementResult | null | undefined;\n""",
    """  const openCreate = () => {\n    const result = analysis.data?.analysisResult;\n    const proposedCategory = result?.categoryCandidates[0]?.category;\n    form.setFieldsValue({\n      title: candidate.data?.titleProposal ?? result?.suggestedTitle ?? '待确认法务事项',\n      category: (proposedCategory === 'general' ? 'general_consultation' : proposedCategory) ?? 'general_consultation',\n      priority: 'medium', ownerId: 'local-legal-user', nextAction: '核实事实、材料和完成时间',\n    });\n    setCreateOpen(true);\n  };\n\n  const continuityProposals = relatedMatterProposals(candidate.data?.relatedMatterProposals);\n  const openLinkAction = (action: 'link_existing' | 'update_existing') => {\n    setMatterId(continuityProposals[0]?.matterId);\n    setLinkAction(action);\n  };\n  const recommendedMatterIds = new Set(continuityProposals.map((value) => value.matterId));\n  const matterOptions = [\n    ...continuityProposals.map((value) => ({\n      value: value.matterId,\n      label: `${value.matterNumber} · ${value.title}`,\n    })),\n    ...(matters.data ?? [])\n      .filter((value) => !recommendedMatterIds.has(value.id))\n      .map((value) => ({ value: value.id, label: `${value.matterNumber} · ${value.title}` })),\n  ];\n\n  const result = analysis.data?.analysisResult as MessageJudgementResult | null | undefined;\n""",
)

replace_once(
    """            </> : <Alert type={analysis.data?.failureCode ? 'error' : 'info'} message={analysis.data?.failureCode ?? '尚未生成 AgentRun'} description={analysis.data?.failureMessage} />}\n            <Divider>法务人工动作</Divider>\n""",
    """            </> : <Alert type={analysis.data?.failureCode ? 'error' : 'info'} message={analysis.data?.failureCode ?? '尚未生成 AgentRun'} description={analysis.data?.failureMessage} />}\n            {continuityProposals.length > 0 && <>\n              <Divider>可能关联事项</Divider>\n              <Alert\n                type=\"info\"\n                showIcon\n                message=\"以下建议只来自已发送沟通或同一会话的人工确认关系，系统不会自动关联 Matter。\"\n                style={{ marginBottom: 12 }}\n              />\n              <List\n                size=\"small\"\n                dataSource={continuityProposals}\n                renderItem={(proposal) => <List.Item>\n                  <Space direction=\"vertical\" size={4} style={{ width: '100%' }}>\n                    <Text strong>{proposal.matterNumber} · {proposal.title}</Text>\n                    <Space wrap>\n                      <Tag color=\"blue\">确定性置信度 {Math.round(proposal.confidence * 100)}%</Tag>\n                      {proposal.signals.map((signal) => <Tag key={signal}>{continuitySignalLabels[signal] ?? signal}</Tag>)}\n                    </Space>\n                  </Space>\n                </List.Item>}\n              />\n            </>}\n            <Divider>法务人工动作</Divider>\n""",
)

replace_once(
    """                <Button type=\"primary\" onClick={openCreate}>创建新 Matter</Button>\n                <Button icon={<LinkOutlined />} onClick={() => setLinkAction('link_existing')}>关联已有 Matter</Button>\n                <Button onClick={() => setLinkAction('update_existing')}>更新已有 Matter</Button>\n""",
    """                <Button type=\"primary\" onClick={openCreate}>创建新 Matter</Button>\n                <Button icon={<LinkOutlined />} onClick={() => openLinkAction('link_existing')}>关联已有 Matter</Button>\n                <Button onClick={() => openLinkAction('update_existing')}>更新已有 Matter</Button>\n""",
)

replace_once(
    """      <Select showSearch style={{ width: '100%', marginTop: 16 }} placeholder=\"选择 Matter\" value={matterId} onChange={setMatterId} loading={matters.isLoading} options={matters.data?.map((matter) => ({ value: matter.id, label: `${matter.matterNumber} · ${matter.title}` }))} />\n""",
    """      <Select showSearch style={{ width: '100%', marginTop: 16 }} placeholder=\"选择 Matter\" value={matterId} onChange={setMatterId} loading={matters.isLoading} options={matterOptions} />\n""",
)
