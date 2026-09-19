import { fireEvent, render } from '@testing-library/react-native';
import React, { useState } from 'react';

import { PromptTextField } from '@/components/PromptTextField';

function Harness({ maxLength = 500 }: { maxLength?: number }) {
  const [value, setValue] = useState('');
  return (
    <PromptTextField
      testID="prompt"
      value={value}
      onChangeText={setValue}
      labelText="输入您的背景需求"
      hintText="我想要让GPT..."
      maxLength={maxLength}
    />
  );
}

describe('PromptTextField', () => {
  it('renders the label, placeholder and initial counter', async () => {
    const { getByText, getByPlaceholderText } = await render(<Harness />);

    expect(getByText('输入您的背景需求')).toBeTruthy();
    // The hint is the TextInput's placeholder prop, not a rendered Text node.
    expect(getByPlaceholderText('我想要让GPT...')).toBeTruthy();
    expect(getByText('0/500')).toBeTruthy();
  });

  it('updates the counter while typing', async () => {
    const { getByTestId, getByText, queryByText } = await render(<Harness />);

    await fireEvent.changeText(getByTestId('prompt'), 'abc');

    expect(getByText('3/500')).toBeTruthy();
    expect(queryByText('0/500')).toBeNull();
  });

  it('omits the counter when no maxLength is configured', async () => {
    const { queryByText } = await render(
      <PromptTextField value="" onChangeText={() => undefined} labelText="No limit" />,
    );

    expect(queryByText('0/500')).toBeNull();
  });
});
