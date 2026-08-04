import { expect, test, type Page, type Route } from '@playwright/test';
import type { AgentRunRecord, AgentRunStatus, MessageAnalysis, MessageCandidate, MessageJudgementResult } from '../src/types/api';

// These deterministic payloads are UI-contract fixtures only. They do not prove a live
// Feishu, Codex, authentication, attachment parsing, or confirm-create integration.
const createJudgement: MessageJudgementResult = {
  legalRelevance: 'relevant',
  messageRole: 'new_request',
  actionability: 'create_candidate',
  suggestedTitle: '品牌联名直播口播合规复核',
  categoryCandidates: [{ category: 'copy_review', confidence: 0.94, reason: '涉及直播口播绝对化表述' }],
  deadlineCandidates: [{ rawText: '今天下班前', resolvedAt: '2026-08-04T18:00:00+08:00', deadlineType: 'business', confidence: 0.82 }],
  confirmedFacts: [{ statement: '业务要求法务审查“全网最低价”表述', sourceMessageId: 'om-create' }],
  inferredFacts: [{ statement: '该表述可能构成绝对化宣传', basis: '消息正文中的价格宣传措辞', confidence: 0.78 }],
  missingInformation: ['最终口播脚本附件', '价格比较依据'],
  reasons: ['消息明确交给法务审查', '存在当日业务期限'],
  confidence: 0.93,
};

const linkJudgement: MessageJudgementResult = {
  legalRelevance: 'relevant',
  messageRole: 'supplemental_material',
  actionability: 'link_candidate',
  suggestedTitle: '音乐版权侵权通知补充材料',
  categoryCandidates: [{ category: 'intellectual_property', confidence: 0.92, reason: '涉及既有版权事项' }],
  deadlineCandidates: [],
  confirmedFacts: [{ statement: '业务说明该通知属于现有音乐版权事项', sourceMessageId: 'om-link' }],
  inferredFacts: [{ statement: '应关联现有事项而非重复新建', basis: '消息明确使用“现有事项”', confidence: 0.9 }],
  missingInformation: ['原事项编号'],
  reasons: ['消息属于既有事项的补充材料'],
  confidence: 0.91,
};

function agentRun(id: string, status: AgentRunStatus, output: MessageJudgementResult | null): AgentRunRecord {
  return {
    id,
    agentKey: 'message_judgement',
    agentVersion: '1.0.0',
    feishuMessageId: id === 'run-create' ? 'om-create' : 'om-link',
    contextSnapshotId: id === 'run-create' ? 'snapshot-create' : 'snapshot-link',
    status,
    objective: '研判授权消息是否形成法务工作',
    inputPayload: { fixture: 'ui-contract-only' },
    outputPayload: output,
    rawStdout: null,
    rawStderr: null,
    promptSnapshot: 'UI contract fixture prompt',
    workingDirectory: '/tmp/ui-contract-fixture',
    startedAt: '2026-08-04T09:01:00+08:00',
    heartbeatAt: '2026-08-04T09:01:05+08:00',
    finishedAt: status === 'completed' ? '2026-08-04T09:01:10+08:00' : null,
    timeoutAt: '2026-08-04T09:06:00+08:00',
    attemptNumber: 1,
    maxAttempts: 3,
    failureCode: null,
    failureMessage: null,
    correlationId: `corr-${id}`,
    createdBy: 'ui-contract-fixture',
    createdAt: '2026-08-04T09:00:58+08:00',
    updatedAt: '2026-08-04T09:01:10+08:00',
    version: 2,
    sources: [{
      sourceType: 'feishu_message',
      sourceId: id === 'run-create' ? 'om-create' : 'om-link',
      sourceVersion: '1',
      sourceHash: `sha256-${id}`,
      displayName: '授权飞书消息',
      citationMetadata: { fixture: 'ui-contract-only' },
    }],
  };
}

const candidates: MessageCandidate[] = [
  {
    id: 'candidate-create',
    contextSnapshotId: 'snapshot-create',
    status: 'pending_confirmation',
    legalRelevance: 'relevant',
    messageRole: 'new_request',
    recommendedAction: 'create_matter',
    confidence: 0.93,
    titleProposal: '品牌联名直播口播合规复核',
    categoryProposals: [{ category: 'copy_review', confidence: 0.94, reason: '涉及直播口播绝对化表述' }],
    deadlineProposals: [{ rawText: '今天下班前', resolvedAt: '2026-08-04T18:00:00+08:00' }],
    relatedMatterProposals: [],
    evidenceRefs: ['om-create'],
    agentRunId: 'run-create',
    feishuMessageId: 'om-create',
    requiresManualReview: true,
    analysisPayload: createJudgement,
    confirmedBy: null,
    confirmedAt: null,
    version: 3,
  },
  {
    id: 'candidate-link',
    contextSnapshotId: 'snapshot-link',
    status: 'pending_confirmation',
    legalRelevance: 'relevant',
    messageRole: 'supplemental_material',
    recommendedAction: 'link_matter',
    confidence: 0.91,
    titleProposal: '音乐版权侵权通知补充材料',
    categoryProposals: [{ category: 'intellectual_property', confidence: 0.92, reason: '涉及既有版权事项' }],
    deadlineProposals: [],
    relatedMatterProposals: [{ matterId: 'matter-existing', confidence: 0.88 }],
    evidenceRefs: ['om-link', 'att-copyright-notice'],
    agentRunId: 'run-link',
    feishuMessageId: 'om-link',
    requiresManualReview: true,
    analysisPayload: linkJudgement,
    confirmedBy: null,
    confirmedAt: null,
    version: 5,
  },
];

const analyses: Record<string, MessageAnalysis> = {
  'om-create': {
    message: {
      id: 'message-create',
      messageId: 'om-create',
      senderId: 'ou_brand_owner',
      messageType: 'text',
      content: { text: '请法务今天审查品牌联名直播口播中的“全网最低价”表述。' },
      createTime: '2026-08-04T09:00:00+08:00',
    },
    messageStatus: 'completed',
    contextSnapshot: {
      id: 'snapshot-create',
      snapshotVersion: 2,
      messageIds: ['om-create', 'om-parent'],
      attachmentIds: [],
      participantIds: ['ou_brand_owner', 'ou_legal'],
      contentHash: 'sha256-snapshot-create',
      truncated: false,
      createdAt: '2026-08-04T09:00:30+08:00',
    },
    agentRun: agentRun('run-create', 'completed', createJudgement),
    analysisResult: createJudgement,
    candidateId: 'candidate-create',
    failureCode: null,
    failureMessage: null,
    canRetry: true,
  },
  'om-link': {
    message: {
      id: 'message-link',
      messageId: 'om-link',
      senderId: 'ou_content_ops',
      messageType: 'post',
      content: { text: '补充：这是现有音乐版权事项的侵权通知，请关联原事项。' },
      createTime: '2026-08-04T09:18:00+08:00',
    },
    messageStatus: 'completed',
    contextSnapshot: {
      id: 'snapshot-link',
      snapshotVersion: 4,
      messageIds: ['om-link', 'om-copyright-parent', 'om-copyright-thread'],
      attachmentIds: ['att-copyright-notice'],
      participantIds: ['ou_content_ops', 'ou_legal', 'ou_copyright_agent'],
      contentHash: 'sha256-snapshot-link',
      truncated: true,
      createdAt: '2026-08-04T09:18:30+08:00',
    },
    agentRun: agentRun('run-link', 'completed', linkJudgement),
    analysisResult: linkJudgement,
    candidateId: 'candidate-link',
    failureCode: null,
    failureMessage: null,
    canRetry: true,
  },
};

type InboxScenario =
  | 'default'
  | 'empty'
  | 'loading'
  | 'list-error'
  | 'forbidden'
  | 'detail-error'
  | 'running'
  | 'retry-stale'
  | 'detail-race'
  | 'stale-detail-response'
  | 'confirm-success'
  | 'confirm-conflict'
  | 'confirm-error';

async function fulfillJson(route: Route, body: unknown, status = 200) {
  await route.fulfill({
    status,
    contentType: 'application/json',
    headers: { 'X-UI-Contract-Fixture': 'true' },
    body: JSON.stringify(body),
  });
}

async function installInboxContract(page: Page, scenario: InboxScenario = 'default') {
  const mutationRequests = [] as string[] & {
    confirmationPayloads: Array<Record<string, unknown>>;
    waitForCreateDetailRequest: () => Promise<void>;
    releaseCreateDetailResponse: () => void;
    waitForLinkDetailRequest: () => Promise<void>;
    releaseLinkDetailResponse: () => void;
  };
  let markCreateDetailRequested = () => undefined;
  let releaseCreateDetailResponse = () => undefined;
  const createDetailRequested = new Promise<void>((resolve) => { markCreateDetailRequested = resolve; });
  const createDetailResponseGate = new Promise<void>((resolve) => { releaseCreateDetailResponse = resolve; });
  let markLinkDetailRequested = () => undefined;
  let releaseLinkDetailResponse = () => undefined;
  const linkDetailRequested = new Promise<void>((resolve) => { markLinkDetailRequested = resolve; });
  const linkDetailResponseGate = new Promise<void>((resolve) => { releaseLinkDetailResponse = resolve; });
  Object.defineProperty(mutationRequests, 'confirmationPayloads', {
    value: [] as Array<Record<string, unknown>>,
  });
  Object.defineProperties(mutationRequests, {
    waitForCreateDetailRequest: { value: () => createDetailRequested },
    releaseCreateDetailResponse: { value: () => releaseCreateDetailResponse() },
    waitForLinkDetailRequest: { value: () => linkDetailRequested },
    releaseLinkDetailResponse: { value: () => releaseLinkDetailResponse() },
  });

  await page.route('**/api/v1/auth/session', (route) => fulfillJson(route, { actorId: 'ui-contract-reviewer' }));
  await page.route(/\/api\/v1\/inbox\/candidates\?/, async (route) => {
    if (scenario === 'loading') await new Promise((resolve) => setTimeout(resolve, 700));
    if (scenario === 'list-error') return fulfillJson(route, { detail: 'UI 合约夹具：候选列表失败' }, 500);
    if (scenario === 'forbidden') return fulfillJson(route, { detail: 'UI 合约夹具：无权查看待确认消息' }, 403);
    return fulfillJson(route, scenario === 'empty' ? [] : candidates);
  });
  await page.route(/\/api\/v1\/feishu\/messages\/([^/]+)\/analysis$/, async (route) => {
    const messageId = decodeURIComponent(new URL(route.request().url()).pathname.split('/').at(-2) ?? '');
    if (scenario === 'detail-race' && messageId === 'om-create') {
      markCreateDetailRequested();
      await createDetailResponseGate;
      return fulfillJson(route, { ...analyses[messageId], candidateId: null });
    }
    if (scenario === 'stale-detail-response' && messageId === 'om-link') {
      markLinkDetailRequested();
      await linkDetailResponseGate;
      return fulfillJson(route, analyses[messageId]);
    }
    if (scenario === 'stale-detail-response' && messageId === 'om-create') {
      return fulfillJson(route, { ...analyses[messageId], candidateId: null });
    }
    if (scenario === 'detail-error' && messageId === 'om-create') {
      return fulfillJson(route, { detail: 'UI 合约夹具：证据详情加载失败' }, 500);
    }
    if (scenario === 'running' && messageId === 'om-create') {
      const runningAnalysis: MessageAnalysis = {
        ...analyses[messageId],
        messageStatus: 'running',
        agentRun: agentRun('run-create', 'running', null),
        analysisResult: null,
        canRetry: false,
      };
      return fulfillJson(route, runningAnalysis);
    }
    return fulfillJson(route, analyses[messageId]);
  });
  await page.route(/\/api\/v1\/(?:inbox\/candidates\/[^/]+\/confirm-create|feishu\/messages\/[^/]+\/retry-analysis)$/, async (route) => {
    const requestPath = new URL(route.request().url()).pathname;
    mutationRequests.push(`${route.request().method()} ${requestPath}`);
    if (requestPath.endsWith('/confirm-create')) {
      mutationRequests.confirmationPayloads.push(route.request().postDataJSON() as Record<string, unknown>);
      if (scenario === 'confirm-success') {
        await new Promise((resolve) => setTimeout(resolve, 350));
        return fulfillJson(route, {
          matterId: 'matter-created',
          matterNumber: 'MAT-2026-0042',
          workItemIds: ['work-item-created'],
          idempotentReplay: false,
        });
      }
      if (scenario === 'confirm-conflict') {
        return fulfillJson(route, { detail: 'Candidate 版本冲突，请重新加载后核对' }, 409);
      }
      if (scenario === 'confirm-error') {
        return fulfillJson(route, { detail: 'UI 合约夹具：创建事项失败' }, 500);
      }
    }
    if (scenario === 'retry-stale' && requestPath.endsWith('/retry-analysis')) {
      return fulfillJson(route, { messageId: 'om-create', status: 'pending_analysis' }, 202);
    }
    await fulfillJson(route, { detail: 'UI contract fixture mutation endpoint must not be used' }, 409);
  });
  await page.route('**/api/v1/matters/matter-created', (route) => fulfillJson(route, {
    id: 'matter-created',
    matterNumber: 'MAT-2026-0042',
    title: '人工修订的品牌口播合规事项',
    primaryCategory: 'copy_review',
    secondaryCategories: [],
    lifecycleStatus: 'open',
    workStatus: 'ready',
    ownerId: 'ou_legal_reviewer',
    collaboratorIds: [],
    requesterIds: [],
    entityIds: [],
    legalRisk: 'high',
    businessImpact: 'project',
    confidentiality: 'internal',
    summary: '人工确认后的事项背景',
    objective: null,
    currentStage: null,
    version: 1,
    openedAt: '2026-08-04T10:00:00+08:00',
    resolvedAt: null,
    closedAt: null,
    reopenedAt: null,
  }));
  await page.route('**/api/v1/matters/matter-created/work-items', (route) => fulfillJson(route, []));

  return mutationRequests;
}

async function openInbox(page: Page) {
  await page.goto('/');
  await page.getByRole('button', { name: '处理待确认消息' }).click();
}

async function openCreateDrawer(page: Page) {
  await page.getByRole('button', { name: /建议：品牌联名直播口播合规复核/ }).click();
  await page.getByRole('button', { name: '审阅并创建事项' }).click();
  return page.getByRole('dialog', { name: '审阅并创建事项' });
}

async function fillRequiredConfirmationFields(page: Page, plannedCompleteAt: string) {
  const drawer = page.getByRole('dialog', { name: '审阅并创建事项' });
  await drawer.getByLabel('事项负责人').fill('ou_legal_reviewer');
  await drawer.getByLabel('法律风险').click();
  await page.locator('.ant-select-dropdown:visible').getByText('高', { exact: true }).click();
  await drawer.getByLabel('业务影响').click();
  await page.locator('.ant-select-dropdown:visible').getByText('项目级', { exact: true }).click();
  await drawer.getByLabel('首个任务负责人').fill('ou_legal_reviewer');
  await drawer.getByLabel('优先级').click();
  await page.locator('.ant-select-dropdown:visible').getByText('紧急', { exact: true }).click();
  await drawer.getByLabel('计划完成时间').fill(plannedCompleteAt);
  await drawer.getByLabel('下一步行动').fill('核对口播全文和价格比较依据');
}

test('dashboard action opens the two-item evidence review queue', async ({ page }) => {
  await installInboxContract(page);
  await openInbox(page);

  await expect(page.getByRole('heading', { name: '待确认消息' })).toBeVisible();
  await expect(page.getByRole('button', { name: /建议：品牌联名直播口播合规复核/ })).toBeVisible();
  await expect(page.getByRole('button', { name: /建议：音乐版权侵权通知补充材料/ })).toBeVisible();
});

test('queue selection changes source evidence, coverage, AI inference, and missing information', async ({ page }) => {
  await installInboxContract(page);
  await openInbox(page);

  await expect(page.getByText('请法务今天审查品牌联名直播口播中的“全网最低价”表述。')).toBeVisible();
  await page.getByRole('button', { name: /建议：音乐版权侵权通知补充材料/ }).click();
  await expect(page.getByText('补充：这是现有音乐版权事项的侵权通知，请关联原事项。')).toBeVisible();
  await expect(page.getByText('快照版本 4')).toBeVisible();
  await expect(page.getByText('att-copyright-notice')).toBeVisible();
  await expect(page.getByText('当前仅验证元数据，未证明附件正文已解析')).toBeVisible();
  await expect(page.getByText('应关联现有事项而非重复新建')).toBeVisible();
  await expect(page.getByText('原事项编号')).toBeVisible();
});

test('delayed detail never mixes the previous Candidate evidence into a create confirmation', async ({ page }) => {
  const contract = await installInboxContract(page, 'detail-race');
  await page.goto('/inbox/candidate-link');
  const linkSource = '补充：这是现有音乐版权事项的侵权通知，请关联原事项。';
  const createSource = '请法务今天审查品牌联名直播口播中的“全网最低价”表述。';
  await expect(page.getByText(linkSource)).toBeVisible();

  await page.evaluate(({ createTitle, staleSource }) => {
    document.body.dataset.staleCandidateDetailObserved = 'false';
    const observer = new MutationObserver(() => {
      const createHeadingVisible = [...document.querySelectorAll('h3')]
        .some((heading) => heading.textContent?.includes(createTitle));
      const staleSourceVisible = document.body.innerText.includes(staleSource);
      const createButton = [...document.querySelectorAll('button')]
        .find((button) => button.textContent?.includes('审阅并创建事项'));
      if (createHeadingVisible && staleSourceVisible && createButton && !createButton.disabled) {
        document.body.dataset.staleCandidateDetailObserved = 'true';
      }
    });
    observer.observe(document.body, { subtree: true, childList: true, characterData: true });
  }, { createTitle: '品牌联名直播口播合规复核', staleSource: linkSource });

  await page.getByRole('button', { name: /建议：品牌联名直播口播合规复核/ }).click();
  await contract.waitForCreateDetailRequest();
  try {
    await expect(page).toHaveURL(/\/inbox\/candidate-create$/);
    await expect(page.getByText(linkSource)).toHaveCount(0);
    await expect(page.getByRole('button', { name: '审阅并创建事项' })).toHaveCount(0);
    await expect.poll(() => page.locator('body').getAttribute('data-stale-candidate-detail-observed')).toBe('false');
  } finally {
    contract.releaseCreateDetailResponse();
  }

  await expect(page.getByText(createSource)).toBeVisible();
  await expect(page.getByRole('button', { name: '审阅并创建事项' })).toBeEnabled();
  await page.getByRole('button', { name: '审阅并创建事项' }).click();
  await expect(page.getByRole('dialog', { name: '审阅并创建事项' }).getByLabel('事项背景（AI 建议，可人工修改）')).toHaveValue(createSource);
});

test('late previous detail response cannot displace the current Candidate evidence', async ({ page }) => {
  const contract = await installInboxContract(page, 'stale-detail-response');
  const linkSource = '补充：这是现有音乐版权事项的侵权通知，请关联原事项。';
  const createSource = '请法务今天审查品牌联名直播口播中的“全网最低价”表述。';
  await page.goto('/inbox/candidate-link');
  await contract.waitForLinkDetailRequest();

  await page.evaluate((staleSource) => {
    document.body.dataset.lateLinkDetailObserved = 'false';
    const observer = new MutationObserver(() => {
      if (window.location.pathname === '/inbox/candidate-create' && document.body.innerText.includes(staleSource)) {
        document.body.dataset.lateLinkDetailObserved = 'true';
      }
    });
    observer.observe(document.body, { subtree: true, childList: true, characterData: true });
  }, linkSource);

  await page.getByRole('button', { name: /建议：品牌联名直播口播合规复核/ }).click();
  await expect(page).toHaveURL(/\/inbox\/candidate-create$/);
  await expect(page.getByText(createSource)).toBeVisible();
  await expect(page.getByRole('button', { name: '审阅并创建事项' })).toBeEnabled();

  const lateLinkResponse = page.waitForResponse((response) => (
    response.url().includes('/feishu/messages/om-link/analysis') && response.status() === 200
  ));
  contract.releaseLinkDetailResponse();
  await lateLinkResponse;
  await page.evaluate(() => new Promise<void>((resolve) => {
    requestAnimationFrame(() => requestAnimationFrame(() => resolve()));
  }));

  await expect(page).toHaveURL(/\/inbox\/candidate-create$/);
  await expect(page.getByText(createSource)).toBeVisible();
  await expect(page.getByText(linkSource)).toHaveCount(0);
  await expect(page.getByRole('button', { name: '审阅并创建事项' })).toBeEnabled();
  await expect(page.locator('body')).toHaveAttribute('data-late-link-detail-observed', 'false');
});

test('candidate deep link restores the selected evidence after refresh', async ({ page }) => {
  await installInboxContract(page);

  await page.goto('/inbox/candidate-link');
  await expect(page).toHaveURL(/\/inbox\/candidate-link$/);
  await expect(page.getByText('补充：这是现有音乐版权事项的侵权通知，请关联原事项。')).toBeVisible();

  await page.reload();
  await expect(page).toHaveURL(/\/inbox\/candidate-link$/);
  await expect(page.getByText('补充：这是现有音乐版权事项的侵权通知，请关联原事项。')).toBeVisible();
});

test('390 queue selection writes the candidate URL and both return controls restore the queue', async ({ page }) => {
  await installInboxContract(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/inbox');

  const createCandidate = page.getByRole('button', { name: /建议：品牌联名直播口播合规复核/ });
  await expect(createCandidate).toBeVisible();
  await createCandidate.click();
  await expect(page).toHaveURL(/\/inbox\/candidate-create$/);
  await page.getByRole('button', { name: '返回消息队列' }).click();
  await expect(page).toHaveURL(/\/inbox$/);
  await expect(createCandidate).toBeVisible();

  await page.getByRole('button', { name: /建议：音乐版权侵权通知补充材料/ }).click();
  await expect(page).toHaveURL(/\/inbox\/candidate-link$/);
  await page.goBack();
  await expect(page).toHaveURL(/\/inbox$/);
  await expect(page.getByRole('button', { name: /建议：音乐版权侵权通知补充材料/ })).toBeVisible();

  await page.setViewportSize({ width: 1024, height: 768 });
  await expect(page.getByText('请法务今天审查品牌联名直播口播中的“全网最低价”表述。')).toBeVisible();
});

test('analysis declares API provenance and a pending human decision without claiming confirmation', async ({ page }) => {
  await installInboxContract(page);
  await openInbox(page);

  const apiStatus = page.getByText('由服务接口提供 · 不代表实时同步', { exact: true });
  await expect(apiStatus).toHaveAttribute('data-status-kind', 'api');
  const humanStatus = page.getByText('待人工决定 · 尚未确认', { exact: true });
  await expect(humanStatus).toHaveAttribute('data-status-kind', 'human');
  await expect(humanStatus).toHaveAttribute('data-status-tone', 'info');
  await expect(page.getByText('人工已确认', { exact: true })).toHaveCount(0);
});

test('non-create recommendations block creation and expose only unavailable dispositions', async ({ page }) => {
  const mutations = await installInboxContract(page);
  await openInbox(page);
  await page.getByRole('button', { name: /建议：音乐版权侵权通知补充材料/ }).click();

  await expect(page.getByText('当前建议处置尚未接入，已阻止错误新建事项')).toBeVisible();
  await expect(page.getByRole('button', { name: '审阅并创建事项' })).toHaveCount(0);
  for (const action of ['关联或更新事项', '补充材料', '仅作信息', '忽略', '暂缓', '合并']) {
    await expect(page.getByRole('button', { name: action, exact: true })).toBeDisabled();
  }
  await expect(page.getByText('后端流程未接入，不会执行')).toBeVisible();
  expect(mutations).toEqual([]);
});

test('create confirmation carries missing-material context and states that dependencies are added after creation', async ({ page }) => {
  await installInboxContract(page);
  await openInbox(page);
  const drawer = await openCreateDrawer(page);

  const missingMaterials = drawer.getByRole('region', { name: '缺失材料承接' });
  await expect(missingMaterials).toContainText('最终口播脚本附件');
  await expect(missingMaterials).toContainText('价格比较依据');
  await expect(drawer.getByLabel('下一步行动')).toHaveValue('补充并核对：最终口播脚本附件、价格比较依据');
  await expect(missingMaterials).toContainText('创建事项后添加依赖');
  await expect(missingMaterials).toContainText('当前接口不会自动创建依赖');
});

test('confirmation drawer protects unsaved human edits and restores focus after discard', async ({ page }) => {
  const mutations = await installInboxContract(page);
  await openInbox(page);
  const trigger = page.getByRole('button', { name: '审阅并创建事项' });
  await trigger.click();

  const drawer = page.getByRole('dialog', { name: '审阅并创建事项' });
  await expect(drawer).toBeVisible();
  await expect(drawer.getByText('AI 建议，可人工修改', { exact: true })).toBeVisible();
  await drawer.getByLabel('事项标题').fill('人工修订的品牌口播合规事项');
  await drawer.getByLabel('事项负责人').fill('ou_legal_reviewer');
  await drawer.getByLabel('法律风险').click();
  await page.locator('.ant-select-dropdown:visible').getByText('高', { exact: true }).click();
  await drawer.getByLabel('业务影响').click();
  await page.locator('.ant-select-dropdown:visible').getByText('项目级', { exact: true }).click();
  await drawer.getByLabel('首个任务负责人').fill('ou_legal_reviewer');
  await drawer.getByLabel('优先级').click();
  await page.locator('.ant-select-dropdown:visible').getByText('紧急', { exact: true }).click();
  await drawer.getByLabel('下一步行动').fill('核对口播全文和价格比较依据');
  await drawer.getByLabel('计划完成时间').fill('2026-08-04 18:00');
  await expect(drawer.getByText('将原子创建 1 个 Matter 和 1 个 WorkItem')).toBeVisible();
  await expect(drawer.getByText('不会发送消息，不会绕过后续审核')).toBeVisible();
  await drawer.getByRole('button', { name: '取消' }).click();
  const discardDialog = page.getByRole('dialog', { name: '放弃未保存的修改？' });
  await expect(discardDialog).toBeVisible();
  await discardDialog.getByRole('button', { name: '继续编辑' }).click();
  await expect(drawer).toBeVisible();
  await expect(drawer.getByLabel('事项标题')).toHaveValue('人工修订的品牌口播合规事项');

  await drawer.getByRole('button', { name: '取消' }).click();
  await page.getByRole('dialog', { name: '放弃未保存的修改？' }).getByRole('button', { name: '放弃修改' }).click();
  await expect(drawer).toBeHidden();
  await expect(trigger).toBeFocused();
  expect(mutations).toEqual([]);
});

test('409 and API failures keep the drawer open without replacing edited values', async ({ browser }) => {
  for (const scenario of ['confirm-conflict', 'confirm-error'] as const) {
    const context = await browser.newContext();
    const page = await context.newPage();
    const mutations = await installInboxContract(page, scenario);
    await openInbox(page);
    const drawer = await openCreateDrawer(page);
    await drawer.getByLabel('事项标题').fill('人工值不得被服务错误覆盖');
    await fillRequiredConfirmationFields(page, '2026-08-04 18:00');

    await drawer.getByRole('button', { name: '确认创建 1 个事项与 1 个任务' }).click();

    await expect.poll(() => mutations.filter((request) => request.endsWith('/confirm-create')).length).toBe(1);
    await expect(drawer).toBeVisible();
    await expect(drawer.getByLabel('事项标题')).toHaveValue('人工值不得被服务错误覆盖');
    await expect(page).toHaveURL(/\/inbox\/candidate-create$/);
    await context.close();
  }
});

test('successful confirmation sends one human-edited payload and enters the created Matter deep link', async ({ page }) => {
  const mutations = await installInboxContract(page, 'confirm-success');
  await openInbox(page);
  const drawer = await openCreateDrawer(page);
  await drawer.getByLabel('事项标题').fill('人工修订的品牌口播合规事项');
  await drawer.getByLabel('事项背景（AI 建议，可人工修改）').fill('人工确认后的事项背景');
  await fillRequiredConfirmationFields(page, '2026-08-04 18:00');
  const submit = drawer.getByRole('button', { name: '确认创建 1 个事项与 1 个任务' });

  await submit.click();
  await expect(submit).toBeDisabled();
  await submit.click({ force: true });
  await expect.poll(() => mutations.filter((request) => request.endsWith('/confirm-create')).length).toBe(1);
  await expect(page).toHaveURL(/\/matters\/matter-created$/);
  await expect(page.getByRole('heading', { name: '人工修订的品牌口播合规事项' })).toBeVisible();
  expect(mutations.confirmationPayloads).toHaveLength(1);
  expect(mutations.confirmationPayloads[0]).toMatchObject({
    title: '人工修订的品牌口播合规事项',
    summary: '人工确认后的事项背景',
  });
});

test('invalid planned completion time stays in the form without page errors or confirm-create', async ({ page }) => {
  const pageErrors: string[] = [];
  page.on('pageerror', (error) => pageErrors.push(error.message));
  const mutations = await installInboxContract(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await openInbox(page);
  const drawer = await openCreateDrawer(page);
  await fillRequiredConfirmationFields(page, '2026-02-30 18:00');

  await drawer.getByRole('button', { name: '确认创建 1 个事项与 1 个任务' }).click();

  await expect(drawer.getByText('请按 YYYY-MM-DD HH:mm 填写有效时间')).toBeVisible();
  await expect(drawer.locator('.ant-drawer-footer')).toBeInViewport();
  await expect(drawer).toBeVisible();
  expect(mutations.filter((request) => request.endsWith('/confirm-create'))).toHaveLength(0);
  expect(pageErrors).toEqual([]);
});

test('required-field rejection is handled without page errors or confirm-create', async ({ page }) => {
  const pageErrors: string[] = [];
  page.on('pageerror', (error) => pageErrors.push(error.message));
  const mutations = await installInboxContract(page);
  await openInbox(page);
  const drawer = await openCreateDrawer(page);

  await drawer.getByRole('button', { name: '确认创建 1 个事项与 1 个任务' }).click();

  await expect(drawer.locator('.ant-form-item-explain-error')).toHaveCount(6);
  await expect(drawer.getByLabel('下一步行动')).toHaveValue('补充并核对：最终口播脚本附件、价格比较依据');
  expect(mutations.filter((request) => request.endsWith('/confirm-create'))).toHaveLength(0);
  expect(pageErrors).toEqual([]);
});

test('successful retry keeps confirmation frozen while Candidate still exposes the old AgentRun', async ({ page }) => {
  const pageErrors: string[] = [];
  const consoleMessages: string[] = [];
  page.on('pageerror', (error) => pageErrors.push(error.message));
  page.on('console', (message) => consoleMessages.push(message.text()));
  const mutations = await installInboxContract(page, 'retry-stale');
  await openInbox(page);

  await expect(page.getByRole('button', { name: '审阅并创建事项' })).toBeEnabled();
  await page.getByRole('button', { name: '重新分析' }).click();
  await expect.poll(() => mutations.filter((request) => request.endsWith('/retry-analysis')).length).toBe(1);

  await expect(page.getByText('重新分析已提交，等待 Candidate 暴露新的 AgentRun')).toBeVisible();
  await expect(page.getByRole('button', { name: '审阅并创建事项' })).toBeDisabled();
  await page.getByRole('button', { name: '刷新' }).click();
  await expect(page.getByText('重新分析已提交，等待 Candidate 暴露新的 AgentRun')).toBeVisible();
  await expect(page.getByRole('button', { name: '审阅并创建事项' })).toBeDisabled();
  expect(mutations.filter((request) => request.endsWith('/confirm-create'))).toHaveLength(0);
  expect(pageErrors).toEqual([]);
  expect(consoleMessages).not.toContainEqual(expect.stringContaining('Static function can not consume context'));
});

test('list loading and empty states never show fabricated candidates', async ({ page }) => {
  await installInboxContract(page, 'loading');
  await openInbox(page);
  const loadingState = page.getByRole('status', { name: '待确认消息加载中' });
  await expect(loadingState).toBeVisible();
  await expect(loadingState).toHaveAttribute('aria-live', 'polite');
  await expect(loadingState).toHaveAttribute('aria-busy', 'true');
  await expect(loadingState.getByText('待确认消息加载中', { exact: true })).toBeVisible();
  await expect(loadingState.getByText('正在从服务接口请求候选消息；加载完成前不显示业务摘要。', { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: /建议：/ })).toHaveCount(0);
  await expect(page.getByRole('heading', { name: '品牌联名直播口播合规复核' })).toBeVisible({ timeout: 2_000 });

  const emptyPage = await page.context().newPage();
  await installInboxContract(emptyPage, 'empty');
  await openInbox(emptyPage);
  await expect(emptyPage.getByText('暂无待确认消息')).toBeVisible();
});

test('list error and forbidden responses remain distinct and retryable', async ({ browser }) => {
  for (const [scenario, text] of [
    ['list-error', '候选列表加载失败'],
    ['forbidden', '无权查看待确认消息'],
  ] as const) {
    const context = await browser.newContext();
    const page = await context.newPage();
    await installInboxContract(page, scenario);
    await openInbox(page);
    await expect(page.getByText(text, { exact: true })).toBeVisible();
    await expect(page.getByRole('button', { name: /重\s*试/ })).toBeVisible();
    await context.close();
  }
});

test('detail failure, missing attachment, and running analysis freeze confirmation', async ({ browser }) => {
  const errorContext = await browser.newContext();
  const errorPage = await errorContext.newPage();
  await installInboxContract(errorPage, 'detail-error');
  await openInbox(errorPage);
  await expect(errorPage.getByText('证据详情加载失败', { exact: true })).toBeVisible();
  await expect(errorPage.getByRole('button', { name: '重试详情' })).toBeVisible();
  await expect(errorPage.getByRole('button', { name: '审阅并创建事项' })).toBeDisabled();
  await errorContext.close();

  const missingContext = await browser.newContext();
  const missingPage = await missingContext.newPage();
  await installInboxContract(missingPage);
  await openInbox(missingPage);
  await expect(missingPage.getByText('当前快照未纳入附件')).toBeVisible();
  await expect(missingPage.getByText('最终口播脚本附件')).toBeVisible();
  await missingContext.close();

  const runningContext = await browser.newContext();
  const runningPage = await runningContext.newPage();
  await installInboxContract(runningPage, 'running');
  await openInbox(runningPage);
  await expect(runningPage.getByText('正在分析，正式确认已冻结')).toBeVisible();
  await expect(runningPage.getByRole('button', { name: '审阅并创建事项' })).toBeDisabled();
  await runningContext.close();
});

test('required viewports preserve overflow, mobile navigation, touch target, and clean Card API', async ({ page }) => {
  const consoleMessages: string[] = [];
  page.on('console', (message) => consoleMessages.push(message.text()));
  await installInboxContract(page);

  for (const viewport of [
    { width: 1440, height: 900 },
    { width: 1024, height: 768 },
    { width: 390, height: 844 },
  ]) {
    await page.setViewportSize(viewport);
    await openInbox(page);
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(viewport.width);
    if (viewport.width === 390) {
      await expect(page.getByRole('heading', { name: '待确认消息' })).toBeInViewport();
      await page.getByRole('button', { name: /建议：品牌联名直播口播合规复核/ }).click();
      const back = page.getByRole('button', { name: '返回消息队列' });
      await expect(back).toHaveJSProperty('offsetHeight', 44);
      await expect(page.getByRole('button', { name: '审阅并创建事项' })).toHaveJSProperty('offsetHeight', 44);
      await back.click();
    }
  }

  expect(consoleMessages).not.toContainEqual(expect.stringContaining('[antd: Card] bordered is deprecated'));
});
