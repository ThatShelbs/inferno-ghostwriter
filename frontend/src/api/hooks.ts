import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { EMPTY_CATALOG } from '../lib/formula'
import type { ReferenceKind } from '../lib/references'
import { api } from './client'
import type {
  ABAdoptOut,
  ABDecideIn,
  ABTestOut,
  AddImageIn,
  AuthStatusOut,
  AuthTestOut,
  BaselineDiffOut,
  CopyHtmlOut,
  DetectorStatusOut,
  AddReferenceUrlIn,
  ArchetypeOut,
  EnrichIn,
  EvolutionOut,
  FormulaCatalogOut,
  FormulaIn,
  FormulaOut,
  GitHubStatusOut,
  GenerateIn,
  Health,
  IdeaCreate,
  IdeaLabOut,
  IdeaOut,
  IdeaResearchIn,
  IdeaSessionCreated,
  IdeaSessionIn,
  IdeaSessionOut,
  IdeaSessionSummary,
  IdeaSourcesIn,
  IdeaSourcesOut,
  IdeaUpdate,
  IdeaWriteIn,
  ImageOut,
  ImagePrioritiesIn,
  ImagePrioritiesOut,
  RedrawAllIn,
  InterviewAnswer,
  InterviewQuestionOut,
  ImageFormatOut,
  RemixDimensionOut,
  OpeningCatalogOut,
  JobOut,
  KitBuildIn,
  KitLinkOut,
  KitOut,
  KitPushIn,
  LinkedInPostOut,
  PersonaCreate,
  PersonaDuplicateIn,
  PersonaEvolutionOut,
  PersonaInsightsOut,
  PersonaOut,
  PersonaUpdate,
  ProjectCreate,
  ProjectCreated,
  ProjectOut,
  ProjectSummary,
  ProjectUpdate,
  RewriteIn,
  SampleOut,
  SampleTextIn,
  SampleWritingOut,
  SeedSamplesOut,
  SecondaryStatusOut,
  SettingsIn,
  SettingsOut,
  SurpriseOut,
  UploadResult,
  VoiceProfileOut,
  VoiceProfileVersion,
  VoiceSourceIn,
  RedrawIn,
} from './types.gen'

export const keys = {
  health: ['health'] as const,
  auth: ['auth'] as const,
  secondaryAuth: ['secondary-auth'] as const,
  settings: ['settings'] as const,
  detector: ['detector'] as const,
  personas: ['personas'] as const,
  persona: (id: number) => ['personas', id] as const,
  samples: (personaId: number) => ['personas', personaId, 'samples'] as const,
  voiceProfile: (personaId: number, version?: number) => ['personas', personaId, 'voice-profile', version ?? 'latest'] as const,
  voiceProfileVersions: (personaId: number) => ['personas', personaId, 'voice-profile-versions'] as const,
  seed: ['seed-samples'] as const,
  sampleWriting: ['sample-writing'] as const,
  projects: ['projects'] as const,
  project: (id: number) => ['projects', id] as const,
  imageFormats: (room: string, kind: string) => ['image-formats', room, kind] as const,
  remixOptions: ['remix-options'] as const,
  imagePriorities: (projectId: number) => ['image-priorities', projectId] as const,
  openingStyles: ['opening-styles'] as const,
  formulaCatalog: ['formula-catalog'] as const,
  formulas: ['formulas'] as const,
  evolution: (personaId: number) => ['personas', personaId, 'evolution'] as const,
  insights: (personaId: number) => ['personas', personaId, 'insights'] as const,
  baselineDiff: (projectId: number) => ['projects', projectId, 'baseline-diff'] as const,
  abTest: (id: number) => ['ab-tests', id] as const,
  ideaLab: ['idea-lab'] as const,
  ideaSources: ['idea-sources'] as const,
  ideaSessions: ['idea-sessions'] as const,
  ideaSession: (id: number) => ['idea-sessions', id] as const,
  idea: (id: number) => ['ideas', id] as const,
  ideaBank: (personaId: number) => ['idea-bank', personaId] as const,
}

// -- system --------------------------------------------------------------------

export const useHealth = () => useQuery({ queryKey: keys.health, queryFn: () => api.get<Health>('/api/health') })

export function useAuthStatus(poll = false) {
  return useQuery({
    queryKey: keys.auth,
    queryFn: () => api.get<AuthStatusOut>('/api/auth/status'),
    refetchInterval: (query) => (poll || query.state.data?.login_in_progress ? 2000 : false),
  })
}

export function useAuthActions() {
  const qc = useQueryClient()
  const update = (status: AuthStatusOut) => qc.setQueryData(keys.auth, status)
  return {
    login: useMutation({ mutationFn: () => api.post<AuthStatusOut>('/api/auth/login'), onSuccess: update }),
    claudeCodeLogin: useMutation({ mutationFn: () => api.post<AuthStatusOut>('/api/auth/claude-code/login'), onSuccess: update }),
    logout: useMutation({ mutationFn: () => api.post<AuthStatusOut>('/api/auth/logout'), onSuccess: update }),
    saveKey: useMutation({
      mutationFn: (apiKey: string) => api.put<AuthStatusOut>('/api/auth/api-key', { api_key: apiKey }),
      onSuccess: update,
    }),
    removeKey: useMutation({ mutationFn: () => api.del<AuthStatusOut>('/api/auth/api-key'), onSuccess: update }),
    test: useMutation({ mutationFn: () => api.post<AuthTestOut>('/api/auth/test') }),
  }
}

export const useSettings = () => useQuery({ queryKey: keys.settings, queryFn: () => api.get<SettingsOut>('/api/settings') })

export function useSecondaryStatus(enabled: boolean) {
  return useQuery({
    queryKey: keys.secondaryAuth,
    queryFn: () => api.get<SecondaryStatusOut[]>('/api/auth/secondary'),
    enabled,
    refetchInterval: (query) => (query.state.data?.some((provider) => provider.login_in_progress) ? 2000 : false),
  })
}

/** The models an image dialog may offer: Auto and Claude plus each optional model signed in now; empty when none is. */
export function useImageModels(): ImageRoute[] {
  const { data: settings } = useSettings()
  const { data: providers } = useSecondaryStatus(settings?.demo === false)
  const online = (providers ?? []).filter((p) => p.signed_in).map((p) => p.provider)
  return online.length > 0 ? ['auto', 'claude', ...online] : []
}

export function useSecondaryAuth(provider: SecondaryStatusOut['provider']) {
  const qc = useQueryClient()
  const refresh = () => qc.invalidateQueries({ queryKey: keys.secondaryAuth })
  const path = `/api/auth/secondary/${provider}`
  return {
    login: useMutation({ mutationFn: () => api.post<AuthTestOut>(`${path}/login`), onSettled: refresh }),
    test: useMutation({ mutationFn: () => api.post<AuthTestOut>(`${path}/test`), onSettled: refresh }),
  }
}

export function useUpdateSettings() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: SettingsIn) => api.put<SettingsOut>('/api/settings', body),
    onSuccess: (data, body) => {
      qc.setQueryData(keys.settings, data)
      // The sign-in status depends on which connection is chosen.
      if (body.claude_connection) void qc.invalidateQueries({ queryKey: keys.auth })
    },
  })
}

/** The local AI-detector models; polls while their one-time setup runs. */
export function useDetector() {
  return useQuery({
    queryKey: keys.detector,
    queryFn: () => api.get<DetectorStatusOut>('/api/detector'),
    refetchInterval: (query) => (['queued', 'running'].includes(query.state.data?.job?.status ?? '') ? 3000 : false),
  })
}

export function useSetupDetector() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => api.post<DetectorStatusOut>('/api/detector/setup'),
    onSuccess: (data) => {
      qc.setQueryData(keys.detector, data)
      void qc.invalidateQueries({ queryKey: keys.settings })
    },
  })
}

// -- personas ---------------------------------------------------------------------

export const usePersonas = () => useQuery({ queryKey: keys.personas, queryFn: () => api.get<PersonaOut[]>('/api/personas') })

export function useActivePersona() {
  const personas = usePersonas()
  return { ...personas, data: personas.data?.find((p) => p.is_active) }
}

export const usePersona = (id: number) =>
  useQuery({
    queryKey: keys.persona(id),
    queryFn: () => api.get<PersonaOut>(`/api/personas/${id}`),
    refetchInterval: (query) => (query.state.data?.active_job_id ? 3000 : false),
  })

export function usePersonaMutations() {
  const qc = useQueryClient()
  const refresh = () => qc.invalidateQueries({ queryKey: keys.personas })
  return {
    create: useMutation({ mutationFn: (body: PersonaCreate) => api.post<PersonaOut>('/api/personas', body), onSuccess: refresh }),
    update: useMutation({
      mutationFn: ({ id, body }: { id: number; body: PersonaUpdate }) => api.patch<PersonaOut>(`/api/personas/${id}`, body),
      onSuccess: refresh,
    }),
    activate: useMutation({
      mutationFn: (id: number) => api.post<PersonaOut[]>(`/api/personas/${id}/activate`),
      onSuccess: (data) => {
        qc.setQueryData(keys.personas, data)
        void refresh()
      },
    }),
    remove: useMutation({
      mutationFn: (id: number) => api.del<void>(`/api/personas/${id}`),
      onSuccess: () => {
        void refresh()
        void qc.invalidateQueries({ queryKey: keys.projects })
      },
    }),
    /** Add the example persona, voice profile and finished post (built offline, no Claude call). */
    createExample: useMutation({
      mutationFn: () => api.post<PersonaOut>('/api/example'),
      // Wait for the refetch: callers navigate home next, and an empty cached list would send them back to the setup guide.
      onSuccess: () => Promise.all([refresh(), qc.invalidateQueries({ queryKey: keys.projects })]),
    }),
    removeExample: useMutation({
      mutationFn: () => api.del<void>('/api/example'),
      onSuccess: () => {
        void refresh()
        void qc.invalidateQueries({ queryKey: keys.projects })
      },
    }),
    duplicate: useMutation({
      mutationFn: ({ id, body }: { id: number; body: PersonaDuplicateIn }) => api.post<PersonaOut>(`/api/personas/${id}/duplicate`, body),
      onSuccess: refresh,
    }),
    generateVoiceProfile: useMutation({
      mutationFn: ({ id, label = '' }: { id: number; label?: string }) => api.post<JobOut>(`/api/personas/${id}/voice-profile`, { label }),
      onSuccess: refresh,
    }),
    /** Choose where the voice starts when the author has no writing: archetype, surprise, named writers or interview. */
    setVoiceSource: useMutation({
      mutationFn: ({ id, body }: { id: number; body: VoiceSourceIn }) => api.put<PersonaOut>(`/api/personas/${id}/voice-source`, body),
      onSuccess: (_data, { id }) => {
        void refresh()
        void qc.invalidateQueries({ queryKey: ['personas', id] })
      },
    }),
    clearVoiceSource: useMutation({
      mutationFn: (id: number) => api.del<PersonaOut>(`/api/personas/${id}/voice-source`),
      onSuccess: (_data, id) => {
        void refresh()
        void qc.invalidateQueries({ queryKey: ['personas', id] })
      },
    }),
    /** Which voice profile version new posts use; null = always the latest. */
    pinVersion: useMutation({
      mutationFn: ({ id, version }: { id: number; version: number | null }) =>
        api.patch<PersonaOut>(`/api/personas/${id}`, { pinned_voice_profile_version: version }),
      onSuccess: (_data, { id }) => {
        void refresh()
        void qc.invalidateQueries({ queryKey: ['personas', id] })
      },
    }),
    /** Forget one learned edit (by index) or, without an index, all of them. */
    forgetLessons: useMutation({
      mutationFn: ({ id, index }: { id: number; index?: number }) =>
        api.del<PersonaOut>(`/api/personas/${id}/lessons${index === undefined ? '' : `?index=${index}`}`),
      onSuccess: (_data, { id }) => {
        void refresh()
        void qc.invalidateQueries({ queryKey: ['personas', id] })
      },
    }),
    labelVersion: useMutation({
      mutationFn: ({ id, version, label }: { id: number; version: number; label: string }) =>
        api.patch<VoiceProfileOut>(`/api/personas/${id}/voice-profile/${version}`, { label }),
      onSuccess: (_data, { id }) => {
        void refresh()
        void qc.invalidateQueries({ queryKey: ['personas', id] })
      },
    }),
  }
}

// -- samples & voice profile -------------------------------------------------------------

export const useSamples = (personaId: number) =>
  useQuery({ queryKey: keys.samples(personaId), queryFn: () => api.get<SampleOut[]>(`/api/personas/${personaId}/samples`) })

export const useSeedSamples = () => useQuery({ queryKey: keys.seed, queryFn: () => api.get<SeedSamplesOut>('/api/seed-samples') })

export const useArchetypes = () => useQuery({ queryKey: ['archetypes'], queryFn: () => api.get<ArchetypeOut[]>('/api/archetypes'), staleTime: Infinity })

export const useVoiceInterview = () =>
  useQuery({ queryKey: ['voice-interview'], queryFn: () => api.get<InterviewQuestionOut[]>('/api/voice-interview'), staleTime: Infinity })

/** A random voice; fetch again with a new seed to shuffle. */
export const fetchSurprise = (seed: number) => api.get<SurpriseOut>(`/api/voice-surprise?seed=${seed}`)

export const useSampleWriting = () => useQuery({ queryKey: keys.sampleWriting, queryFn: () => api.get<SampleWritingOut>('/api/sample-writing') })

export function useSampleMutations(personaId: number) {
  const qc = useQueryClient()
  const refresh = () => {
    void qc.invalidateQueries({ queryKey: keys.samples(personaId) })
    void qc.invalidateQueries({ queryKey: keys.personas })
  }
  return {
    upload: useMutation({
      mutationFn: ({ files, kind }: { files: File[]; kind: 'own' | 'influence' }) => {
        const form = new FormData()
        files.forEach((file) => form.append('files', file))
        form.append('kind', kind)
        return api.post<UploadResult>(`/api/personas/${personaId}/samples`, form)
      },
      onSuccess: refresh,
    }),
    importUrl: useMutation({
      mutationFn: ({ url, kind }: { url: string; kind: 'own' | 'influence' }) => api.post<SampleOut>(`/api/personas/${personaId}/samples/url`, { url, kind }),
      onSuccess: refresh,
    }),
    addText: useMutation({
      mutationFn: (body: SampleTextIn) => api.post<SampleOut>(`/api/personas/${personaId}/samples/text`, body),
      onSuccess: refresh,
    }),
    importSampleWriting: useMutation({
      mutationFn: () => api.post<UploadResult>(`/api/personas/${personaId}/samples/import-sample-writing`),
      onSuccess: refresh,
    }),
    importSeed: useMutation({
      mutationFn: () => api.post<UploadResult>(`/api/personas/${personaId}/samples/import-seed`),
      onSuccess: refresh,
    }),
    setKind: useMutation({
      mutationFn: ({ id, kind }: { id: number; kind: 'own' | 'influence' }) => api.patch<SampleOut>(`/api/samples/${id}`, { kind }),
      onSuccess: refresh,
    }),
    remove: useMutation({ mutationFn: (id: number) => api.del<void>(`/api/samples/${id}`), onSuccess: refresh }),
  }
}

export const useVoiceProfile = (personaId: number, version?: number) =>
  useQuery({
    queryKey: keys.voiceProfile(personaId, version),
    queryFn: () => api.get<VoiceProfileOut>(`/api/personas/${personaId}/voice-profile${version ? `?version=${version}` : ''}`),
    retry: false,
  })

export const useVoiceProfileVersions = (personaId: number) =>
  useQuery({
    queryKey: keys.voiceProfileVersions(personaId),
    queryFn: () => api.get<VoiceProfileVersion[]>(`/api/personas/${personaId}/voice-profile/versions`),
  })

export function useSaveVoiceProfile(personaId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ markdown, label = '' }: { markdown: string; label?: string }) =>
      api.put<VoiceProfileOut>(`/api/personas/${personaId}/voice-profile`, { markdown, label }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['personas', personaId] })
      void qc.invalidateQueries({ queryKey: keys.personas })
    },
  })
}

// -- projects -----------------------------------------------------------------------------

export const useProjects = () => useQuery({ queryKey: keys.projects, queryFn: () => api.get<ProjectSummary[]>('/api/projects') })

export const useProject = (id: number) =>
  useQuery({
    queryKey: keys.project(id),
    queryFn: () => api.get<ProjectOut>(`/api/projects/${id}`),
    // Publishing or rating a post starts an analysis in the background; poll until it is ready to review.
    refetchInterval: (query) => (query.state.data?.evolutions?.some((e) => e.state === 'analyzing') ? 2000 : false),
  })

export function useProjectMutations(projectId?: number) {
  const qc = useQueryClient()
  const setProject = (data: ProjectOut) => {
    qc.setQueryData(keys.project(data.id), data)
    void qc.invalidateQueries({ queryKey: keys.projects })
  }
  return {
    create: useMutation({
      mutationFn: (body: ProjectCreate) => api.post<ProjectCreated>('/api/projects', body),
      onSuccess: (data) => setProject(data.project),
    }),
    update: useMutation({
      mutationFn: (body: ProjectUpdate) => api.patch<ProjectOut>(`/api/projects/${projectId}`, body),
      onSuccess: setProject,
    }),
    /** Write the whole post again; with a body, first apply a new brief, dials or persona. */
    generate: useMutation({
      mutationFn: (body?: GenerateIn) => api.post<JobOut>(`/api/projects/${projectId}/generate`, body),
      onSuccess: () => qc.invalidateQueries({ queryKey: keys.project(projectId ?? 0) }),
    }),
    /** Apply the author's feedback with surgical edits; text and images that are not mentioned stay. */
    tweak: useMutation({ mutationFn: (feedback: string) => api.post<JobOut>(`/api/projects/${projectId}/tweak`, { feedback }) }),
    /** Draw an image near a highlighted passage; Claude picks the spot and reworks adjacent text. Follow the job with `useJob`. */
    addImage: useMutation({ mutationFn: (body: AddImageIn) => api.post<JobOut>(`/api/projects/${projectId}/images`, body) }),
    /** Bring back an earlier text version (index 0 = undo the last change). */
    restoreRevision: useMutation({
      mutationFn: (index: number) => api.post<ProjectOut>(`/api/projects/${projectId}/revisions/${index}/restore`),
      onSuccess: setProject,
    }),
    rewrite: useMutation({
      mutationFn: (body: RewriteIn) => api.post<ProjectOut>(`/api/projects/${projectId}/rewrite`, body),
      onSuccess: setProject,
    }),
    /** Replace the title options; the current and pinned titles are kept. */
    regenerateTitles: useMutation({
      mutationFn: () => api.post<ProjectOut>(`/api/projects/${projectId}/titles`),
      onSuccess: setProject,
    }),
    /** Ask 3-5 interview questions for this post (replaces earlier ones). Follow the job with `useJob`. */
    interview: useMutation({ mutationFn: () => api.post<JobOut>(`/api/projects/${projectId}/interview`) }),
    /** Save interview answers without writing the post yet. */
    saveInterview: useMutation({
      mutationFn: (answers: InterviewAnswer[]) => api.put<ProjectOut>(`/api/projects/${projectId}/interview`, { answers }),
      onSuccess: setProject,
    }),
    /** Re-run the AI-generation detection report on the current text. */
    checkAuthenticity: useMutation({
      mutationFn: () => api.post<ProjectOut>(`/api/projects/${projectId}/authenticity`),
      onSuccess: setProject,
    }),
    remove: useMutation({
      mutationFn: (id: number) => api.del<void>(`/api/projects/${id}`),
      onSuccess: () => qc.invalidateQueries({ queryKey: keys.projects }),
    }),
  }
}

// -- A/B tests -------------------------------------------------------------------

/** One A/B test: the two posts by position while it is open; the winner, roles and tweaks once decided. */
export const useABTest = (id: number | null | undefined) =>
  useQuery({ queryKey: keys.abTest(id ?? 0), queryFn: () => api.get<ABTestOut>(`/api/ab-tests/${id}`), enabled: !!id })

export function useABTestMutations(projectId: number, testId?: number) {
  const qc = useQueryClient()
  const refresh = () => {
    void qc.invalidateQueries({ queryKey: keys.project(projectId) })
    void qc.invalidateQueries({ queryKey: keys.projects })
    if (testId) void qc.invalidateQueries({ queryKey: keys.abTest(testId) })
  }
  return {
    refresh,
    /** Write the post twice: as the persona is, and with every setting nudged. A body first applies a new brief, dials or persona. */
    start: useMutation({ mutationFn: (body?: GenerateIn) => api.post<JobOut>(`/api/projects/${projectId}/ab-tests`, body), onSuccess: refresh }),
    decide: useMutation({ mutationFn: (body: ABDecideIn) => api.post<JobOut>(`/api/ab-tests/${testId}/decide`, body) }),
    /** Adopt the chosen tweaks into the persona (an empty list keeps it as it is). */
    adopt: useMutation({
      mutationFn: (tweakIds: string[]) => api.post<ABAdoptOut>(`/api/ab-tests/${testId}/adopt`, { tweak_ids: tweakIds }),
      onSuccess: (data) => {
        qc.setQueryData(keys.abTest(data.ab_test.id), data.ab_test)
        refresh()
        void qc.invalidateQueries({ queryKey: ['personas'] })
      },
    }),
    retry: useMutation({ mutationFn: () => api.post<JobOut>(`/api/ab-tests/${testId}/retry`) }),
    discard: useMutation({ mutationFn: () => api.del<void>(`/api/ab-tests/${testId}`), onSuccess: refresh }),
  }
}

// -- persona evolution -------------------------------------------------------------

/** Proposals learned from this persona's published posts, its edit-rate trend and its playbook. Polls while one is analyzing. */
export const usePersonaEvolution = (personaId: number) =>
  useQuery({
    queryKey: keys.evolution(personaId),
    queryFn: () => api.get<PersonaEvolutionOut>(`/api/personas/${personaId}/evolution`),
    refetchInterval: (query) => (query.state.data?.evolutions.some((e) => e.state === 'analyzing') ? 2000 : false),
  })

/** The persona's Insights page: the voice digest plus charts measured from samples and posts. */
export const usePersonaInsights = (personaId: number) =>
  useQuery({
    queryKey: keys.insights(personaId),
    queryFn: () => api.get<PersonaInsightsOut>(`/api/personas/${personaId}/insights`),
    staleTime: 0,
  })

/** Rebuild the digest for the voice profile in use; follow the returned job with `useJob`. */
export const useRefreshInsights = (personaId: number) => useMutation({ mutationFn: () => api.post<JobOut>(`/api/personas/${personaId}/insights/refresh`) })

/** The generated text against the current text, word by word. */
export const useBaselineDiff = (projectId: number, enabled: boolean) =>
  useQuery({
    queryKey: keys.baselineDiff(projectId),
    queryFn: () => api.get<BaselineDiffOut>(`/api/projects/${projectId}/baseline-diff`),
    enabled,
    staleTime: 0,
  })

export function useEvolutionMutations(personaId: number, projectId?: number) {
  const qc = useQueryClient()
  const refresh = () => {
    void qc.invalidateQueries({ queryKey: keys.evolution(personaId) })
    void qc.invalidateQueries({ queryKey: keys.persona(personaId) })
    void qc.invalidateQueries({ queryKey: keys.personas })
    if (projectId) void qc.invalidateQueries({ queryKey: keys.project(projectId) })
  }
  return {
    refresh,
    /** Analyze a post (again): its edits, or what made it land. */
    analyze: useMutation({
      mutationFn: (kind: 'edits' | 'secret_sauce') => api.post<EvolutionOut>(`/api/projects/${projectId}/evolutions`, { kind }),
      onSuccess: refresh,
    }),
    /** Apply the chosen changes; returns the job (a profile change makes a new voice profile version). */
    apply: useMutation({
      mutationFn: ({ id, itemIds }: { id: number; itemIds: string[] }) => api.post<JobOut>(`/api/evolutions/${id}/apply`, { item_ids: itemIds }),
    }),
    dismiss: useMutation({
      mutationFn: (id: number) => api.post<EvolutionOut>(`/api/evolutions/${id}/dismiss`),
      onSuccess: refresh,
    }),
    /** Forget one playbook entry (by index) or, without an index, all of them. */
    forgetPlaybook: useMutation({
      mutationFn: (index?: number) => api.del<PersonaOut>(`/api/personas/${personaId}/playbook${index === undefined ? '' : `?index=${index}`}`),
      onSuccess: refresh,
    }),
  }
}

// -- idea lab ---------------------------------------------------------------------

/** The research base: trends, when it was last refreshed, and any research job in flight. */
export const useIdeaLab = () => useQuery({ queryKey: keys.ideaLab, queryFn: () => api.get<IdeaLabOut>('/api/idea-lab') })

export const useIdeaSources = (enabled = true) =>
  useQuery({ queryKey: keys.ideaSources, queryFn: () => api.get<IdeaSourcesOut>('/api/idea-lab/sources'), enabled })

export const useIdeaSessions = () => useQuery({ queryKey: keys.ideaSessions, queryFn: () => api.get<IdeaSessionSummary[]>('/api/idea-lab/sessions') })

export const useIdeaSession = (id: number | null | undefined) =>
  useQuery({ queryKey: keys.ideaSession(id ?? 0), queryFn: () => api.get<IdeaSessionOut>(`/api/idea-lab/sessions/${id}`), enabled: !!id })

/** One idea, e.g. to prefill a new post from it. */
export const useIdea = (id: number | null | undefined) =>
  useQuery({ queryKey: keys.idea(id ?? 0), queryFn: () => api.get<IdeaOut>(`/api/ideas/${id}`), enabled: !!id, retry: false })

/** The saved bank: ideas kept (and dismissed) across every brainstorm, newest first. */
export const useIdeaBank = (personaId: number | null | undefined) =>
  useQuery({
    queryKey: keys.ideaBank(personaId ?? 0),
    queryFn: () => {
      const params = new URLSearchParams([
        ['state', 'saved'],
        ['state', 'used'],
        ['state', 'dismissed'],
      ])
      if (personaId) params.set('persona_id', String(personaId))
      return api.get<IdeaOut[]>(`/api/ideas?${params}`)
    },
  })

export function useIdeaLabMutations() {
  const qc = useQueryClient()
  const refreshLab = () => {
    void qc.invalidateQueries({ queryKey: keys.ideaLab })
    void qc.invalidateQueries({ queryKey: keys.ideaSources })
  }
  const refreshBank = () => qc.invalidateQueries({ queryKey: ['idea-bank'] })
  const refreshSessions = () => {
    void refreshBank()
    return qc.invalidateQueries({ queryKey: keys.ideaSessions })
  }
  /** Put a changed idea into its cached session so the board updates at once; the bank reloads. */
  const setIdea = (idea: IdeaOut) => {
    qc.setQueryData(keys.idea(idea.id), idea)
    qc.setQueryData<IdeaSessionOut>(keys.ideaSession(idea.session_id), (session) =>
      session ? { ...session, items: session.items.map((item) => (item.id === idea.id ? idea : item)) } : session,
    )
    void refreshBank()
  }
  return {
    refreshLab,
    refreshSessions,
    /** Refresh the whole research base, or with a query add one more search to it. Follow the job with `useJob`. */
    research: useMutation({ mutationFn: (body: IdeaResearchIn = {}) => api.post<JobOut>('/api/idea-lab/research', body) }),
    brainstorm: useMutation({
      mutationFn: (body: IdeaSessionIn) => api.post<IdeaSessionCreated>('/api/idea-lab/sessions', body),
      onSuccess: (data) => {
        qc.setQueryData(keys.ideaSession(data.session.id), data.session)
        void refreshSessions()
      },
    }),
    deleteSession: useMutation({ mutationFn: (id: number) => api.del<void>(`/api/idea-lab/sessions/${id}`), onSuccess: refreshSessions }),
    deleteTrend: useMutation({ mutationFn: (id: number) => api.del<void>(`/api/idea-lab/trends/${id}`), onSuccess: refreshLab }),
    saveSources: useMutation({
      mutationFn: (body: IdeaSourcesIn) => api.put<IdeaSourcesOut>('/api/idea-lab/sources', body),
      onSuccess: (data) => qc.setQueryData(keys.ideaSources, data),
    }),
    updateIdea: useMutation({
      mutationFn: ({ id, body }: { id: number; body: IdeaUpdate }) => api.patch<IdeaOut>(`/api/ideas/${id}`, body),
      onSuccess: setIdea,
    }),
    /** Add an idea of the author's own straight to the bank. */
    createIdea: useMutation({
      mutationFn: (body: IdeaCreate) => api.post<IdeaOut>('/api/ideas', body),
      onSuccess: setIdea,
    }),
    /** Start a post (or an A/B test) from the idea. */
    writeIdea: useMutation({
      mutationFn: ({ id, body }: { id: number; body: IdeaWriteIn }) => api.post<ProjectCreated>(`/api/ideas/${id}/write`, body),
      onSuccess: (data, { id }) => {
        qc.setQueryData(keys.project(data.project.id), data.project)
        void qc.invalidateQueries({ queryKey: keys.projects })
        void qc.invalidateQueries({ queryKey: keys.idea(id) })
        void qc.invalidateQueries({ queryKey: ['idea-sessions'] })
        void refreshBank()
      },
    }),
  }
}

/** What an image's room can switch to: meme formats, opening styles (plus the meme bank) or other ways to draw it. */
export const useImageFormats = (room: string, kind: string, enabled = true) =>
  useQuery({
    queryKey: keys.imageFormats(room, kind),
    queryFn: () => api.get<ImageFormatOut[]>(`/api/image-formats?room=${encodeURIComponent(room)}&kind=${encodeURIComponent(kind)}`),
    staleTime: Infinity,
    enabled,
  })

/** What a redraw can change (colors, cast, staging, medium); it never changes while the app runs. */
export const useRemixOptions = (enabled = true) =>
  useQuery({ queryKey: keys.remixOptions, queryFn: () => api.get<RemixDimensionOut[]>('/api/remix-options'), staleTime: Infinity, enabled })

/** The chart of styles, formats and looks to prefer or avoid, with this post's and the persona's choices. */
export const useImagePriorities = (projectId: number, enabled = true) =>
  useQuery({
    queryKey: keys.imagePriorities(projectId),
    queryFn: () => api.get<ImagePrioritiesOut>(`/api/projects/${projectId}/image-priorities`),
    enabled,
  })

export function useSetImagePriorities(projectId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: ImagePrioritiesIn) => api.put<ImagePrioritiesOut>(`/api/projects/${projectId}/image-priorities`, body),
    onSuccess: (data) => qc.setQueryData(keys.imagePriorities(projectId), data),
  })
}

const EMPTY_OPENING_CATALOG: OpeningCatalogOut = { styles: [], suggested_by_type: {} }

/** Every way a post can open, and which styles suit each article type; it never changes while the app runs. */
export function useOpeningStyles() {
  const query = useQuery({ queryKey: keys.openingStyles, queryFn: () => api.get<OpeningCatalogOut>('/api/opening-styles'), staleTime: Infinity })
  return { ...query, data: query.data?.styles ? query.data : EMPTY_OPENING_CATALOG }
}

// -- formulas ------------------------------------------------------------------

/** Every article type, opener, body and closer style; it never changes while the app runs. */
export function useFormulaCatalog() {
  const query = useQuery({ queryKey: keys.formulaCatalog, queryFn: () => api.get<FormulaCatalogOut>('/api/formulas/catalog'), staleTime: Infinity })
  return { ...query, data: query.data?.article_types ? query.data : EMPTY_CATALOG }
}

/** The formulas the author saved under a name. */
export function useFormulas() {
  const query = useQuery({ queryKey: keys.formulas, queryFn: () => api.get<FormulaOut[]>('/api/formulas') })
  return { ...query, data: Array.isArray(query.data) ? query.data : [] }
}

export function useFormulaMutations() {
  const qc = useQueryClient()
  const onSuccess = () => qc.invalidateQueries({ queryKey: keys.formulas })
  return {
    create: useMutation({ mutationFn: (body: FormulaIn) => api.post<FormulaOut>('/api/formulas', body), onSuccess }),
    update: useMutation({ mutationFn: ({ id, body }: { id: number; body: FormulaIn }) => api.put<FormulaOut>(`/api/formulas/${id}`, body), onSuccess }),
    remove: useMutation({ mutationFn: (id: number) => api.del<void>(`/api/formulas/${id}`), onSuccess }),
  }
}

/** Who does an image redraw or edit: 'auto' follows Settings -> Image work. */
export type ImageRoute = NonNullable<RedrawIn['model']>

/** What a redraw should make: one of the image's stored ideas, or new pitches in another format, with an optional steer. */
export interface RedrawPicks {
  /** An index from ``image.room.pitches``. */
  concept?: number
  /** A meme format, opening style or way to draw it (see useImageFormats). */
  format?: string
  /** The author's steer in their own words. */
  note?: string
  /** Pinned parts of the redraw's twist, e.g. { palette: 'viridis', cast: 'dogs' }; the rest is chosen for you. */
  tweaks?: Record<string, string>
  /** False skips Claude's critique and only tries the twist. */
  improve?: boolean
  /** Who pitches and designs it: 'auto' follows Settings; an optional model only while it is signed in. */
  model?: ImageRoute
  /** Pitch a new round of ideas (added to the board) and draw the best of them. */
  pitch?: boolean
  /** The hook the board showed for `concept`; the server refuses (409) when the ideas changed since. */
  pitchHook?: string
  /** The author's changes to the idea before it is drawn ("Adjust" on the board). */
  conceptEdit?: { hook?: string; concept?: string; words?: string[] }
}

export function useImageMutations(projectId: number) {
  const qc = useQueryClient()
  const refresh = () => qc.invalidateQueries({ queryKey: keys.project(projectId) })
  return {
    redraw: useMutation({
      mutationFn: ({ id, rethink, ...picks }: { id: number; rethink: boolean } & RedrawPicks) =>
        api.post<JobOut>(`/api/images/${id}/redraw`, {
          rethink,
          concept: picks.concept ?? null,
          format: picks.format ?? null,
          note: picks.note ?? '',
          tweaks: picks.tweaks ?? null,
          improve: picks.improve ?? true,
          model: picks.model ?? 'auto',
          pitch: picks.pitch ?? false,
          pitch_hook: picks.pitchHook ?? null,
          concept_edit: picks.conceptEdit ?? null,
        }),
    }),
    /** Make an image extend an earlier one; it is drawn again from that image's data and look. */
    buildOn: useMutation({
      mutationFn: ({ id, slotId }: { id: number; slotId: string }) => api.post<JobOut>(`/api/images/${id}/build-on`, { slot_id: slotId }),
    }),
    /** Make an image stand on its own again; its picture stays. */
    clearBuildOn: useMutation({ mutationFn: (id: number) => api.del<ImageOut>(`/api/images/${id}/build-on`), onSuccess: refresh }),
    /** Redraw the images that build on this one so they match it again. */
    matchDependents: useMutation({ mutationFn: (id: number) => api.post<JobOut>(`/api/images/${id}/redraw-dependents`) }),
    /** Retype an image's words (a meme or a code-drawn opening image); it is drawn again at once, without asking Claude. */
    words: useMutation({
      mutationFn: ({ id, words }: { id: number; words: Record<string, string> }) => api.put<ImageOut>(`/api/images/${id}/words`, { words }),
      onSuccess: refresh,
    }),
    /** Show another finalist of the image's last fresh run; no call to Claude. */
    pick: useMutation({
      mutationFn: ({ id, index }: { id: number; index: number }) => api.post<ImageOut>(`/api/images/${id}/pick`, { index }),
      onSuccess: refresh,
    }),
    /**
     * Redraw the post's images. With no plan: every image Claude drew, as it is (e.g. after changing the brand kit).
     * With a plan (Image studio): start over, steer with a note, and give each slot its own idea, look and model.
     */
    redrawAll: useMutation({ mutationFn: (plan?: RedrawAllIn) => api.post<JobOut>(`/api/projects/${projectId}/images/redraw`, plan) }),
    /** Change an image as described ("make the arrows orange"), keeping the rest of it. */
    edit: useMutation({
      mutationFn: ({ id, instruction, model }: { id: number; instruction: string; model?: ImageRoute }) =>
        api.post<JobOut>(`/api/images/${id}/edit`, { instruction, model: model ?? 'auto' }),
    }),
    /** Attach a style reference ("make it like this"); the designer and the judge see it on every draw of this image. */
    setReference: useMutation({
      mutationFn: ({ id, file }: { id: number; file: File }) => {
        const form = new FormData()
        form.append('file', file)
        return api.post<ImageOut>(`/api/images/${id}/reference`, form)
      },
      onSuccess: refresh,
    }),
    clearReference: useMutation({ mutationFn: (id: number) => api.del<ImageOut>(`/api/images/${id}/reference`), onSuccess: refresh }),
    upload: useMutation({
      mutationFn: ({ id, file }: { id: number; file: File }) => {
        const form = new FormData()
        form.append('file', file)
        return api.post<ImageOut>(`/api/images/${id}/upload`, form)
      },
      onSuccess: refresh,
    }),
    revert: useMutation({
      mutationFn: ({ id, index }: { id: number; index: number }) => api.post<ImageOut>(`/api/images/${id}/revert`, { index }),
      onSuccess: refresh,
    }),
    update: useMutation({
      mutationFn: ({ id, ...body }: { id: number; caption?: string; alt?: string; credit?: string }) => api.patch<ImageOut>(`/api/images/${id}`, body),
      onSuccess: refresh,
    }),
  }
}

/** References in a post: find more, redraw one (optionally as another kind), swap a version back, or remove one. */
export function useReferenceMutations(projectId: number) {
  const qc = useQueryClient()
  const setProject = (project: ProjectOut) => qc.setQueryData(keys.project(projectId), project)
  return {
    enrich: useMutation({
      mutationFn: (body: EnrichIn = {}) => api.post<JobOut>(`/api/projects/${projectId}/references`, body),
    }),
    addUrl: useMutation({
      mutationFn: (body: AddReferenceUrlIn) => api.post<JobOut>(`/api/projects/${projectId}/references/url`, body),
    }),
    redraw: useMutation({
      mutationFn: ({ id, kind }: { id: number; kind?: ReferenceKind }) => api.post<JobOut>(`/api/references/${id}/redraw`, { kind: kind ?? null }),
    }),
    revert: useMutation({
      mutationFn: ({ id, index }: { id: number; index: number }) => api.post<ProjectOut>(`/api/references/${id}/revert`, { index }),
      onSuccess: setProject,
    }),
    remove: useMutation({
      mutationFn: (id: number) => api.del<ProjectOut>(`/api/references/${id}`),
      onSuccess: setProject,
    }),
  }
}

export const fetchCopyHtml = (projectId: number, platform: string) => api.get<CopyHtmlOut>(`/api/projects/${projectId}/copy/${platform}`)

export const useLinkedInPost = (projectId: number, enabled: boolean) =>
  useQuery({
    queryKey: [...keys.project(projectId), 'linkedin-post'],
    queryFn: () => api.get<LinkedInPostOut>(`/api/projects/${projectId}/linkedin-post`),
    enabled,
  })

export function useWriteLinkedInPost(projectId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => api.post<LinkedInPostOut>(`/api/projects/${projectId}/linkedin-post`),
    onSuccess: (data) => qc.setQueryData([...keys.project(projectId), 'linkedin-post'], data),
  })
}

export const useKit = (projectId: number, enabled: boolean) =>
  useQuery({
    queryKey: [...keys.project(projectId), 'kit'],
    queryFn: () => api.get<KitOut>(`/api/projects/${projectId}/kit`),
    enabled,
  })

export const useGitHubStatus = (enabled: boolean) =>
  useQuery({
    queryKey: ['github-status'],
    queryFn: () => api.get<GitHubStatusOut>('/api/github/status'),
    enabled,
  })

export function useKitActions(projectId: number) {
  const qc = useQueryClient()
  const refresh = () => qc.invalidateQueries({ queryKey: [...keys.project(projectId), 'kit'] })
  return {
    refresh,
    build: useMutation({ mutationFn: (body: KitBuildIn) => api.post<JobOut>(`/api/projects/${projectId}/kit`, body) }),
    push: useMutation({ mutationFn: (body: KitPushIn) => api.post<JobOut>(`/api/projects/${projectId}/kit/push`, body) }),
    link: useMutation({
      mutationFn: () => api.post<KitLinkOut>(`/api/projects/${projectId}/kit/link`),
      onSuccess: () => {
        void qc.invalidateQueries({ queryKey: keys.project(projectId) })
      },
    }),
  }
}
