import type { OpeningStyleOut } from '../api/types.gen'

/** The open styles every Auto round includes, whatever the article type. */
export const OPEN_STYLES = ['editorial', 'data_art']

/** What Auto will weigh, in words: "Pitches across Cheat sheet and Framework diagram, plus open visual metaphors and data art." */
export function openingHint(suits: string[], styles: OpeningStyleOut[]): string {
  const label = (id: string) => styles.find((s) => s.id === id)?.label ?? id
  const fits = suits.filter((s) => !OPEN_STYLES.includes(s)).map(label)
  const lead = fits.length ? `Pitches ideas across ${listJoin(fits)}, plus` : 'Pitches'
  return `${lead} open visual metaphors and data art; a judge scores every idea, the best are drawn, and you pick from the top three.`
}

export function listJoin(items: string[]): string {
  if (items.length <= 1) return items.join('')
  return `${items.slice(0, -1).join(', ')} and ${items[items.length - 1]}`
}
