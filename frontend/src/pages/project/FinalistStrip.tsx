import type { FinalistOut } from '../../api/types.gen'
import { cx } from '../../lib/cx'
import { scoreLabel } from '../../lib/imageRoom'

/** The best few candidates of the image's last fresh run. Clicking one shows it instead; Claude is not asked. */
export function FinalistStrip({ finalists, disabled, onPick }: { finalists: FinalistOut[]; disabled?: boolean; onPick: (index: number) => void }) {
  if (finalists.length < 2) return null
  return (
    <div className="mt-3" aria-label="Finalists">
      <p className="mb-2 text-center text-xs text-muted">The judge&rsquo;s top {finalists.length}: pick the one you like.</p>
      <div className="flex justify-center gap-2">
        {finalists.map((f) => (
          <button
            key={f.index}
            type="button"
            disabled={disabled || f.current}
            aria-pressed={f.current}
            aria-label={`Finalist ${f.index + 1}: ${f.label}`}
            title={[f.label, f.reads_as && `Reads as: ${f.reads_as}`, f.score != null && scoreLabel(f.score)].filter(Boolean).join('\n')}
            onClick={() => onPick(f.index)}
            className={cx(
              'w-28 overflow-hidden rounded-lg border-2 bg-sunken transition',
              f.current ? 'border-accent' : 'border-transparent opacity-80 hover:border-line hover:opacity-100',
            )}
          >
            <img src={f.url} alt="" className="aspect-video w-full object-cover" />
          </button>
        ))}
      </div>
    </div>
  )
}
