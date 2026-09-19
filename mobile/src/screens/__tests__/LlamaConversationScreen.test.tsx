import { fireEvent, render, waitFor } from '@testing-library/react-native';
import React from 'react';

import LlamaConversationScreen from '@/screens/LlamaConversationScreen';
import { createApi, createFetchMock, jsonResponse } from '@/testing/helpers';

describe('LlamaConversationScreen', () => {
  it('starts with an empty-state prompt', async () => {
    const { fetchImpl } = createFetchMock(() => jsonResponse(200, {}));
    const { getByText } = await render(
      <LlamaConversationScreen api={createApi(fetchImpl)} />,
    );

    expect(getByText('Start a conversation with Llama!')).toBeTruthy();
  });

  it('sends the whole history to Ollama and renders the reply', async () => {
    const { fetchImpl, requests } = createFetchMock(() =>
      jsonResponse(200, { api_response: { message: { content: 'hello there' } } }),
    );
    const { getByTestId, getByText } = await render(
      <LlamaConversationScreen api={createApi(fetchImpl)} />,
    );

    await fireEvent.changeText(getByTestId('llama-input'), 'hi');
    await fireEvent.press(getByTestId('llama-send'));

    await waitFor(() => expect(getByText('hello there')).toBeTruthy());
    expect(getByText('You')).toBeTruthy();
    expect(getByText('Llama')).toBeTruthy();

    const body = JSON.parse(String(requests[0]?.init.body));
    expect(requests[0]?.url).toBe('http://backend.test/submit_content');
    expect(body.model).toBe('llama3');
    expect(body.stream).toBe(false);
    expect(body.messages).toEqual([{ role: 'user', content: 'hi' }]);
  });

  it('rolls back the optimistic message when the request fails', async () => {
    const { fetchImpl } = createFetchMock(() => jsonResponse(500, { error: 'ollama down' }));
    const { getByTestId, getByText, queryByText } = await render(
      <LlamaConversationScreen api={createApi(fetchImpl)} />,
    );

    await fireEvent.changeText(getByTestId('llama-input'), 'first question');
    await fireEvent.press(getByTestId('llama-send'));

    await waitFor(() => expect(getByText('Submission failed. Status: 500')).toBeTruthy());
    expect(queryByText('first question')).toBeNull();
    expect(getByText('Start a conversation with Llama!')).toBeTruthy();
  });

  it('rolls back only the failed message once an earlier reply exists', async () => {
    let attempt = 0;
    const { fetchImpl } = createFetchMock(() => {
      attempt += 1;
      return attempt === 1
        ? jsonResponse(200, { api_response: { message: { content: 'first answer' } } })
        : jsonResponse(500, { error: 'ollama down' });
    });
    const { getByTestId, getByText, queryByText } = await render(
      <LlamaConversationScreen api={createApi(fetchImpl)} />,
    );

    await fireEvent.changeText(getByTestId('llama-input'), 'first question');
    await fireEvent.press(getByTestId('llama-send'));
    await waitFor(() => expect(getByText('first answer')).toBeTruthy());

    await fireEvent.changeText(getByTestId('llama-input'), 'second question');
    await fireEvent.press(getByTestId('llama-send'));
    await waitFor(() => expect(getByText('Submission failed. Status: 500')).toBeTruthy());

    // The earlier turn survives; only the failed one is dropped.
    expect(getByText('first question')).toBeTruthy();
    expect(getByText('first answer')).toBeTruthy();
    expect(queryByText('second question')).toBeNull();
  });

  it('refuses to send an empty message', async () => {
    const { fetchImpl, requests } = createFetchMock(() => jsonResponse(200, {}));
    const { getByTestId, getByText } = await render(
      <LlamaConversationScreen api={createApi(fetchImpl)} />,
    );

    await fireEvent.press(getByTestId('llama-send'));

    await waitFor(() => expect(getByText('The input cannot be empty!')).toBeTruthy());
    expect(requests).toHaveLength(0);
  });
});
