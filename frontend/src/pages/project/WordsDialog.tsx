import { Type } from 'lucide-react'
import { useState } from 'react'

import type { WordSlotOut } from '../../api/types.gen'
import { Button, Dialog, Field, Input, Notice, Textarea } from '../../components/ui'

/** Retype the words in an image (a meme or a code-drawn opening image). Saving redraws it at once; Claude is not asked. */
export function WordsDialog({
  open,
  onClose,
  slots,
  saving,
  error,
  onSave,
}: {
  open: boolean
  onClose: () => void
  slots: WordSlotOut[]
  saving: boolean
  error?: string | null
  onSave: (words: Record<string, string>) => void
}) {
  const [words, setWords] = useState<Record<string, string>>({})
  const value = (slot: WordSlotOut) => words[slot.name] ?? slot.text
  const missing = slots.some((slot) => !slot.optional && !value(slot).trim())
  const changed = slots.some((slot) => value(slot) !== slot.text)

  return (
    <Dialog open={open} onClose={onClose} title="Edit the words">
      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault()
          onSave(Object.fromEntries(slots.map((slot) => [slot.name, value(slot)])))
        }}
      >
        <p className="text-sm text-muted">
          The picture stays as it is and the text is refitted. Numbers and sources stay as researched. Nothing is sent to Claude.
        </p>
        {slots.map((slot) => {
          const id = `word-${slot.name.replaceAll('.', '-')}`
          const text = value(slot)
          const long = text.length > slot.max_chars
          const hint = `${slot.hint}${slot.optional ? ' Optional.' : ''} ${text.length}/${slot.max_chars}${long ? ': long text is drawn smaller.' : ''}`
          const props = { id, value: text, onChange: (e: { target: { value: string } }) => setWords({ ...words, [slot.name]: e.target.value }) }
          return (
            <Field key={slot.name} label={slot.name.replaceAll('_', ' ').replaceAll('.', ' ')} hint={hint} htmlFor={id}>
              {slot.max_chars > 60 ? <Textarea rows={2} {...props} /> : <Input {...props} />}
            </Field>
          )
        })}
        {error && <Notice tone="error">{error}</Notice>}
        <Button type="submit" icon={<Type className="size-4" />} loading={saving} disabled={missing || !changed}>
          Save words
        </Button>
      </form>
    </Dialog>
  )
}
