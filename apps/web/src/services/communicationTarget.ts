export interface CommunicationTargetDisplay {
  label: string;
  value: string;
  display: string;
  recognized: boolean;
}

function nonEmptyString(value: unknown): string | undefined {
  return typeof value === 'string' && value.trim() ? value.trim() : undefined;
}

export function formatCommunicationTarget(target: Record<string, unknown>): CommunicationTargetDisplay {
  const replyToMessageId = nonEmptyString(target.replyToMessageId);
  if (replyToMessageId) {
    return { label: '回复原消息', value: replyToMessageId, display: `回复原消息：${replyToMessageId}`, recognized: true };
  }

  const receiveId = nonEmptyString(target.receiveId);
  if (receiveId) {
    const receiveIdType = nonEmptyString(target.receiveIdType) ?? 'open_id';
    return {
      label: `收件人（${receiveIdType}）`,
      value: receiveId,
      display: `收件人（${receiveIdType}）：${receiveId}`,
      recognized: true,
    };
  }

  const chatId = nonEmptyString(target.chatId);
  if (chatId) return { label: '群聊', value: chatId, display: `群聊：${chatId}`, recognized: true };

  const recipient = nonEmptyString(target.recipient);
  if (recipient) return { label: '收件人', value: recipient, display: `收件人：${recipient}`, recognized: true };

  return { label: '外发目标', value: '无法识别目标', display: '无法识别目标', recognized: false };
}
