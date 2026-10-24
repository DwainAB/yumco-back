/**
 * Validation des demandes à l'assistant IA (schemas/ai.py, ai_conversation.py).
 */
import { ge, lengthBetween, maxItems, py, z } from '../../lib/validation.js';

export const AI_CONVERSATIONS_PAGE_SIZE = 10;

export const AIChatMessage = z.object({ role: py.str(), content: py.str() });
export type AIChatMessage = z.output<typeof AIChatMessage>;

export const AIChatRequest = z.object({
  conversation_id: py.int().nullable().optional(),
  message: py.str().superRefine(lengthBetween(1, 12000)),
  history: z.array(AIChatMessage).superRefine(maxItems(8)).default([]),
});
export type AIChatRequest = z.output<typeof AIChatRequest>;

export const AIConversationCreate = z.object({ title: py.str().superRefine(lengthBetween(1, 120)) });

export const AIConversationListQuery = z.object({
  page: py.int().superRefine(ge(1)).default(1),
  q: py.str().superRefine(lengthBetween(1, 120)).optional(),
});
