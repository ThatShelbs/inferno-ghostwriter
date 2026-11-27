import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { ImageOut, ProjectOut } from '../../api/types.gen'
import { ImageStudio } from './ImageStudio'

const image = (id: number, slot: string, kind: string): ImageOut =>
  ({
    id,
    slot_id: slot,
    position: id,
    kind,
    status: 'ready',
    provider: 'claude-svg',
    url: `/files/${slot}.png`,
    alt: '',
    caption: '',
    credit: '',
    purpose: '',
    prompt: '',
    seed: null,
    width: 1600,
    height: 900,
    error: null,
    history: [],
    remix_dimensions: ['palette', 'medium'],
    room: null,
  }) as unknown as ImageOut

const PROJECT = { id: 3, images: [image(1, 'hero', 'hero'), image(2, 'img2', 'diagram'), image(3, 'meme', 'meme')] } as unknown as ProjectOut

const FORMATS = [
  { id: 'diagram', label: 'Diagram', group: 'Ways to draw it', when_to_use: '' },
  { id: 'exploding_brain', label: 'Exploding brain', group: 'Famous meme formats', when_to_use: '' },
]
const DIMENSIONS = [
  {
    id: 'palette',
    label: 'Colors',
    options: [
      { id: 'inferno', label: 'Inferno', swatch: ['#000', '#f80'] },
      { id: 'sepia', label: 'Sepia', swatch: ['#321', '#ba8'] },
    ],
  },
  { id: 'medium', label: 'Medium', options: [{ id: 'flat', label: 'Flat', swatch: [] }] },
]
const CHART = {
  tags: [
    { id: 'style:editorial', label: 'Visual metaphor', group: 'Opening styles', hint: '', swatch: [] },
    { id: 'kind:chart', label: 'Chart', group: 'Image kinds', hint: '', swatch: [] },
  ],
  post: {},
  persona: { 'kind:chart': 'avoid' },
}

function setup() {
  const onStarted = vi.fn()
  const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async (url, init) => {
    const path = String(url)
    if (init?.method === 'POST' && path.endsWith('/images/redraw')) return new Response(JSON.stringify({ id: 'job-1', status: 'running' }), { status: 202 })
    if (init?.method === 'PUT') return new Response(JSON.stringify({ ...CHART, post: JSON.parse(String(init.body)).post }))
    if (path.includes('/image-formats')) return new Response(JSON.stringify(FORMATS))
    if (path.includes('/remix-options')) return new Response(JSON.stringify(DIMENSIONS))
    if (path.includes('/image-priorities')) return new Response(JSON.stringify(CHART))
    return new Response(JSON.stringify({ demo: true }))
  })
  render(
    <QueryClientProvider client={new QueryClient()}>
      <ImageStudio open onClose={() => {}} project={PROJECT} onStarted={onStarted} />
    </QueryClientProvider>,
  )
  const sent = (suffix: string, method = 'POST') => {
    const call = fetchMock.mock.calls.find(([url, init]) => String(url).endsWith(suffix) && init?.method === method)
    return call?.[1]?.body ? JSON.parse(String(call[1].body)) : undefined
  }
  return { sent, onStarted }
}

afterEach(() => vi.restoreAllMocks())

describe('ImageStudio', () => {
  it('starts every image over with a written note', async () => {
    const { sent, onStarted } = setup()
    await userEvent.type(screen.getByLabelText(/Feedback for every slot/), 'more like a subway map')
    await userEvent.click(screen.getByRole('button', { name: 'Start over: 3 images' }))
    await waitFor(() => expect(onStarted).toHaveBeenCalledWith('job-1'))
    expect(sent('/images/redraw')).toMatchObject({ fresh: true, note: 'more like a subway map', slots: [], image_ids: [1, 2, 3] })
  })

  it('can keep the ideas and only redraw them', async () => {
    const { sent } = setup()
    await userEvent.click(screen.getByRole('switch', { name: 'Pitch all-new ideas' }))
    await userEvent.click(screen.getByRole('button', { name: 'Redraw 3 images' }))
    await waitFor(() => expect(sent('/images/redraw')).toMatchObject({ fresh: false, image_ids: [1, 2, 3] }))
  })

  it('gives slot two its own meme and palette and leaves the others to the run', async () => {
    const { sent } = setup()
    const slot = within(await screen.findByRole('listitem', { name: 'Diagram' }))
    await waitFor(() => expect(within(slot.getByLabelText('Idea')).getByRole('option', { name: 'Exploding brain' })).toBeInTheDocument())
    await userEvent.selectOptions(slot.getByLabelText('Idea'), 'exploding_brain')
    await userEvent.selectOptions(slot.getByLabelText('Colors'), 'inferno')
    await userEvent.click(screen.getByRole('button', { name: 'Start over: 3 images' }))
    await waitFor(() => expect(sent('/images/redraw')).toBeDefined())
    expect(sent('/images/redraw')).toMatchObject({
      image_ids: [1, 3],
      slots: [{ image_id: 2, format: 'exploding_brain', tweaks: { palette: 'inferno' }, next: false }],
    })
  })

  it('draws one slot alone and leaves out an unchecked slot', async () => {
    const { sent } = setup()
    const slot = within(await screen.findByRole('listitem', { name: 'Diagram' }))
    await userEvent.click(slot.getByRole('button', { name: 'Draw this slot' }))
    await waitFor(() => expect(sent('/images/redraw')).toMatchObject({ image_ids: [2], slots: [] }))
  })

  it('sets a palette on every slot at once', async () => {
    const { sent } = setup()
    const all = within(await screen.findByRole('region', { name: 'All slots' }))
    await waitFor(() => expect(within(all.getByLabelText('Colors')).getByRole('option', { name: 'Sepia' })).toBeInTheDocument())
    await userEvent.selectOptions(all.getByLabelText('Colors'), 'sepia')
    await userEvent.click(screen.getByRole('button', { name: 'Start over: 3 images' }))
    await waitFor(() => expect(sent('/images/redraw')?.slots).toHaveLength(3))
    // Slots that become memes would only take house palettes; sepia reaches the slots that stay as they are.
    expect(sent('/images/redraw').slots.every((s: { tweaks: Record<string, string> }) => s.tweaks.palette === 'sepia')).toBe(true)
  })

  it('shows the priorities chart and saves a changed chip', async () => {
    const { sent } = setup()
    await userEvent.click(screen.getByRole('tab', { name: 'Priorities' }))
    // The persona's default shows as the starting point.
    const chart = await screen.findByRole('button', { name: 'Chart: avoid' })
    expect(chart).toHaveAttribute('aria-pressed', 'true')
    const metaphor = screen.getByRole('button', { name: 'Visual metaphor: neutral' })
    await userEvent.click(metaphor)
    expect(screen.getByRole('button', { name: 'Visual metaphor: prefer' })).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Save priorities' }))
    await waitFor(() =>
      expect(sent('/image-priorities', 'PUT')).toEqual({ post: { 'kind:chart': 'avoid', 'style:editorial': 'prefer' }, save_as_default: false }),
    )
  })
})
