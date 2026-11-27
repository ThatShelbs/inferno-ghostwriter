import { useQueryClient } from '@tanstack/react-query'
import { ChevronDown, Dices, History, ImagePlus, Layers, Lightbulb, PencilLine, SkipForward, Type, Undo2, Wand2 } from 'lucide-react'
import { useRef, useState } from 'react'
import { Link } from 'react-router'

import { errorText } from '../../api/client'
import { keys, useImageFormats, useImageModels, useImageMutations, useRemixOptions, type RedrawPicks } from '../../api/hooks'
import type { ImageOut } from '../../api/types.gen'
import { useJob } from '../../api/useJob'
import { Badge, Button, Notice, Spinner } from '../../components/ui'
import { fullCaption } from '../../lib/article'
import { cx } from '../../lib/cx'
import { kindLabel } from '../../lib/imageRoom'
import { buildOnChoices, dependentsOf, remixTwists } from '../../lib/remix'
import { textSyncNote, type TextSyncNote } from '../../lib/textSync'
import { FinalistStrip } from './FinalistStrip'
import { BuildOnDialog, CaptionDialog, EditDialog, VersionsDialog } from './ImageDialogs'
import { ImageRoomDialog, type PitchEdit } from './ImageRoomDialog'
import { RedrawDialog } from './RedrawDialog'
import { WordsDialog } from './WordsDialog'

/** How a hands-on image names the library its code is about (the server sends the import name). */
const HANDS_ON_LIBRARY: Record<string, string> = {
  matplotlib: 'Matplotlib',
  seaborn: 'Seaborn',
  plotly: 'Plotly',
  altair: 'Altair',
  bokeh: 'Bokeh',
  plotnine: 'plotnine',
  pandas: 'pandas',
}

type Open = 'ideas' | 'redraw' | 'words' | 'edit' | 'caption' | 'versions' | 'build' | null

/**
 * One image in the post. Every image, whatever its kind, has the same tools: Ideas (its room), Redraw (one click, or
 * with options), Edit, Words (when it has text), Replace, Versions, Builds on (in-body images) and Caption, plus the
 * finalist strip. An upload has them too: it is recreated from its picture when it is edited or redrawn.
 */
export function ImageCard({ projectId, image, images = [] }: { projectId: number; image: ImageOut; images?: ImageOut[] }) {
  const qc = useQueryClient()
  const mutations = useImageMutations(projectId)
  const models = useImageModels()
  const [jobId, setJobId] = useState<string | null>(null)
  const [open, setOpen] = useState<Open>(null)
  const fileInput = useRef<HTMLInputElement>(null)
  const [textNote, setTextNote] = useState<TextSyncNote | null>(null)
  // Set when a redraw of this image leaves the images that build on it drawn from its old version.
  const [unmatched, setUnmatched] = useState(false)
  // What the running job is doing, in the author's words ("Drawing that idea…").
  const [action, setAction] = useState('')
  // A new version was just made: one click brings the previous one back (no model call).
  const [undoable, setUndoable] = useState(false)
  const job = useJob(jobId, (state) => {
    setJobId(null)
    setTextNote(textSyncNote(state))
    setUnmatched(((state.result?.dependents as string[] | undefined) ?? []).length > 0)
    setUndoable(state.status === 'succeeded')
    void qc.invalidateQueries({ queryKey: keys.project(projectId) })
  })
  const tracked = [
    mutations.redraw,
    mutations.edit,
    mutations.buildOn,
    mutations.matchDependents,
    mutations.upload,
    mutations.pick,
    mutations.revert,
    mutations.words,
    mutations.setReference,
    mutations.clearReference,
    mutations.update,
  ]
  // Busy from the click on (not only once a job runs), so a double click never starts two jobs.
  const busy = !!jobId || tracked.some((m) => m.isPending)
  // Any refused request is shown on the card (a refused redraw used to vanish).
  const failed = tracked.find((m) => m !== mutations.words && m.error)
  const clearErrors = () => tracked.forEach((m) => m.reset())
  const upload = image.provider === 'upload'
  const editable = !['placeholder', ''].includes(image.provider)
  const room = image.room ?? null
  const formats = useImageFormats(room?.room ?? 'body', image.kind, open === 'ideas' && !!room)
  const remixOptions = useRemixOptions(open === 'redraw')
  // A hands-on data viz picture is whatever the code above it draws: no pitches, remixes or words, just rerun and edit the code.
  const handsOn = image.kind === 'hands_on_viz'
  const needsCodeSetting = handsOn && image.status === 'error' && /run example code/i.test(image.error ?? '')
  // Images that build on each other share one source, so they look like the same data taken further.
  const bases = buildOnChoices(image, images)
  const base = images.find((other) => other.slot_id === image.builds_on)
  const dependents = dependentsOf(image, images)
  const nameOf = (slotId: string) => {
    const other = images.find((i) => i.slot_id === slotId)
    return other ? `${kindLabel(other)} "${other.caption || other.purpose}"` : slotId
  }
  const started = (label: string) => (j: { id: string }) => {
    setAction(label)
    setUndoable(false)
    setJobId(j.id)
  }
  const redraw = (rethink: boolean, picks: RedrawPicks = {}, label = upload ? 'Recreating your picture…' : 'Redrawing…') => {
    setOpen(null)
    clearErrors()
    mutations.redraw.mutate({ id: image.id, rethink, ...picks }, { onSuccess: started(label) })
  }
  const restore = (index: number) => {
    setOpen(null)
    clearErrors()
    setAction('Bringing that version back…')
    mutations.revert.mutate({ id: image.id, index }, { onSuccess: () => setUndoable(index !== image.history.length - 2) })
  }
  const slots = room?.slots ?? []
  const label = image.kind === 'hero' && room?.format_label ? `Opening image · ${room.format_label}` : kindLabel(image)

  return (
    <figure className="group my-8 font-sans not-italic">
      {/* The opening image is the thumbnail and often carries a headline, so its label sits above it, not on it. */}
      {image.kind === 'hero' && (
        <div className="mb-2 flex justify-center">
          <Badge tone="accent">{label}</Badge>
        </div>
      )}
      <div className="relative overflow-hidden rounded-xl border border-line bg-sunken">
        {image.url ? (
          <img src={image.url} alt={image.alt} className={cx('w-full', busy && 'opacity-40')} />
        ) : (
          <div className="flex aspect-video items-center justify-center p-6 text-center text-sm text-muted">
            {image.status === 'pending' ? <Spinner label="Creating image…" /> : image.purpose}
          </div>
        )}
        {busy && (
          <div className="absolute inset-0 flex items-center justify-center">
            <span className="rounded-full bg-surface px-4 py-2 shadow">
              <Spinner label={(jobId && job.message) || action || 'Working…'} />
            </span>
          </div>
        )}
        {image.kind !== 'hero' && (
          <div className="absolute top-2 left-2">
            <Badge tone="accent">{upload ? `${label} · your picture` : label}</Badge>
          </div>
        )}
      </div>

      {fullCaption(image) && <figcaption className="mt-2 text-center text-sm text-muted">{fullCaption(image)}</figcaption>}
      <FinalistStrip finalists={image.finalists ?? []} disabled={busy} onPick={(index) => mutations.pick.mutate({ id: image.id, index })} />
      {room?.why && !busy && (
        <p className="mt-1 text-center text-xs text-muted" aria-label="Why the judge picked this one">
          Why this one: {/[.!?]$/.test(room.why) ? room.why : `${room.why}.`}
        </p>
      )}
      {image.status === 'error' && (
        <Notice tone="error">
          {image.error}
          {needsCodeSetting && (
            <>
              {' '}
              <Link to="/settings" className="font-semibold underline">
                Open Settings
              </Link>
            </>
          )}
        </Notice>
      )}
      {handsOn && image.hands_on && !busy && (
        <p className="mt-1 text-center text-xs text-muted" aria-label="The code behind this picture">
          Made by running the code above: {image.hands_on.lines} lines
          {image.hands_on.library ? ` of ${HANDS_ON_LIBRARY[image.hands_on.library] ?? image.hands_on.library}` : ''},{' '}
          {image.hands_on.chars.toLocaleString('en-US')} characters
        </p>
      )}
      {handsOn && image.hands_on?.stale && !busy && (
        <div className="mt-2">
          <Notice tone="warn" title="The code above changed since this picture was made">
            <Button size="sm" variant="secondary" className="mt-2" icon={<Dices className="size-4" />} onClick={() => redraw(false, {}, 'Running the code…')}>
              Rerun code
            </Button>
          </Notice>
        </div>
      )}
      {job.status === 'failed' && <Notice tone="error">{job.error}</Notice>}
      {failed?.error && <Notice tone="error">{errorText(failed.error)}</Notice>}
      {undoable && !busy && image.history.length > 1 && (
        <p className="mt-1 text-center text-xs text-muted" aria-label="Undo">
          New version on show.{' '}
          <button type="button" className="inline-flex items-center gap-0.5 font-semibold underline" onClick={() => restore(image.history.length - 2)}>
            <Undo2 className="size-3" aria-hidden />
            Undo
          </button>
        </p>
      )}
      {textNote && !busy && (
        <div className="mt-2">
          <Notice tone={textNote.tone} title="Text updated to match">
            {textNote.text}
          </Notice>
        </div>
      )}
      {image.remix && !busy && (image.remix.brainstormed || image.remix.tweaks.length > 0) && (
        <p className="mt-1 text-center text-xs text-muted" aria-label="What the last redraw tried">
          {image.remix.brainstormed && image.remix.improvements[0] ? `Last redraw set out to: ${image.remix.improvements[0].replace(/\.$/, '')}. ` : ''}
          {remixTwists(image.remix) ? `Tried ${remixTwists(image.remix)}.` : ''}
        </p>
      )}
      {image.reference_url && !busy && <p className="mt-1 text-center text-xs text-muted">Style reference on: every draw aims for its look.</p>}
      {base && <p className="mt-1 text-center text-xs text-muted">Builds on the {nameOf(base.slot_id)}: same data and look, taken further.</p>}
      {unmatched && dependents.length > 0 && !busy && (
        <div className="mt-2">
          <Notice tone="warn" title="Other images build on this one">
            <p>
              {dependents.map(nameOf).join(', ')} {dependents.length === 1 ? 'was' : 'were'} drawn from the previous version.
            </p>
            <Button
              size="sm"
              variant="secondary"
              className="mt-2"
              icon={<Layers className="size-4" />}
              loading={mutations.matchDependents.isPending}
              onClick={() =>
                mutations.matchDependents.mutate(image.id, {
                  onSuccess: (j) => {
                    setUnmatched(false)
                    started('Redrawing the images that build on it…')(j)
                  },
                })
              }
            >
              Redraw {dependents.length === 1 ? 'it' : 'them'} to match
            </Button>
          </Notice>
        </div>
      )}
      {room?.fallback_from && (
        <p className="mt-1 text-center text-xs text-muted">
          The first pick ({room.fallback_from}) could not be drawn, so this is the next best idea. Open Ideas to see them all.
        </p>
      )}
      {room && (room.sources ?? []).length > 0 && (
        <p className="mt-1 text-center text-xs text-muted">
          Sources:{' '}
          {(room.sources ?? []).map((source, i) => (
            <span key={source.title}>
              {i > 0 && '; '}
              {source.url ? (
                <a href={source.url} target="_blank" rel="noreferrer" className="underline">
                  {source.title}
                </a>
              ) : (
                source.title
              )}
            </span>
          ))}
        </p>
      )}
      {image.kind === 'screenshot' && image.provider === 'claude-svg' && (
        <p className="mt-2 text-center text-xs text-muted">Claude drew this mock screen. Use Replace if you have the real screenshot.</p>
      )}

      <div className="mt-3 flex flex-wrap justify-center gap-2" aria-label={`Actions for ${kindLabel(image)}`}>
        {!handsOn && (
          <Button
            size="sm"
            variant="secondary"
            icon={<Lightbulb className="size-4" />}
            onClick={() => (room ? setOpen('ideas') : redraw(true, { pitch: true }, 'Pitching ideas…'))}
            disabled={busy}
            title="Every idea pitched for this image: pick one, adjust one, pitch new ones or try another format"
          >
            Ideas
          </Button>
        )}
        {!handsOn && room && (room.ideas_left ?? 0) > 0 && (
          <Button
            size="sm"
            variant="secondary"
            icon={<SkipForward className="size-4" />}
            onClick={() => redraw(true, {}, 'Drawing the next idea…')}
            disabled={busy}
            title="Replace this image with the next idea pitched for it (no new pitching)"
          >
            Next idea
          </Button>
        )}
        <span className="inline-flex">
          <Button
            size="sm"
            variant="secondary"
            icon={<Dices className="size-4" />}
            className={handsOn ? undefined : 'rounded-r-none'}
            onClick={() => redraw(false, {}, handsOn ? 'Running the code…' : undefined)}
            disabled={busy}
            title={
              handsOn
                ? 'Run the code above again and keep the chart it draws'
                : upload
                  ? 'Draw your picture again in this post’s style (then you can edit it and build on it)'
                  : 'Redraw the same idea, better: Claude critiques it first and fixes its weakest point'
            }
          >
            {handsOn ? 'Rerun code' : 'Redraw'}
          </Button>
          {!handsOn && (
            <Button
              size="sm"
              variant="secondary"
              className="rounded-l-none border-l-0 px-1.5"
              icon={<ChevronDown className="size-4" />}
              onClick={() => setOpen('redraw')}
              disabled={busy}
              aria-label="Redraw options"
              title="Steer the redraw, pin what it experiments with, or add a style reference"
            />
          )}
        </span>
        {(editable || handsOn) && (
          <Button
            size="sm"
            variant="secondary"
            icon={<Wand2 className="size-4" />}
            onClick={() => setOpen('edit')}
            disabled={busy}
            title={
              handsOn
                ? 'Tell Claude what to change in the code; it updates the post and runs it again'
                : upload
                  ? 'Say what to change in your picture; it is recreated with the change'
                  : 'Tell Claude what to change; the rest stays'
            }
          >
            {handsOn ? 'Edit code' : 'Edit'}
          </Button>
        )}
        {!handsOn && slots.length > 0 && (
          <Button
            size="sm"
            variant="secondary"
            icon={<Type className="size-4" />}
            onClick={() => {
              mutations.words.reset()
              setOpen('words')
            }}
            disabled={busy}
            title="Retype the text; the picture stays and Claude is not asked"
          >
            Words
          </Button>
        )}
        <Button
          size="sm"
          variant="secondary"
          icon={<ImagePlus className="size-4" />}
          onClick={() => fileInput.current?.click()}
          disabled={busy}
          title="Use your own picture; you can still edit it, redraw it and build on it"
        >
          Replace
        </Button>
        {image.history.length > 1 && (
          <Button size="sm" variant="ghost" icon={<History className="size-4" />} onClick={() => setOpen('versions')} disabled={busy}>
            Versions ({image.history.length})
          </Button>
        )}
        {(bases.length > 0 || base) && (
          <Button
            size="sm"
            variant="ghost"
            icon={<Layers className="size-4" />}
            onClick={() => {
              mutations.buildOn.reset()
              setOpen('build')
            }}
            disabled={busy}
            title="Draw this image from an earlier one, so both share the same data, colors and shapes"
          >
            Builds on
          </Button>
        )}
        <Button size="sm" variant="ghost" icon={<PencilLine className="size-4" />} onClick={() => setOpen('caption')} disabled={busy}>
          Caption
        </Button>
        <input
          ref={fileInput}
          type="file"
          accept="image/*"
          className="hidden"
          aria-label="Upload replacement image"
          onChange={(e) => {
            const file = e.target.files?.[0]
            if (file) {
              clearErrors()
              setAction('Uploading your picture…')
              mutations.upload.mutate({ id: image.id, file }, { onSuccess: () => setUndoable(true) })
            }
            e.target.value = ''
          }}
        />
      </div>

      {room && open === 'ideas' && (
        <ImageRoomDialog
          open
          onClose={() => setOpen(null)}
          room={room}
          formats={formats.data ?? []}
          onPick={(pitch, model, edit?: PitchEdit) =>
            redraw(false, { concept: pitch.index, pitchHook: pitch.hook, conceptEdit: edit, model }, `Drawing: ${(edit?.hook || pitch.hook).slice(0, 60)}…`)
          }
          onNext={(model) => redraw(true, { model }, 'Drawing the next idea…')}
          onPitch={(note, model) => redraw(true, { pitch: true, note, model }, 'Pitching new ideas…')}
          onFormat={(id, note, model) => redraw(false, { format: id, note, model }, 'Drawing it in that format…')}
          onRestore={restore}
          models={models}
        />
      )}
      {open === 'words' && (
        <WordsDialog
          open
          onClose={() => setOpen(null)}
          slots={slots}
          saving={mutations.words.isPending}
          error={mutations.words.error ? errorText(mutations.words.error) : null}
          onSave={(words) =>
            mutations.words.mutate(
              { id: image.id, words },
              {
                onSuccess: () => {
                  setOpen(null)
                  setUndoable(true)
                },
              },
            )
          }
        />
      )}
      {open === 'redraw' && (
        <RedrawDialog
          open
          onClose={() => setOpen(null)}
          image={image}
          dimensions={remixOptions.data ?? []}
          onRedraw={(tweaks, improve, note, model) => redraw(false, { tweaks, improve, note, model })}
          models={models}
          referenceUrl={image.reference_url}
          onReference={(file) => mutations.setReference.mutate({ id: image.id, file })}
          onClearReference={() => mutations.clearReference.mutate(image.id)}
        />
      )}
      {open === 'build' && (
        <BuildOnDialog
          image={image}
          bases={bases}
          labelOf={(other) => `${kindLabel(other)}${other.provider === 'upload' ? ' (your picture)' : ''}: ${other.caption || other.purpose}`}
          mutations={mutations}
          onClose={() => setOpen(null)}
          onJob={(id) => started('Building on it…')({ id })}
        />
      )}
      {open === 'versions' && <VersionsDialog image={image} mutations={mutations} onClose={() => setOpen(null)} />}
      {open === 'edit' && (
        <EditDialog
          image={image}
          mutations={mutations}
          onClose={() => setOpen(null)}
          onJob={(id) => started(upload ? 'Recreating your picture with the change…' : 'Editing…')({ id })}
          models={models}
        />
      )}
      {open === 'caption' && <CaptionDialog image={image} mutations={mutations} onClose={() => setOpen(null)} />}
    </figure>
  )
}
