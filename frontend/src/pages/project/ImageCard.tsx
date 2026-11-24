import { useQueryClient } from '@tanstack/react-query'
import { Dices, History, ImagePlus, Layers, Lightbulb, PencilLine, Sparkles, Type, Wand2 } from 'lucide-react'
import { useRef, useState } from 'react'

import { errorText } from '../../api/client'
import { keys, useImageFormats, useImageMutations, useRemixOptions, type RedrawPicks } from '../../api/hooks'
import type { ImageOut } from '../../api/types.gen'
import { useJob } from '../../api/useJob'
import { Badge, Button, Notice, Spinner } from '../../components/ui'
import { fullCaption } from '../../lib/article'
import { KIND_LABEL } from '../../lib/imageRoom'
import { cx } from '../../lib/cx'
import { buildOnChoices, dependentsOf, remixTwists } from '../../lib/remix'
import { textSyncNote, type TextSyncNote } from '../../lib/textSync'
import { FinalistStrip } from './FinalistStrip'
import { BuildOnDialog, CaptionDialog, EditDialog, VersionsDialog } from './ImageDialogs'
import { ImageRoomDialog } from './ImageRoomDialog'
import { RemixDialog } from './RemixDialog'
import { WordsDialog } from './WordsDialog'

type Open = 'ideas' | 'remix' | 'words' | 'edit' | 'caption' | 'versions' | 'build' | null

/**
 * One image in the post. Every image, whatever its kind, has the same tools: Ideas (its room), Redraw, Remix, Edit,
 * Words (when it has text), Replace, Versions, Builds on (in-body images) and Caption, plus the finalist strip.
 */
export function ImageCard({ projectId, image, images = [] }: { projectId: number; image: ImageOut; images?: ImageOut[] }) {
  const qc = useQueryClient()
  const mutations = useImageMutations(projectId)
  const [jobId, setJobId] = useState<string | null>(null)
  const [open, setOpen] = useState<Open>(null)
  const fileInput = useRef<HTMLInputElement>(null)
  const [textNote, setTextNote] = useState<TextSyncNote | null>(null)
  // Set when a redraw of this image leaves the images that build on it drawn from its old version.
  const [unmatched, setUnmatched] = useState(false)
  const job = useJob(jobId, (state) => {
    setJobId(null)
    setTextNote(textSyncNote(state))
    setUnmatched(((state.result?.dependents as string[] | undefined) ?? []).length > 0)
    void qc.invalidateQueries({ queryKey: keys.project(projectId) })
  })
  const busy = !!jobId || mutations.upload.isPending || mutations.pick.isPending
  const drawn = !['upload', 'placeholder', ''].includes(image.provider)
  const room = image.room ?? null
  const formats = useImageFormats(room?.room ?? 'body', image.kind, open === 'ideas' && !!room)
  const remixOptions = useRemixOptions(open === 'remix')
  const canRemix = drawn && (image.remix_dimensions ?? []).length > 0
  // Images that build on each other share one source, so they look like the same data taken further.
  const bases = buildOnChoices(image, images)
  const base = images.find((other) => other.slot_id === image.builds_on)
  const dependents = dependentsOf(image, images)
  const nameOf = (slotId: string) => {
    const other = images.find((i) => i.slot_id === slotId)
    return other ? `${KIND_LABEL[other.kind] ?? other.kind} "${other.caption || other.purpose}"` : slotId
  }
  const redraw = (rethink: boolean, picks: RedrawPicks = {}) => {
    setOpen(null)
    mutations.redraw.mutate({ id: image.id, rethink, ...picks }, { onSuccess: (j) => setJobId(j.id) })
  }
  const slots = room?.slots ?? []
  const label = image.kind === 'hero' && room?.format_label ? `Opening image · ${room.format_label}` : (KIND_LABEL[image.kind] ?? image.kind)

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
              <Spinner label={job.message || 'Redrawing…'} />
            </span>
          </div>
        )}
        {image.kind !== 'hero' && (
          <div className="absolute top-2 left-2">
            <Badge tone="accent">{label}</Badge>
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
      {image.status === 'error' && <Notice tone="error">{image.error}</Notice>}
      {job.status === 'failed' && <Notice tone="error">{job.error}</Notice>}
      {mutations.upload.error && <Notice tone="error">{errorText(mutations.upload.error)}</Notice>}
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
                    setJobId(j.id)
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

      <div className="mt-3 flex flex-wrap justify-center gap-2" aria-label={`Actions for ${KIND_LABEL[image.kind] ?? 'image'}`}>
        <Button
          size="sm"
          variant="secondary"
          icon={<Lightbulb className="size-4" />}
          onClick={() => (room ? setOpen('ideas') : redraw(true))}
          disabled={busy}
          title="Every idea pitched for this image: pick one, pitch new ones with a steer, or try another format"
        >
          Ideas
        </Button>
        <Button
          size="sm"
          variant="secondary"
          icon={<Dices className="size-4" />}
          onClick={() => redraw(false)}
          disabled={busy}
          title="Claude critiques this image, then redraws the same idea to fix its weakest point"
        >
          Redraw
        </Button>
        {canRemix && (
          <Button
            size="sm"
            variant="secondary"
            icon={<Sparkles className="size-4" />}
            onClick={() => setOpen('remix')}
            disabled={busy}
            title="Choose what the redraw experiments with, and steer it in your own words"
          >
            Remix
          </Button>
        )}
        {drawn && (
          <Button
            size="sm"
            variant="secondary"
            icon={<Wand2 className="size-4" />}
            onClick={() => setOpen('edit')}
            disabled={busy}
            title="Tell Claude what to change; the rest stays"
          >
            Edit
          </Button>
        )}
        {slots.length > 0 && (
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
        <Button size="sm" variant="secondary" icon={<ImagePlus className="size-4" />} onClick={() => fileInput.current?.click()} disabled={busy}>
          Replace
        </Button>
        {image.history.length > 1 && (
          <Button size="sm" variant="ghost" icon={<History className="size-4" />} onClick={() => setOpen('versions')}>
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
        <Button size="sm" variant="ghost" icon={<PencilLine className="size-4" />} onClick={() => setOpen('caption')}>
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
            if (file) mutations.upload.mutate({ id: image.id, file })
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
          onPick={(index) => redraw(false, { concept: index })}
          onPitch={(note) => redraw(true, { note })}
          onFormat={(id, note) => redraw(false, { format: id, note })}
        />
      )}
      {open === 'words' && (
        <WordsDialog
          open
          onClose={() => setOpen(null)}
          slots={slots}
          saving={mutations.words.isPending}
          error={mutations.words.error ? errorText(mutations.words.error) : null}
          onSave={(words) => mutations.words.mutate({ id: image.id, words }, { onSuccess: () => setOpen(null) })}
        />
      )}
      {open === 'remix' && (
        <RemixDialog
          open
          onClose={() => setOpen(null)}
          image={image}
          dimensions={remixOptions.data ?? []}
          onRemix={(tweaks, improve, note) => redraw(false, { tweaks, improve, note })}
        />
      )}
      {open === 'build' && (
        <BuildOnDialog
          image={image}
          bases={bases}
          labelOf={(other) => `${KIND_LABEL[other.kind] ?? other.kind}: ${other.caption || other.purpose}`}
          mutations={mutations}
          onClose={() => setOpen(null)}
          onJob={setJobId}
        />
      )}
      {open === 'versions' && <VersionsDialog image={image} mutations={mutations} onClose={() => setOpen(null)} />}
      {open === 'edit' && <EditDialog image={image} mutations={mutations} onClose={() => setOpen(null)} onJob={setJobId} />}
      {open === 'caption' && <CaptionDialog image={image} mutations={mutations} onClose={() => setOpen(null)} />}
    </figure>
  )
}
