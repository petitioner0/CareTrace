import { FormEvent, useCallback, useEffect, useMemo, useState } from 'react'
import { api, ApiError } from './api'
import type { Conflict, Glance, GlanceItem, Patient, Provenance, Role, TimelineEntry, User } from './types'

const roleCopy: Record<Role, { label: string; subtitle: string }> = {
  clinician: { label: 'Clinician', subtitle: 'Full clinical review & decisions' },
  staff: { label: 'Care staff', subtitle: 'Tasks, notes & coordination' },
  patient: { label: 'Patient', subtitle: 'Approved summaries only' },
  admin: { label: 'Clinic admin', subtitle: 'Clinic-scoped oversight' },
}

type Session = { token: string; user: User }

function Login({ onLogin }: { onLogin: (session: Session) => void }) {
  const [busy, setBusy] = useState<Role | null>(null)
  const [error, setError] = useState('')

  async function login(role: Role) {
    setBusy(role)
    setError('')
    try {
      const response = await api<{ access_token: string; user: User }>('/auth/token', undefined, {
        method: 'POST',
        body: JSON.stringify({ email: `${role}@caretrace.demo`, password: 'demo123' }),
      })
      onLogin({ token: response.access_token, user: response.user })
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Could not sign in')
    } finally {
      setBusy(null)
    }
  }

  return (
    <main className="login-page">
      <section className="login-intro">
        <div className="brand-mark">CT</div>
        <p className="eyebrow">LONGITUDINAL CARE NOTE</p>
        <h1>CareTrace</h1>
        <p className="lead">The patient story, compressed for action and anchored to evidence.</p>
        <div className="trust-strip">
          <span>Source-backed</span><span>Role-scoped</span><span>Human-controlled</span>
        </div>
      </section>
      <section className="login-panel" aria-labelledby="demo-title">
        <p className="eyebrow">SYNTHETIC DEMO</p>
        <h2 id="demo-title">Choose a role</h2>
        <p className="muted">Each view uses a real server-issued token and server-enforced permissions.</p>
        <div className="role-grid">
          {(Object.keys(roleCopy) as Role[]).map((role) => (
            <button className="role-card" key={role} onClick={() => login(role)} disabled={Boolean(busy)}>
              <span className={`role-icon ${role}`}>{role === 'clinician' ? 'MD' : role.slice(0, 2).toUpperCase()}</span>
              <strong>{roleCopy[role].label}</strong>
              <small>{busy === role ? 'Signing in…' : roleCopy[role].subtitle}</small>
              <span className="arrow">→</span>
            </button>
          ))}
        </div>
        {error && <p className="error-banner">{error}</p>}
        <p className="demo-note">Synthetic data only · Not clinical decision support</p>
      </section>
    </main>
  )
}

function SourceDrawer({ source, onClose }: { source: Provenance; onClose: () => void }) {
  return (
    <div className="drawer-backdrop" onClick={onClose}>
      <aside className="drawer" onClick={(event) => event.stopPropagation()} aria-label="Source evidence">
        <button className="close-button" onClick={onClose} aria-label="Close source drawer">×</button>
        <p className="eyebrow">PROVENANCE · INTEGRITY {source.integrity.toUpperCase()}</p>
        <h2>Exact source evidence</h2>
        <div className="source-path">
          <span>Highlight</span><b>→</b><span>Entry v{source.entry_version}</span><b>→</b><span>Exact span</span>
        </div>
        <blockquote>{source.original_quote || source.quote}</blockquote>
        <dl className="metadata-list">
          <div><dt>Source support</dt><dd>{source.source_support}</dd></div>
          <div><dt>Match method</dt><dd>{source.match_method}</dd></div>
          <div><dt>Immutable version</dt><dd>{source.source_entry_version_id.slice(0, 8)}</dd></div>
          <div><dt>Original span</dt><dd>{source.original_start_offset}–{source.original_end_offset}</dd></div>
        </dl>
        <button className="primary-button" onClick={() => {
          document.getElementById(`entry-${source.source_entry_id}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' })
          onClose()
        }}>Jump to timeline entry</button>
      </aside>
    </div>
  )
}

function HighlightCard({ item, token, onRefresh, onSource }: {
  item: GlanceItem
  token: string
  onRefresh: () => void
  onSource: (id: string) => void
}) {
  const [expanded, setExpanded] = useState(false)
  const critical = item.risk_floor >= 90
  const elevated = item.risk_floor >= 75

  async function feedback(action: string) {
    await api(`/highlights/${item.id}/feedback`, token, { method: 'POST', body: JSON.stringify({ action }) })
    onRefresh()
  }

  return (
    <article className={`highlight-card ${critical ? 'critical' : elevated ? 'elevated' : ''}`}>
      <div className="highlight-topline">
        <div className="badge-row">
          {critical && <span className="badge risk-critical">Critical floor</span>}
          {!critical && elevated && <span className="badge risk-high">Conflict floor</span>}
          <span className="badge support">✓ {item.source_support}</span>
          {item.unresolved && <span className="badge action">Open action</span>}
        </div>
        <div className="score"><strong>{Math.round(item.score)}</strong><small>priority</small></div>
      </div>
      <h3>{item.text}</h3>
      <p className="risk-reason">{item.risk_reason}</p>
      <div className="card-actions">
        <button className="source-button" onClick={() => onSource(item.provenance_id)}>↗ View exact source</button>
        <button onClick={() => feedback('accept')}>Accept</button>
        <button onClick={() => feedback('pin')}>{item.pinned ? 'Pinned' : 'Pin'}</button>
        <button onClick={() => feedback('reject')}>Reject</button>
        <button className="details-button" onClick={() => setExpanded(!expanded)}>{expanded ? 'Hide score' : 'Why this?'}</button>
      </div>
      {expanded && (
        <div className="score-detail">
          <span>Rule score <b>{item.score_breakdown.rule_score}</b></span>
          <span>Learned bonus <b>{item.score_breakdown.learned_bonus > 0 ? '+' : ''}{item.score_breakdown.learned_bonus}</b></span>
          <span>Risk floor <b>{item.score_breakdown.risk_floor}</b></span>
          <p>Preference can adjust relevance by at most ±8. It cannot suppress a critical floor.</p>
        </div>
      )}
    </article>
  )
}

function TimelineCard({ entry, session, onRefresh }: { entry: TimelineEntry; session: Session; onRefresh: () => void }) {
  const [showHistory, setShowHistory] = useState(false)
  const [versions, setVersions] = useState<Array<{ version: number; changed_section: string; created_at: string }>>([])
  const ownedKeys: Partial<Record<Role, string[]>> = {
    staff: ['staff_note'], clinician: ['clinician_note', 'plan'], admin: ['admin_note'], patient: ['patient_input'],
  }
  const canEdit = entry.sections.some((section) => ownedKeys[session.user.role]?.includes(section.key))

  async function loadHistory() {
    if (!showHistory) {
      setVersions(await api(`/entries/${entry.id}/versions`, session.token))
    }
    setShowHistory(!showHistory)
  }

  async function edit(section: TimelineEntry['sections'][number]) {
    const content = window.prompt('Edit this section. A stale version will be rejected instead of overwritten.', section.content)
    if (!content || content === section.content) return
    try {
      await api(`/entries/${entry.id}/sections/${section.key}`, session.token, {
        method: 'PATCH', body: JSON.stringify({ content, base_version: section.version }),
      })
      onRefresh()
    } catch (reason) {
      if (reason instanceof ApiError && reason.status === 409) window.alert('This section changed elsewhere. Refresh and review the current version before editing.')
      else throw reason
    }
  }

  async function comment() {
    const content = window.prompt('Add an internal comment')
    if (!content) return
    await api(`/entries/${entry.id}/comments`, session.token, { method: 'POST', body: JSON.stringify({ content }) })
    onRefresh()
  }

  return (
    <article className="timeline-card" id={`entry-${entry.id}`}>
      <div className="timeline-marker" />
      <div className="timeline-meta">
        <span className={`entry-type ${entry.author_role}`}>{entry.entry_type.replaceAll('_', ' ')}</span>
        <time>{new Date(entry.created_at).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' })}</time>
        <span>v{entry.current_version}</span>
      </div>
      <h3>{entry.title}</h3>
      {entry.sections.map((section) => (
        <div className="entry-section" key={section.key}>
          <div><span>{section.key.replaceAll('_', ' ')}</span><small>section v{section.version}</small></div>
          <p>{section.content}</p>
          {ownedKeys[session.user.role]?.includes(section.key) && <button onClick={() => edit(section)}>Edit section</button>}
        </div>
      ))}
      {entry.comments.length > 0 && (
        <div className="comments">
          {entry.comments.map((item) => <p key={item.id}><b>Comment</b> {item.content} <span>{item.resolved ? 'Resolved' : 'Open'}</span></p>)}
        </div>
      )}
      <div className="timeline-actions">
        {session.user.role !== 'patient' && <button onClick={comment}>Add comment</button>}
        {session.user.role !== 'patient' && <button onClick={loadHistory}>{showHistory ? 'Hide history' : 'Revision history'}</button>}
        {canEdit && <span className="editable-note">Editable only by {session.user.role}</span>}
      </div>
      {showHistory && <div className="history-list">{versions.map((version) => <span key={version.version}>v{version.version} · {version.changed_section || 'created'}</span>)}</div>}
    </article>
  )
}

function PatientView({ session, patient, onLogout }: { session: Session; patient: Patient; onLogout: () => void }) {
  const [items, setItems] = useState<Array<{ id: string; item_type: string; content: string; approved_at: string }>>([])
  useEffect(() => { api<typeof items>('/patient-facing-items', session.token).then(setItems) }, [session.token])
  return (
    <div className="patient-shell">
      <header className="app-header">
        <div className="brand"><span>CT</span><b>CareTrace</b></div>
        <div className="user-area"><span>Patient view · {session.user.display_name}</span><button onClick={onLogout}>Sign out</button></div>
      </header>
      <main className="patient-main">
        <p className="eyebrow">APPROVED FOR YOU</p>
        <h1>Hello, {patient.name.split(' ')[0]}</h1>
        <p className="lead">Only summaries and instructions approved by your clinical team appear here.</p>
        <div className="patient-items">
          {items.map((item) => <article key={item.id}><span>{item.item_type}</span><h2>{item.content}</h2><small>Clinician approved · {new Date(item.approved_at).toLocaleDateString()}</small></article>)}
        </div>
        <div className="privacy-callout"><b>What is not shown</b><p>Internal comments, raw AI-scribed notes, audit details and care-team drafts remain private.</p></div>
      </main>
    </div>
  )
}

function CareWorkspace({ session, onLogout }: { session: Session; onLogout: () => void }) {
  const [patients, setPatients] = useState<Patient[]>([])
  const [patientId, setPatientId] = useState('')
  const [glance, setGlance] = useState<Glance | null>(null)
  const [timeline, setTimeline] = useState<TimelineEntry[]>([])
  const [conflicts, setConflicts] = useState<Conflict[]>([])
  const [source, setSource] = useState<Provenance | null>(null)
  const [tab, setTab] = useState<'glance' | 'timeline' | 'conflicts'>('glance')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    api<Patient[]>('/patients', session.token).then((data) => {
      setPatients(data)
      if (data[0]) setPatientId(data[0].id)
    }).catch((reason) => setError(String(reason)))
  }, [session.token])

  const refresh = useCallback(async () => {
    if (!patientId) return
    setLoading(true)
    try {
      const [nextGlance, nextTimeline, nextConflicts] = await Promise.all([
        api<Glance>(`/patients/${patientId}/glance`, session.token),
        api<TimelineEntry[]>(`/patients/${patientId}/timeline`, session.token),
        api<Conflict[]>(`/conflicts?patient_id=${patientId}`, session.token),
      ])
      setGlance(nextGlance); setTimeline(nextTimeline); setConflicts(nextConflicts); setError('')
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Unable to load patient') }
    finally { setLoading(false) }
  }, [patientId, session.token])

  useEffect(() => { refresh() }, [refresh])

  async function showSource(id: string) { setSource(await api<Provenance>(`/provenance/${id}`, session.token)) }

  async function addNote(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const data = new FormData(event.currentTarget)
    await api(`/patients/${patientId}/entries`, session.token, {
      method: 'POST', body: JSON.stringify({ title: data.get('title'), content: data.get('content') }),
    })
    event.currentTarget.reset(); await refresh(); setTab('timeline')
  }

  const patient = patients.find((item) => item.id === patientId)
  const openConflicts = conflicts.filter((item) => item.status === 'open')

  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="brand"><span>CT</span><b>CareTrace</b></div>
        <div className="header-center"><span className="live-dot" /> Precomputed glance · no LLM on page load</div>
        <div className="user-area"><span><b>{session.user.display_name}</b><small>{roleCopy[session.user.role].label}</small></span><button onClick={onLogout}>Sign out</button></div>
      </header>
      <aside className="patient-sidebar">
        <p className="eyebrow">PATIENTS</p>
        {patients.map((item) => <button className={item.id === patientId ? 'active' : ''} key={item.id} onClick={() => setPatientId(item.id)}><span>{item.name.split(' ').map((name) => name[0]).join('')}</span><div><b>{item.name}</b><small>{item.display_code}</small></div></button>)}
        <div className="scope-note"><b>Clinic scoped</b><p>Every query is filtered by the clinic in your signed token.</p></div>
      </aside>
      <main className="workspace">
        <section className="patient-heading">
          <div><p className="eyebrow">SHARED CARE NOTE</p><h1>{patient?.name || 'Loading patient…'}</h1><p>{patient?.display_code} · Synthetic demonstration record</p></div>
          <div className="heading-stats"><div><b>{glance?.open_actions.length || 0}</b><span>open actions</span></div><div><b>{openConflicts.length}</b><span>conflicts</span></div></div>
        </section>
        <nav className="tabs" aria-label="Care note views">
          <button className={tab === 'glance' ? 'active' : ''} onClick={() => setTab('glance')}>Glance</button>
          <button className={tab === 'timeline' ? 'active' : ''} onClick={() => setTab('timeline')}>Timeline <span>{timeline.length}</span></button>
          <button className={tab === 'conflicts' ? 'active' : ''} onClick={() => setTab('conflicts')}>Review queue <span>{openConflicts.length}</span></button>
        </nav>
        {error && <p className="error-banner">{error}</p>}
        {loading && <div className="loading-state">Loading the patient record…</div>}
        {!loading && tab === 'glance' && glance && (
          <div className="glance-layout">
            <section>
              <div className="section-title"><div><p className="eyebrow">TOP CARD</p><h2>What needs attention now</h2></div><small>Updated {new Date(glance.generated_at).toLocaleTimeString()}</small></div>
              <div className="policy-notice"><b>Priority support, not diagnosis.</b> {glance.policy_notice}</div>
              <div className="highlight-list">{glance.items.map((item) => <HighlightCard key={item.id} item={item} token={session.token} onRefresh={refresh} onSource={showSource} />)}</div>
            </section>
            <aside className="actions-panel">
              <p className="eyebrow">OPEN ACTIONS</p><h2>{glance.open_actions.length} items</h2>
              {glance.open_actions.map((item) => <button key={item.id} onClick={() => showSource(item.provenance_id)}><span className={item.risk_floor >= 90 ? 'urgent-dot' : 'action-dot'} />{item.text}</button>)}
              {!glance.open_actions.length && <p className="muted">No unresolved actions.</p>}
              <div className="trust-legend"><b>Trust legend</b><span><i className="verified-dot" /> Verified: unique exact quote</span><span><i className="supported-dot" /> Supported: normalized unique match</span></div>
            </aside>
          </div>
        )}
        {!loading && tab === 'timeline' && (
          <div className="timeline-layout">
            <section className="timeline-feed"><div className="section-title"><div><p className="eyebrow">LONGITUDINAL TIMELINE</p><h2>Every entry, in order</h2></div></div>{timeline.map((entry) => <TimelineCard key={entry.id} entry={entry} session={session} onRefresh={refresh} />)}</section>
            <aside><form className="note-form" onSubmit={addNote}><p className="eyebrow">ADD {session.user.role.toUpperCase()} NOTE</p><label>Title<input name="title" required placeholder="e.g. Follow-up call" /></label><label>Note<textarea name="content" required rows={5} placeholder="Add role-owned context…" /></label><button className="primary-button">Add to timeline</button><small>Other roles cannot overwrite this section.</small></form></aside>
          </div>
        )}
        {!loading && tab === 'conflicts' && (
          <section className="conflict-panel"><div className="section-title"><div><p className="eyebrow">HUMAN REVIEW REQUIRED</p><h2>Conflicting clinical facts</h2></div></div>{conflicts.map((conflict) => <article key={conflict.id}><div><span className={`badge ${conflict.status === 'open' ? 'risk-high' : 'support'}`}>{conflict.status}</span><b>{conflict.entity_type} conflict</b></div><p>{conflict.fact_a.quote}</p><p>{conflict.fact_b.quote}</p><small>CareTrace flags the conflict; only a clinician can choose the authoritative fact.</small></article>)}</section>
        )}
      </main>
      {source && <SourceDrawer source={source} onClose={() => setSource(null)} />}
    </div>
  )
}

export default function App() {
  const [session, setSession] = useState<Session | null>(null)
  const [patient, setPatient] = useState<Patient | null>(null)

  useEffect(() => {
    if (!session || session.user.role !== 'patient') return
    api<Patient[]>('/patients', session.token).then((items) => setPatient(items[0] || null))
  }, [session])

  if (!session) return <Login onLogin={setSession} />
  if (session.user.role === 'patient') {
    if (!patient) return <div className="loading-state fullscreen">Loading your approved care information…</div>
    return <PatientView session={session} patient={patient} onLogout={() => { setSession(null); setPatient(null) }} />
  }
  return <CareWorkspace session={session} onLogout={() => setSession(null)} />
}

