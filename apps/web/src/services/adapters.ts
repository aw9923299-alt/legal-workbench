import type { AgentRun, InboxItem, Task } from '../types/domain';
import { agentRuns, inboxItems, tasks } from '../data/mock';

export interface FeishuAdapter {
  listInboxItems(): Promise<InboxItem[]>;
  fetchThreadContext(messageId: string): Promise<string[]>;
  pauseSync(): Promise<void>;
}

export interface TaskRepository {
  listTasks(): Promise<Task[]>;
  updateTask(id: string, patch: Partial<Task>): Promise<Task>;
}

export interface AgentGateway {
  listRuns(): Promise<AgentRun[]>;
  invoke(agentId: string, taskId: string): Promise<AgentRun>;
}

const wait = (ms = 240) => new Promise((resolve) => setTimeout(resolve, ms));

export const mockFeishuAdapter: FeishuAdapter = {
  async listInboxItems() { await wait(); return inboxItems; },
  async fetchThreadContext(messageId) { await wait(); return inboxItems.find((item) => item.id === messageId)?.context ?? []; },
  async pauseSync() { await wait(); },
};

export const mockTaskRepository: TaskRepository = {
  async listTasks() { await wait(); return tasks; },
  async updateTask(id, patch) {
    await wait();
    const task = tasks.find((item) => item.id === id);
    if (!task) throw new Error('任务不存在');
    return { ...task, ...patch };
  },
};

export const mockAgentGateway: AgentGateway = {
  async listRuns() { await wait(); return agentRuns; },
  async invoke(agentId, taskId) {
    await wait(600);
    return {
      id: `run-${Date.now()}`,
      agentName: agentId,
      version: 'mock',
      status: '待审批',
      taskId,
      startedAt: '刚刚',
      duration: '24 秒',
      confidence: 0.87,
      cost: 1.26,
      output: '已生成模拟分析结果，等待人工确认后回写。',
    };
  },
};
