import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { ImageOut, ImageRoomOut } from '../../api/types.gen'
import { rankPitches, scoreLabel } from '../../lib/imageRoom'
import { ImageCard } from './ImageCard'

const ROOM: ImageRoomOut = {
  room: 'meme',
  format: 'nope_yep',
  format_label: 'Nope / Yep',
  why: 'It reads at a glance.',
  ideas_left: 2,
  fallback_from: '',
  pitches: [
    {
      index: 0,
      format: 'nope_yep',
      format_label: 'Nope / Yep',
      hook: 'Pie charts, rejected',
      concept: '',
      words: ['Pie', 'Bars'],
      anchor: 'compare lengths',
      anchored: true,
      reads_as: 'A smug choice of bars',
      score: 8.5,
      note: '',
      ruled_out: false,
      tried: true,
      current: true,
    },
    {
      index: 1,
      format: 'venn',
      format_label: 'Venn diagram',
      hook: 'The overlap nobody wanted',
      concept: '',
      words: [],
      anchor: '',
      anchored: true,
      reads_as: '',
      score: 6,
      note: '',
      ruled_out: false,
      tried: false,
      current: false,
    },
    {
      index: 2,
      format: 'terminal',
      format_label: 'Terminal session',
      hook: 'Ruled out joke',
      concept: '',
      words: [],
      anchor: '',
      anchored: false,
      reads_as: '',
      score: 9,
      note: '',
      ruled_out: true,
      tried: false,
      current: false,
    },
  ],
  slots: [{ name: 'top', hint: 'The rejected option', text: 'Pie', max_chars: 40, optional: false }],
  sources: [],
}

function meme(extra: Partial<ImageOut> = {}): ImageOut {
  return {
    id: 7,
    slot_id: 'meme',
    position: 3,
    kind: 'meme',
    status: 'ready',
    provider: 'claude-meme',
    url: '/files/meme.png',
    alt: 'A meme',
    caption: '',
    credit: '',
    purpose: 'Closing laugh',
    prompt: '',
    seed: null,
    width: 1080,
    height: 1080,
    error: null,
    history: [],
    builds_on: '',
    remix: null,
    remix_dimensions: ['palette'],
    room: ROOM,
    finalists: [
      { index: 0, url: '/f0.png', label: 'Nope / Yep: pies', score: 8.5, reads_as: 'bars win', current: true },
      { index: 1, url: '/f1.png', label: 'Venn: overlap', score: 6, reads_as: '', current: false },
      { index: 2, url: '/f2.png', label: 'Terminal', score: 5, reads_as: '', current: false },
    ],
    ...extra,
  }
}

function setup(image: ImageOut = meme()) {
  const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async (url) => {
    const body = String(url).includes('/image-formats') ? [{ id: 'venn', label: 'Venn diagram', group: 'Chart jokes', when_to_use: '' }] : image
    return new Response(JSON.stringify(body))
  })
  render(
    <QueryClientProvider client={new QueryClient()}>
      <ImageCard projectId={3} image={image} images={[image]} />
    </QueryClientProvider>,
  )
  const sent = (path: string) => {
    const call = fetchMock.mock.calls.find(([url, init]) => url === path && init?.method === 'POST')
    return call?.[1]?.body ? JSON.parse(String(call[1].body)) : undefined
  }
  return { sent }
}

// Redraws start a job; the card follows it over server-sent events, which jsdom does not have.
vi.stubGlobal(
  'EventSource',
  class {
    addEventListener() {}
    close() {}
  },
)

afterEach(() => vi.restoreAllMocks())

describe('ImageCard', () => {
  it('gives every kind the same tools and no ratings or feed preview', () => {
    for (const image of [meme(), meme({ id: 8, kind: 'diagram', slot_id: 'img1', provider: 'claude-svg', room: { ...ROOM, room: 'body', slots: [] } })]) {
      const { unmount } = render(
        <QueryClientProvider client={new QueryClient()}>
          <ImageCard projectId={3} image={image} images={[image]} />
        </QueryClientProvider>,
      )
      for (const name of ['Ideas', 'Redraw', 'Remix', 'Edit', 'Replace', 'Caption']) {
        expect(screen.getByRole('button', { name })).toBeInTheDocument()
      }
      expect(screen.queryByRole('button', { name: 'I like this one' })).not.toBeInTheDocument()
      expect(screen.queryByRole('button', { name: 'Feed preview' })).not.toBeInTheDocument()
      unmount()
    }
  })

  it('shows why the judge picked it and lets the author pick another finalist', async () => {
    const { sent } = setup()
    expect(screen.getByLabelText('Why the judge picked this one')).toHaveTextContent('Why this one: It reads at a glance.')
    const strip = screen.getByLabelText('Finalists')
    expect(within(strip).getByRole('button', { name: /Finalist 1/ })).toBeDisabled()
    await userEvent.click(within(strip).getByRole('button', { name: /Finalist 2/ }))
    await waitFor(() => expect(sent('/api/images/7/pick')).toEqual({ index: 1 }))
  })

  it('opens the shared ideas room, ranks pitches and sends a steer with new pitches', async () => {
    const { sent } = setup()
    await userEvent.click(screen.getByRole('button', { name: 'Ideas' }))
    const cards = within(screen.getByLabelText('Pitched ideas')).getAllByRole('listitem')
    expect(cards[0]).toHaveTextContent('Pie charts, rejected')
    expect(cards[2]).toHaveTextContent('Ruled out')
    expect(cards[0]).toHaveTextContent('Riffs on: “compare lengths”')
    await userEvent.type(screen.getByLabelText(/Steer the next round/), 'more like the original')
    await userEvent.click(screen.getByRole('button', { name: 'Pitch new ideas' }))
    await waitFor(() => expect(sent('/api/images/7/redraw')).toMatchObject({ rethink: true, note: 'more like the original' }))
  })
})

describe('image room helpers', () => {
  it('ranks by score with ruled-out ideas last and formats scores', () => {
    expect(rankPitches(ROOM.pitches ?? []).map((p) => p.index)).toEqual([0, 1, 2])
    expect(scoreLabel(8.5)).toBe('8.5/10')
    expect(scoreLabel(7)).toBe('7/10')
  })
})
