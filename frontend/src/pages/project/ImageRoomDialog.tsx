import { ChevronDown, Lightbulb, PencilLine, RefreshCw, SkipForward, Sparkles } from 'lucide-react'
import { useState } from 'react'

import type { ImageRoute } from '../../api/hooks'
import type { ImageFormatOut, ImageRoomOut, PitchOut } from '../../api/types.gen'
import { Badge, Button, Dialog, Field, Input, Textarea } from '../../components/ui'
import { cx } from '../../lib/cx'
import { boardSections, formatGroups, moreLikeThis, scoreLabel } from '../../lib/imageRoom'
import { ImageModelPicker } from './ImageModelPicker'
import { SteerChips } from './RedrawDialog'

const ROOM_TITLE: Record<string, string> = {
  opening: 'Opening image ideas',
  meme: 'Meme ideas',
  body: 'Image ideas',
}

/** The author's changes to an idea before it is drawn. */
export interface PitchEdit {
  hook?: string
  concept?: string
  words?: string[]
}

/**
 * The ideas board every image shares (opening image, meme, in-body images). The idea on show sits on top; ideas not
 * drawn yet come next, newest round first; ideas already drawn show their picture (clicking it brings that version
 * back for free). Any idea can be adjusted before it is drawn, or used as the seed of a new round ("More like this").
 * New rounds are added to the board, so nothing the author saw goes away.
 */
export function ImageRoomDialog({
  open,
  onClose,
  room,
  formats,
  onPick,
  onNext,
  onPitch,
  onFormat,
  onRestore,
  models = [],
}: {
  open: boolean
  onClose: () => void
  room: ImageRoomOut
  formats: ImageFormatOut[]
  /** Draw this idea as it is (with the author's changes, if any). Each action also says who does the work. */
  onPick: (pitch: PitchOut, model: ImageRoute, edit?: PitchEdit) => void
  /** Draw the best idea not drawn yet (no new pitching). */
  onNext: (model: ImageRoute) => void
  /** Pitch a new round with the author's steer ('' for none). */
  onPitch: (note: string, model: ImageRoute) => void
  onFormat: (id: string, note: string, model: ImageRoute) => void
  /** Bring back the version that drew this idea (no model call). */
  onRestore?: (version: number) => void
  /** The models the author may choose from (empty: no optional model is signed in, so no choice is shown). */
  models?: ImageRoute[]
}) {
  const [note, setNote] = useState('')
  const [model, setModel] = useState<ImageRoute>('auto')
  const [showRuledOut, setShowRuledOut] = useState(false)
  const { current, fresh, tried, ruledOut } = boardSections(room.pitches ?? [])
  const groups = formatGroups(formats, room.suggested ?? [], room.format)
  const newest = Math.max(0, ...(room.pitches ?? []).map((p) => p.batch ?? 0))
  const card = (pitch: PitchOut) => (
    <PitchCard
      key={pitch.index}
      pitch={pitch}
      isNew={newest > 0 && (pitch.batch ?? 0) === newest && !pitch.tried}
      onPick={(edit) => onPick(pitch, model, edit)}
      onMore={() => onPitch(moreLikeThis(pitch, note), model)}
      onRestore={onRestore}
    />
  )

  return (
    <Dialog open={open} onClose={onClose} title={ROOM_TITLE[room.room] ?? 'Ideas'} wide>
      <div className="space-y-4">
        <p className="text-sm text-muted">
          Every idea pitched for this image. Each riffs on a passage of your post. Picking one draws it exactly as written; Adjust changes it first.
        </p>
        <ul className="space-y-3" aria-label="Pitched ideas">
          {current && (
            <>
              <SectionLabel>Showing now</SectionLabel>
              {card(current)}
              {room.why && (
                <li role="presentation" className="-mt-1 list-none text-xs text-muted">
                  Why it won: {room.why}
                </li>
              )}
            </>
          )}
          {fresh.length > 0 && <SectionLabel>Not drawn yet</SectionLabel>}
          {fresh.map(card)}
          {tried.length > 0 && <SectionLabel>Drawn before</SectionLabel>}
          {tried.map(card)}
          {ruledOut.length > 0 && (
            <li role="presentation" className="list-none">
              <button type="button" className="flex items-center gap-1 text-xs text-muted underline" onClick={() => setShowRuledOut(!showRuledOut)}>
                <ChevronDown className={cx('size-3.5 transition-transform', showRuledOut && 'rotate-180')} aria-hidden />
                {showRuledOut ? 'Hide' : 'Show'} {ruledOut.length} ruled out
              </button>
            </li>
          )}
          {showRuledOut && ruledOut.map(card)}
        </ul>
        {(room.pitches ?? []).length === 0 && <p className="text-sm text-muted">No ideas yet for this image. Pitch some below.</p>}

        <div className="space-y-3 border-t border-line pt-4">
          <Field
            label="Steer the next round (optional)"
            hint="Tap a steer or say it in your own words: 'about the deploy bit', 'more like the original meme'."
            htmlFor="room-note"
          >
            <div className="space-y-2">
              <SteerChips note={note} onChange={setNote} label="Steers for new ideas" />
              <Textarea id="room-note" rows={2} value={note} maxLength={500} onChange={(e) => setNote(e.target.value)} />
            </div>
          </Field>
          <ImageModelPicker id="room-model" value={model} onChange={setModel} models={models} />
          <div className="flex flex-wrap items-center gap-2">
            {(room.ideas_left ?? 0) > 0 && (
              <Button
                size="sm"
                variant="secondary"
                icon={<SkipForward className="size-4" />}
                onClick={() => onNext(model)}
                title="Draw the best idea not drawn yet; nothing new is pitched"
              >
                Draw next idea
              </Button>
            )}
            <Button size="sm" icon={<RefreshCw className="size-4" />} onClick={() => onPitch(note.trim(), model)} title="A new round is added to this board">
              {(room.pitches ?? []).length ? 'Pitch new ideas' : 'Pitch ideas'}
            </Button>
          </div>
          {groups.length > 0 && (
            <div className="space-y-2" aria-label="Try another format">
              <p className="text-sm font-semibold">Try another format</p>
              {groups.map(({ group, formats: items }) => (
                <div key={group} className="flex flex-wrap items-center gap-1.5">
                  <span className="w-full text-xs text-muted">{group}</span>
                  {items.map((f) => (
                    <button
                      key={f.id}
                      type="button"
                      title={f.when_to_use}
                      onClick={() => onFormat(f.id, note.trim(), model)}
                      className={cx(
                        'rounded-full border px-2.5 py-0.5 text-xs hover:border-accent',
                        group === 'Suggested' ? 'border-accent bg-accent-soft' : 'border-line',
                      )}
                    >
                      {f.label}
                    </button>
                  ))}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </Dialog>
  )
}

function SectionLabel({ children }: { children: string }) {
  return (
    <li role="presentation" className="list-none pt-1 text-xs font-semibold tracking-wide text-muted uppercase">
      {children}
    </li>
  )
}

function PitchCard({
  pitch,
  isNew,
  onPick,
  onMore,
  onRestore,
}: {
  pitch: PitchOut
  isNew: boolean
  onPick: (edit?: PitchEdit) => void
  onMore: () => void
  onRestore?: (version: number) => void
}) {
  const [adjusting, setAdjusting] = useState(false)
  const [hook, setHook] = useState(pitch.hook)
  const [concept, setConcept] = useState(pitch.concept)
  const [words, setWords] = useState<string[]>(pitch.words ?? [])
  const restore = pitch.version !== null && pitch.version !== undefined && !pitch.current && onRestore ? onRestore : null
  return (
    <li className={cx('flex gap-3 rounded-xl border p-3', pitch.current ? 'border-accent' : 'border-line', pitch.ruled_out && 'opacity-60')}>
      {pitch.thumb_url && (
        <button
          type="button"
          disabled={!restore}
          onClick={() => restore && pitch.version != null && restore(pitch.version)}
          title={restore ? 'Bring this version back (no model call)' : undefined}
          className="shrink-0 self-start"
        >
          <img src={pitch.thumb_url} alt={`How "${pitch.hook}" was drawn`} className="w-28 rounded-md border border-line" />
          {restore && <span className="mt-0.5 block text-center text-[11px] text-muted underline">Bring it back</span>}
        </button>
      )}
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <Badge>{pitch.format_label}</Badge>
          {pitch.current && <Badge tone="accent">Showing now</Badge>}
          {isNew && <Badge tone="success">New</Badge>}
          {pitch.tried && !pitch.current && <Badge>Tried</Badge>}
          {pitch.edited && <Badge>Your edit</Badge>}
          {pitch.ruled_out && <Badge tone="danger">Ruled out</Badge>}
          {pitch.score !== null && pitch.score !== undefined && <span className="ml-auto text-sm font-semibold">{scoreLabel(pitch.score)}</span>}
        </div>
        {adjusting ? (
          <form
            className="mt-2 space-y-2"
            onSubmit={(e) => {
              e.preventDefault()
              onPick({ hook: hook.trim(), concept: concept.trim(), words: words.length ? words.map((w) => w.trim()) : undefined })
            }}
          >
            <Field label="The idea in a line" htmlFor={`hook-${pitch.index}`}>
              <Input id={`hook-${pitch.index}`} value={hook} maxLength={300} onChange={(e) => setHook(e.target.value)} />
            </Field>
            {pitch.concept && (
              <Field label="The picture" htmlFor={`concept-${pitch.index}`}>
                <Textarea id={`concept-${pitch.index}`} rows={2} value={concept} maxLength={1200} onChange={(e) => setConcept(e.target.value)} />
              </Field>
            )}
            {words.map((word, i) => (
              <Field key={i} label={`Words ${i + 1}`} htmlFor={`words-${pitch.index}-${i}`}>
                <Input id={`words-${pitch.index}-${i}`} value={word} onChange={(e) => setWords(words.map((w, k) => (k === i ? e.target.value : w)))} />
              </Field>
            ))}
            <div className="flex gap-2">
              <Button size="sm" type="submit" icon={<Lightbulb className="size-4" />} disabled={!hook.trim()}>
                Draw this
              </Button>
              <Button size="sm" variant="ghost" onClick={() => setAdjusting(false)}>
                Cancel
              </Button>
            </div>
          </form>
        ) : (
          <>
            <p className="mt-2 text-sm font-medium">{pitch.hook}</p>
            {pitch.concept && <p className="mt-1 text-sm text-muted">{pitch.concept}</p>}
            {(pitch.words ?? []).length > 0 && <p className="mt-1 text-sm">“{(pitch.words ?? []).join(' / ')}”</p>}
            {pitch.anchor && (
              <p className="mt-1 text-xs text-muted">
                Riffs on: “{pitch.anchor}”{!pitch.anchored && ' (not found in the post)'}
              </p>
            )}
            {pitch.reads_as && <p className="mt-1 text-xs text-muted">The judge read the drawing as: {pitch.reads_as}</p>}
            {pitch.note && <p className="mt-1 text-xs text-muted">Judge: {pitch.note}</p>}
            <div className="mt-2 flex flex-wrap gap-2">
              {!pitch.current && (
                <Button size="sm" variant="secondary" icon={<Lightbulb className="size-4" />} onClick={() => onPick()}>
                  Use this one
                </Button>
              )}
              <Button size="sm" variant="ghost" icon={<PencilLine className="size-4" />} onClick={() => setAdjusting(true)}>
                Adjust
              </Button>
              <Button size="sm" variant="ghost" icon={<Sparkles className="size-4" />} onClick={onMore} title="Pitch a new round seeded by this idea">
                More like this
              </Button>
            </div>
          </>
        )}
      </div>
    </li>
  )
}
