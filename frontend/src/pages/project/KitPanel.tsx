import { Check, Download, ExternalLink, FlaskConical, GitBranch, Link2, Upload } from 'lucide-react'
import { useState } from 'react'

import { errorText } from '../../api/client'
import { useGitHubStatus, useKit, useKitActions } from '../../api/hooks'
import type { KitBuildIn, KitOut } from '../../api/types.gen'
import { useJob } from '../../api/useJob'
import { Badge, Button, Field, Input, Notice, ProgressBar, Select, Spinner, Textarea } from '../../components/ui'
import { cx } from '../../lib/cx'

type Library = KitBuildIn['library']

function FitSummary({ kit }: { kit: KitOut }) {
  return (
    <div className="space-y-1">
      <div className="flex flex-wrap items-center gap-2">
        <p className="font-semibold">Hands-on kit</p>
        {kit.fit.recommended && <Badge tone="accent">Recommended for this post</Badge>}
      </div>
      <p className="text-sm text-muted">
        A companion repo readers can follow along with: the whole article as a Jupyter notebook with runnable cells, the chart data, beginner-friendly scripts,
        starter prompts and every image. Open it in Google Colab or push it to your GitHub.
      </p>
      {kit.fit.reasons.length > 0 && <p className="text-xs text-muted">Why it fits: {kit.fit.reasons.join(' · ')}</p>}
    </div>
  )
}

function GitHubSection({ projectId, kit, busy, onJob }: { projectId: number; kit: KitOut; busy: boolean; onJob: (id: string) => void }) {
  const status = useGitHubStatus(true)
  const actions = useKitActions(projectId)
  const [name, setName] = useState<string | null>(null)
  const [visibility, setVisibility] = useState<'private' | 'public'>('private')
  const repo = kit.repo

  if (status.isLoading) return <Spinner label="Checking GitHub" />
  const gh = status.data
  const push = () => actions.push.mutate({ name: name ?? kit.default_name, visibility }, { onSuccess: (job) => onJob(job.id) })

  return (
    <div className="space-y-3 rounded-xl border border-line p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="flex items-center gap-2 font-semibold">
          <GitBranch className="size-4" /> GitHub
        </p>
        {gh?.signed_in && <span className="text-xs text-muted">Signed in as {gh.login}</span>}
      </div>
      {gh && !gh.signed_in && (
        <Notice tone="info" title={gh.installed ? 'Sign in to GitHub' : 'Install the GitHub CLI'}>
          <p>{gh.message}</p>
          <p className="mt-1">
            Then run <code className="rounded bg-surface-2 px-1">{gh.sign_in_command}</code> once in a terminal and{' '}
            <button type="button" className="underline" onClick={() => void status.refetch()}>
              check again
            </button>
            . You can still download the kit as a zip.
          </p>
        </Notice>
      )}
      {repo ? (
        <div className="space-y-2">
          <p className="text-sm">
            <a href={repo.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 font-semibold underline">
              {repo.owner}/{repo.name} <ExternalLink className="size-3" />
            </a>{' '}
            <Badge>{repo.visibility}</Badge>
          </p>
          <div className="flex flex-wrap gap-2">
            {repo.colab_url && (
              <a href={repo.colab_url} target="_blank" rel="noreferrer">
                <Button size="sm" variant="secondary" icon={<FlaskConical className="size-4" />}>
                  Open in Colab
                </Button>
              </a>
            )}
            <Button
              size="sm"
              variant="secondary"
              icon={<Upload className="size-4" />}
              disabled={!gh?.signed_in || busy}
              onClick={push}
              loading={actions.push.isPending}
            >
              Push update
            </Button>
            <Button
              size="sm"
              icon={kit.linked ? <Check className="size-4" /> : <Link2 className="size-4" />}
              disabled={kit.linked}
              loading={actions.link.isPending}
              onClick={() => actions.link.mutate(undefined, { onSuccess: () => void actions.refresh() })}
            >
              {kit.linked ? 'Linked in your post' : 'Add link to post'}
            </Button>
          </div>
          {repo.visibility === 'private' && (
            <p className="text-xs text-muted">Colab can open notebooks from public repos only. Make it public on GitHub when you publish.</p>
          )}
        </div>
      ) : (
        <div className="space-y-3">
          <Field label="Repository name" htmlFor="kit-repo-name">
            <Input id="kit-repo-name" value={name ?? kit.default_name} onChange={(e) => setName(e.target.value)} disabled={!gh?.signed_in} />
          </Field>
          <div className="flex gap-2" role="radiogroup" aria-label="Visibility">
            {(['private', 'public'] as const).map((v) => (
              <button
                key={v}
                type="button"
                role="radio"
                aria-checked={visibility === v}
                onClick={() => setVisibility(v)}
                className={cx(
                  'rounded-lg border px-3 py-1.5 text-sm capitalize',
                  visibility === v ? 'border-accent bg-accent-soft' : 'border-line hover:bg-surface-2',
                )}
              >
                {v}
              </button>
            ))}
          </div>
          <Button icon={<Upload className="size-4" />} disabled={!gh?.signed_in || busy || !kit.built} loading={actions.push.isPending} onClick={push}>
            Create repo &amp; push
          </Button>
        </div>
      )}
      {(actions.push.error || actions.link.error) && <Notice tone="error">{errorText(actions.push.error ?? actions.link.error)}</Notice>}
    </div>
  )
}

export function KitPanel({ projectId }: { projectId: number }) {
  const kit = useKit(projectId, true)
  const actions = useKitActions(projectId)
  const [jobId, setJobId] = useState<string | null>(null)
  const [library, setLibrary] = useState<Library | null>(null)
  const [articleUrl, setArticleUrl] = useState<string | null>(null)
  const [note, setNote] = useState<string | null>(null)
  const job = useJob(jobId, () => {
    setJobId(null)
    void actions.refresh()
  })
  const [lastError, setLastError] = useState<string | null>(null)

  if (kit.isLoading || !kit.data) return kit.error ? <Notice tone="error">{errorText(kit.error)}</Notice> : <Spinner label="Loading the kit" />
  const data = kit.data
  const busy = jobId !== null
  const build = () => {
    setLastError(null)
    actions.build.mutate(
      { library: library ?? (data.library as Library), article_url: articleUrl ?? data.article_url, note: note ?? data.note },
      { onSuccess: (j) => setJobId(j.id), onError: (e) => setLastError(errorText(e)) },
    )
  }
  const failed = job.status === 'failed' ? job.error : null

  return (
    <div className="space-y-4">
      <FitSummary kit={data} />
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Charts" htmlFor="kit-library">
          <Select id="kit-library" value={library ?? data.library} onChange={(e) => setLibrary(e.target.value as Library)}>
            {data.libraries.map((l) => (
              <option key={l.id} value={l.id}>
                {l.label}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Article link (optional)" htmlFor="kit-article-url" hint="Shown in the README once the post is live.">
          <Input id="kit-article-url" placeholder="https://" value={articleUrl ?? data.article_url} onChange={(e) => setArticleUrl(e.target.value)} />
        </Field>
      </div>
      <Field label="Note for the kit (optional)" htmlFor="kit-note">
        <Textarea
          id="kit-note"
          rows={2}
          className="text-sm"
          placeholder="e.g. Use the public penguins dataset; add a cell that compares two models."
          value={note ?? data.note}
          onChange={(e) => setNote(e.target.value)}
        />
      </Field>
      <div className="flex flex-wrap gap-2">
        <Button icon={<FlaskConical className="size-4" />} onClick={build} loading={actions.build.isPending} disabled={busy}>
          {data.built ? 'Rebuild kit' : 'Build kit'}
        </Button>
        {data.built && (
          <a href={`/api/projects/${projectId}/kit/download`} download>
            <Button variant="secondary" icon={<Download className="size-4" />} disabled={busy}>
              Download kit (.zip)
            </Button>
          </a>
        )}
      </div>
      {busy && (
        <div className="space-y-1">
          <ProgressBar value={job.progress} label="Kit progress" />
          <p className="text-xs text-muted">{job.message || 'Working…'}</p>
        </div>
      )}
      {(failed || lastError) && <Notice tone="error">{failed ?? lastError}</Notice>}
      {data.notes.length > 0 && (
        <Notice tone="warn" title="Left out of the kit">
          <ul className="list-disc pl-4">
            {data.notes.map((n) => (
              <li key={n}>{n}</li>
            ))}
          </ul>
        </Notice>
      )}
      {data.built && (
        <details className="rounded-xl border border-line p-3 text-sm">
          <summary className="cursor-pointer font-semibold">{data.files.length} files</summary>
          <ul className="mt-2 columns-1 font-mono text-xs sm:columns-2">
            {data.files.map((f) => (
              <li key={f}>{f}</li>
            ))}
          </ul>
        </details>
      )}
      {data.built && <GitHubSection projectId={projectId} kit={data} busy={busy} onJob={setJobId} />}
    </div>
  )
}
