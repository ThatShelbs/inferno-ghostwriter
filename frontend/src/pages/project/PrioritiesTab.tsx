import { Ban, Star } from 'lucide-react'
import { useState } from 'react'

import { errorText } from '../../api/client'
import { useImagePriorities, useSetImagePriorities } from '../../api/hooks'
import { Button, Notice, Spinner, Switch } from '../../components/ui'
import { cx } from '../../lib/cx'
import { chartSummary, cyclePriority, groupTags, setPriority, type Priority } from '../../lib/studio'

/**
 * The chart of styles, formats and looks to favor or avoid. Each chip cycles Neutral -> Prefer -> Avoid. The chart
 * steers every new round of ideas and every random experiment in this post; a pin set on one image still wins.
 */
export function PrioritiesTab({ projectId }: { projectId: number }) {
  const { data, isLoading, error } = useImagePriorities(projectId)
  const save = useSetImagePriorities(projectId)
  // What the author changed here; until then the chart is the persona's defaults with this post's own choices on top.
  const [edited, setEdited] = useState<Record<string, string> | null>(null)
  const [asDefault, setAsDefault] = useState(false)
  const [saved, setSaved] = useState(false)
  const chart = edited ?? { ...data?.persona, ...data?.post }
  const setChart = (next: (current: Record<string, string>) => Record<string, string>) => setEdited(next(chart))

  if (isLoading) return <Spinner label="Loading the chart…" />
  if (error || !data) return <Notice tone="error">{error ? errorText(error) : 'Could not load the priorities.'}</Notice>

  const change = (tag: string) => {
    setSaved(false)
    setChart((current) => setPriority(current, tag, cyclePriority(current[tag] as Priority | undefined)))
  }

  return (
    <div className="space-y-5">
      <p className="text-sm text-muted">
        Tap a chip to prefer it (<Star className="inline size-3.5" aria-hidden />) or avoid it (<Ban className="inline size-3.5" aria-hidden />
        ); tap again to go neutral. Preferred styles are pitched first and looks come up more often; avoided ones are left out. It costs no extra model calls.
      </p>
      {groupTags(data.tags).map(({ group, tags }) => (
        <section key={group} aria-label={group} className="space-y-2">
          <h3 className="text-sm font-bold">{group}</h3>
          <div className="flex flex-wrap gap-1.5">
            {tags.map((tag) => {
              const state = chart[tag.id] as Priority | undefined
              return (
                <button
                  key={tag.id}
                  type="button"
                  title={tag.hint || undefined}
                  aria-label={`${tag.label}: ${state ?? 'neutral'}`}
                  aria-pressed={state !== undefined}
                  onClick={() => change(tag.id)}
                  className={cx(
                    'inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs',
                    state === 'prefer' && 'border-accent bg-accent-soft font-semibold',
                    state === 'avoid' && 'border-danger text-danger line-through',
                    state === undefined && 'border-line hover:border-accent',
                  )}
                >
                  {(tag.swatch ?? []).length > 0 && (
                    <span aria-hidden className="flex">
                      {(tag.swatch ?? []).map((color) => (
                        <span key={color} className="size-3 first:rounded-l-full last:rounded-r-full" style={{ backgroundColor: color }} />
                      ))}
                    </span>
                  )}
                  {state === 'prefer' && <Star className="size-3" aria-hidden />}
                  {state === 'avoid' && <Ban className="size-3" aria-hidden />}
                  {tag.label}
                </button>
              )
            })}
          </div>
        </section>
      ))}
      <div className="flex flex-wrap items-center gap-4 border-t border-line pt-4">
        <Button loading={save.isPending} onClick={() => save.mutate({ post: chart, save_as_default: asDefault }, { onSuccess: () => setSaved(true) })}>
          Save priorities
        </Button>
        <span className="flex items-center gap-2 text-sm">
          <Switch checked={asDefault} onChange={setAsDefault} label="Make this my default for every post" />
          Make this my default for every post
        </span>
        <span className="text-xs text-muted" aria-live="polite">
          {saved ? 'Saved. ' : ''}
          {chartSummary(chart)}
        </span>
      </div>
      {save.error && <Notice tone="error">{errorText(save.error)}</Notice>}
    </div>
  )
}
