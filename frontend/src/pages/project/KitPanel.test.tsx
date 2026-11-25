import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { GitHubStatusOut, KitOut } from '../../api/types.gen'
import { KitPanel } from './KitPanel'

const KIT: KitOut = {
  fit: { recommended: true, article_type: 'tutorial', reasons: ['2 code examples readers can run', '1 chart to recreate from data'] },
  built: false,
  built_at: null,
  library: 'auto',
  note: '',
  article_url: '',
  files: [],
  notes: [],
  repo: null,
  default_name: 'pie-charts-are-lame',
  linked: false,
  libraries: [
    { id: 'auto', label: 'Auto' },
    { id: 'altair', label: 'Altair (Vega-Lite)' },
  ],
}

const SIGNED_OUT: GitHubStatusOut = {
  installed: true,
  signed_in: false,
  login: '',
  message: 'Sign in to GitHub.',
  sign_in_command: 'gh auth login --web --git-protocol https',
}

class FakeEventSource {
  addEventListener() {}
  close() {}
}

function setup(kit: KitOut, github: GitHubStatusOut = SIGNED_OUT) {
  vi.stubGlobal('EventSource', FakeEventSource)
  const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async (url, init) => {
    const path = String(url)
    if (path === '/api/github/status') return new Response(JSON.stringify(github))
    if (init?.method === 'POST') return new Response(JSON.stringify({ id: 'job1', kind: 'build_kit', status: 'queued' }))
    return new Response(JSON.stringify(kit))
  })
  render(
    <QueryClientProvider client={new QueryClient()}>
      <KitPanel projectId={7} />
    </QueryClientProvider>,
  )
  const posted = (path: string) => {
    const call = fetchMock.mock.calls.find(([url, init]) => url === path && init?.method === 'POST')
    return call?.[1]?.body ? JSON.parse(String(call[1].body)) : undefined
  }
  return { posted }
}

afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

describe('KitPanel', () => {
  it('recommends the kit and builds it with the chosen chart library', async () => {
    const { posted } = setup(KIT)
    expect(await screen.findByText('Recommended for this post')).toBeInTheDocument()
    expect(screen.getByText(/2 code examples readers can run/)).toBeInTheDocument()
    await userEvent.selectOptions(screen.getByLabelText('Charts'), 'altair')
    await userEvent.click(screen.getByRole('button', { name: 'Build kit' }))
    await waitFor(() => expect(posted('/api/projects/7/kit')).toBeDefined())
    expect(posted('/api/projects/7/kit')).toEqual({ library: 'altair', article_url: '', note: '' })
  })

  it('offers the download and shows how to sign in to GitHub', async () => {
    setup({ ...KIT, built: true, files: ['README.md', 'notebook.ipynb'] })
    expect(await screen.findByRole('button', { name: 'Download kit (.zip)' })).toBeInTheDocument()
    expect(screen.getByText('2 files')).toBeInTheDocument()
    expect(await screen.findByText('gh auth login --web --git-protocol https')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Create repo & push' })).toBeDisabled()
  })

  it('links to the pushed repository and Colab', async () => {
    setup(
      {
        ...KIT,
        built: true,
        repo: {
          owner: 'me',
          name: 'pie-kit',
          visibility: 'public',
          url: 'https://github.com/me/pie-kit',
          colab_url: 'https://colab.research.google.com/github/me/pie-kit/blob/main/notebook.ipynb',
          pushed_at: '2026-11-25T00:00:00',
        },
      },
      { ...SIGNED_OUT, signed_in: true, login: 'me' },
    )
    expect(await screen.findByRole('link', { name: /me\/pie-kit/ })).toHaveAttribute('href', 'https://github.com/me/pie-kit')
    expect(screen.getByRole('button', { name: 'Open in Colab' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Add link to post' })).toBeEnabled()
  })
})
