/**
 * Conversations avec l'assistant IA (ai_conversation_service.py).
 */
import { prisma } from '../../db/prisma.js';
import type { AiConversation, AiConversationMessage } from '../../generated/prisma/client.js';
import { notFound } from '../../lib/http-error.js';
import { datetime, datetimeOrNull } from '../../lib/serialize.js';

export const toConversationSummary = (conversation: AiConversation) => ({
  id: conversation.id,
  restaurant_id: conversation.restaurant_id,
  created_by_user_id: conversation.created_by_user_id,
  title: conversation.title,
  created_at: datetime(conversation.created_at!),
  updated_at: datetimeOrNull(conversation.updated_at),
});

export const toConversationDetail = (conversation: AiConversation & { messages: AiConversationMessage[] }) => ({
  ...toConversationSummary(conversation),
  messages: conversation.messages.map((message) => ({
    id: message.id,
    role: message.role,
    content: message.content,
    input_tokens: message.input_tokens,
    output_tokens: message.output_tokens,
    total_tokens: message.total_tokens,
    created_at: datetime(message.created_at!),
  })),
});

export const createConversation = (restaurantId: number, userId: number, title: string) =>
  prisma.aiConversation.create({ data: { restaurant_id: restaurantId, created_by_user_id: userId, title: title.trim() } });

/** Conversations du restaurant, les plus récentes d'abord, filtrées sur le titre. */
export const listConversations = async (restaurantId: number, page: number, query: string | undefined, pageSize: number) => {
  const normalized = query?.trim();
  const where = { restaurant_id: restaurantId, ...(normalized ? { title: { contains: normalized, mode: 'insensitive' as const } } : {}) };
  const [items, total] = await Promise.all([
    prisma.aiConversation.findMany({
      where,
      orderBy: [{ updated_at: { sort: 'desc', nulls: 'first' } }, { created_at: { sort: 'desc', nulls: 'first' } }, { id: 'desc' }],
      skip: (page - 1) * pageSize,
      take: pageSize,
    }),
    prisma.aiConversation.count({ where }),
  ]);
  return { items, total };
};

export const getConversation = async (restaurantId: number, conversationId: number) => {
  const conversation = await prisma.aiConversation.findFirst({
    where: { restaurant_id: restaurantId, id: conversationId },
    include: { messages: { orderBy: [{ created_at: 'asc' }, { id: 'asc' }] } },
  });
  if (!conversation) throw notFound('Conversation not found');
  return conversation;
};

/** Ajoute un message ; la conversation prend l'heure du message comme date de mise à jour. */
export const addConversationMessage = async (
  conversationId: number,
  message: { role: string; content: string; input_tokens?: number; output_tokens?: number; total_tokens?: number },
) => {
  const created = await prisma.aiConversationMessage.create({
    data: {
      conversation_id: conversationId,
      role: message.role,
      content: message.content,
      input_tokens: message.input_tokens ?? null,
      output_tokens: message.output_tokens ?? null,
      total_tokens: message.total_tokens ?? null,
    },
  });
  await prisma.aiConversation.update({ where: { id: conversationId }, data: { updated_at: created.created_at } });
  return created;
};
