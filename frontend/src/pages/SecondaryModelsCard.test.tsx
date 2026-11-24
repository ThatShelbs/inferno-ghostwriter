import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, it, vi } from 'vitest'

import { SecondaryModelsCard } from './SecondaryModelsCard'

it('starts with Claude and saves only the stage or fallback the author changes', async () => {
  let secondary = {}
  const updates: object[] = []
  const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    if (String(input) === '/api/settings') {
      if (init?.method === 'PUT') {
        const body = JSON.parse(String(init.body))
        updates.push(body)
        secondary = { ...secondary, ...body.secondary }
      }
      return Response.json({ demo: false, secondary })
    }
    return Response.json([
      { provider: 'codex', model: 'GPT-6.2 Sol (Medium)', installed: true, signed_in: true, login_in_progress: false },
      { provider: 'gemini', model: 'Gemini 4 Argon (Medium)', installed: true, signed_in: false, login_in_progress: false },
    ])
  })
  try {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <SecondaryModelsCard />
      </QueryClientProvider>,
    )
    const draft = await screen.findByRole('combobox', { name: 'First draft' })
    const critique = screen.getByRole('combobox', { name: 'Editorial critique' })
    expect(draft).toHaveValue('claude')
    expect(within(critique).getByRole('option', { name: 'Gemini 4 Argon (Medium)' })).toBeDisabled()
    const user = userEvent.setup()
    await user.selectOptions(critique, 'codex')
    await waitFor(() => expect(critique).toHaveValue('codex'))
    const fallback = screen.getByRole('group', { name: 'Use when Claude reaches a usage limit' })
    await user.click(within(fallback).getByRole('checkbox', { name: 'ChatGPT' }))
    await waitFor(() => expect(within(fallback).getByRole('checkbox', { name: 'ChatGPT (1)' })).toBeChecked())
    expect(updates).toEqual([{ secondary: { critique: 'codex' } }, { secondary: { fallback: ['codex'] } }])
    expect(draft).toHaveValue('claude')
  } finally {
    fetchMock.mockRestore()
  }
})
