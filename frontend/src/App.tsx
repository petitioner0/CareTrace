import { FormEvent, useCallback, useEffect, useMemo, useState } from 'react'
import { api, ApiError } from './api'
import type { Conflict, Glance, GlanceItem, Patient, PatientFacingItem, Provenance, Role, TimelineEntry, User } from './types'

const roleCopy: Record<Role, { label: string; subtitle: string }> = {
  clinician: { label: 'Clinician', subtitle: 'Full clinical review & decisions' },
  staff: { label: 'Care staff', subtitle: 'Tasks, notes & coordination' },
  patient: { label: 'Patient', subtitle: 'Approved summaries only' },
  admin: { label: 'Clinic admin', subtitle: 'Clinic-scoped oversight' },
}

type Session = { token: string; user: User }

function Login({ onLogin }: { onLogin: (session: Session) => void }) {
  const [selectedRole, setSelectedRole] = useState<Role | null>(null)
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [busy, setBusy] = useState<Role | null>(null)
  const [error, setError] = useState('')

  function chooseRole(role: Role) {
    setSelectedRole(role)
    setEmail('')
    setPassword('')
    setShowPassword(false)
    setError('')
  }

  function returnToRoles() {
    setSelectedRole(null)
    setEmail('')
    setPassword('')
    setError('')
  }

  async function login(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!selectedRole) return
    setBusy(selectedRole)
    setError('')
    try {
      const response = await api<{ access_token: string; user: User }>('/auth/token', undefined, {
        method: 'POST',
        body: JSON.stringify({ email: email.trim(), password }),
      })
      if (response.user.role !== selectedRole) {
        setError(`This account is registered as ${roleCopy[response.user.role].label}, not ${roleCopy[selectedRole].label}.`)
        return
      }
      onLogin({ token: response.access_token, user: response.user })
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'The email or password did not match this account.')
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
        {!selectedRole ? (
          <>
            <h2 id="demo-title">Choose a role</h2>
            <p className="muted">Choose a view, then sign in with that role's account. Access is still verified by the server.</p>
            <div className="role-grid">
              {(Object.keys(roleCopy) as Role[]).map((role) => (
                <button className="role-card" key={role} onClick={() => chooseRole(role)}>
                  <span className={`role-icon ${role}`}>{role === 'clinician' ? 'MD' : role.slice(0, 2).toUpperCase()}</span>
                  <strong>{roleCopy[role].label}</strong>
                  <small>{roleCopy[role].subtitle}</small>
                  <span className="arrow">→</span>
                </button>
              ))}
            </div>
          </>
        ) : (
          <>
            <button className="back-button" type="button" onClick={returnToRoles}>← Choose another role</button>
            <div className="selected-role">
              <span className={`role-icon ${selectedRole}`}>{selectedRole === 'clinician' ? 'MD' : selectedRole.slice(0, 2).toUpperCase()}</span>
              <div><small>Signing in as</small><h2 id="demo-title">{roleCopy[selectedRole].label}</h2><p>{roleCopy[selectedRole].subtitle}</p></div>
            </div>
            <form className="login-form" onSubmit={login}>
              <label className="login-field">
                <span>Email address</span>
                <input
                  type="email"
                  name="email"
                  autoComplete="username"
                  autoFocus
                  required
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  placeholder={`${selectedRole}@caretrace.demo`}
                />
              </label>
              <label className="login-field">
                <span>Password</span>
                <div className="password-input">
                  <input
                    type={showPassword ? 'text' : 'password'}
                    name="password"
                    autoComplete="current-password"
                    required
                    value={password}
                    onChange={(event) => setPassword(event.target.value)}
                    placeholder="Enter password"
                  />
                  <button type="button" onClick={() => setShowPassword(!showPassword)} aria-label={showPassword ? 'Hide password' : 'Show password'}>
                    {showPassword ? 'Hide' : 'Show'}
                  </button>
                </div>
              </label>
              <div className="demo-credentials">
                <b>Demo credentials</b>
                <span>{selectedRole}@caretrace.demo</span>
                <span>Password: demo123</span>
              </div>
              {error && <p className="error-banner" role="alert" aria-live="polite">{error}</p>}
              <button className="primary-button login-submit" type="submit" disabled={Boolean(busy)}>
                {busy ? 'Verifying account…' : `Sign in as ${roleCopy[selectedRole].label}`}
              </button>
            </form>
          </>
        )}
        <p className="demo-note">Synthetic data only · Not clinical decision support</p>
      </section>
    </main>
  )
}

function SourceDrawer({ source, riskFloor, riskReason, onClose, onJump }: {
  source: Provenance
  riskFloor: number
  riskReason: string
  onClose: () => void
  onJump: (entryId: string) => void
}) {
  const sources = source.sources?.length ? source.sources : [source]
  const riskTone = riskFloor >= 90 ? 'critical' : riskFloor >= 75 ? 'elevated' : 'standard'
  const riskLabel = riskTone === 'critical' ? 'Critical priority' : riskTone === 'elevated' ? 'Elevated priority' : 'Standard priority'
  return (
    <div className={`drawer-backdrop risk-${riskTone}`} onClick={onClose}>
      <aside className={`drawer risk-${riskTone}`} onClick={(event) => event.stopPropagation()} aria-label="Source evidence">
        <button className="close-button" onClick={onClose} aria-label="Close source drawer">×</button>
        <p className="eyebrow">PROVENANCE · ALL SOURCES INTEGRITY VERIFIED</p>
        <h2>{source.multiple_sources ? `${sources.length} evidence sources` : 'Exact source evidence'}</h2>
        <div className="source-risk-context">
          <strong>{riskLabel}</strong>
          <span>{riskReason}</span>
        </div>
        {source.multiple_sources && <div className="multiple-source-notice">Multiple sources matched this evidence. Review every source below.</div>}
        <div className="source-list">
          {sources.map((item, index) => (
            <section className="source-evidence" key={item.id}>
              <div className="source-path">
                <span>Highlight</span><b>→</b><span>Source {index + 1} · Entry v{item.entry_version}</span><b>→</b><span>Exact span</span>
              </div>
              <h3>{item.source_entry_title || `Source ${index + 1}`}</h3>
              <blockquote>{item.original_quote || item.quote}</blockquote>
              <dl className="metadata-list">
                <div><dt>Source support</dt><dd>{item.source_support}</dd></div>
                <div><dt>Match method</dt><dd>{item.match_method}</dd></div>
                <div><dt>Immutable version</dt><dd>{item.source_entry_version_id.slice(0, 8)}</dd></div>
                <div><dt>Original span</dt><dd>{item.original_start_offset}–{item.original_end_offset}</dd></div>
              </dl>
              <button className="primary-button" onClick={() => onJump(item.source_entry_id)}>Jump to this timeline entry</button>
            </section>
          ))}
        </div>
      </aside>
    </div>
  )
}

function HighlightCard({ item, token, onRefresh, onSource }: {
  item: GlanceItem
  token: string
  onRefresh: () => Promise<void>
  onSource: (item: GlanceItem) => void
}) {
  const [expanded, setExpanded] = useState(false)
  const [feedbackBusy, setFeedbackBusy] = useState<string | null>(null)
  const [feedbackError, setFeedbackError] = useState('')
  const critical = item.risk_floor >= 90
  const elevated = item.risk_floor >= 75

  async function feedback(action: string) {
    setFeedbackBusy(action)
    setFeedbackError('')
    try {
      await api(`/highlights/${item.id}/feedback`, token, { method: 'POST', body: JSON.stringify({ action }) })
      await onRefresh()
    } catch (reason) {
      setFeedbackError(reason instanceof Error ? reason.message : 'Unable to save this feedback.')
    } finally {
      setFeedbackBusy(null)
    }
  }

  return (
    <article className={`highlight-card ${critical ? 'critical' : elevated ? 'elevated' : ''}`}>
      <div className="highlight-topline">
        <div className="badge-row">
          {critical && <span className="badge risk-critical">Critical floor</span>}
          {!critical && elevated && <span className="badge risk-high">Conflict floor</span>}
          <span className="badge support">✓ {item.source_support}</span>
          {item.multiple_sources && <span className="badge multiple-source">{item.source_count} sources matched</span>}
          {item.unresolved && <span className="badge action">Open action</span>}
        </div>
        <div className="score"><strong>{Math.round(item.score)}</strong><small>priority</small></div>
      </div>
      <h3>{item.text}</h3>
      <p className="risk-reason">{item.risk_reason}</p>
      <div className="card-actions">
        <button type="button" className="source-button" onClick={() => onSource(item)}>↗ View exact source</button>
        <button type="button" className={item.accepted ? 'feedback-active accepted' : ''} aria-pressed={item.accepted} disabled={Boolean(feedbackBusy) || item.accepted} onClick={() => feedback('accept')}>{feedbackBusy === 'accept' ? 'Saving…' : item.accepted ? 'Accepted' : 'Accept'}</button>
        <button type="button" className={item.highlighted ? 'feedback-active highlighted' : ''} aria-pressed={item.highlighted} disabled={Boolean(feedbackBusy) || item.highlighted} onClick={() => feedback('highlight')}>{feedbackBusy === 'highlight' ? 'Saving…' : item.highlighted ? 'Highlighted' : 'Highlight'}</button>
        <button type="button" className={item.pinned ? 'feedback-active pinned' : ''} aria-pressed={item.pinned} disabled={Boolean(feedbackBusy)} title={item.pinned ? 'Remove pin' : 'Keep at the top'} onClick={() => feedback(item.pinned ? 'unpin' : 'pin')}>{feedbackBusy === 'pin' || feedbackBusy === 'unpin' ? 'Saving…' : item.pinned ? 'Pinned' : 'Pin'}</button>
        <button type="button" className={item.rejected ? 'feedback-active rejected' : ''} aria-pressed={item.rejected} disabled={Boolean(feedbackBusy) || item.rejected} onClick={() => feedback('reject')}>{feedbackBusy === 'reject' ? 'Saving…' : item.rejected ? 'Rejected' : 'Reject'}</button>
        <button type="button" className="details-button" onClick={() => setExpanded(!expanded)}>{expanded ? 'Hide score' : 'Why this?'}</button>
      </div>
      {feedbackError && <p className="feedback-error" role="alert" aria-live="polite">{feedbackError}</p>}
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

function TimelineCard({ entry, session, onRefresh, isTarget = false }: { entry: TimelineEntry; session: Session; onRefresh: () => void; isTarget?: boolean }) {
  const [showHistory, setShowHistory] = useState(false)
  const [versions, setVersions] = useState<Array<{ version: number; changed_section: string; created_at: string }>>([])
  const [showCommentForm, setShowCommentForm] = useState(false)
  const [commentText, setCommentText] = useState('')
  const [commentSubmitting, setCommentSubmitting] = useState(false)
  const [commentError, setCommentError] = useState('')
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

  async function comment(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const content = commentText.trim()
    if (!content) return
    setCommentSubmitting(true)
    setCommentError('')
    try {
      await api(`/entries/${entry.id}/comments`, session.token, { method: 'POST', body: JSON.stringify({ content }) })
      setCommentText('')
      setShowCommentForm(false)
      onRefresh()
    } catch (reason) {
      setCommentError(reason instanceof Error ? reason.message : 'Unable to add this comment.')
    } finally {
      setCommentSubmitting(false)
    }
  }

  return (
    <article className={`timeline-card${isTarget ? ' timeline-target' : ''}`} id={`entry-${entry.id}`} tabIndex={-1}>
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
        {session.user.role !== 'patient' && <button onClick={() => { setShowCommentForm(!showCommentForm); setCommentError('') }} aria-expanded={showCommentForm}>{showCommentForm ? 'Close comment' : 'Add comment'}</button>}
        {session.user.role !== 'patient' && <button onClick={loadHistory}>{showHistory ? 'Hide history' : 'Revision history'}</button>}
        {canEdit && <span className="editable-note">Editable only by {session.user.role}</span>}
      </div>
      {showCommentForm && (
        <form className="comment-form" onSubmit={comment}>
          <label htmlFor={`comment-${entry.id}`}>Internal care-team comment</label>
          <textarea id={`comment-${entry.id}`} value={commentText} onChange={(event) => setCommentText(event.target.value)} rows={3} maxLength={2000} required autoFocus disabled={commentSubmitting} placeholder="Add context, a question, or a handoff note…" />
          {commentError && <p className="note-status error" role="alert" aria-live="polite">{commentError}</p>}
          <div>
            <button type="button" onClick={() => { setShowCommentForm(false); setCommentText(''); setCommentError('') }} disabled={commentSubmitting}>Cancel</button>
            <button className="primary-button" type="submit" disabled={commentSubmitting || !commentText.trim()}>{commentSubmitting ? 'Adding comment…' : 'Add comment'}</button>
          </div>
        </form>
      )}
      {showHistory && <div className="history-list">{versions.map((version) => <span key={version.version}>v{version.version} · {version.changed_section || 'created'}</span>)}</div>}
    </article>
  )
}

function PatientView({ session, patient, onLogout }: { session: Session; patient: Patient; onLogout: () => void }) {
  const [items, setItems] = useState<PatientFacingItem[]>([])
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
  const [source, setSource] = useState<{ provenance: Provenance; highlight: GlanceItem } | null>(null)
  const [tab, setTab] = useState<'glance' | 'timeline' | 'conflicts'>('glance')
  const [targetEntryId, setTargetEntryId] = useState<string | null>(null)
  const [pendingJumpId, setPendingJumpId] = useState<string | null>(null)
  const [noteSubmitting, setNoteSubmitting] = useState(false)
  const [noteStatus, setNoteStatus] = useState<{ tone: 'success' | 'error'; message: string } | null>(null)
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

  const refreshGlance = useCallback(async () => {
    if (!patientId) return
    const nextGlance = await api<Glance>(`/patients/${patientId}/glance`, session.token)
    setGlance(nextGlance)
  }, [patientId, session.token])

  useEffect(() => { refresh() }, [refresh])

  useEffect(() => {
    if (tab !== 'timeline' || loading || !pendingJumpId) return
    const frame = window.requestAnimationFrame(() => {
      const target = document.getElementById(`entry-${pendingJumpId}`)
      if (!target) return
      target.scrollIntoView({ behavior: 'smooth', block: 'center' })
      target.focus({ preventScroll: true })
      setPendingJumpId(null)
    })
    return () => window.cancelAnimationFrame(frame)
  }, [loading, pendingJumpId, tab, timeline])

  async function showSource(highlight: GlanceItem) {
    const provenance = await api<Provenance>(`/provenance/${highlight.provenance_id}`, session.token)
    setSource({ provenance, highlight })
  }

  function jumpToTimelineEntry(entryId: string) {
    setSource(null)
    setTargetEntryId(entryId)
    setPendingJumpId(entryId)
    setTab('timeline')
  }

  async function addNote(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = event.currentTarget
    const data = new FormData(form)
    setNoteSubmitting(true)
    setNoteStatus(null)
    try {
      await api(`/patients/${patientId}/entries`, session.token, {
        method: 'POST', body: JSON.stringify({ title: data.get('title'), content: data.get('content') }),
      })
      form.reset()
      await refresh()
      setTab('timeline')
      setNoteStatus({ tone: 'success', message: 'Note added to the timeline.' })
    } catch (reason) {
      setNoteStatus({ tone: 'error', message: reason instanceof Error ? reason.message : 'Unable to add this note.' })
    } finally {
      setNoteSubmitting(false)
    }
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
              <div className="highlight-list">{glance.items.map((item) => <HighlightCard key={item.id} item={item} token={session.token} onRefresh={refreshGlance} onSource={showSource} />)}</div>
            </section>
            <aside className="actions-panel">
              <p className="eyebrow">OPEN ACTIONS</p><h2>{glance.open_actions.length} items</h2>
              {glance.open_actions.map((item) => <button key={item.id} onClick={() => showSource(item)}><span className={item.risk_floor >= 90 ? 'urgent-dot' : 'action-dot'} />{item.text}</button>)}
              {!glance.open_actions.length && <p className="muted">No unresolved actions.</p>}
              <div className="trust-legend"><b>Trust outcomes</b><span><i className="verified-dot" /> verified: backend-validated exact quote</span><span><i className="supported-dot" /> supported: backend-validated normalized match</span><span><i className="review-dot" /> review_required: not auto-surfaced</span><span><i className="abstained-dot" /> abstained: no eligible claim</span></div>
            </aside>
          </div>
        )}
        {!loading && tab === 'timeline' && (
          <div className="timeline-layout">
            <section className="timeline-feed"><div className="section-title"><div><p className="eyebrow">LONGITUDINAL TIMELINE</p><h2>Every entry, in order</h2></div></div>{timeline.map((entry) => <TimelineCard key={entry.id} entry={entry} session={session} onRefresh={refresh} isTarget={entry.id === targetEntryId} />)}</section>
            <aside><form className="note-form" onSubmit={addNote}><p className="eyebrow">ADD {session.user.role.toUpperCase()} NOTE</p><label>Title<input name="title" required placeholder="e.g. Follow-up call" disabled={noteSubmitting} /></label><label>Note<textarea name="content" required rows={5} placeholder="Add role-owned context…" disabled={noteSubmitting} /></label><button className="primary-button" type="submit" disabled={noteSubmitting}>{noteSubmitting ? 'Adding note…' : 'Add to timeline'}</button>{noteStatus && <p className={`note-status ${noteStatus.tone}`} role={noteStatus.tone === 'error' ? 'alert' : 'status'} aria-live="polite">{noteStatus.message}</p>}<small>Other roles cannot overwrite this section.</small></form></aside>
          </div>
        )}
        {!loading && tab === 'conflicts' && (
          <section className="conflict-panel"><div className="section-title"><div><p className="eyebrow">HUMAN REVIEW QUEUE</p><h2>Conflicting clinical facts</h2></div></div>{conflicts.map((conflict) => <article key={conflict.id}><div><span className={`badge ${conflict.status === 'open' ? 'risk-high' : 'support'}`}>{conflict.status}</span><b>{conflict.entity_type} conflict</b></div><p>{conflict.fact_a.quote}</p><p>{conflict.fact_b.quote}</p><small>CareTrace flags the conflict; only a clinician can choose the authoritative fact.</small></article>)}</section>
        )}
      </main>
      {source && <SourceDrawer source={source.provenance} riskFloor={source.highlight.risk_floor} riskReason={source.highlight.risk_reason} onClose={() => setSource(null)} onJump={jumpToTimelineEntry} />}
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
