import type { PitchOut } from '../api/types.gen'

/** The pitches best first: usable ones by the judge's score (pitch order when not judged), ruled-out ones last. */
export function rankPitches(pitches: PitchOut[]): PitchOut[] {
  return [...pitches].sort((a, b) => Number(a.ruled_out) - Number(b.ruled_out) || (b.score ?? -1) - (a.score ?? -1) || a.index - b.index)
}

/** A judge's score as the board shows it: "7.5/10". */
export function scoreLabel(score: number): string {
  return `${Number.isInteger(score) ? score : score.toFixed(1)}/10`
}

/** How each image kind is named on its card. */
export const KIND_LABEL: Record<string, string> = {
  hero: 'Opening image',
  diagram: 'Diagram',
  chart: 'Chart',
  illustration: 'Illustration',
  icon: 'Icons',
  meme: 'Closing meme',
  screenshot: 'Screenshot',
}
