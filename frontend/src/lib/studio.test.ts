import { describe, expect, it } from 'vitest'

import type { ImageOut, PriorityTagOut } from '../api/types.gen'
import {
  KEEP,
  NEXT,
  applyToAll,
  buildRequest,
  chartSummary,
  cyclePriority,
  drawable,
  emptyDraft,
  groupTags,
  initialDrafts,
  roomFor,
  setPriority,
  type SlotDraft,
} from './studio'

const image = (id: number, kind: string, provider = 'claude-svg'): ImageOut =>
  ({ id, slot_id: `img${id}`, position: id, kind, provider, history: [] }) as unknown as ImageOut

const RUN = { fresh: true, note: '  steer  ', model: 'auto' as const, improve: true }
const drafts = (): Record<number, SlotDraft> => ({ 1: emptyDraft(), 2: emptyDraft(), 3: emptyDraft() })

describe('which slots the studio steers', () => {
  it('skips uploads, placeholders and hands-on charts', () => {
    const all = [image(1, 'hero'), image(2, 'diagram'), image(3, 'chart', 'upload'), image(4, 'illustration', 'placeholder'), image(5, 'hands_on_viz')]
    expect(drawable(all).map((i) => i.id)).toEqual([1, 2])
    expect(Object.keys(initialDrafts(all))).toEqual(['1', '2'])
  })

  it('asks each slot for its own menu', () => {
    expect(roomFor({ kind: 'hero' })).toBe('opening')
    expect(roomFor({ kind: 'meme' })).toBe('meme')
    expect(roomFor({ kind: 'diagram' })).toBe('slot')
  })
})

describe('the request', () => {
  it('sends slots that follow the run as plain ids', () => {
    expect(buildRequest(drafts(), RUN)).toEqual({ fresh: true, note: 'steer', model: 'auto', improve: true, slots: [], image_ids: [1, 2, 3] })
  })

  it('maps slot two to a meme with the inferno palette and leaves the others to the run', () => {
    const d = drafts()
    d[2] = { ...d[2], concept: 'exploding_brain', look: { palette: 'inferno', cast: 'auto' } }
    const request = buildRequest(d, RUN)
    expect(request.image_ids).toEqual([1, 3])
    expect(request.slots).toEqual([{ image_id: 2, next: false, format: 'exploding_brain', tweaks: { palette: 'inferno' }, model: null, note: null }])
  })

  it('takes the next idea for one slot and carries its own model and note', () => {
    const d = drafts()
    d[3] = { ...d[3], concept: NEXT, model: 'codex', note: ' only here ' }
    expect(buildRequest(d, RUN).slots).toEqual([{ image_id: 3, next: true, format: null, tweaks: null, model: 'codex', note: 'only here' }])
  })

  it('leaves out slots that are not included, and runs one slot alone on request', () => {
    const d = drafts()
    d[1] = { ...d[1], include: false }
    expect(buildRequest(d, RUN).image_ids).toEqual([2, 3])
    // "Draw this slot" runs the one slot even when it is unchecked, and nothing else.
    expect(buildRequest(d, RUN, 1).image_ids).toEqual([1])
    expect(buildRequest(d, RUN, 1).slots).toEqual([])
  })
})

describe('the all-slots row', () => {
  it('sets a choice on every slot and a slot can differ afterwards', () => {
    let d = applyToAll(drafts(), { look: { dimension: 'palette', id: 'viridis' }, model: 'gemini' })
    expect(Object.values(d).every((s) => s.look.palette === 'viridis' && s.model === 'gemini')).toBe(true)
    d = { ...d, 2: { ...(d[2] ?? emptyDraft()), look: { palette: 'magma' } } }
    expect((buildRequest(d, RUN).slots ?? []).map((s) => s.tweaks)).toEqual([{ palette: 'viridis' }, { palette: 'magma' }, { palette: 'viridis' }])
  })

  it('applies a concept only where the slot offers it', () => {
    const d = applyToAll(drafts(), { concept: 'nope_yep' }, (id) => id !== 2)
    expect(d[1]?.concept).toBe('nope_yep')
    expect(d[2]?.concept).toBe(KEEP)
  })
})

describe('the priorities chart', () => {
  it('cycles neutral, prefer, avoid', () => {
    expect(cyclePriority(undefined)).toBe('prefer')
    expect(cyclePriority('prefer')).toBe('avoid')
    expect(cyclePriority('avoid')).toBeUndefined()
  })

  it('sets and clears a tag without touching the others', () => {
    const one = setPriority({ 'kind:chart': 'avoid' }, 'style:editorial', 'prefer')
    expect(one).toEqual({ 'kind:chart': 'avoid', 'style:editorial': 'prefer' })
    expect(setPriority(one, 'kind:chart', undefined)).toEqual({ 'style:editorial': 'prefer' })
  })

  it('groups tags in the server order and summarizes the chart', () => {
    const tags = [
      { id: 'style:a', label: 'A', group: 'Opening styles' },
      { id: 'kind:b', label: 'B', group: 'Image kinds' },
      { id: 'style:c', label: 'C', group: 'Opening styles' },
    ] as PriorityTagOut[]
    expect(groupTags(tags).map((g) => [g.group, g.tags.length])).toEqual([
      ['Opening styles', 2],
      ['Image kinds', 1],
    ])
    expect(chartSummary({})).toBe('Nothing prioritized yet')
    expect(chartSummary({ a: 'prefer', b: 'prefer', c: 'avoid' })).toBe('2 preferred, 1 avoided')
  })
})
