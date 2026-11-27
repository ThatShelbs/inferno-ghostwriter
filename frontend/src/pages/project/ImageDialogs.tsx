import { Layers, Wand2 } from 'lucide-react'
import { useState } from 'react'

import { errorText } from '../../api/client'
import type { ImageRoute, useImageMutations } from '../../api/hooks'
import type { ImageOut } from '../../api/types.gen'
import { Button, Dialog, Field, Input, Notice, Select, Textarea } from '../../components/ui'
import { ImageModelPicker } from './ImageModelPicker'

type Mutations = ReturnType<typeof useImageMutations>

const PROVIDER_LABEL: Record<string, string> = {
  'claude-svg': 'Claude SVG',
  'vega-lite': 'Claude + Vega-Lite',
  'claude-meme': 'Claude meme',
  'claude-opening': 'Claude + layout',
  'claude-scene': 'Claude scene',
  'claude-art': 'Claude generative art',
  'claude-diagram': 'Claude diagram',
  'gpt-image': 'GPT image (ChatGPT)',
  'hands-on-code': 'Code run on this computer',
  montage: 'Side-by-side sheet',
  placeholder: 'Placeholder',
  upload: 'Your upload',
}

/** Tell Claude what to change ("make the arrows orange"); the rest of the image stays. */
export function EditDialog({
  image,
  mutations,
  onClose,
  onJob,
  models = [],
}: {
  image: ImageOut
  mutations: Mutations
  onClose: () => void
  onJob: (id: string) => void
  /** The models the author may choose from (empty: no optional model is signed in, so no choice is shown). */
  models?: ImageRoute[]
}) {
  const [instruction, setInstruction] = useState('')
  const [model, setModel] = useState<ImageRoute>('auto')
  // Only GPT can change a painting, so a painting's edit offers no choice.
  const painted = image.provider === 'gpt-image'
  // A hands-on picture is the output of the code above it, so editing it edits that code (and the post) and runs it again.
  const code = image.kind === 'hands_on_viz'
  return (
    <Dialog open onClose={onClose} title={code ? 'Edit the code' : 'Edit this image'}>
      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault()
          mutations.edit.mutate(
            { id: image.id, instruction: instruction.trim(), model },
            {
              onSuccess: (j) => {
                onJob(j.id)
                onClose()
              },
            },
          )
        }}
      >
        <Field
          label="What should change?"
          hint={
            code
              ? 'Claude changes the code in your post as you describe, runs it again and keeps the new chart. The current picture stays in Versions and the old code in the post history.'
              : image.provider === 'upload'
                ? 'Your picture is recreated with this change (same content, words and layout). From then on it edits, redraws and builds on like any image. The original stays in Versions.'
                : 'Claude keeps the idea and layout and changes only what you describe. The current version stays in Versions.'
          }
          htmlFor={`instruct-${image.id}`}
        >
          <Textarea
            id={`instruct-${image.id}`}
            rows={3}
            value={instruction}
            autoFocus
            placeholder={code ? 'Sort the bars by total and label the axes in percent' : 'Make the arrows orange and label the y-axis in percent'}
            onChange={(e) => setInstruction(e.target.value)}
          />
        </Field>
        {!painted && !code && <ImageModelPicker id={`edit-model-${image.id}`} value={model} onChange={setModel} models={models} />}
        {mutations.edit.error && <Notice tone="error">{errorText(mutations.edit.error)}</Notice>}
        <Button type="submit" icon={<Wand2 className="size-4" />} loading={mutations.edit.isPending} disabled={instruction.trim().length < 3}>
          {code ? 'Edit code' : 'Edit image'}
        </Button>
      </form>
    </Dialog>
  )
}

/** Caption, credit and alt text. */
export function CaptionDialog({ image, mutations, onClose }: { image: ImageOut; mutations: Mutations; onClose: () => void }) {
  const [caption, setCaption] = useState(image.caption)
  const [alt, setAlt] = useState(image.alt)
  const [credit, setCredit] = useState(image.credit)
  return (
    <Dialog open onClose={onClose} title="Caption and credit">
      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault()
          mutations.update.mutate({ id: image.id, caption, alt, credit }, { onSuccess: onClose })
        }}
      >
        <Field label="Caption" htmlFor={`cap-${image.id}`}>
          <Input id={`cap-${image.id}`} value={caption} onChange={(e) => setCaption(e.target.value)} />
        </Field>
        <Field label="Credit" hint="Who made it and with what model or tool." htmlFor={`credit-${image.id}`}>
          <Input id={`credit-${image.id}`} value={credit} onChange={(e) => setCredit(e.target.value)} />
        </Field>
        <Field label="Alt text" hint="Describes the image for screen readers." htmlFor={`alt-${image.id}`}>
          <Input id={`alt-${image.id}`} value={alt} onChange={(e) => setAlt(e.target.value)} />
        </Field>
        <Button type="submit" loading={mutations.update.isPending}>
          Save
        </Button>
      </form>
    </Dialog>
  )
}

/** Every version of the image; clicking one restores it. */
export function VersionsDialog({ image, mutations, onClose }: { image: ImageOut; mutations: Mutations; onClose: () => void }) {
  return (
    <Dialog open onClose={onClose} title="Image versions" wide>
      <p className="mb-3 text-sm text-muted">Click a version to bring it back. Nothing is redrawn and nothing is lost.</p>
      {mutations.revert.error && <Notice tone="error">{errorText(mutations.revert.error)}</Notice>}
      <div className="grid gap-4 sm:grid-cols-2">
        {image.history.map((entry) => (
          <button
            key={entry.index}
            type="button"
            disabled={mutations.revert.isPending}
            className="rounded-xl border border-line p-2 text-left hover:border-accent disabled:opacity-60"
            onClick={() => mutations.revert.mutate({ id: image.id, index: entry.index }, { onSuccess: onClose })}
          >
            <img src={entry.url} alt={`Version ${entry.index + 1}`} className="w-full rounded-lg" />
            <p className="mt-1 text-xs text-muted">
              v{entry.index + 1} · {PROVIDER_LABEL[entry.provider] ?? entry.provider}{' '}
              {entry.created_at ? `· ${new Date(entry.created_at).toLocaleString()}` : ''}
            </p>
          </button>
        ))}
      </div>
    </Dialog>
  )
}

/** Draw this image from an earlier one, so both share the same data, colors and shapes. */
export function BuildOnDialog({
  image,
  bases,
  labelOf,
  mutations,
  onClose,
  onJob,
}: {
  image: ImageOut
  bases: ImageOut[]
  labelOf: (other: ImageOut) => string
  mutations: Mutations
  onClose: () => void
  onJob: (id: string) => void
}) {
  const [choice, setChoice] = useState(image.builds_on ?? '')
  const pending = mutations.buildOn.isPending || mutations.clearBuildOn.isPending
  const error = mutations.buildOn.error ?? mutations.clearBuildOn.error
  return (
    <Dialog open onClose={onClose} title="Build on an earlier image">
      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault()
          if (!choice) return mutations.clearBuildOn.mutate(image.id, { onSuccess: onClose })
          mutations.buildOn.mutate(
            { id: image.id, slotId: choice },
            {
              onSuccess: (j) => {
                onJob(j.id)
                onClose()
              },
            },
          )
        }}
      >
        <p className="text-sm text-muted">
          When two images tell one story (a chart, then the same chart split into groups), draw the second from the first: it reuses the same data, colors and
          shapes and adds only what is new. Your own pictures can be built on too.
        </p>
        <Field label="This image builds on" htmlFor={`builds-on-${image.id}`}>
          <Select id={`builds-on-${image.id}`} value={choice} disabled={pending} onChange={(e) => setChoice(e.target.value)}>
            <option value="">Nothing (it stands alone)</option>
            {bases.map((other) => (
              <option key={other.id} value={other.slot_id}>
                {labelOf(other)}
              </option>
            ))}
          </Select>
        </Field>
        <p className="text-xs text-muted">
          {choice ? 'This image is drawn again from the one you chose. The current version stays in Versions.' : 'The image keeps its current picture.'}
        </p>
        {error && <Notice tone="error">{errorText(error)}</Notice>}
        <Button type="submit" icon={<Layers className="size-4" />} loading={pending} disabled={choice === (image.builds_on ?? '')}>
          {choice ? 'Draw it from that image' : 'Stand alone'}
        </Button>
      </form>
    </Dialog>
  )
}
