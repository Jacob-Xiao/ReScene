/** One visible turn in the Llama chat. */
export interface ConversationMessage {
  role: string;
  content: string;
  /** ISO timestamp; display-only, never sent to the model. */
  time?: string;
}

export interface LlamaChatMessage {
  role: string;
  content: string;
}

/**
 * Converts the visible conversation history into the `messages` array the
 * Ollama chat API expects, so the model sees the full conversation.
 *
 * Direct port of `buildLlamaMessages` in
 * `lib/pages/sub_pages/llama_page_subpages/llama_conversation_page.dart`.
 */
export function buildLlamaMessages(history: readonly ConversationMessage[]): LlamaChatMessage[] {
  return history
    .filter((message) => message.role === 'user' || message.role === 'assistant')
    .map((message) => ({
      role: message.role,
      content: typeof message.content === 'string' ? message.content : '',
    }));
}

/**
 * Extracts the reply text from a `/submit_content` payload.
 *
 * Ollama answers with `{ api_response: { message: { content } } }` for chat
 * completions, but older/model-specific responses nest `content` directly;
 * both shapes are accepted, matching the Flutter client.
 */
export function extractLlamaContent(body: Record<string, unknown> | null): string {
  const fallback = 'No response content received.';
  const apiResponse = body?.api_response;
  if (typeof apiResponse !== 'object' || apiResponse === null) return fallback;
  const nested = apiResponse as Record<string, unknown>;

  const message = nested.message;
  if (typeof message === 'object' && message !== null) {
    const content = (message as Record<string, unknown>).content;
    if (typeof content === 'string') return content;
  }
  if (typeof nested.content === 'string') return nested.content;
  return fallback;
}
