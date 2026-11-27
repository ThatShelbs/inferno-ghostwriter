import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { ImageOut, ImageRoomOut, PitchOut } from '../../api/types.gen'
import { boardSections, formatGroups, kindLabel, rankPitches, scoreLabel, toggleSteer } from '../../lib/imageRoom'
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
      for (const name of ['Ideas', 'Redraw', 'Redraw options', 'Edit', 'Replace', 'Caption']) {
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
    expect(cards[0]).toHaveTextContent('Showing now')
    // Ruled-out ideas are folded away until asked for.
    expect(cards).toHaveLength(2)
    await userEvent.click(screen.getByRole('button', { name: 'Show 1 ruled out' }))
    expect(within(screen.getByLabelText('Pitched ideas')).getAllByRole('listitem')[2]).toHaveTextContent('Ruled out')
    expect(cards[0]).toHaveTextContent('Riffs on: “compare lengths”')
    await userEvent.type(screen.getByLabelText(/Steer the next round/), 'more like the original')
    await userEvent.click(screen.getByRole('button', { name: 'Pitch new ideas' }))
    await waitFor(() => expect(sent('/api/images/7/redraw')).toMatchObject({ rethink: true, pitch: true, note: 'more like the original' }))
  })

  it('draws a picked idea as it is, and an adjusted one with the changes', async () => {
    const { sent } = setup()
    await userEvent.click(screen.getByRole('button', { name: 'Ideas' }))
    const venn = within(screen.getByLabelText('Pitched ideas')).getAllByRole('listitem')[1]
    await userEvent.click(within(venn).getByRole('button', { name: 'Use this one' }))
    await waitFor(() => expect(sent('/api/images/7/redraw')).toMatchObject({ concept: 1, pitch_hook: 'The overlap nobody wanted', concept_edit: null }))
  })

  it('lets the author adjust an idea before it is drawn', async () => {
    const { sent } = setup()
    await userEvent.click(screen.getByRole('button', { name: 'Ideas' }))
    const venn = within(screen.getByLabelText('Pitched ideas')).getAllByRole('listitem')[1]
    await userEvent.click(within(venn).getByRole('button', { name: 'Adjust' }))
    const hook = within(venn).getByLabelText('The idea in a line')
    await userEvent.clear(hook)
    await userEvent.type(hook, 'Overlap, sharper')
    await userEvent.click(within(venn).getByRole('button', { name: 'Draw this' }))
    await waitFor(() => expect(sent('/api/images/7/redraw')).toMatchObject({ concept: 1, concept_edit: { hook: 'Overlap, sharper' } }))
  })

  it('shows a refused redraw instead of failing silently', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (url, init) =>
      String(url).includes('/redraw') && init?.method === 'POST'
        ? new Response(JSON.stringify({ detail: 'ChatGPT is not signed in.' }), { status: 422 })
        : new Response(JSON.stringify(meme())),
    )
    render(
      <QueryClientProvider client={new QueryClient()}>
        <ImageCard projectId={3} image={meme()} images={[meme()]} />
      </QueryClientProvider>,
    )
    await userEvent.click(screen.getByRole('button', { name: 'Redraw' }))
    expect(await screen.findByText(/ChatGPT is not signed in/)).toBeInTheDocument()
  })
})

describe('hands-on data viz card', () => {
  const handsOn = (extra: Partial<ImageOut> = {}) =>
    meme({
      id: 9,
      kind: 'hands_on_viz',
      slot_id: 'img2',
      provider: 'hands-on-code',
      room: null,
      finalists: [],
      remix_dimensions: [],
      hands_on: { library: 'matplotlib', lines: 12, chars: 345, stale: false },
      ...extra,
    })
  const renderCard = (image: ImageOut) =>
    render(
      <MemoryRouter>
        <QueryClientProvider client={new QueryClient()}>
          <ImageCard projectId={3} image={image} images={[image]} />
        </QueryClientProvider>
      </MemoryRouter>,
    )

  it('offers only code tools and reports the size of the code', () => {
    renderCard(handsOn())
    expect(screen.getByLabelText('The code behind this picture')).toHaveTextContent('12 lines of Matplotlib, 345 characters')
    for (const name of ['Rerun code', 'Edit code', 'Replace', 'Caption']) {
      expect(screen.getByRole('button', { name })).toBeInTheDocument()
    }
    for (const name of ['Ideas', 'Redraw', 'Redraw options', 'Words']) {
      expect(screen.queryByRole('button', { name })).not.toBeInTheDocument()
    }
    expect(screen.queryByText(/code above changed/)).not.toBeInTheDocument()
  })

  it('warns when the code changed and reruns it', async () => {
    const image = handsOn({ hands_on: { library: 'matplotlib', lines: 12, chars: 345, stale: true } })
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockImplementation(async () => new Response(JSON.stringify({ id: 'job1', kind: 'redraw_image', status: 'running' })))
    renderCard(image)
    expect(screen.getByText('The code above changed since this picture was made')).toBeInTheDocument()
    await userEvent.click(
      within(screen.getByText('The code above changed since this picture was made').closest('div')!.parentElement!).getByRole('button', { name: 'Rerun code' }),
    )
    await waitFor(() => expect(fetchMock.mock.calls.some(([url]) => url === '/api/images/9/redraw')).toBe(true))
  })

  it('points to Settings when running code is off', () => {
    renderCard(handsOn({ status: 'error', url: null, error: 'Running example code is off. Turn on “Run example code” in Settings to draw this chart.' }))
    expect(screen.getByRole('link', { name: 'Open Settings' })).toHaveAttribute('href', '/settings')
  })
})

describe('image room helpers', () => {
  it('ranks by score with ruled-out ideas last and formats scores', () => {
    expect(rankPitches(ROOM.pitches ?? []).map((p) => p.index)).toEqual([0, 1, 2])
    expect(scoreLabel(8.5)).toBe('8.5/10')
    expect(scoreLabel(7)).toBe('7/10')
  })
})

describe('ideas board helpers', () => {
  const pitch = (index: number, extra: Partial<PitchOut> = {}): PitchOut => ({
    index,
    format: 'venn',
    format_label: 'Venn',
    hook: `Idea ${index}`,
    concept: '',
    ...extra,
  })

  it('lays the board out: on show, not drawn yet (newest round first), drawn before, ruled out', () => {
    const board = boardSections([
      pitch(0, { current: true, tried: true }),
      pitch(1, { tried: true, score: 9 }),
      pitch(2, { score: 8 }),
      pitch(3, { batch: 1, score: 5 }),
      pitch(4, { ruled_out: true }),
    ])
    expect(board.current?.index).toBe(0)
    expect(board.fresh.map((p) => p.index)).toEqual([3, 2])
    expect(board.tried.map((p) => p.index)).toEqual([1])
    expect(board.ruledOut.map((p) => p.index)).toEqual([4])
  })

  it('suggests formats first and toggles quick steers', () => {
    const formats = [
      { id: 'venn', label: 'Venn', group: 'Charts', when_to_use: '' },
      { id: 'drake', label: 'Nope / Yep', group: 'Classics', when_to_use: '' },
    ]
    expect(formatGroups(formats, ['drake']).map((g) => [g.group, g.formats.map((f) => f.id)])).toEqual([
      ['Suggested', ['drake']],
      ['Charts', ['venn']],
    ])
    expect(toggleSteer('', 'Simpler')).toBe('Simpler')
    expect(toggleSteer('Simpler; about deploys', 'simpler')).toBe('about deploys')
    expect(kindLabel({ kind: 'icon', kind_label: '' })).toBe('Icon')
    expect(kindLabel({ kind: 'icon', kind_label: 'Icons row' })).toBe('Icons row')
  })
})
