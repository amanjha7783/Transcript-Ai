import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from 'react'
import {
  Activity, ArrowDownToLine, ArrowLeft, BookOpen, BrainCircuit, Check, ChevronRight,
  CircleHelp, Clock3, FileAudio, FileText, Film, Globe2, Languages, Library,
  ListVideo, LoaderCircle, LogOut, MessageSquareText, Moon, Plus, Search,
  Send, Settings2, Sparkles, Subtitles, Sun, Trash2, UploadCloud, Video,
  WandSparkles, X,
} from 'lucide-react'
import { api, downloadExport, mediaUrl } from './lib/api'

type VideoItem = {
  id: string; title: string; source_type: string; source_url?: string; thumbnail_url?: string;
  duration?: number; language?: string; status: string; rag_status: string; error_message?: string;
  created_at?: string;
}
type Segment = { text: string; start: number; end: number; speaker?: string | null }
type ChatItem = { role: 'user' | 'assistant'; content: string; sources?: { start: number; end: number; text: string; score?: number }[] }

const languages = [
  ['hi', 'Hindi'], ['en', 'English'], ['mr', 'Marathi'], ['bn', 'Bengali'], ['gu', 'Gujarati'],
  ['ta', 'Tamil'], ['te', 'Telugu'], ['kn', 'Kannada'], ['ml', 'Malayalam'], ['pa', 'Punjabi'],
  ['ur', 'Urdu'], ['es', 'Spanish'], ['fr', 'French'], ['de', 'German'], ['zh', 'Chinese'],
  ['ja', 'Japanese'], ['ar', 'Arabic'], ['pt', 'Portuguese'],
]
const tabs = [
  { id: 'transcript', label: 'Transcript', icon: FileText },
  { id: 'translate', label: 'Translate', icon: Languages },
  { id: 'summary', label: 'Summary', icon: Sparkles },
  { id: 'chat', label: 'Ask video', icon: MessageSquareText },
  { id: 'study', label: 'Study tools', icon: BookOpen },
  { id: 'chapters', label: 'Chapters', icon: ListVideo },
  { id: 'subtitles', label: 'Subtitles', icon: Subtitles },
  { id: 'export', label: 'Export', icon: ArrowDownToLine },
]

function formatTime(value = 0) {
  const s = Math.max(0, Math.floor(value))
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60
  return h > 0 ? `${h}:${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}` : `${m}:${String(sec).padStart(2, '0')}`
}
function errorMessage(error: any) {
  return error?.response?.data?.detail || error?.message || 'Something went wrong. Please try again.'
}

export default function App() {
  const [token, setToken] = useState(localStorage.getItem('videomind_token') || '')
  const [userEmail, setUserEmail] = useState('')
  const [dark, setDark] = useState(true)
  const [videos, setVideos] = useState<VideoItem[]>([])
  const [selected, setSelected] = useState<VideoItem | null>(null)
  const [loading, setLoading] = useState(false)
  const [notice, setNotice] = useState('')
  const [error, setError] = useState('')

  const refreshVideos = useCallback(async () => {
    const response = await api.get('/videos')
    setVideos(response.data)
    if (selected) {
      const updated = response.data.find((v: VideoItem) => v.id === selected.id)
      if (updated) setSelected(updated)
    }
  }, [selected])

  useEffect(() => {
    if (!token) return
    api.get('/auth/me').then((res) => setUserEmail(res.data.email)).catch(() => {
      localStorage.removeItem('videomind_token'); setToken('')
    })
    refreshVideos().catch((e) => setError(errorMessage(e)))
  }, [token]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!notice && !error) return
    const timer = window.setTimeout(() => { setNotice(''); setError('') }, 5200)
    return () => window.clearTimeout(timer)
  }, [notice, error])

  const login = async (email: string, password: string, mode: 'login' | 'register') => {
    const response = await api.post(`/auth/${mode === 'login' ? 'login' : 'register'}`, { email, password })
    localStorage.setItem('videomind_token', response.data.access_token)
    setToken(response.data.access_token)
    setUserEmail(response.data.user.email)
  }
  const logout = () => {
    localStorage.removeItem('videomind_token'); setToken(''); setSelected(null); setVideos([])
  }
  const addVideo = async (file?: File, url?: string) => {
    setLoading(true); setError(''); setNotice('')
    try {
      let response
      if (file) {
        const body = new FormData(); body.append('file', file)
        response = await api.post('/videos/upload', body, { headers: { 'Content-Type': 'multipart/form-data' } })
      } else {
        response = await api.post('/videos/process-url', { url })
      }
      setSelected(response.data)
      setNotice('Video added. Processing has started; this page will update automatically.')
      await refreshVideos()
    } catch (e) { setError(errorMessage(e)) }
    finally { setLoading(false) }
  }
  const removeVideo = async (video: VideoItem) => {
    if (!window.confirm(`Delete “${video.title}” and its processed data?`)) return
    try {
      await api.delete(`/videos/${video.id}`)
      if (selected?.id === video.id) setSelected(null)
      await refreshVideos(); setNotice('Video deleted.')
    } catch (e) { setError(errorMessage(e)) }
  }

  if (!token) return <AuthScreen onAuth={login} />

  return (
    <div className={dark ? 'app dark' : 'app light'}>
      <aside className="sidebar">
        <div className="brand"><div className="brand-mark"><BrainCircuit size={22} /></div><div><b>VideoMind</b><span>AI workspace</span></div></div>
        <div className="side-label">WORKSPACE</div>
        <button className={`side-link ${!selected ? 'active' : ''}`} onClick={() => setSelected(null)}><Library size={17} /> My library</button>
        <button className="side-link" onClick={() => document.getElementById('upload-card')?.scrollIntoView({ behavior: 'smooth' })}><Plus size={17} /> New video</button>
        <div className="side-label side-spacer">YOUR LIBRARY <span>{videos.length}</span></div>
        <div className="side-video-list">
          {videos.slice(0, 7).map((video) => (
            <button className={`side-video ${selected?.id === video.id ? 'selected' : ''}`} key={video.id} onClick={() => setSelected(video)}>
              <Film size={15} /><span>{video.title}</span>
            </button>
          ))}
          {!videos.length && <p className="side-empty">Your processed videos will appear here.</p>}
        </div>
        <div className="sidebar-bottom">
          <div className="user-mini"><div className="avatar">{userEmail.slice(0, 1).toUpperCase() || 'U'}</div><div className="user-copy"><b>{userEmail || 'Your account'}</b><span>Personal workspace</span></div></div>
          <button className="side-link" onClick={() => setDark(!dark)}>{dark ? <Sun size={17} /> : <Moon size={17} />} {dark ? 'Light mode' : 'Dark mode'}</button>
          <button className="side-link" onClick={logout}><LogOut size={17} /> Sign out</button>
        </div>
      </aside>

      <main className="main-area">
        <header className="topbar">
          <div className="breadcrumb"><span>Workspace</span><ChevronRight size={14} /><b>{selected ? 'Video workspace' : 'My library'}</b></div>
          <div className="topbar-right"><span className="status-dot" /> <span>AI services ready to configure</span><div className="top-avatar">{userEmail.slice(0, 1).toUpperCase()}</div></div>
        </header>
        {notice && <div className="toast success"><Check size={16} />{notice}<button onClick={() => setNotice('')}><X size={14} /></button></div>}
        {error && <div className="toast danger"><CircleHelp size={16} />{error}<button onClick={() => setError('')}><X size={14} /></button></div>}
        {selected ? <VideoWorkspace video={selected} onBack={() => setSelected(null)} onUpdated={refreshVideos} onError={setError} /> : (
          <Dashboard videos={videos} loading={loading} onAdd={addVideo} onOpen={setSelected} onDelete={removeVideo} />
        )}
        <footer className="footer"><span>VideoMind AI</span><span>Multilingual video understanding · RAG-powered learning</span></footer>
      </main>
    </div>
  )
}

function AuthScreen({ onAuth }: { onAuth: (email: string, password: string, mode: 'login' | 'register') => Promise<void> }) {
  const [mode, setMode] = useState<'login' | 'register'>('register')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const submit = async (event: FormEvent) => {
    event.preventDefault(); setBusy(true); setError('')
    try { await onAuth(email, password, mode) } catch (e) { setError(errorMessage(e)) } finally { setBusy(false) }
  }
  return <div className="auth-page">
    <div className="auth-visual"><div className="auth-brand"><div className="brand-mark"><BrainCircuit size={22} /></div><b>VideoMind AI</b></div><div className="auth-copy"><div className="eyebrow"><Sparkles size={14} /> YOUR VIDEO KNOWLEDGE STUDIO</div><h1>Understand any video.<br /><em>In any language.</em></h1><p>Turn lectures, tutorials, and talks into searchable knowledge, accurate answers, and study material.</p><div className="feature-pills"><span><Languages size={15} /> Multilingual</span><span><BrainCircuit size={15} /> RAG-powered</span><span><Subtitles size={15} /> Timestamped</span></div></div><div className="visual-orbit orbit-one"/><div className="visual-orbit orbit-two"/><div className="auth-foot">TRANSCRIBE · TRANSLATE · UNDERSTAND</div></div>
    <div className="auth-panel"><form className="auth-form" onSubmit={submit}><div className="eyebrow">WELCOME TO VIDEOMIND</div><h2>{mode === 'register' ? 'Create your workspace' : 'Welcome back'}</h2><p className="muted">{mode === 'register' ? 'Start turning video into knowledge.' : 'Sign in to continue to your video library.'}</p><label>Email address<input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@example.com" required /></label><label>Password<input type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="At least 8 characters" minLength={8} required /></label>{error && <div className="inline-error">{error}</div>}<button className="primary-btn full" disabled={busy}>{busy ? <LoaderCircle className="spin" size={17} /> : null}{mode === 'register' ? 'Create account' : 'Sign in'} <ChevronRight size={17} /></button><p className="auth-switch">{mode === 'register' ? 'Already have an account?' : 'New to VideoMind?'} <button type="button" onClick={() => setMode(mode === 'register' ? 'login' : 'register')}>{mode === 'register' ? 'Sign in' : 'Create account'}</button></p><div className="auth-note">Your videos and transcripts are private to your account.</div></form></div>
  </div>
}

function Dashboard({ videos, loading, onAdd, onOpen, onDelete }: {
  videos: VideoItem[]; loading: boolean; onAdd: (file?: File, url?: string) => Promise<void>;
  onOpen: (video: VideoItem) => void; onDelete: (video: VideoItem) => void;
}) {
  const [url, setUrl] = useState('')
  const [dragging, setDragging] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)
  const [search, setSearch] = useState('')
  const filtered = useMemo(() => videos.filter((v) => v.title.toLowerCase().includes(search.toLowerCase())), [videos, search])
  const submitUrl = async (e: FormEvent) => { e.preventDefault(); if (!url.trim()) return; await onAdd(undefined, url.trim()); setUrl('') }
  const upload = async (file?: File) => { if (file) await onAdd(file) }
  return <div className="page-content dashboard-page">
    <div className="page-heading"><div><div className="eyebrow">YOUR KNOWLEDGE WORKSPACE</div><h1>My library<span className="heading-period">.</span></h1><p>Bring a video. Get the knowledge inside it.</p></div><div className="heading-badge"><Sparkles size={15} /> RAG-powered video intelligence</div></div>
    <section className="ingest-grid" id="upload-card">
      <div className={`upload-card ${dragging ? 'dragging' : ''}`} onDragOver={(e) => { e.preventDefault(); setDragging(true) }} onDragLeave={() => setDragging(false)} onDrop={(e) => { e.preventDefault(); setDragging(false); upload(e.dataTransfer.files[0]) }}>
        <div className="card-topline"><div className="icon-tile purple"><UploadCloud size={20} /></div><span className="step-label">01 / UPLOAD</span></div><h3>Upload a video</h3><p>Drop a lecture, tutorial, or recording. We'll extract its speech and build a searchable transcript.</p><button className="primary-btn" onClick={() => inputRef.current?.click()} disabled={loading}>{loading ? <LoaderCircle className="spin" size={16} /> : <Plus size={16} />} Choose video file</button><input ref={inputRef} type="file" accept="video/mp4,video/quicktime,video/x-msvideo,video/x-matroska,video/webm,.mkv" hidden onChange={(e) => upload(e.target.files?.[0])} /><div className="support-line"><FileAudio size={13} /> MP4, MOV, AVI, MKV, WebM · up to configured limit</div>
      </div>
      <div className="url-card"><div className="card-topline"><div className="icon-tile blue"><Globe2 size={20} /></div><span className="step-label">02 / PUBLIC LINK</span></div><h3>Paste a video link</h3><p>Start from an accessible public video. Caption retrieval is supported for YouTube in this MVP.</p><form onSubmit={submitUrl} className="url-form"><input type="url" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://www.youtube.com/watch?v=..." required /><button className="primary-btn" disabled={loading || !url.trim()}>{loading ? <LoaderCircle className="spin" size={16} /> : <ArrowDownToLine size={16} />} Process link</button></form><div className="support-line"><Globe2 size={13} /> Public captions required · platform access rules apply</div></div>
    </section>
    <section className="library-section"><div className="section-heading"><div><div className="eyebrow">RECENT WORK</div><h2>Your videos <span className="count-pill">{videos.length}</span></h2></div><div className="search-box"><Search size={16} /><input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search your library" /></div></div>
      {filtered.length ? <div className="video-grid">{filtered.map((video) => <VideoCard key={video.id} video={video} onOpen={() => onOpen(video)} onDelete={() => onDelete(video)} />)}</div> : <div className="empty-state"><div className="empty-icon"><Film size={26} /></div><h3>{videos.length ? 'No matching videos' : 'Your library is ready'}</h3><p>{videos.length ? 'Try another title or clear your search.' : 'Upload a video or paste a public YouTube link to create your first transcript.'}</p></div>}
    </section>
    <section className="workflow-strip"><div><span className="workflow-number">01</span><b>Transcribe</b><small>Speech to timestamped text</small></div><ChevronRight size={16} /><div><span className="workflow-number">02</span><b>Index with RAG</b><small>Chunks, embeddings, retrieval</small></div><ChevronRight size={16} /><div><span className="workflow-number">03</span><b>Understand</b><small>Chat, translate, learn, export</small></div></section>
  </div>
}

function VideoCard({ video, onOpen, onDelete }: { video: VideoItem; onOpen: () => void; onDelete: () => void }) {
  const ready = video.status === 'ready'
  return <article className="video-card"><button className="video-thumb" onClick={onOpen}>
    {video.thumbnail_url ? <img src={video.thumbnail_url} alt="Video thumbnail" /> : <div className="thumb-placeholder"><Film size={28} /></div>}
    <span className={`status-chip ${ready ? 'ready' : video.status === 'failed' ? 'failed' : 'working'}`}>{ready ? <Check size={12} /> : video.status === 'failed' ? <X size={12} /> : <LoaderCircle size={12} className="spin" />}{video.status}</span>
  </button><div className="video-card-body"><button className="video-title" onClick={onOpen}>{video.title}</button><div className="video-meta"><span><Languages size={12} /> {video.language || 'Detecting language'}</span><span><Clock3 size={12} /> {video.duration ? formatTime(video.duration) : '—'}</span></div><div className="video-card-footer"><span className={`rag-label ${video.rag_status === 'indexed' ? 'ok' : ''}`}><span /> {video.rag_status === 'indexed' ? 'RAG indexed' : video.rag_status.replace('_', ' ')}</span><button className="icon-button danger-hover" onClick={onDelete} title="Delete video"><Trash2 size={15} /></button></div>{video.error_message && <p className="card-error">{video.error_message}</p>}</div></article>
}

function VideoWorkspace({ video, onBack, onUpdated, onError }: { video: VideoItem; onBack: () => void; onUpdated: () => Promise<void>; onError: (message: string) => void }) {
  const [activeTab, setActiveTab] = useState('transcript')
  const [currentVideo, setCurrentVideo] = useState(video)
  const [segments, setSegments] = useState<Segment[]>([])
  const [translation, setTranslation] = useState<Segment[]>([])
  const [targetLanguage, setTargetLanguage] = useState('hi')
  const [languageName, setLanguageName] = useState('Hindi')
  const [selectedLanguage, setSelectedLanguage] = useState('original')
  const [summaryKind, setSummaryKind] = useState('detailed')
  const [summaryLanguage, setSummaryLanguage] = useState('original')
  const [summary, setSummary] = useState('')
  const [question, setQuestion] = useState('')
  const [chatLanguage, setChatLanguage] = useState('auto')
  const [youtubeStart, setYoutubeStart] = useState(0)
  const [chat, setChat] = useState<ChatItem[]>([])
  const [studyKind, setStudyKind] = useState('notes')
  const [studyResult, setStudyResult] = useState<any>(null)
  const [difficulty, setDifficulty] = useState('medium')
  const [count, setCount] = useState(10)
  const [chapters, setChapters] = useState<any[]>([])
  const [search, setSearch] = useState('')
  const [searchResults, setSearchResults] = useState<any[]>([])
  const [busy, setBusy] = useState(false)
  const [saveBusy, setSaveBusy] = useState(false)
  const [subFormat, setSubFormat] = useState('srt')
  const [exportKind, setExportKind] = useState('transcript')
  const [exportFormat, setExportFormat] = useState('pdf')
  const [activeTime, setActiveTime] = useState(0)
  const [translationLanguages, setTranslationLanguages] = useState<string[]>([])
  const videoRef = useRef<HTMLVideoElement>(null)
  const transcriptRef = useRef<HTMLDivElement>(null)

  const refresh = useCallback(async () => {
    const [statusRes, transcriptRes, translationsRes, chaptersRes, chatRes] = await Promise.all([
      api.get(`/videos/${video.id}/status`), api.get(`/videos/${video.id}/transcript`),
      api.get(`/videos/${video.id}/translations`), api.get(`/videos/${video.id}/chapters`),
      api.get(`/videos/${video.id}/chat-history`),
    ])
    setCurrentVideo((old) => ({ ...old, ...statusRes.data }))
    setSegments(transcriptRes.data.segments || [])
    setTranslationLanguages(translationsRes.data.map((item: any) => item.language))
    setChapters(chaptersRes.data || [])
    setChat(chatRes.data || [])
  }, [video.id])

  useEffect(() => { refresh().catch((e) => onError(errorMessage(e))) }, [refresh])
  useEffect(() => {
    if (currentVideo.status === 'ready' || currentVideo.status === 'failed') return
    const id = window.setInterval(() => { refresh().catch(() => undefined) }, 3000)
    return () => window.clearInterval(id)
  }, [currentVideo.status, refresh])

  const runAction = async (fn: () => Promise<void>) => {
    setBusy(true)
    try { await fn() } catch (e) { onError(errorMessage(e)) } finally { setBusy(false) }
  }
  const seek = (time: number) => {
    if (youtubeId) setYoutubeStart(Math.floor(time))
    if (videoRef.current) { videoRef.current.currentTime = time; videoRef.current.play().catch(() => undefined) }
    setActiveTime(time)
  }
  const translate = () => runAction(async () => {
    const language = languages.find(([code]) => code === targetLanguage)?.[1] || targetLanguage
    setLanguageName(language)
    const response = await api.post(`/videos/${video.id}/translate`, { language: targetLanguage, language_name: language })
    setTranslation(response.data.segments); setSelectedLanguage(targetLanguage)
    if (!translationLanguages.includes(targetLanguage)) setTranslationLanguages((old) => [...old, targetLanguage])
    await onUpdated()
  })
  const loadTranslation = async (code: string) => {
    setSelectedLanguage(code)
    if (code === 'original') { setTranslation([]); return }
    await runAction(async () => {
      const response = await api.get(`/videos/${video.id}/translations/${code}`)
      setTranslation(response.data.segments || [])
    })
  }
  const createSummary = () => runAction(async () => {
    const response = await api.post(`/videos/${video.id}/summarize`, { kind: summaryKind, language: summaryLanguage })
    setSummary(response.data.content); setActiveTab('summary')
  })
  const sendQuestion = () => runAction(async () => {
    if (!question.trim()) return
    const text = question.trim(); setQuestion(''); setChat((old) => [...old, { role: 'user', content: text }])
    try {
      const response = await api.post(`/videos/${video.id}/chat`, { question: text, language: chatLanguage, top_k: 5 })
      setChat((old) => [...old, { role: 'assistant', content: response.data.answer, sources: response.data.sources }])
    } catch (e) { setChat((old) => [...old, { role: 'assistant', content: `Unable to answer: ${errorMessage(e)}` }]); throw e }
  })
  const createStudy = () => runAction(async () => {
    const response = await api.post(`/videos/${video.id}/study`, { kind: studyKind, language: 'original', difficulty, count })
    setStudyResult({ content: response.data.content, sources: response.data.sources || [] }); setActiveTab('study')
  })
  const createChapters = () => runAction(async () => {
    const response = await api.post(`/videos/${video.id}/chapters`)
    setChapters(response.data.chapters || []); setActiveTab('chapters')
  })
  const searchTranscript = () => runAction(async () => {
    const response = await api.post(`/videos/${video.id}/search`, { query: search, top_k: 10 })
    setSearchResults(response.data.results || [])
  })
  const saveTranscript = () => runAction(async () => {
    setSaveBusy(true)
    const normalized = segments.map((segment, index) => ({ ...segment, segment_index: index }))
    await api.put(`/videos/${video.id}/transcript`, { segments: normalized })
    await refresh(); setSaveBusy(false)
  })
  const downloadSubtitle = async () => {
    const response = await api.get(`/videos/${video.id}/subtitles/${selectedLanguage}`, { params: { fmt: subFormat }, responseType: 'blob' })
    const url = URL.createObjectURL(response.data); const a = document.createElement('a'); a.href = url; a.download = `videomind-${selectedLanguage}.${subFormat}`; a.click(); URL.revokeObjectURL(url)
  }
  const filteredSegments = segments.filter((segment) => !search || segment.text.toLowerCase().includes(search.toLowerCase()))
  const isReady = currentVideo.status === 'ready'
  const youtubeId = currentVideo.source_url?.includes('youtu') ? (() => { try { const u = new URL(currentVideo.source_url!); return u.hostname === 'youtu.be' ? u.pathname.slice(1) : u.searchParams.get('v') || u.pathname.split('/').filter(Boolean).pop() } catch { return '' } })() : ''
  const displayedSegments = selectedLanguage === 'original' ? segments : (translation.length ? translation : segments)

  return <div className="page-content workspace-page">
    <button className="back-link" onClick={onBack}><ArrowLeft size={16} /> Back to library</button>
    <div className="workspace-heading"><div><div className="eyebrow">VIDEO WORKSPACE / {currentVideo.source_type.toUpperCase()}</div><h1>{currentVideo.title}<span className="heading-period">.</span></h1><div className="workspace-meta"><span><Languages size={13} /> {currentVideo.language || 'Detecting language'}</span><span><Clock3 size={13} /> {currentVideo.duration ? formatTime(currentVideo.duration) : 'Duration pending'}</span><span className={`rag-label ${currentVideo.rag_status === 'indexed' ? 'ok' : ''}`}><span /> {currentVideo.rag_status === 'indexed' ? 'RAG indexed' : currentVideo.rag_status}</span></div></div><div className={`status-chip ${isReady ? 'ready' : currentVideo.status === 'failed' ? 'failed' : 'working'}`}>{isReady ? <Check size={13} /> : <LoaderCircle className="spin" size={13} />}{currentVideo.status}</div></div>
    {!isReady && <div className="processing-banner"><LoaderCircle className="spin" size={18} /><div><b>{currentVideo.status === 'failed' ? 'Processing failed' : 'Processing your video'}</b><span>{currentVideo.error_message || 'Extracting speech, creating transcript segments, and indexing them for semantic search. This page refreshes automatically.'}</span></div></div>}
    {isReady && currentVideo.rag_status !== 'indexed' && <div className="warning-banner"><CircleHelp size={17} /><span>The transcript is ready, but RAG indexing did not complete. Check backend logs and the embedding model configuration before using chat or semantic search. {currentVideo.error_message}</span></div>}
    <div className="player-transcript-grid">
      <div className="player-card">{youtubeId ? <div className="youtube-frame"><iframe src={`https://www.youtube-nocookie.com/embed/${youtubeId}?start=${youtubeStart}`} title="Video player" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" allowFullScreen /></div> : currentVideo.source_type === 'upload' ? <video ref={videoRef} className="video-player" src={mediaUrl(video.id)} controls onTimeUpdate={(e) => setActiveTime(e.currentTarget.currentTime)} /> : <div className="player-placeholder"><Video size={36} /><span>Video preview unavailable</span></div>}
        <div className="player-details"><div><b>{currentVideo.title}</b><small>{currentVideo.source_type === 'youtube' ? 'Public video source' : 'Uploaded video'}</small></div><span className="duration-tag">{formatTime(currentVideo.duration || 0)}</span></div>
      </div>
      <div className="transcript-peek"><div className="panel-header"><div><div className="eyebrow">LIVE TRANSCRIPT</div><h3>{selectedLanguage === 'original' ? 'Original transcript' : `${languages.find(([c]) => c === selectedLanguage)?.[1] || selectedLanguage} transcript`}</h3></div><span className="segment-count">{displayedSegments.length} segments</span></div><div className="peek-segments" ref={transcriptRef}>{displayedSegments.slice(0, 7).map((segment, index) => <button key={index} className={`peek-segment ${activeTime >= segment.start && activeTime <= segment.end ? 'active' : ''}`} onClick={() => seek(segment.start)}><span>{formatTime(segment.start)}</span><p>{segment.text}</p></button>)}{displayedSegments.length > 7 && <button className="view-all" onClick={() => setActiveTab('transcript')}>View complete transcript <ChevronRight size={14} /></button>}{!displayedSegments.length && <p className="muted small-pad">Transcript will appear here after processing.</p>}</div></div>
    </div>
    <div className="workspace-tabs">{tabs.map((tab) => { const Icon = tab.icon; return <button key={tab.id} className={activeTab === tab.id ? 'active' : ''} onClick={() => setActiveTab(tab.id)}><Icon size={15} /> {tab.label}</button> })}</div>
    <section className="workspace-panel">
      {activeTab === 'transcript' && <div className="tool-layout"><div className="tool-main"><div className="panel-header"><div><div className="eyebrow">SOURCE TEXT</div><h2>Transcript editor</h2></div><button className="secondary-btn" onClick={saveTranscript} disabled={!isReady || busy || saveBusy}>{saveBusy || busy ? <LoaderCircle className="spin" size={15} /> : <Check size={15} />} Save & re-index</button></div><div className="transcript-toolbar"><div className="search-box"><Search size={15} /><input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Find a word or phrase" /></div><span>{segments.reduce((sum, item) => sum + item.text.split(/\s+/).filter(Boolean).length, 0)} words</span></div><div className="segment-list">{filteredSegments.map((segment, index) => <div className="editable-segment" key={`${segment.start}-${index}`}><button className="timestamp-button" onClick={() => seek(segment.start)}>{formatTime(segment.start)}<span>↗</span></button><textarea value={segment.text} onChange={(e) => setSegments((old) => old.map((item) => item === segment ? { ...item, text: e.target.value } : item))} rows={Math.max(1, Math.min(4, Math.ceil(segment.text.length / 100)))} />{segment.speaker && <small>{segment.speaker}</small>}</div>)}{!filteredSegments.length && <div className="empty-state compact"><p>No transcript segments yet, or no search matches.</p></div>}</div></div><aside className="tool-aside"><div className="aside-card"><div className="icon-tile purple"><BrainCircuit size={18} /></div><h3>RAG knowledge index</h3><p>Transcript chunks are embedded and stored with timestamps. Ask questions to retrieve relevant moments from this video.</p><div className="aside-stat"><span>Index status</span><b>{currentVideo.rag_status}</b></div><div className="aside-stat"><span>Source language</span><b>{currentVideo.language || 'Unknown'}</b></div></div><div className="aside-card"><h3>Search by meaning</h3><p>Try a natural-language query to locate concepts even when the exact words are different.</p><div className="stacked-input"><input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="e.g. explain gradient descent" /><button className="primary-btn full" onClick={searchTranscript} disabled={busy || !search.trim()}><Search size={15} /> Semantic search</button></div>{searchResults.map((r, i) => <button className="search-result" key={i} onClick={() => seek(r.start)}><span>{formatTime(r.start)} · {Math.round(r.score * 100)}%</span><p>{r.text}</p></button>)}</div></aside></div>}
      {activeTab === 'translate' && <div className="feature-view"><div className="feature-intro"><div className="icon-tile blue"><Languages size={20} /></div><div><div className="eyebrow">MULTILINGUAL ENGINE</div><h2>Translate the transcript</h2><p>Translate each timestamped segment while keeping its timing aligned with the original video.</p></div></div><div className="control-row"><label>Target language<select value={targetLanguage} onChange={(e) => { setTargetLanguage(e.target.value); setLanguageName(languages.find(([c]) => c === e.target.value)?.[1] || e.target.value) }}>{languages.map(([code, label]) => <option key={code} value={code}>{label}</option>)}</select></label><button className="primary-btn" onClick={translate} disabled={!isReady || busy}><WandSparkles size={16} /> {busy ? 'Translating…' : 'Translate transcript'}</button></div><div className="language-tabs"><button className={selectedLanguage === 'original' ? 'selected' : ''} onClick={() => loadTranslation('original')}>Original · {currentVideo.language || 'auto'}</button>{translationLanguages.map((code) => <button key={code} className={selectedLanguage === code ? 'selected' : ''} onClick={() => loadTranslation(code)}>{languages.find(([c]) => c === code)?.[1] || code}</button>)}</div><div className="translation-list">{(selectedLanguage === 'original' ? segments : translation).map((segment, index) => <div className="translation-row" key={index}><button onClick={() => seek(segment.start)}>{formatTime(segment.start)}</button><p>{segment.text}</p></div>)}{selectedLanguage !== 'original' && !translation.length && <p className="muted">Choose a language tab to load or generate its translation.</p>}</div></div>}
      {activeTab === 'summary' && <div className="feature-view"><div className="feature-intro"><div className="icon-tile purple"><Sparkles size={20} /></div><div><div className="eyebrow">AI SUMMARIZATION</div><h2>Get the key ideas</h2><p>Generate grounded summaries from your transcript. Long transcripts are processed in sections before the final summary.</p></div></div><div className="control-row"><label>Summary style<select value={summaryKind} onChange={(e) => setSummaryKind(e.target.value)}><option value="short">Short summary</option><option value="detailed">Detailed summary</option><option value="bullet-point">Bullet-point summary</option><option value="key takeaways">Key takeaways</option><option value="beginner-friendly">Beginner-friendly explanation</option><option value="technical">Technical summary</option><option value="revision">Revision summary</option></select></label><label>Language<select value={summaryLanguage} onChange={(e) => setSummaryLanguage(e.target.value)}><option value="original">Original language</option>{languages.map(([c, n]) => <option key={c} value={c}>{n}</option>)}</select></label><button className="primary-btn" onClick={createSummary} disabled={!isReady || busy}><Sparkles size={16} /> Generate summary</button></div>{summary ? <div className="generated-content"><div className="generated-head"><b>Generated summary</b><button className="secondary-btn" onClick={() => navigator.clipboard.writeText(summary)}><FileText size={14} /> Copy</button></div><div className="prose-text">{summary}</div></div> : <div className="empty-state compact"><div className="empty-icon"><Sparkles size={22} /></div><p>Your summary will appear here.</p></div>}</div>}
      {activeTab === 'chat' && <div className="chat-view"><div className="chat-main"><div className="panel-header"><div><div className="eyebrow">RETRIEVAL-AUGMENTED GENERATION</div><h2>Ask this video</h2><p className="muted">Answers use retrieved transcript chunks and cite their timestamps.</p></div><div className="chat-header-tools"><select aria-label="Answer language" value={chatLanguage} onChange={(e) => setChatLanguage(e.target.value)}><option value="auto">Auto detect</option>{languages.map(([code, label]) => <option key={code} value={label}>{label}</option>)}</select><span className="rag-badge"><span /> RAG ACTIVE</span></div></div><div className="chat-messages">{chat.length ? chat.map((message, index) => <div className={`chat-message ${message.role}`} key={index}><div className="chat-avatar">{message.role === 'assistant' ? <BrainCircuit size={16} /> : 'You'}</div><div className="chat-bubble"><p>{message.content}</p>{message.sources?.length ? <div className="source-list"><b>Retrieved video moments</b>{message.sources.map((source, i) => <button key={i} onClick={() => seek(source.start)}><Clock3 size={12} /> {formatTime(source.start)}–{formatTime(source.end)} <span>{source.text.slice(0, 130)}{source.text.length > 130 ? '…' : ''}</span></button>)}</div> : null}</div></div>) : <div className="chat-empty"><div className="empty-icon"><MessageSquareText size={24} /></div><h3>Start a conversation with your video</h3><p>Ask for an explanation, a definition, or the timestamp where a topic is discussed.</p><div className="suggested-questions"><button onClick={() => setQuestion('What are the main ideas in this video?')}>What are the main ideas?</button><button onClick={() => setQuestion('Explain the most difficult concept in simple language.')}>Explain a difficult concept</button><button onClick={() => setQuestion('Give me the key takeaways from this video.')}>Give me key takeaways</button></div></div>}</div><form className="chat-input-row" onSubmit={(e) => { e.preventDefault(); sendQuestion() }}><input value={question} onChange={(e) => setQuestion(e.target.value)} placeholder="Ask anything about this video…" disabled={!isReady} /><button className="primary-btn" disabled={!isReady || busy || !question.trim()}><Send size={16} /></button></form></div><aside className="chat-side"><div className="aside-card"><div className="icon-tile purple"><BrainCircuit size={18} /></div><h3>How RAG answers</h3><ol className="rag-steps"><li><b>Embed</b><span>Your question is converted into a multilingual vector.</span></li><li><b>Retrieve</b><span>Relevant transcript chunks are searched for this video.</span></li><li><b>Generate</b><span>The LLM answers from retrieved context and returns source moments.</span></li></ol></div><div className="aside-card"><h3>Good questions</h3><p>Ask about definitions, comparisons, examples, conclusions, or specific moments. The assistant will say when the transcript does not contain enough evidence.</p></div></aside></div>}
      {activeTab === 'study' && <div className="feature-view"><div className="feature-intro"><div className="icon-tile amber"><BookOpen size={20} /></div><div><div className="eyebrow">AI STUDY ASSISTANT</div><h2>Turn the video into study material</h2><p>Generate transcript-grounded learning resources with source timestamps when available.</p></div></div><div className="control-row"><label>Material type<select value={studyKind} onChange={(e) => setStudyKind(e.target.value)}><option value="notes">Comprehensive study notes</option><option value="mcqs">MCQ practice questions</option><option value="flashcards">Flashcards</option><option value="viva">Viva questions</option></select></label><label>Difficulty<select value={difficulty} onChange={(e) => setDifficulty(e.target.value)}><option value="easy">Easy</option><option value="medium">Medium</option><option value="hard">Hard</option><option value="mixed">Mixed</option></select></label><label>Count<input type="number" min={1} max={50} value={count} onChange={(e) => setCount(Math.min(50, Math.max(1, Number(e.target.value))))} disabled={studyKind === 'notes'} /></label><button className="primary-btn" onClick={createStudy} disabled={!isReady || busy}><WandSparkles size={16} /> Generate material</button></div>{studyResult ? <div className="generated-content"><div className="generated-head"><b>{studyKind.toUpperCase()}</b><button className="secondary-btn" onClick={() => navigator.clipboard.writeText(typeof studyResult === 'string' ? studyResult : JSON.stringify(studyResult, null, 2))}><FileText size={14} /> Copy</button></div><StudyResult data={studyResult} onSeek={seek} /></div> : <div className="empty-state compact"><div className="empty-icon"><BookOpen size={22} /></div><p>Choose a learning format and generate your study material.</p></div>}</div>}
      {activeTab === 'chapters' && <div className="feature-view"><div className="feature-intro"><div className="icon-tile blue"><ListVideo size={20} /></div><div><div className="eyebrow">AUTOMATIC CHAPTERING</div><h2>Navigate by topic</h2><p>Detect meaningful topic sections and jump directly to the relevant moment.</p></div><button className="primary-btn" onClick={createChapters} disabled={!isReady || busy}><WandSparkles size={16} /> Generate chapters</button></div><div className="chapter-list">{chapters.map((chapter, i) => <button className="chapter-item" key={i} onClick={() => seek(chapter.start)}><span className="chapter-index">{String(i + 1).padStart(2, '0')}</span><div><b>{chapter.title}</b><p>{chapter.summary}</p><small>{formatTime(chapter.start)} – {formatTime(chapter.end)}</small></div><ChevronRight size={17} /></button>)}{!chapters.length && <div className="empty-state compact"><p>No chapters generated yet.</p></div>}</div></div>}
      {activeTab === 'subtitles' && <div className="feature-view"><div className="feature-intro"><div className="icon-tile blue"><Subtitles size={20} /></div><div><div className="eyebrow">TIMESTAMP-SYNCHRONIZED CAPTIONS</div><h2>Download subtitles</h2><p>Subtitles retain the time ranges of the original transcript segments.</p></div></div><div className="control-row"><label>Subtitle language<select value={selectedLanguage} onChange={(e) => setSelectedLanguage(e.target.value)}><option value="original">Original ({currentVideo.language || 'auto'})</option>{translationLanguages.map((code) => <option value={code} key={code}>{languages.find(([c]) => c === code)?.[1] || code}</option>)}</select></label><label>Format<select value={subFormat} onChange={(e) => setSubFormat(e.target.value)}><option value="srt">SRT</option><option value="vtt">WebVTT</option></select></label><button className="primary-btn" onClick={downloadSubtitle} disabled={!isReady}><ArrowDownToLine size={16} /> Download subtitles</button></div><div className="info-callout"><Subtitles size={18} /><p>Translated subtitle text is aligned to the original segment timestamps. Translation may change sentence length, so review the subtitle timing before publishing.</p></div></div>}
      {activeTab === 'export' && <div className="feature-view"><div className="feature-intro"><div className="icon-tile purple"><ArrowDownToLine size={20} /></div><div><div className="eyebrow">EXPORT CENTER</div><h2>Take your knowledge with you</h2><p>Download transcripts, summaries, study materials, and chat history.</p></div></div><div className="control-row"><label>Content<select value={exportKind} onChange={(e) => setExportKind(e.target.value)}><option value="transcript">Transcript</option><option value="summary">Latest summary</option><option value="study">Latest study material</option><option value="chat">Chat history</option></select></label><label>File format<select value={exportFormat} onChange={(e) => setExportFormat(e.target.value)}><option value="pdf">PDF</option><option value="docx">DOCX</option><option value="txt">TXT</option><option value="md">Markdown</option></select></label><label>Language<select value={selectedLanguage} onChange={(e) => setSelectedLanguage(e.target.value)}><option value="original">Original</option>{translationLanguages.map((code) => <option value={code} key={code}>{languages.find(([c]) => c === code)?.[1] || code}</option>)}</select></label><button className="primary-btn" onClick={() => runAction(() => downloadExport(video.id, exportKind, exportFormat, selectedLanguage))} disabled={busy}><ArrowDownToLine size={16} /> Download file</button></div><div className="export-grid"><div><FileText size={20} /><b>Transcript</b><span>Timestamped source text</span></div><div><Sparkles size={20} /><b>Summary</b><span>AI-generated key ideas</span></div><div><BookOpen size={20} /><b>Study pack</b><span>Notes and question sets</span></div><div><MessageSquareText size={20} /><b>Chat history</b><span>Questions and grounded answers</span></div></div></div>}
    </section>
  </div>
}

function StudyResult({ data, onSeek }: { data: any; onSeek: (time: number) => void }) {
  const content = data?.content ?? data
  const sources = data?.sources || []
  if (content?.markdown) return <><div className="prose-text">{content.markdown}</div><StudySources sources={sources} onSeek={onSeek} /></>
  const rows = Array.isArray(content) ? content : []
  if (!rows.length) return <><pre className="json-output">{JSON.stringify(content, null, 2)}</pre><StudySources sources={sources} onSeek={onSeek} /></>
  return <><div className="study-items">{rows.map((item: any, index: number) => <article className="study-item" key={index}><div className="study-item-top"><span>ITEM {String(index + 1).padStart(2, '0')}</span>{item.timestamp !== undefined && <button onClick={() => onSeek(Number(item.timestamp))}><Clock3 size={12} /> {formatTime(Number(item.timestamp))}</button>}</div><h3>{item.question || item.front || `Card ${index + 1}`}</h3>{item.options && <ol className="option-list">{item.options.map((option: string, i: number) => <li key={i}>{option}</li>)}</ol>}{item.answer && <p><b>Answer:</b> {item.answer}</p>}{item.explanation && <p className="muted">{item.explanation}</p>}{item.difficulty && <span className="difficulty-tag">{item.difficulty}</span>}</article>)}</div><StudySources sources={sources} onSeek={onSeek} /></>
}

function StudySources({ sources, onSeek }: { sources: any[]; onSeek: (time: number) => void }) {
  if (!sources.length) return null
  return <div className="study-sources"><b>RAG source moments</b>{sources.map((source, index) => <button key={index} onClick={() => onSeek(source.start)}><Clock3 size={12} /> {formatTime(source.start)}–{formatTime(source.end)} <span>{source.text.slice(0, 145)}{source.text.length > 145 ? '…' : ''}</span></button>)}</div>
}
