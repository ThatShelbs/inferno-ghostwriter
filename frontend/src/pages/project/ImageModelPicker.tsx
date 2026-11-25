import type { ImageRoute } from '../../api/hooks'
import { Field, Select } from '../../components/ui'

const LABELS: Record<ImageRoute, string> = {
  auto: 'Auto (Settings → Image work)',
  claude: 'Claude',
  codex: 'ChatGPT (Codex)',
  gemini: 'Gemini',
}

/**
 * Who does this redraw or edit: the pitches and designs go to the chosen model (the judge stays as set in Settings).
 * Shown only while an optional model (ChatGPT or Gemini) is signed in; otherwise Claude does it and nothing is shown.
 */
export function ImageModelPicker({
  id,
  value,
  onChange,
  models,
}: {
  id: string
  value: ImageRoute
  onChange: (model: ImageRoute) => void
  models: ImageRoute[]
}) {
  if (models.length === 0) return null
  return (
    <Field label="Model" hint="Who pitches and designs this one. Claude or Gemini skip GPT painting; the judge stays as set in Settings." htmlFor={id}>
      <Select id={id} value={value} onChange={(e) => onChange(e.target.value as ImageRoute)}>
        {models.map((model) => (
          <option key={model} value={model}>
            {LABELS[model]}
          </option>
        ))}
      </Select>
    </Field>
  )
}
