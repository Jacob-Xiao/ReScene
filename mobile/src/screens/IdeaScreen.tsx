import { MaterialIcons } from '@expo/vector-icons';
import * as ImagePicker from 'expo-image-picker';
import React, { useCallback, useMemo, useState } from 'react';
import { ActivityIndicator, Image, Pressable, StyleSheet, Text, View } from 'react-native';

import { ApiService } from '@/api/client';
import { AppButton } from '@/components/AppButton';
import { Banner, type BannerTone } from '@/components/Banner';
import { PromptTextField } from '@/components/PromptTextField';
import { ApiConfig } from '@/config';
import { colors, radius, spacing } from '@/theme';

interface PickedImage {
  uri: string;
  name: string;
  mimeType: string;
}

interface StatusMessage {
  tone: BannerTone;
  message: string;
}

/** React Native's FormData takes `{ uri, name, type }` file descriptors. */
function appendImage(form: FormData, field: string, file: PickedImage): void {
  form.append(field, { uri: file.uri, name: file.name, type: file.mimeType } as unknown as Blob);
}

/** Both endpoints return raw base64 PNG payloads, sometimes as a data URI. */
function toPngDataUri(payload: string): string {
  return payload.startsWith('data:') ? payload : `data:image/png;base64,${payload}`;
}

/** Strips the `data:image/png;base64,` prefix before POSTing to `/makeGPT`. */
export function stripDataUri(payload: string): string {
  const comma = payload.indexOf(',');
  return comma === -1 ? payload : payload.slice(comma + 1);
}

function imagePayload(image: unknown): string | null {
  return typeof image === 'string' && image.length > 0 ? image : null;
}

function errorText(value: unknown): string {
  return typeof value === 'string' && value.length > 0 ? value : 'Unknown error';
}

export interface IdeaScreenProps {
  api?: ApiService;
}

/**
 * Port of `lib/pages/idea_page.dart`: pick an image, segment it through
 * `/yolo_seg`, then background-edit the mask through `/makeGPT`.
 */
export default function IdeaScreen({ api }: IdeaScreenProps) {
  const apiClient = useMemo(() => api ?? new ApiService(), [api]);

  const [input, setInput] = useState<PickedImage | null>(null);
  /** Transparent PNG returned by `/yolo_seg`, held as a data URI. */
  const [mask, setMask] = useState<string | null>(null);
  /** Edited image returned by `/makeGPT`, held as a data URI. */
  const [output, setOutput] = useState<string | null>(null);
  const [prompt, setPrompt] = useState('');
  const [segmenting, setSegmenting] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [status, setStatus] = useState<StatusMessage | null>(null);

  const pickImage = useCallback(async () => {
    try {
      const result = await ImagePicker.launchImageLibraryAsync({
        mediaTypes: ['images'],
        quality: 1,
      });
      if (result.canceled) return;
      const asset = result.assets[0];
      if (!asset) return;
      setInput({
        uri: asset.uri,
        name: asset.fileName ?? 'upload.jpg',
        mimeType: asset.mimeType ?? 'image/jpeg',
      });
      setMask(null);
      setOutput(null);
      setStatus(null);
    } catch {
      setStatus({ tone: 'error', message: 'Image selection failed' });
    }
  }, []);

  const segment = useCallback(async () => {
    if (segmenting) return; // double-tap guard
    if (input === null) {
      setStatus({ tone: 'info', message: 'Please select an image!' });
      return;
    }

    setSegmenting(true);
    setMask(null);
    setOutput(null);
    setStatus(null);
    try {
      const form = new FormData();
      appendImage(form, 'image', input);
      const result = await apiClient.postMultipart(ApiConfig.yoloSegPath, form);

      if (!result.ok) {
        setStatus({ tone: 'error', message: `Request failed: ${result.status}` });
        return;
      }
      if (result.body?.success !== true) {
        setStatus({
          tone: 'error',
          message: `Processing failed: ${errorText(result.body?.error)}`,
        });
        return;
      }
      const image = imagePayload(result.body.image);
      if (image === null) {
        setStatus({ tone: 'error', message: 'The return is missing image data!' });
        return;
      }
      setMask(toPngDataUri(image));
    } catch (error) {
      setStatus({ tone: 'error', message: `Send failed: ${describe(error)}` });
    } finally {
      setSegmenting(false);
    }
  }, [apiClient, input, segmenting]);

  const generate = useCallback(async () => {
    if (generating) return; // double-tap guard
    if (mask === null) {
      setStatus({ tone: 'info', message: 'Please process an image first!' });
      return;
    }
    if (prompt.trim() === '') {
      setStatus({ tone: 'info', message: 'Please enter your background requirements!' });
      return;
    }

    setGenerating(true);
    setStatus(null);
    try {
      const result = await apiClient.post(ApiConfig.makeGptPath, {
        body: { image: stripDataUri(mask), prompt: prompt.trim() },
        timeoutMs: ApiConfig.gptTimeoutMs,
      });

      if (!result.ok) {
        setStatus({ tone: 'error', message: `GPT request failed: ${result.status}` });
        return;
      }
      if (result.body?.success !== true) {
        setStatus({
          tone: 'error',
          message: `GPT processing failed: ${errorText(result.body?.error)}`,
        });
        return;
      }
      const image = imagePayload(result.body.image);
      if (image === null) {
        setStatus({ tone: 'error', message: 'GPT response is missing image data!' });
        return;
      }
      setOutput(toPngDataUri(image));
    } catch (error) {
      setStatus({ tone: 'error', message: `Send to GPT failed: ${describe(error)}` });
    } finally {
      setGenerating(false);
    }
  }, [apiClient, mask, prompt, generating]);

  const busy = segmenting || generating;
  const busyLabel = generating ? 'Generating with GPT...' : 'Processing the image...';
  const gptEnabled = mask !== null && !generating;

  return (
    <View style={styles.page}>
      <View style={styles.row}>
        <ImageBox
          testID="idea-input-box"
          image={input?.uri ?? null}
          label="Input image"
          tone="input"
          onPress={() => void pickImage()}
        />
        <ImageBox testID="idea-mask-box" image={mask} label="Mask image" tone="output" />
      </View>

      <View style={styles.row}>
        <ImageBox testID="idea-output-box" image={output} label="Output image" tone="output" />
        <View style={styles.actions}>
          {busy ? (
            <View style={styles.progress}>
              <ActivityIndicator color={colors.primary} />
              <Text style={styles.progressLabel}>{busyLabel}</Text>
            </View>
          ) : (
            <>
              <AppButton
                testID="idea-segment"
                label="Segment"
                onPress={() => void segment()}
                disabled={segmenting}
                backgroundColor={colors.primary}
                style={styles.actionButton}
              />
              <AppButton
                testID="idea-gpt"
                label="Send to GPT"
                onPress={() => void generate()}
                disabled={!gptEnabled}
                backgroundColor={gptEnabled ? colors.success : colors.textFaint}
                style={styles.actionButton}
              />
            </>
          )}
        </View>
      </View>

      <View style={styles.spacer} />

      {status !== null ? (
        <View style={styles.bannerSlot}>
          <Banner message={status.message} tone={status.tone} testID="idea-status" />
        </View>
      ) : null}

      <PromptTextField
        testID="idea-prompt"
        value={prompt}
        onChangeText={setPrompt}
        labelText="输入您的背景需求"
        hintText="我想要让GPT..."
        height={70}
        autoFocus
        maxLength={500}
      />
    </View>
  );
}

interface ImageBoxProps {
  image: string | null;
  label: string;
  tone: 'input' | 'output';
  onPress?: () => void;
  testID?: string;
}

function ImageBox({ image, label, tone, onPress, testID }: ImageBoxProps) {
  const isInput = tone === 'input';
  return (
    <View style={[styles.imageBox, { borderColor: isInput ? '#93C5FD' : '#86EFAC' }]}>
      <View style={[styles.imageBoxHeader, { backgroundColor: isInput ? '#EFF6FF' : '#F0FDF4' }]}>
        <Text style={[styles.imageBoxTitle, { color: isInput ? colors.primaryDark : '#166534' }]}>
          {label}
        </Text>
      </View>
      <Pressable
        testID={testID}
        accessibilityRole={onPress ? 'button' : 'image'}
        onPress={onPress}
        disabled={onPress === undefined}
        style={styles.imageCanvas}
      >
        {image !== null ? (
          <Image source={{ uri: image }} style={styles.image} resizeMode="contain" />
        ) : (
          <MaterialIcons
            name={isInput ? 'add-photo-alternate' : 'image-search'}
            size={48}
            color={colors.textFaint}
          />
        )}
      </Pressable>
    </View>
  );
}

function describe(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

const styles = StyleSheet.create({
  page: { flex: 1, backgroundColor: colors.background },
  row: { flex: 23, flexDirection: 'row' },
  spacer: { flex: 54 },
  imageBox: {
    flex: 1,
    margin: spacing.lg,
    borderWidth: 2,
    borderRadius: radius.md,
    backgroundColor: colors.surfaceMuted,
    overflow: 'hidden',
  },
  imageBoxHeader: {
    padding: spacing.md,
    alignItems: 'center',
  },
  imageBoxTitle: { fontSize: 16, fontWeight: '600' },
  imageCanvas: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    padding: spacing.sm,
  },
  image: { width: '100%', height: '100%' },
  actions: {
    justifyContent: 'center',
    gap: spacing.lg,
    paddingHorizontal: 24,
    paddingVertical: 20,
  },
  actionButton: { minWidth: 140 },
  progress: { alignItems: 'center', gap: spacing.md },
  progressLabel: { color: colors.textMuted },
  bannerSlot: { paddingHorizontal: spacing.lg, paddingBottom: spacing.sm },
});
