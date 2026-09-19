import { MaterialIcons } from '@expo/vector-icons';
import React, { useCallback, useMemo, useRef, useState } from 'react';
import { ActivityIndicator, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';

import { ApiService } from '@/api/client';
import { Banner } from '@/components/Banner';
import { IconButton } from '@/components/IconButton';
import { ApiConfig } from '@/config';
import { buildLlamaMessages, extractLlamaContent, type ConversationMessage } from '@/models/llama';
import { colors, radius, spacing } from '@/theme';

export interface LlamaConversationScreenProps {
  api?: ApiService;
}

/**
 * Port of `lib/pages/sub_pages/llama_page_subpages/llama_conversation_page.dart`.
 *
 * The user message is shown optimistically and rolled back when the request
 * fails. The Flutter version guarded the rollback with "the history contains no
 * assistant message at all", which leaves a failed message stranded once any
 * earlier reply exists; here the guard is simply "the failed message is still
 * the last one", which keeps the successful path identical and fixes that case.
 */
export default function LlamaConversationScreen({ api }: LlamaConversationScreenProps) {
  const apiClient = useMemo(() => api ?? new ApiService(), [api]);

  const [history, setHistory] = useState<ConversationMessage[]>([]);
  const [draft, setDraft] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const scrollRef = useRef<ScrollView>(null);

  const scrollToBottom = useCallback(() => {
    // Defer until the new bubble has been laid out.
    requestAnimationFrame(() => scrollRef.current?.scrollToEnd({ animated: true }));
  }, []);

  const send = useCallback(async () => {
    if (loading) return; // double-submit guard
    const advice = draft.trim();
    if (advice === '') {
      setError('The input cannot be empty!');
      return;
    }

    setLoading(true);
    setError(null);

    const optimistic: ConversationMessage = {
      role: 'user',
      content: advice,
      time: new Date().toISOString(),
    };
    const withUserMessage = [...history, optimistic];
    setHistory(withUserMessage);
    scrollToBottom();

    try {
      const result = await apiClient.post(ApiConfig.submitContentPath, {
        body: {
          model: ApiConfig.llamaModel,
          messages: buildLlamaMessages(withUserMessage),
          stream: false,
        },
      });

      if (!result.ok) {
        setHistory((current) =>
          current.length > 0 && current[current.length - 1] === optimistic
            ? current.slice(0, -1)
            : current,
        );
        setError(`Submission failed. Status: ${result.status}`);
        return;
      }

      setHistory((current) => [
        ...current,
        {
          role: 'assistant',
          content: extractLlamaContent(result.body),
          time: new Date().toISOString(),
        },
      ]);
      setDraft('');
      scrollToBottom();
    } catch (caught) {
      setHistory((current) =>
        current.length > 0 && current[current.length - 1] === optimistic
          ? current.slice(0, -1)
          : current,
      );
      setError(`Network error: ${caught instanceof Error ? caught.message : String(caught)}`);
    } finally {
      setLoading(false);
    }
  }, [apiClient, draft, history, loading, scrollToBottom]);

  return (
    <View style={styles.page}>
      <View style={styles.composer}>
        <TextInput
          testID="llama-input"
          style={styles.input}
          value={draft}
          onChangeText={setDraft}
          placeholder="Ask Llama anything..."
          placeholderTextColor={colors.textFaint}
          multiline
          onSubmitEditing={() => {
            if (!loading) void send();
          }}
        />
        <IconButton
          testID="llama-send"
          icon="send"
          accessibilityLabel="Send message"
          size={24}
          color={loading ? colors.textFaint : colors.primary}
          disabled={loading}
          onPress={() => void send()}
        />
      </View>

      {loading ? (
        <View style={styles.thinking}>
          <ActivityIndicator color={colors.primary} />
          <Text style={styles.thinkingLabel}>Llama is thinking...</Text>
        </View>
      ) : null}

      {error !== null ? (
        <View style={styles.bannerSlot}>
          <Banner message={error} testID="llama-error" />
        </View>
      ) : null}

      <View style={styles.transcript}>
        {history.length === 0 ? (
          <View style={styles.empty}>
            <MaterialIcons name="chat-bubble-outline" size={64} color={colors.textFaint} />
            <Text style={styles.emptyLabel}>Start a conversation with Llama!</Text>
          </View>
        ) : (
          <ScrollView ref={scrollRef} contentContainerStyle={styles.transcriptContent}>
            {history.map((message, index) => (
              <MessageBubble key={`${message.role}-${index}`} message={message} />
            ))}
          </ScrollView>
        )}
      </View>
    </View>
  );
}

function MessageBubble({ message }: { message: ConversationMessage }) {
  const isUser = message.role === 'user';
  return (
    <View
      style={[
        styles.bubble,
        { backgroundColor: isUser ? '#EFF6FF' : '#F0FDF4' },
        { borderColor: isUser ? '#DBEAFE' : '#DCFCE7' },
      ]}
    >
      <View style={styles.bubbleHeader}>
        <MaterialIcons
          name={isUser ? 'person' : 'smart-toy'}
          size={16}
          color={isUser ? colors.primary : colors.success}
        />
        <Text style={[styles.bubbleAuthor, { color: isUser ? colors.primaryDark : '#166534' }]}>
          {isUser ? 'You' : 'Llama'}
        </Text>
      </View>
      <Text style={styles.bubbleText}>{message.content}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  page: { flex: 1, padding: spacing.lg, backgroundColor: colors.background },
  composer: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    minHeight: 60,
    paddingHorizontal: spacing.lg,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
  },
  input: { flex: 1, maxHeight: 90, fontSize: 15, color: colors.text, paddingVertical: spacing.md },
  thinking: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: spacing.md, paddingVertical: 10 },
  thinkingLabel: { color: colors.textMuted },
  bannerSlot: { paddingTop: spacing.md },
  transcript: {
    flex: 1,
    marginTop: spacing.lg,
    padding: spacing.lg,
    backgroundColor: colors.surfaceMuted,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
  },
  transcriptContent: { paddingBottom: spacing.sm },
  empty: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: spacing.lg },
  emptyLabel: { color: colors.textMuted, fontSize: 16, fontStyle: 'italic' },
  bubble: {
    marginVertical: spacing.xs,
    padding: spacing.md,
    borderWidth: 1,
    borderRadius: radius.md,
  },
  bubbleHeader: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  bubbleAuthor: { fontWeight: '700' },
  bubbleText: { marginTop: spacing.sm, fontSize: 14, lineHeight: 20, color: colors.text },
});
