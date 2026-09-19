import { useRouter } from 'expo-router';
import React from 'react';
import { ScrollView, StyleSheet, View } from 'react-native';

import { SelectingBar } from '@/components/SelectingBar';
import { colors } from '@/theme';

/**
 * Port of `lib/pages/llama_page.dart`: the chat entry list. Selecting the row
 * pushes the conversation screen.
 */
export default function LlamaScreen() {
  const router = useRouter();

  return (
    <ScrollView style={styles.page} contentContainerStyle={styles.content}>
      <View>
        <SelectingBar
          testID="llama-model-row"
          title="Llama模型"
          content="Llama3.2-8B"
          iconName="computer"
          onPress={() => router.push('/llama-conversation')}
        />
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  page: { flex: 1, backgroundColor: colors.background },
  content: { paddingTop: 6, paddingBottom: 120 },
});
