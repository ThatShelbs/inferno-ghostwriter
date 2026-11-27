import type { ImageRoute } from '../api/hooks'
import type { ImageFormatOut, ImageOut, PriorityTagOut, RedrawAllIn, SlotPlanIn } from '../api/types.gen'
import { kindLabel } from './imageRoom'

/** What the author chose for one slot in Image studio. Empty / 'keep' / 'auto' mean "follow the run". */
export interface SlotDraft {
  /** Part of the run (the checkbox). */
  include: boolean
  /** 'keep' = the idea on show (or all-new ideas when starting over), 'next' = the next idea, else a format / style / meme id. */
  concept: string
  /** Look pins by remix dimension (palette, medium, cast, staging); 'auto' or missing = chosen for you. */
  look: Record<string, string>
  /** '' = the run's model. */
  model: ImageRoute | ''
  /** This slot's own steer; '' = the run's note. */
  note: string
}

export const KEEP = 'keep'
export const NEXT = 'next'
export const AUTO = 'auto'

export const emptyDraft = (): SlotDraft => ({ include: true, concept: KEEP, look: {}, model: '', note: '' })

/** One draft per image that Claude drew (uploads and placeholders stay as they are). */
export function initialDrafts(images: ImageOut[]): Record<number, SlotDraft> {
  return Object.fromEntries(drawable(images).map((image) => [image.id, emptyDraft()]))
}

export function drawable(images: ImageOut[]): ImageOut[] {
  return images.filter((image) => !['upload', 'placeholder', ''].includes(image.provider) && image.kind !== 'hands_on_viz')
}

/** The pinned looks only (palette, medium, ...); "auto" and empty picks are dropped. */
export function pinnedLook(look: Record<string, string>): Record<string, string> {
  return Object.fromEntries(Object.entries(look).filter(([, id]) => id && id !== AUTO))
}

/** True when the slot carries a choice of its own, not just the run's settings. */
export function hasOwnChoice(draft: SlotDraft): boolean {
  return draft.concept !== KEEP || Object.keys(pinnedLook(draft.look)).length > 0 || draft.model !== '' || draft.note.trim() !== ''
}

/**
 * The request for a run. Slots with a choice of their own go in `slots`; the others just ride along in `image_ids`.
 * `only` runs a single slot ("Draw this slot") and leaves every other image alone.
 */
export function buildRequest(
  drafts: Record<number, SlotDraft>,
  run: { fresh: boolean; note: string; model: ImageRoute; improve: boolean },
  only?: number,
): RedrawAllIn {
  const slots: SlotPlanIn[] = []
  const ids: number[] = []
  for (const [key, draft] of Object.entries(drafts)) {
    const id = Number(key)
    if (only !== undefined ? id !== only : !draft.include) continue
    if (!hasOwnChoice(draft)) {
      ids.push(id)
      continue
    }
    const tweaks = pinnedLook(draft.look)
    slots.push({
      image_id: id,
      next: draft.concept === NEXT,
      format: draft.concept !== KEEP && draft.concept !== NEXT ? draft.concept : null,
      tweaks: Object.keys(tweaks).length ? tweaks : null,
      model: draft.model || null,
      note: draft.note.trim() || null,
    })
  }
  return { fresh: run.fresh, note: run.note.trim(), model: run.model, improve: run.improve, slots, image_ids: ids }
}

/** How many images a run would draw, for the button label. */
export function runSize(drafts: Record<number, SlotDraft>): number {
  return Object.values(drafts).filter((d) => d.include).length
}

/** Set one field for every slot (the "All slots" row); a concept only goes where the slot's own menu offers it. */
export function applyToAll(
  drafts: Record<number, SlotDraft>,
  patch: Partial<Pick<SlotDraft, 'concept' | 'model' | 'note'>> & { look?: { dimension: string; id: string } },
  accepts: (imageId: number, concept: string) => boolean = () => true,
): Record<number, SlotDraft> {
  return Object.fromEntries(
    Object.entries(drafts).map(([key, draft]) => {
      const next = { ...draft }
      if (patch.concept !== undefined && accepts(Number(key), patch.concept)) next.concept = patch.concept
      if (patch.model !== undefined) next.model = patch.model
      if (patch.note !== undefined) next.note = patch.note
      if (patch.look) next.look = { ...draft.look, [patch.look.dimension]: patch.look.id }
      return [Number(key), next]
    }),
  )
}

/** What the slot's concept menu is asked for: the opener, the closer or a middle slot ("slot": its kinds plus every meme). */
export function roomFor(image: Pick<ImageOut, 'kind'>): 'opening' | 'meme' | 'slot' {
  return image.kind === 'hero' ? 'opening' : image.kind === 'meme' ? 'meme' : 'slot'
}

/** The label a slot shows in the studio: its name and, when it has one, the style it is drawn in. */
export function slotName(image: ImageOut): string {
  const style = image.room?.format_label
  const base = kindLabel(image)
  return style && image.kind !== 'hero' && style !== base ? `${base} · ${style}` : base
}

/** A short line saying what this slot will do, for the row's summary. */
export function slotSummary(draft: SlotDraft, formats: ImageFormatOut[], fresh: boolean): string {
  const look = Object.keys(pinnedLook(draft.look)).length
  const concept =
    draft.concept === NEXT
      ? 'next idea'
      : draft.concept !== KEEP
        ? (formats.find((f) => f.id === draft.concept)?.label ?? draft.concept)
        : fresh
          ? 'new idea'
          : 'same idea'
  return [concept, look ? `${look} look${look === 1 ? '' : 's'} pinned` : ''].filter(Boolean).join(' · ')
}

// -- priorities ------------------------------------------------------------------

export type Priority = 'prefer' | 'avoid'

/** A chip cycles: neutral -> prefer -> avoid -> neutral. */
export function cyclePriority(current: Priority | undefined): Priority | undefined {
  return current === undefined ? 'prefer' : current === 'prefer' ? 'avoid' : undefined
}

/** Set one tag; neutral removes it. Returns a new chart. */
export function setPriority(chart: Record<string, string>, tag: string, value: Priority | undefined): Record<string, string> {
  const rest = Object.fromEntries(Object.entries(chart).filter(([id]) => id !== tag))
  return value ? { ...rest, [tag]: value } : rest
}

/** The chart's tags grouped for display, in the server's order (a group keeps its first position). */
export function groupTags(tags: PriorityTagOut[]): { group: string; tags: PriorityTagOut[] }[] {
  const groups: { group: string; tags: PriorityTagOut[] }[] = []
  for (const tag of tags) {
    const at = groups.find((g) => g.group === tag.group)
    if (at) at.tags.push(tag)
    else groups.push({ group: tag.group, tags: [tag] })
  }
  return groups
}

/** "2 preferred, 1 avoided", or "Nothing prioritized yet". */
export function chartSummary(chart: Record<string, string>): string {
  const values = Object.values(chart)
  const prefer = values.filter((v) => v === 'prefer').length
  const avoid = values.filter((v) => v === 'avoid').length
  if (!prefer && !avoid) return 'Nothing prioritized yet'
  return [prefer ? `${prefer} preferred` : '', avoid ? `${avoid} avoided` : ''].filter(Boolean).join(', ')
}
