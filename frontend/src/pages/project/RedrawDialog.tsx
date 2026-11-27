import { ChevronDown, Dices, ImagePlus, X } from 'lucide-react'
import { useRef, useState } from 'react'

import type { ImageRoute } from '../../api/hooks'
import type { ImageOut, RemixDimensionOut } from '../../api/types.gen'
import { Button, Dialog, Field, Select, Switch, Textarea } from '../../components/ui'
import { cx } from '../../lib/cx'
import { STEER_CHIPS, toggleSteer } from '../../lib/imageRoom'
import { remixSummary } from '../../lib/remix'
import { ImageModelPicker } from './ImageModelPicker'

const SURPRISE = 'auto'

/** One-click steers: each fills the note (a chip that is on shows as pressed). */
export function SteerChips({ note, onChange, label = 'Quick steers' }: { note: string; onChange: (note: string) => void; label?: string }) {
  const on = new Set(
    note
      .split(/\s*;\s*/)
      .map((p) => p.trim().toLowerCase())
      .filter(Boolean),
  )
  return (
    <div className="flex flex-wrap gap-1.5" role="group" aria-label={label}>
      {STEER_CHIPS.map((chip) => (
        <button
          key={chip}
          type="button"
          aria-pressed={on.has(chip.toLowerCase())}
          onClick={() => onChange(toggleSteer(note, chip))}
          className={cx(
            'rounded-full border px-2.5 py-0.5 text-xs',
            on.has(chip.toLowerCase()) ? 'border-accent bg-accent-soft font-semibold' : 'border-line hover:border-accent',
          )}
        >
          {chip}
        </button>
      ))}
    </div>
  )
}

/**
 * Redraw with options: steer it in a word or two, pin what it experiments with (colors, who is in it, staging,
 * medium), skip the critique, pick the model, or give it a style reference. The plain Redraw button is the same
 * redraw with every option left to the app.
 */
export function RedrawDialog({
  open,
  onClose,
  image,
  dimensions,
  onRedraw,
  models = [],
  referenceUrl,
  onReference,
  onClearReference,
}: {
  open: boolean
  onClose: () => void
  image: ImageOut
  /** The whole catalog; only the dimensions this image can vary are shown */
  dimensions: RemixDimensionOut[]
  onRedraw: (tweaks: Record<string, string>, improve: boolean, note: string, model: ImageRoute) => void
  /** The models the author may choose from (empty: no optional model is signed in, so no choice is shown). */
  models?: ImageRoute[]
  /** The author's style reference for this image, if any, and how to set or clear it. */
  referenceUrl?: string | null
  onReference?: (file: File) => void
  onClearReference?: () => void
}) {
  const [picks, setPicks] = useState<Record<string, string>>({})
  const [improve, setImprove] = useState(true)
  const [note, setNote] = useState('')
  const [model, setModel] = useState<ImageRoute>('auto')
  const [experiments, setExperiments] = useState(false)
  const fileInput = useRef<HTMLInputElement>(null)
  const shown = dimensions.filter((d) => (image.remix_dimensions ?? []).includes(d.id))
  const last = remixSummary(image.remix)
  const pinned = Object.fromEntries(Object.entries(picks).filter(([, id]) => id && id !== SURPRISE))
  const upload = image.provider === 'upload'

  return (
    <Dialog open={open} onClose={onClose} title="Redraw options">
      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault()
          onRedraw(pinned, improve, note.trim(), model)
        }}
      >
        <p className="text-sm text-muted">
          {upload
            ? 'Your picture is drawn again in this post’s style, so you can edit it and build on it. It stays in Versions.'
            : 'The same idea, drawn better. Steer it, or leave everything as it is. The current version stays in Versions.'}
        </p>
        {last && <p className="text-xs text-muted">Last redraw: {last}</p>}
        <Field label="Steer it (optional)" hint="Tap a quick steer or say it in your own words." htmlFor={`redraw-note-${image.id}`}>
          <div className="space-y-2">
            <SteerChips note={note} onChange={setNote} />
            <Textarea id={`redraw-note-${image.id}`} rows={2} maxLength={500} value={note} onChange={(e) => setNote(e.target.value)} />
          </div>
        </Field>

        {shown.length > 0 && !upload && (
          <div className="rounded-xl border border-line">
            <button
              type="button"
              aria-expanded={experiments}
              onClick={() => setExperiments(!experiments)}
              className="flex w-full items-center justify-between px-3 py-2 text-left text-sm font-semibold"
            >
              Experiment with…
              <ChevronDown className={cx('size-4 transition-transform', experiments && 'rotate-180')} aria-hidden />
            </button>
            {experiments && (
              <div className="space-y-3 border-t border-line p-3">
                <p className="text-xs text-muted">Anything left on Surprise me is picked for you, avoiding what the last redraws tried.</p>
                {shown.map((dimension) => {
                  const id = `remix-${image.id}-${dimension.id}`
                  const chosen = dimension.options.find((o) => o.id === picks[dimension.id])
                  return (
                    <Field key={dimension.id} label={dimension.label} htmlFor={id}>
                      <div className="flex items-center gap-3">
                        <Select id={id} value={picks[dimension.id] ?? SURPRISE} onChange={(e) => setPicks({ ...picks, [dimension.id]: e.target.value })}>
                          <option value={SURPRISE}>Surprise me</option>
                          {dimension.options.map((option) => (
                            <option key={option.id} value={option.id}>
                              {option.label}
                            </option>
                          ))}
                        </Select>
                        {chosen && (chosen.swatch ?? []).length > 0 && (
                          <span aria-hidden className="flex shrink-0">
                            {(chosen.swatch ?? []).map((color) => (
                              <span key={color} className="size-4 first:rounded-l-full last:rounded-r-full" style={{ backgroundColor: color }} />
                            ))}
                          </span>
                        )}
                      </div>
                    </Field>
                  )
                })}
              </div>
            )}
          </div>
        )}

        {onReference && (
          <div className="flex flex-wrap items-center gap-3 rounded-xl border border-line p-3" aria-label="Style reference">
            {referenceUrl ? <img src={referenceUrl} alt="Your style reference" className="h-12 rounded-md border border-line" /> : null}
            <p className="min-w-48 flex-1 text-xs text-muted">
              {referenceUrl
                ? 'Every draw of this image aims for the look of your reference (never its content).'
                : 'Make it like this: attach any image whose look you want; the designer and the judge both see it.'}
            </p>
            <Button size="sm" variant="secondary" icon={<ImagePlus className="size-4" />} onClick={() => fileInput.current?.click()}>
              {referenceUrl ? 'Change reference' : 'Add a style reference'}
            </Button>
            {referenceUrl && onClearReference && (
              <Button size="sm" variant="ghost" icon={<X className="size-4" />} onClick={onClearReference}>
                Remove
              </Button>
            )}
            <input
              ref={fileInput}
              type="file"
              accept="image/*"
              className="hidden"
              aria-label="Upload a style reference"
              onChange={(e) => {
                const file = e.target.files?.[0]
                if (file) onReference(file)
                e.target.value = ''
              }}
            />
          </div>
        )}

        <ImageModelPicker id={`remix-model-${image.id}`} value={model} onChange={setModel} models={models} />
        {!upload && (
          <div className="flex items-center gap-3">
            <Switch checked={improve} onChange={setImprove} label="Critique first" />
            <span className="text-sm">Let Claude critique the current picture first and fix its weakest point</span>
          </div>
        )}
        <Button type="submit" icon={<Dices className="size-4" />}>
          Redraw
        </Button>
      </form>
    </Dialog>
  )
}
