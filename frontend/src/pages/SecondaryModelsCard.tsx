import { errorText } from '../api/client'
import { useSecondaryAuth, useSecondaryStatus, useSettings, useUpdateSettings } from '../api/hooks'
import type { SecondarySettings, SecondaryStatusOut } from '../api/types.gen'
import { Button, Card, Field, Notice, Select } from '../components/ui'

type Provider = SecondaryStatusOut['provider']
const NAMES: Record<Provider, string> = { codex: 'ChatGPT via Codex', gemini: 'Google Gemini via Antigravity' }
const STAGES = [
  ['draft', 'First draft'],
  ['critique', 'Editorial critique'],
  ['revision', 'Voice revision'],
  ['tweak', 'Tweaks and selected passages'],
] as const
const IMAGE_WORK = [
  ['pitch', 'Image ideas (pitches)'],
  ['design', 'Charts, diagrams and layouts'],
  ['svg', 'Hand-drawn SVG illustrations'],
  ['judge', 'Picture judge'],
] as const
type ImageWork = (typeof IMAGE_WORK)[number][0]
// How often ChatGPT paints each kind of image (the backend's ImageRouting shares and their defaults).
const PAINT_SHARES = [
  ['native_share', 'Illustrations, icons and metaphor openers', 0.6],
  ['meme_share', 'Memes (famous, comic and caption formats)', 0.8],
  ['art_share', 'Data art openers', 0.8],
] as const
const SHARE_OPTIONS = [
  [0, 'Never'],
  [0.25, 'About a quarter'],
  [0.5, 'About half'],
  [0.6, 'About 60%'],
  [0.75, 'About three quarters'],
  [0.8, 'About 80%'],
  [1, 'Always'],
] as const
const USES = [
  ['fallback', 'Use when Claude reaches a usage limit'],
  ['judges', 'Add a judge for image and meme pitches'],
  ['ideation', 'Add pitches in Idea Lab and the image rooms'],
] as const

function Connection({ status }: { status: SecondaryStatusOut }) {
  const { login, test } = useSecondaryAuth(status.provider)
  const busy = login.isPending || test.isPending || status.login_in_progress
  const problem = test.error ?? login.error
  return (
    <section className="space-y-2 rounded-xl bg-surface-2 p-4">
      <h3 className="font-semibold">{NAMES[status.provider]}</h3>
      <p className="text-sm text-muted">
        {status.model} · {status.signed_in ? 'Connected' : status.installed ? 'Sign in or test an existing login' : 'CLI installation required'}
      </p>
      {status.installed ? (
        <div className="flex flex-wrap gap-2">
          <Button
            size="sm"
            variant="secondary"
            loading={login.isPending || status.login_in_progress}
            disabled={busy}
            onClick={() => {
              test.reset()
              login.mutate()
            }}
          >
            {status.provider === 'codex' ? 'Sign in with ChatGPT' : 'Sign in with Google'}
          </Button>
          <Button
            size="sm"
            variant="ghost"
            loading={test.isPending}
            disabled={busy}
            onClick={() => {
              login.reset()
              test.mutate()
            }}
          >
            Test connection
          </Button>
        </div>
      ) : (
        <a className="text-sm font-semibold text-accent underline" href={status.install_url} target="_blank" rel="noreferrer">
          Install {status.provider === 'codex' ? 'Codex CLI' : 'Antigravity CLI'}
        </a>
      )}
      {problem && <Notice tone="error">{errorText(problem)}</Notice>}
      {login.data && <Notice tone="info">{login.data.message}</Notice>}
      {test.data && <Notice tone={test.data.ok ? 'info' : 'error'}>{test.data.message}</Notice>}
    </section>
  )
}

export function SecondaryModelsCard() {
  const { data: settings } = useSettings()
  const { data: providers, error } = useSecondaryStatus(settings?.demo === false)
  const update = useUpdateSettings()
  if (!settings || settings.demo) return null
  const selected = settings.secondary
  const save = (values: Partial<SecondarySettings>) => update.mutate({ secondary: values })

  return (
    <Card className="space-y-4">
      <div>
        <h2 className="text-lg font-bold">Optional models</h2>
        <p className="text-sm text-muted">
          Claude is the primary connection. Choose where a signed-in model can help. Enabled providers may receive your brief, draft, or voice samples as part
          of that task.
        </p>
      </div>
      {error && <Notice tone="error">{errorText(error)}</Notice>}
      {providers?.map((status) => (
        <Connection key={status.provider} status={status} />
      ))}
      {providers && (
        <>
          <fieldset className="grid gap-3 sm:grid-cols-2" disabled={update.isPending}>
            <legend className="mb-2 font-semibold">Writing by stage</legend>
            {STAGES.map(([stage, label]) => (
              <Field key={stage} label={label} htmlFor={`secondary-${stage}`}>
                <Select id={`secondary-${stage}`} value={selected[stage] ?? 'claude'} onChange={(event) => save({ [stage]: event.target.value })}>
                  <option value="claude">Claude</option>
                  {providers.map((status) => (
                    <option key={status.provider} value={status.provider} disabled={!status.signed_in}>
                      {status.model}
                    </option>
                  ))}
                </Select>
              </Field>
            ))}
          </fieldset>
          <fieldset className="grid gap-3 sm:grid-cols-2" disabled={update.isPending}>
            <legend className="mb-2 font-semibold">Image work</legend>
            <p className="text-sm text-muted sm:col-span-2">
              Auto sends each kind of image work to the signed-in model that suits it and falls back to Claude: ideas and charts to ChatGPT or Gemini, the
              picture judge to ChatGPT, hand-drawn SVG to Claude. This saves most of a post&apos;s Claude usage.
            </p>
            {IMAGE_WORK.map(([work, label]) => (
              <Field key={work} label={label} htmlFor={`image-${work}`}>
                <Select
                  id={`image-${work}`}
                  value={selected.images?.[work as ImageWork] ?? 'auto'}
                  onChange={(event) => save({ images: { [work]: event.target.value } } as Partial<SecondarySettings>)}
                >
                  <option value="auto">Auto (best fit)</option>
                  <option value="claude">Claude</option>
                  {providers
                    .filter((status) => work !== 'judge' || status.provider === 'codex')
                    .map((status) => (
                      <option key={status.provider} value={status.provider} disabled={!status.signed_in}>
                        {status.model}
                      </option>
                    ))}
                </Select>
              </Field>
            ))}
            <Field label="ChatGPT's own image generation" htmlFor="image-raster">
              <Select
                id="image-raster"
                value={selected.images?.raster === false ? 'off' : 'on'}
                onChange={(event) => save({ images: { raster: event.target.value === 'on' } } as Partial<SecondarySettings>)}
              >
                <option value="on">On, when ChatGPT is signed in</option>
                <option value="off">Off: code draws every image</option>
              </Select>
            </Field>
            {PAINT_SHARES.map(([share, label, fallback]) => (
              <Field key={share} label={label} htmlFor={`image-${share}`}>
                <Select
                  id={`image-${share}`}
                  disabled={selected.images?.raster === false}
                  value={String(selected.images?.[share] ?? fallback)}
                  onChange={(event) => save({ images: { [share]: Number(event.target.value) } } as Partial<SecondarySettings>)}
                >
                  {SHARE_OPTIONS.map(([value, text]) => (
                    <option key={value} value={String(value)}>
                      {text}
                    </option>
                  ))}
                </Select>
              </Field>
            ))}
            <p className="text-sm text-muted sm:col-span-2">
              ChatGPT generates these images from the same idea instead of code drawing them, never both, and paints memes whole, words included (the judge
              checks the spelling). Charts, diagrams, screenshots and chart or chat-style memes stay code-drawn, and code draws any image ChatGPT cannot make.
            </p>
          </fieldset>
          <fieldset className="space-y-3" disabled={update.isPending}>
            <legend className="font-semibold">Additional uses</legend>
            <p className="text-sm text-muted">Fallbacks run in the order you enable them. Claude handles web research.</p>
            {USES.map(([use, label]) => (
              <div key={use} className="space-y-1">
                <p id={`secondary-${use}`} className="text-sm font-medium">
                  {label}
                </p>
                <div role="group" aria-labelledby={`secondary-${use}`} className="flex flex-wrap gap-x-4 gap-y-1">
                  {providers.map(({ provider, signed_in }) => {
                    const enabled = selected[use] ?? []
                    const checked = enabled.includes(provider)
                    return (
                      <label key={provider} className="flex items-center gap-2 text-sm">
                        <input
                          type="checkbox"
                          className="accent-[var(--app-accent)]"
                          checked={checked}
                          disabled={!checked && !signed_in}
                          onChange={() => save({ [use]: checked ? enabled.filter((value) => value !== provider) : [...enabled, provider] })}
                        />
                        {provider === 'codex' ? 'ChatGPT' : 'Gemini'}
                        {use === 'fallback' && checked && ` (${enabled.indexOf(provider) + 1})`}
                      </label>
                    )
                  })}
                </div>
              </div>
            ))}
          </fieldset>
        </>
      )}
      {update.error && <Notice tone="error">{errorText(update.error)}</Notice>}
    </Card>
  )
}
