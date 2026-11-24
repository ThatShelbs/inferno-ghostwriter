import { Lightbulb, RefreshCw } from 'lucide-react'
import { useState } from 'react'

import type { ImageFormatOut, ImageRoomOut, PitchOut } from '../../api/types.gen'
import { Badge, Button, Dialog, Field, Select, Textarea } from '../../components/ui'
import { cx } from '../../lib/cx'
import { rankPitches, scoreLabel } from '../../lib/imageRoom'

const ROOM_TITLE: Record<string, string> = {
  opening: 'Opening image ideas',
  meme: 'Meme ideas',
  body: 'Image ideas',
}

/**
 * The ideas board every image shares: the pitches the room made for it, best first, what the judge saw in the ones it
 * drew, and three ways forward (use an idea, pitch new ones with a steer, or try another format).
 */
export function ImageRoomDialog({
  open,
  onClose,
  room,
  formats,
  onPick,
  onPitch,
  onFormat,
}: {
  open: boolean
  onClose: () => void
  room: ImageRoomOut
  formats: ImageFormatOut[]
  onPick: (index: number) => void
  /** Pitch new ideas, with the author's steer ('' for none). */
  onPitch: (note: string) => void
  onFormat: (id: string, note: string) => void
}) {
  const [note, setNote] = useState('')
  const ranked = rankPitches(room.pitches ?? [])
  const groups = [...new Set(formats.map((f) => f.group))]

  return (
    <Dialog open={open} onClose={onClose} title={ROOM_TITLE[room.room] ?? 'Ideas'} wide>
      <div className="space-y-4">
        <p className="text-sm text-muted">
          Every idea pitched for this image, best first. Each one riffs on a passage of your post; the judge scored them and said what the drawn ones read as.
          Picking one draws it at once.
        </p>
        {room.why && <p className="text-xs text-muted">Why the current one won: {room.why}</p>}
        {ranked.length === 0 && <p className="text-sm text-muted">No ideas are stored for this image yet. Pitch some below.</p>}
        <ul className="space-y-3" aria-label="Pitched ideas">
          {ranked.map((pitch) => (
            <PitchCard key={pitch.index} pitch={pitch} onPick={() => onPick(pitch.index)} />
          ))}
        </ul>

        <div className="space-y-3 border-t border-line pt-4">
          <Field
            label="Steer the next round (optional)"
            hint="In your own words: 'fewer words', 'more like the original meme', 'about the deploy bit'."
            htmlFor="room-note"
          >
            <Textarea id="room-note" rows={2} value={note} maxLength={500} onChange={(e) => setNote(e.target.value)} />
          </Field>
          <div className="flex flex-wrap items-center gap-2">
            <Button size="sm" icon={<RefreshCw className="size-4" />} onClick={() => onPitch(note.trim())}>
              {(room.ideas_left ?? 0) > 0 && !note.trim() ? 'Next best idea' : 'Pitch new ideas'}
            </Button>
            {formats.length > 0 && (
              <Select
                aria-label="Try another format"
                className="h-8 w-64 max-w-full text-sm"
                value=""
                onChange={(e) => e.target.value && onFormat(e.target.value, note.trim())}
              >
                <option value="">Try another format…</option>
                {groups.map((group) => (
                  <optgroup key={group} label={group}>
                    {formats
                      .filter((f) => f.group === group)
                      .map((f) => (
                        <option key={f.id} value={f.id} title={f.when_to_use} disabled={f.id === room.format}>
                          {f.label}
                        </option>
                      ))}
                  </optgroup>
                ))}
              </Select>
            )}
          </div>
        </div>
      </div>
    </Dialog>
  )
}

function PitchCard({ pitch, onPick }: { pitch: PitchOut; onPick: () => void }) {
  return (
    <li className={cx('rounded-xl border p-3', pitch.current ? 'border-accent' : 'border-line', pitch.ruled_out && 'opacity-60')}>
      <div className="flex flex-wrap items-center gap-2">
        <Badge>{pitch.format_label}</Badge>
        {pitch.current && <Badge tone="accent">Showing now</Badge>}
        {pitch.tried && !pitch.current && <Badge>Tried</Badge>}
        {pitch.ruled_out && <Badge tone="danger">Ruled out</Badge>}
        {pitch.score !== null && pitch.score !== undefined && <span className="ml-auto text-sm font-semibold">{scoreLabel(pitch.score)}</span>}
      </div>
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
      {!pitch.current && (
        <Button size="sm" variant="secondary" className="mt-2" icon={<Lightbulb className="size-4" />} onClick={onPick}>
          Use this one
        </Button>
      )}
    </li>
  )
}
