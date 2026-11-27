import type { ImageFormatOut, ImageOut, PitchOut } from '../api/types.gen'

/** The pitches best first: usable ones by the judge's score (pitch order when not judged), ruled-out ones last. */
export function rankPitches(pitches: PitchOut[]): PitchOut[] {
  return [...pitches].sort((a, b) => Number(a.ruled_out) - Number(b.ruled_out) || (b.score ?? -1) - (a.score ?? -1) || a.index - b.index)
}

/** A judge's score as the board shows it: "7.5/10". */
export function scoreLabel(score: number): string {
  return `${Number.isInteger(score) ? score : score.toFixed(1)}/10`
}

/** How each image kind is named on its card (the server sends `kind_label`; this is the fallback). */
export const KIND_LABEL: Record<string, string> = {
  hero: 'Opening image',
  diagram: 'Diagram',
  chart: 'Chart',
  illustration: 'Illustration',
  icon: 'Icon',
  meme: 'Closing meme',
  screenshot: 'Screenshot mock',
  hands_on_viz: 'Hands-on data viz',
}

/** One label everywhere: the server's, else the fallback table. */
export function kindLabel(image: Pick<ImageOut, 'kind' | 'kind_label'>): string {
  return image.kind_label || KIND_LABEL[image.kind] || image.kind
}

/**
 * The ideas board, laid out: the idea on show, then ideas not drawn yet (newest round first, best first within a
 * round), then ones already drawn, with ruled-out ideas kept apart (the board folds them away).
 */
export function boardSections(pitches: PitchOut[]): { current: PitchOut | null; fresh: PitchOut[]; tried: PitchOut[]; ruledOut: PitchOut[] } {
  const current = pitches.find((p) => p.current) ?? null
  const rest = rankPitches(pitches.filter((p) => !p.current))
  const byRound = (a: PitchOut, b: PitchOut) => (b.batch ?? 0) - (a.batch ?? 0)
  return {
    current,
    fresh: rest.filter((p) => !p.ruled_out && !p.tried).sort(byRound),
    tried: rest.filter((p) => !p.ruled_out && p.tried),
    ruledOut: rest.filter((p) => p.ruled_out),
  }
}

/** The format menu as chips: a "Suggested" group first (formats of the best untried pitches), then the rest by group. */
export function formatGroups(formats: ImageFormatOut[], suggested: string[] = [], current = ''): { group: string; formats: ImageFormatOut[] }[] {
  const byId = new Map(formats.map((f) => [f.id, f]))
  const picked = suggested.map((id) => byId.get(id)).filter((f): f is ImageFormatOut => !!f && f.id !== current)
  const taken = new Set(picked.map((f) => f.id))
  const groups: { group: string; formats: ImageFormatOut[] }[] = picked.length ? [{ group: 'Suggested', formats: picked }] : []
  for (const group of [...new Set(formats.map((f) => f.group))]) {
    const items = formats.filter((f) => f.group === group && !taken.has(f.id))
    if (items.length) groups.push({ group, formats: items })
  }
  return groups
}

/** Quick steers for a redraw or a new round of ideas: one click fills the note (free: it is only words). */
export const STEER_CHIPS = ['Simpler', 'Bolder', 'Fewer words', 'Funnier', 'More technical', 'New layout'] as const

/** Add a quick steer to a note (or take it out again when it is already there). */
export function toggleSteer(note: string, chip: string): string {
  const parts = note
    .split(/\s*;\s*/)
    .map((p) => p.trim())
    .filter(Boolean)
  const has = parts.some((p) => p.toLowerCase() === chip.toLowerCase())
  return (has ? parts.filter((p) => p.toLowerCase() !== chip.toLowerCase()) : [...parts, chip]).join('; ')
}

/** The steer for "More like this": that idea as the seed of a new round, plus the author's own steer. */
export function moreLikeThis(pitch: Pick<PitchOut, 'hook' | 'concept'>, note: string): string {
  const seed = `More ideas like this one, each a different take: "${pitch.hook}"${pitch.concept ? ` (${pitch.concept})` : ''}`
  return [seed, note.trim()].filter(Boolean).join('; ').slice(0, 500)
}
