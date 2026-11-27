import { ChevronDown, Dices, SlidersHorizontal } from 'lucide-react'
import { useMemo, useState } from 'react'

import { errorText } from '../../api/client'
import { useImageFormats, useImageModels, useImageMutations, useRemixOptions, type ImageRoute } from '../../api/hooks'
import type { ImageFormatOut, ImageOut, ProjectOut, RemixDimensionOut } from '../../api/types.gen'
import { Button, Dialog, Field, Input, Notice, Select, Switch, Textarea } from '../../components/ui'
import { Tabs } from '../../components/tabs'
import { cx } from '../../lib/cx'
import { panelDomId } from '../../lib/tabs'
import {
  AUTO,
  KEEP,
  NEXT,
  applyToAll,
  buildRequest,
  drawable,
  emptyDraft,
  initialDrafts,
  roomFor,
  runSize,
  slotName,
  slotSummary,
  type SlotDraft,
} from '../../lib/studio'
import { SteerChips } from './RedrawDialog'
import { PrioritiesTab } from './PrioritiesTab'

type StudioTab = 'slots' | 'priorities'

/** Colors a meme may use (the house ramps); a meme drawn in any other palette would clash with the post. */
const HOUSE_PALETTES = ['inferno', 'magma', 'viridis']
const WAYS = 'Ways to draw it'
const OPENING = 'Opening styles'

const MODEL_LABEL: Record<ImageRoute, string> = { auto: 'Auto', claude: 'Claude', codex: 'ChatGPT', gemini: 'Gemini' }

const isMeme = (format: ImageFormatOut) => format.group !== WAYS && format.group !== OPENING

/**
 * Image studio: one place to steer every image in the post. Start the whole set over (with a note), or give each
 * slot its own idea, look and model, or run a single slot. The same controls the cards have, side by side.
 */
export function ImageStudio({
  open,
  onClose,
  project,
  onStarted,
}: {
  open: boolean
  onClose: () => void
  project: ProjectOut
  /** The job that was started, so the page can show its progress. */
  onStarted: (jobId: string) => void
}) {
  const [tab, setTab] = useState<StudioTab>('slots')
  const images = useMemo(() => drawable(project.images ?? []), [project.images])
  const models = useImageModels()
  const { redrawAll } = useImageMutations(project.id)
  const { data: dimensions = [] } = useRemixOptions(open)
  const memeBank = useImageFormats('meme', '', open)
  // Only what the author changed is stored; every slot of the post has a draft (a slot that appeared later starts plain).
  const [edits, setEdits] = useState<Record<number, SlotDraft>>({})
  const drafts = useMemo(() => ({ ...initialDrafts(images), ...edits }), [images, edits])
  const [fresh, setFresh] = useState(true)
  const [note, setNote] = useState('')
  const [model, setModel] = useState<ImageRoute>('auto')
  const [improve, setImprove] = useState(true)

  const count = runSize(drafts)
  const patch = (id: number, change: Partial<SlotDraft>) => setEdits({ ...edits, [id]: { ...(drafts[id] ?? emptyDraft()), ...change } })
  const run = (only?: number) =>
    redrawAll.mutate(buildRequest(drafts, { fresh, note, model, improve }, only), {
      onSuccess: (job) => {
        onStarted(job.id)
        onClose()
      },
    })

  return (
    <Dialog open={open} onClose={onClose} title="Image studio" huge>
      <div className="space-y-4">
        <Tabs
          variant="segmented"
          label="Image studio"
          idPrefix="studio"
          value={tab}
          onChange={setTab}
          tabs={[
            { id: 'slots', label: `Slots (${images.length})` },
            { id: 'priorities', label: 'Priorities' },
          ]}
        />
        {tab === 'priorities' ? (
          <div role="tabpanel" id={panelDomId('studio', 'priorities')} aria-labelledby="studio-tab-priorities">
            <PrioritiesTab projectId={project.id} />
          </div>
        ) : (
          <div role="tabpanel" id={panelDomId('studio', 'slots')} aria-labelledby="studio-tab-slots" className="space-y-4">
            {images.length === 0 ? (
              <Notice tone="info">This post has no drawn images to steer yet.</Notice>
            ) : (
              <>
                <section aria-label="Start over" className="space-y-3 rounded-xl border border-line bg-surface-2 p-4">
                  <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
                    <span className="flex items-center gap-2 text-sm font-semibold">
                      <Switch checked={fresh} onChange={setFresh} label="Pitch all-new ideas" />
                      {fresh ? 'Start over: pitch all-new ideas' : 'Keep each slot’s idea, just redraw it'}
                    </span>
                    {!fresh && (
                      <span className="flex items-center gap-2 text-sm">
                        <Switch checked={improve} onChange={setImprove} label="Critique first" />
                        Critique each picture first
                      </span>
                    )}
                    {models.length > 0 && (
                      <label className="flex items-center gap-2 text-sm">
                        <span className="font-semibold">Model</span>
                        <Select className="w-40" aria-label="Model for the whole run" value={model} onChange={(e) => setModel(e.target.value as ImageRoute)}>
                          {models.map((m) => (
                            <option key={m} value={m}>
                              {MODEL_LABEL[m]}
                            </option>
                          ))}
                        </Select>
                      </label>
                    )}
                  </div>
                  <Field label="Feedback for every slot (optional)" hint="Say what to change in your own words, or tap a quick steer." htmlFor="studio-note">
                    <div className="space-y-2">
                      <SteerChips note={note} onChange={setNote} />
                      <Textarea
                        id="studio-note"
                        rows={2}
                        maxLength={500}
                        value={note}
                        onChange={(e) => setNote(e.target.value)}
                        placeholder="More like a subway map, fewer words…"
                      />
                    </div>
                  </Field>
                </section>

                <AllSlotsRow
                  dimensions={dimensions}
                  memeBank={memeBank.data ?? []}
                  models={models}
                  fresh={fresh}
                  onChange={(change) => setEdits(applyToAll(drafts, change))}
                />

                <ul className="space-y-2" aria-label="Slots">
                  {images.map((image) => (
                    <SlotRow
                      key={image.id}
                      image={image}
                      draft={drafts[image.id] ?? emptyDraft()}
                      dimensions={dimensions}
                      models={models}
                      fresh={fresh}
                      busy={redrawAll.isPending}
                      onChange={(change) => patch(image.id, change)}
                      onRunOne={() => run(image.id)}
                    />
                  ))}
                </ul>

                {redrawAll.error && <Notice tone="error">{errorText(redrawAll.error)}</Notice>}
                <div className="flex flex-wrap items-center gap-3 border-t border-line pt-4">
                  <Button variant="flame" icon={<Dices className="size-4" />} loading={redrawAll.isPending} disabled={count === 0} onClick={() => run()}>
                    {fresh ? `Start over: ${count} ${count === 1 ? 'image' : 'images'}` : `Redraw ${count} ${count === 1 ? 'image' : 'images'}`}
                  </Button>
                  <p className="text-xs text-muted">Earlier versions stay under Versions on each image. Uploads and hands-on charts are left alone.</p>
                </div>
              </>
            )}
          </div>
        )}
      </div>
    </Dialog>
  )
}

/** The look controls shared by the "All slots" row and every slot row. */
function PaletteSelect({
  id,
  dimension,
  houseOnly,
  value,
  onChange,
}: {
  id: string
  dimension: RemixDimensionOut | undefined
  houseOnly: boolean
  value: string
  onChange: (id: string) => void
}) {
  if (!dimension) return null
  const options = dimension.options.filter((o) => !houseOnly || HOUSE_PALETTES.includes(o.id))
  const chosen = options.find((o) => o.id === value)
  return (
    <div className="flex items-center gap-2">
      <Select id={id} aria-label="Colors" value={value} onChange={(e) => onChange(e.target.value)}>
        <option value={AUTO}>Colors: surprise me</option>
        {options.map((o) => (
          <option key={o.id} value={o.id}>
            {o.label}
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
  )
}

function ModelSelect({
  id,
  models,
  value,
  onChange,
  unset,
}: {
  id: string
  models: ImageRoute[]
  value: ImageRoute | ''
  onChange: (m: ImageRoute | '') => void
  unset: string
}) {
  if (models.length === 0) return null
  return (
    <Select id={id} aria-label="Model" value={value} onChange={(e) => onChange(e.target.value as ImageRoute | '')}>
      <option value="">{unset}</option>
      {models.map((m) => (
        <option key={m} value={m}>
          {MODEL_LABEL[m]}
        </option>
      ))}
    </Select>
  )
}

/** Set one thing for every slot at once; a slot can still be changed afterwards (it then differs from the rest). */
function AllSlotsRow({
  dimensions,
  memeBank,
  models,
  fresh,
  onChange,
}: {
  dimensions: RemixDimensionOut[]
  memeBank: ImageFormatOut[]
  models: ImageRoute[]
  fresh: boolean
  onChange: (change: Partial<Pick<SlotDraft, 'concept' | 'model' | 'note'>> & { look?: { dimension: string; id: string } }) => void
}) {
  const [palette, setPalette] = useState(AUTO)
  const [concept, setConcept] = useState(KEEP)
  const [model, setModel] = useState<ImageRoute | ''>('')
  return (
    <section aria-label="All slots" className="space-y-2 rounded-xl border border-dashed border-line p-3">
      <h3 className="text-sm font-bold">All slots at once</h3>
      <div className="grid gap-2 sm:grid-cols-3">
        <Select
          aria-label="Idea for all slots"
          value={concept}
          onChange={(e) => {
            setConcept(e.target.value)
            onChange({ concept: e.target.value })
          }}
        >
          <option value={KEEP}>Idea: {fresh ? 'a new one each' : 'keep each'}</option>
          <option value={NEXT}>Idea: the next one each</option>
          {groupFormats(memeBank).map(({ group, formats }) => (
            <optgroup key={group} label={`Make every slot a meme · ${group}`}>
              {formats.map((f) => (
                <option key={f.id} value={f.id}>
                  {f.label}
                </option>
              ))}
            </optgroup>
          ))}
        </Select>
        <PaletteSelect
          id="studio-all-palette"
          dimension={dimensions.find((d) => d.id === 'palette')}
          houseOnly={concept !== KEEP && concept !== NEXT}
          value={palette}
          onChange={(id) => {
            setPalette(id)
            onChange({ look: { dimension: 'palette', id } })
          }}
        />
        <ModelSelect
          id="studio-all-model"
          models={models}
          value={model}
          unset="Model: the run’s"
          onChange={(m) => {
            setModel(m)
            onChange({ model: m })
          }}
        />
      </div>
      <p className="text-xs text-muted">Sets the choice on every slot below. Change any slot afterwards to make it different.</p>
    </section>
  )
}

function groupFormats(formats: ImageFormatOut[]): { group: string; formats: ImageFormatOut[] }[] {
  return [...new Set(formats.map((f) => f.group))].map((group) => ({ group, formats: formats.filter((f) => f.group === group) }))
}

function SlotRow({
  image,
  draft,
  dimensions,
  models,
  fresh,
  busy,
  onChange,
  onRunOne,
}: {
  image: ImageOut
  draft: SlotDraft
  dimensions: RemixDimensionOut[]
  models: ImageRoute[]
  fresh: boolean
  busy: boolean
  onChange: (change: Partial<SlotDraft>) => void
  onRunOne: () => void
}) {
  const [more, setMore] = useState(false)
  const formats = useImageFormats(roomFor(image), image.kind).data ?? []
  const picked = formats.find((f) => f.id === draft.concept)
  // A meme (or any slot turning into one) may only use the house color ramps.
  const memeLike = image.kind === 'meme' || image.kind === 'hero' || (picked !== undefined && isMeme(picked))
  const extraDimensions = dimensions.filter((d) => d.id !== 'palette' && (image.remix_dimensions ?? []).includes(d.id))
  const id = `studio-${image.id}`
  const groups = groupFormats(formats)

  return (
    <li className={cx('rounded-xl border p-3', draft.include ? 'border-line' : 'border-line opacity-60')} aria-label={slotName(image)}>
      <div className="flex flex-wrap items-center gap-3">
        <input
          type="checkbox"
          className="size-4 accent-[var(--app-accent)]"
          checked={draft.include}
          onChange={(e) => onChange({ include: e.target.checked })}
          aria-label={`Include ${slotName(image)}`}
        />
        {image.url ? (
          <img src={image.url} alt="" className="h-10 w-[4.5rem] rounded-md border border-line object-cover" />
        ) : (
          <span className="h-10 w-[4.5rem] rounded-md border border-line bg-sunken" />
        )}
        <div className="min-w-40 flex-1">
          <p className="text-sm font-semibold">{slotName(image)}</p>
          <p className="text-xs text-muted">{slotSummary(draft, formats, fresh)}</p>
        </div>
        <Button
          size="sm"
          variant="secondary"
          icon={<Dices className="size-4" />}
          disabled={busy}
          onClick={onRunOne}
          title="Draw only this slot, with exactly these choices"
        >
          Draw this slot
        </Button>
        <Button
          size="sm"
          variant="ghost"
          icon={more ? <ChevronDown className="size-4 rotate-180" /> : <SlidersHorizontal className="size-4" />}
          aria-expanded={more}
          onClick={() => setMore(!more)}
        >
          More
        </Button>
      </div>
      <div className="mt-2 grid gap-2 sm:grid-cols-3">
        <Select id={`${id}-concept`} aria-label="Idea" value={draft.concept} onChange={(e) => onChange({ concept: e.target.value })}>
          <option value={KEEP}>Idea: {fresh ? 'a new one' : 'keep the one on show'}</option>
          <option value={NEXT}>Idea: the next one</option>
          {groups.map(({ group, formats: items }) => (
            <optgroup key={group} label={group}>
              {items.map((f) => (
                <option key={f.id} value={f.id}>
                  {f.label}
                </option>
              ))}
            </optgroup>
          ))}
        </Select>
        <PaletteSelect
          id={`${id}-palette`}
          dimension={dimensions.find((d) => d.id === 'palette')}
          houseOnly={memeLike}
          value={draft.look.palette ?? AUTO}
          onChange={(value) => onChange({ look: { ...draft.look, palette: value } })}
        />
        <ModelSelect id={`${id}-model`} models={models} value={draft.model} unset="Model: the run’s" onChange={(m) => onChange({ model: m })} />
      </div>
      {more && (
        <div className="mt-2 grid gap-2 border-t border-line pt-2 sm:grid-cols-3">
          {extraDimensions.map((dimension) => (
            <Field key={dimension.id} label={dimension.label} htmlFor={`${id}-${dimension.id}`}>
              <Select
                id={`${id}-${dimension.id}`}
                value={draft.look[dimension.id] ?? AUTO}
                onChange={(e) => onChange({ look: { ...draft.look, [dimension.id]: e.target.value } })}
              >
                <option value={AUTO}>Surprise me</option>
                {dimension.options.map((o) => (
                  <option key={o.id} value={o.id}>
                    {o.label}
                  </option>
                ))}
              </Select>
            </Field>
          ))}
          <div className="sm:col-span-3">
            <Field label="A note for this slot only" htmlFor={`${id}-note`} hint="Replaces the feedback above for this slot.">
              <Input id={`${id}-note`} maxLength={500} value={draft.note} onChange={(e) => onChange({ note: e.target.value })} />
            </Field>
          </div>
        </div>
      )}
    </li>
  )
}
