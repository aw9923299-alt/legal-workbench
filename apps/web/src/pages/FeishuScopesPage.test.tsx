import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { legalApi } from '../services/api';
import type { FeishuScope, FeishuUserAuthorization } from '../types/api';
import FeishuScopesPage from './FeishuScopesPage';

const authorization: FeishuUserAuthorization = {
  id: 'auth-1',
  openId: 'ou_personal',
  tenantKey: 'tenant-personal',
  displayName: '法务账号',
  scopes: ['offline_access', 'im:message:readonly'],
  missingScopes: [],
  usable: true,
  capabilities: [
    { capability: 'core_identity', label: 'Identity', status: 'ready', grantedScopes: ['offline_access'], missingScopes: [] },
    { capability: 'message_history', label: 'Messages', status: 'ready', grantedScopes: ['im:message:readonly'], missingScopes: [] },
    { capability: 'chat_discovery', label: 'Chat discovery', status: 'ready', grantedScopes: ['im:chat:readonly'], missingScopes: [] },
    { capability: 'document_read', label: 'Documents', status: 'ready', grantedScopes: ['docs:document.content:read'], missingScopes: [] },
    { capability: 'drive_search', label: 'Drive', status: 'ready', grantedScopes: ['drive:drive.search:readonly'], missingScopes: [] },
    { capability: 'attachment_read', label: 'Attachments', status: 'partial', grantedScopes: ['im:message:readonly'], missingScopes: [] },
  ],
  accessExpiresAt: '2026-08-08T12:00:00Z',
  refreshExpiresAt: '2026-09-08T12:00:00Z',
  status: 'connected',
  lastRefreshedAt: null,
  lastErrorCode: null,
  createdAt: '2026-08-08T00:00:00Z',
  updatedAt: '2026-08-08T00:00:00Z',
};

const scope: FeishuScope = {
  id: 'scope-1',
  provider: 'feishu',
  externalScopeId: 'oc_synthetic_scope',
  displayName: '合成测试群',
  status: 'unapproved',
  syncMode: 'disabled',
  identityType: 'user',
  scopeType: 'group',
  authorizationId: authorization.id,
  backfillDays: 7,
  highValueLegal: false,
  lastMessageAt: null,
  lastErrorCode: null,
  lastErrorMessage: null,
  lastCompensatedAt: null,
  lastCompensationStatus: null,
  approvedBy: null,
  approvedAt: null,
  version: 1,
  createdAt: '2026-08-08T00:00:00Z',
  updatedAt: '2026-08-08T00:00:00Z',
};

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <MemoryRouter>
      <QueryClientProvider client={client}><FeishuScopesPage /></QueryClientProvider>
    </MemoryRouter>,
  );
}

describe('Feishu personal data sources page', () => {
  beforeEach(() => {
    vi.spyOn(legalApi, 'listFeishuUserAuthorizations').mockResolvedValue([authorization]);
    vi.spyOn(legalApi, 'listFeishuScopes').mockResolvedValue([scope]);
    vi.spyOn(legalApi, 'listFeishuFolderSubscriptions').mockResolvedValue([]);
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it('shows user identity and applies an allow decision through the existing scope API', async () => {
    const change = vi.spyOn(legalApi, 'changeFeishuScope').mockResolvedValue({
      ...scope,
      status: 'allowed',
      syncMode: 'all_messages',
      version: 2,
    });

    renderPage();

    expect(await screen.findByText('法务账号')).toBeInTheDocument();
    expect(screen.getAllByText('合成测试群').length).toBeGreaterThan(0);
    expect(screen.getAllByText('User').length).toBeGreaterThan(0);
    expect(screen.getAllByText('未批准').length).toBeGreaterThan(0);
    fireEvent.click(screen.getAllByRole('button', { name: /允许采集/ })[0]);

    await waitFor(() => expect(change).toHaveBeenCalledWith(
      'scope-1',
      1,
      { action: 'allow', syncMode: 'all_messages' },
      expect.any(Object),
    ));
  }, 10_000);

  it('searches and imports a selected docx through the native document pipeline', async () => {
    vi.spyOn(legalApi, 'searchFeishuUserDocuments').mockResolvedValue([{
      token: 'doccnAbCdEf',
      type: 'docx',
      title: '合同审查清单',
      url: 'https://acme.feishu.cn/docx/doccnAbCdEf',
    }]);
    const importDocument = vi.spyOn(legalApi, 'importFeishuUserDocument').mockResolvedValue({
      documentId: 'document-1',
      documentVersionId: 'version-1',
      createdVersion: true,
      segmentCount: 4,
    });
    renderPage();

    expect(await screen.findByText('法务账号')).toBeInTheDocument();
    const search = await screen.findByPlaceholderText('搜索我的飞书文档');
    fireEvent.change(search, { target: { value: '合同审查' } });
    fireEvent.click(screen.getByRole('button', { name: /搜\s*索/ }));
    expect(await screen.findByText('合同审查清单')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /导入/ }));

    await waitFor(() => expect(importDocument).toHaveBeenCalledWith(
      'doccnAbCdEf',
      {
        authorizationId: 'auth-1',
        documentType: 'docx',
        title: '合同审查清单',
        sourceUrl: 'https://acme.feishu.cn/docx/doccnAbCdEf',
      },
      expect.any(Object),
    ));
  });

  it('shows the exact missing personal message permission', async () => {
    vi.mocked(legalApi.listFeishuUserAuthorizations).mockResolvedValue([{
      ...authorization,
      status: 'connected',
      capabilities: authorization.capabilities.map((capability) => (
        capability.capability === 'message_history'
          ? { ...capability, status: 'permission_missing', missingScopes: ['im:message.group_msg:get_as_user'] }
          : capability
      )),
    }]);

    renderPage();

    expect(await screen.findByText('Messages')).toBeInTheDocument();
    expect(screen.getByText('im:message.group_msg:get_as_user')).toBeInTheDocument();
  });

  it('shows independent capability degradation without disabling the token', async () => {
    vi.mocked(legalApi.listFeishuUserAuthorizations).mockResolvedValue([{
      ...authorization,
      capabilities: authorization.capabilities.map((capability) => {
        if (capability.capability === 'document_read') {
          return { ...capability, status: 'permission_missing', grantedScopes: [], missingScopes: ['docs:document.content:read'] };
        }
        if (capability.capability === 'drive_search') {
          return { ...capability, status: 'permission_missing', grantedScopes: [], missingScopes: ['drive:drive.search:readonly'] };
        }
        return capability;
      }),
    }]);
    renderPage();

    expect(await screen.findByText('Messages')).toBeInTheDocument();
    expect(screen.getByText('Chat discovery')).toBeInTheDocument();
    expect(screen.getByText('Documents')).toBeInTheDocument();
    expect(screen.getByText('Drive')).toBeInTheDocument();
    expect(screen.getByText('Attachments')).toBeInTheDocument();
    expect(screen.getAllByText('权限不足')).toHaveLength(2);
    expect(screen.getByText('部分可用')).toBeInTheDocument();
  });
});
