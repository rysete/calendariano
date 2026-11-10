import { useState, useEffect } from 'react';
import axios from 'axios';
import { Calendar, Users, Download, ChevronRight, Check, X, Clock, Upload, FileText, AlertCircle, Settings2, Link } from 'lucide-react';
import './App.css';

interface Month {
  id: string;
  name: string;
  year: number;
  month: number;
}

interface Employee {
  id: number;
  name: string;
  turno: string;
  num_trabalho: number;
}

interface EscalaItem {
  date: string;
  day: number;
  weekday: string;
  status: string;
  start_time: string;
  end_time: string;
  colegas?: string[];
}

interface EscalaData {
  name: string;
  turno: string;
  month_name: string;
  escala: EscalaItem[];
}

interface TurnoInfo {
  inicio: string;
  fim: string;
}

interface GoogleStatus {
  configured: boolean;
  authenticated: boolean;
  redirect_uri: string;
  client_type: string | null;
  error?: string | null;
}

interface GoogleCalendarInfo {
  id: string;
  summary: string;
  primary?: boolean;
  access_role?: string;
  can_write?: boolean;
}

const API_BASE = `${window.location.origin}/api`;

function App() {
  const [fileId, setFileId] = useState<string | null>(null);
  const [months, setMonths] = useState<Month[]>([]);
  const [turnos, setTurnos] = useState<Record<string, TurnoInfo>>({});
  const [selectedMonth, setSelectedMonth] = useState<string | null>(null);
  const [employees, setEmployees] = useState<Employee[]>([]);
  const [selectedEmployeeId, setSelectedEmployeeId] = useState<number | null>(null);
  const [escalaData, setEscalaData] = useState<EscalaData | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [calendarUrl, setCalendarUrl] = useState<string | null>(null);
  const [nameColumn, setNameColumn] = useState<number>(0);
  const [githubUser, setGithubUser] = useState<string>('');
  const [githubRepo, setGithubRepo] = useState<string>('');
  const [googleStatus, setGoogleStatus] = useState<GoogleStatus | null>(null);
  const [googleCalendars, setGoogleCalendars] = useState<GoogleCalendarInfo[]>([]);
  const [selectedGoogleCalendar, setSelectedGoogleCalendar] = useState<string>('primary');
  const [googleSyncing, setGoogleSyncing] = useState(false);
  const [googleMessage, setGoogleMessage] = useState<string | null>(null);

  // Carregar configurações do localStorage
  useEffect(() => {
    const savedUser = localStorage.getItem('escala_github_user');
    const savedRepo = localStorage.getItem('escala_github_repo');
    const savedCol = localStorage.getItem('escala_name_column');
    const savedGoogleCalendar = localStorage.getItem('escala_google_calendar');
    if (savedUser) setGithubUser(savedUser);
    if (savedRepo) setGithubRepo(savedRepo);
    if (savedCol) setNameColumn(parseInt(savedCol));
    if (savedGoogleCalendar) setSelectedGoogleCalendar(savedGoogleCalendar);
  }, []);

  const saveSettings = () => {
    localStorage.setItem('escala_github_user', githubUser);
    localStorage.setItem('escala_github_repo', githubRepo);
    localStorage.setItem('escala_name_column', nameColumn.toString());
    localStorage.setItem('escala_google_calendar', selectedGoogleCalendar);
    alert("Configurações salvas!");
  };

  const loadGoogleStatus = async () => {
    try {
      const res = await axios.get(`${API_BASE}/google/status`, { params: { t: Date.now() } });
      setGoogleStatus(res.data);
      if (res.data.authenticated) {
        const calendarsRes = await axios.get(`${API_BASE}/google/calendars`);
        const writableCalendars = calendarsRes.data.filter((cal: GoogleCalendarInfo) => cal.can_write !== false);
        setGoogleCalendars(writableCalendars);
        const saved = localStorage.getItem('escala_google_calendar');
        const savedStillExists = writableCalendars.find((cal: GoogleCalendarInfo) => cal.id === saved);
        if (saved && savedStillExists) {
          setSelectedGoogleCalendar(saved);
        } else {
          const primary = writableCalendars.find((cal: GoogleCalendarInfo) => cal.primary);
          setSelectedGoogleCalendar(primary?.id || writableCalendars[0]?.id || 'primary');
        }
      }
    } catch (err: any) {
      setGoogleStatus(null);
      console.error(err.response?.data?.detail || "Erro ao carregar status Google");
    }
  };

  useEffect(() => {
    loadGoogleStatus();
  }, []);

  const uploadGoogleCredentials = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    const formData = new FormData();
    formData.append('file', file);
    setSaving(true);
    setError(null);
    try {
      await axios.post(`${API_BASE}/google/credentials`, formData);
      setGoogleMessage("Credenciais Google salvas. Agora conecte a conta.");
      await loadGoogleStatus();
    } catch (err: any) {
      setError(err.response?.data?.detail || "Erro ao salvar credenciais Google.");
    } finally {
      setSaving(false);
      event.target.value = '';
    }
  };

  const connectGoogle = async () => {
    setSaving(true);
    setError(null);
    try {
      const res = await axios.get(`${API_BASE}/google/auth-url`, { params: { t: Date.now() } });
      window.open(res.data.auth_url, '_blank', 'noopener,noreferrer,width=960,height=760');
      setGoogleMessage("Autorize no Google e depois clique em Atualizar status.");
    } catch (err: any) {
      setError(err.response?.data?.detail || "Erro ao iniciar conexão com Google.");
    } finally {
      setSaving(false);
    }
  };

  const syncGoogleCalendar = async () => {
    if (!escalaData) return;
    if (!googleStatus?.authenticated) {
      setShowSettings(true);
      setError("Conecte a conta Google antes de sincronizar.");
      return;
    }

    setGoogleSyncing(true);
    setError(null);
    try {
      localStorage.setItem('escala_google_calendar', selectedGoogleCalendar || 'primary');
      const res = await axios.post(`${API_BASE}/google/sync`, {
        calendar_id: selectedGoogleCalendar || 'primary',
        escala: escalaData,
      });
      const { created, updated, deleted, skipped } = res.data;
      setGoogleMessage(`Google sincronizado: ${created} criados, ${updated} atualizados, ${deleted} removidos, ${skipped} ignorados.`);
    } catch (err: any) {
      setError(err.response?.data?.detail || "Erro ao sincronizar com Google Calendar.");
    } finally {
      setGoogleSyncing(false);
    }
  };

  // Carregar turnos disponíveis ao iniciar
  useEffect(() => {
    axios.get(`${API_BASE}/turnos`)
      .then(res => setTurnos(res.data))
      .catch(() => console.error("Erro ao carregar turnos"));
  }, []);

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
    alert("Link copiado!");
  };

  const processFile = async (file: File) => {
    if (!file.name.endsWith('.xlsx') && !file.name.endsWith('.xls')) {
      setError("Por favor, envie um arquivo Excel (.xlsx ou .xls)");
      return;
    }

    const formData = new FormData();
    formData.append('file', file);
    formData.append('col_nome', nameColumn.toString());

    setLoading(true);
    setError(null);
    try {
      const res = await axios.post(`${API_BASE}/upload?col_nome=${nameColumn}`, formData);
      const uploadedMonths = res.data.months || [];
      setFileId(res.data.file_id);
      setMonths(uploadedMonths);
      setSelectedMonth(uploadedMonths[0]?.id || null);
      setEmployees([]);
      setSelectedEmployeeId(null);
      setEscalaData(null);
    } catch (err: any) {
      setError(err.response?.data?.detail || "Erro ao processar o arquivo.");
    } finally {
      setLoading(false);
    }
  };

  const handleFileUpload = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (file) processFile(file);
  };

  const requestFileUpload = () => {
    const nativeBridge = (window as any).webkit?.messageHandlers?.escala;
    if (nativeBridge) {
      nativeBridge.postMessage(JSON.stringify({ type: 'open-file' }));
      return;
    }

    document.getElementById('fileInput')?.click();
  };

  useEffect(() => {
    const handleNativeUpload = (event: Event) => {
      const detail = (event as CustomEvent).detail;
      if (!detail) return;

      if (detail.error) {
        setError(detail.error);
        setLoading(false);
        return;
      }

      const uploadedMonths = detail.months || [];
      setFileId(detail.file_id);
      setMonths(uploadedMonths);
      setSelectedMonth(uploadedMonths[0]?.id || null);
      setEmployees([]);
      setSelectedEmployeeId(null);
      setEscalaData(null);
      setError(null);
      setLoading(false);
    };

    const handleNativeUploadStart = () => {
      setLoading(true);
      setError(null);
    };

    window.addEventListener('escala:native-upload-start', handleNativeUploadStart);
    window.addEventListener('escala:native-upload-result', handleNativeUpload);

    return () => {
      window.removeEventListener('escala:native-upload-start', handleNativeUploadStart);
      window.removeEventListener('escala:native-upload-result', handleNativeUpload);
    };
  }, []);

  const generateCalendarLink = async () => {
    if (!escalaData) return;
    setSaving(true);
    try {
      const res = await axios.post(`${API_BASE.replace('/api', '')}/api/escala/save-link`, escalaData);
      let fullUrl = res.data.url;
      
      // Se tiver configurações do GitHub, gera o link do GitHub Pages
      if (githubUser && githubRepo) {
        const safeName = "".concat(...Array.from(escalaData.name.toLowerCase()).map(c => /[a-z0-9]/.test(c) ? c : "_")).replace(/^_+|_+$/g, '');
        fullUrl = `https://${githubUser}.github.io/${githubRepo}/${safeName}.ics`;
      }
      
      // Converter para webcal:// (ajuda o Google)
      const webcalUrl = fullUrl.replace('http://', 'webcal://').replace('https://', 'webcal://');
      setCalendarUrl(webcalUrl);
      copyToClipboard(webcalUrl);
    } catch {
      setError("Erro ao gerar link da agenda");
    } finally {
      setSaving(false);
    }
  };

  const downloadIcs = async () => {
    if (!escalaData || !calendarUrl) return;
    setSaving(true);
    try {
      const linkId = calendarUrl.split('/').pop();
      const res = await axios.get(`${API_BASE}/calendar/${linkId}`, { responseType: 'blob' });
      const url = window.URL.createObjectURL(new Blob([res.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', `escala_${escalaData.name.replace(/\s+/g, '_')}.ics`);
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    } catch {
      setError("Gere o Link da Agenda primeiro para habilitar o download.");
    } finally {
      setSaving(false);
    }
  };

  useEffect(() => {
    if (fileId && selectedMonth) {
      setLoading(true);
      axios.get(`${API_BASE}/employees/${fileId}/${selectedMonth}`)
        .then(res => {
          const loadedEmployees = res.data || [];
          setEmployees(loadedEmployees);
          setSelectedEmployeeId(loadedEmployees[0]?.id ?? null);
          setEscalaData(null);
        })
        .catch(() => setError("Erro ao carregar funcionários"))
        .finally(() => setLoading(false));
    }
  }, [fileId, selectedMonth]);

  useEffect(() => {
    if (fileId && selectedMonth && selectedEmployeeId !== null) {
      setLoading(true);
      axios.get(`${API_BASE}/escala/${fileId}/${selectedMonth}/${selectedEmployeeId}`)
        .then(res => setEscalaData(res.data))
        .catch(() => setError("Erro ao carregar dados da escala"))
        .finally(() => setLoading(false));
    }
  }, [fileId, selectedMonth, selectedEmployeeId]);

  const handleStatusToggle = (index: number) => {
    if (!escalaData) return;
    const newEscala = [...escalaData.escala];
    const item = newEscala[index];
    item.status = item.status === 'TRABALHO' ? 'FOLGA' : 'TRABALHO';
    setEscalaData({ ...escalaData, escala: newEscala });
  };

  const handleTimeChange = (index: number, field: 'start_time' | 'end_time', value: string) => {
    if (!escalaData) return;
    const newEscala = [...escalaData.escala];
    newEscala[index][field] = value;
    setEscalaData({ ...escalaData, escala: newEscala });
  };

  const handleTurnoChange = (newTurno: string) => {
    if (!escalaData) return;
    let startTime = "";
    let endTime = "";
    if (turnos[newTurno]) {
      startTime = turnos[newTurno].inicio;
      endTime = turnos[newTurno].fim;
    } else {
      const match = newTurno.match(/(\d{1,2})[xX-](\d{1,2})/);
      if (match) {
        startTime = `${match[1].padStart(2, '0')}:00`;
        endTime = `${match[2].padStart(2, '0')}:00`;
      }
    }
    const newEscala = escalaData.escala.map(item => ({
      ...item,
      start_time: (item.status === 'TRABALHO' && startTime) ? startTime : item.start_time,
      end_time: (item.status === 'TRABALHO' && endTime) ? endTime : item.end_time
    }));
    setEscalaData({ ...escalaData, turno: newTurno, escala: newEscala });
  };

  const downloadCsv = async () => {
    if (!escalaData) return;
    setSaving(true);
    try {
      const res = await axios.post(`${API_BASE}/export/csv`, escalaData, { responseType: 'blob' });
      const url = window.URL.createObjectURL(new Blob([res.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', `escala_${escalaData.name.replace(/\s+/g, '_')}.csv`);
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    } catch {
      setError("Erro ao gerar CSV");
    } finally {
      setSaving(false);
    }
  };

  const [showSettings, setShowSettings] = useState(false);

  return (
    <div className={`app-container ${isDragging ? 'dragging' : ''}`} 
         onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }} 
         onDragLeave={() => setIsDragging(false)} 
         onDrop={(e) => { e.preventDefault(); setIsDragging(false); const f = e.dataTransfer.files?.[0]; if(f) processFile(f); }}>
      
      <header className="app-header">
        <div className="logo">
          <Calendar className="icon-main" />
          <h1>Escala Web Editor</h1>
        </div>
        <div className="header-actions">
          <button className="btn btn-secondary" onClick={() => setShowSettings(!showSettings)}>
            <Settings2 size={18} /> Configurações
          </button>
          <button className="btn btn-secondary" onClick={requestFileUpload}>
            <Upload size={18} /> {fileId ? 'Trocar Planilha' : 'Carregar Excel'}
          </button>
          <input id="fileInput" type="file" onChange={handleFileUpload} accept=".xlsx, .xls" style={{ display: 'none' }} />
          {escalaData && (
            <>
              <button onClick={generateCalendarLink} className="btn btn-secondary">
                <Link size={18} /> {calendarUrl ? 'Link Criado' : 'Link Agenda'}
              </button>
              {googleStatus?.authenticated && (
                <label className="calendar-target">
                  <Calendar size={16} />
                  <select value={selectedGoogleCalendar} onChange={(e) => setSelectedGoogleCalendar(e.target.value)}>
                    {googleCalendars.length === 0 && <option value="primary">Principal</option>}
                    {googleCalendars.map(cal => (
                      <option key={cal.id} value={cal.id}>{cal.summary}{cal.primary ? ' (principal)' : ''}</option>
                    ))}
                  </select>
                </label>
              )}
              <button onClick={syncGoogleCalendar} className="btn btn-secondary" disabled={googleSyncing}>
                <Calendar size={18} /> {googleSyncing ? 'Sincronizando...' : 'Sync Google'}
              </button>
              <button onClick={downloadCsv} className="btn btn-primary" disabled={saving}>
                <Download size={18} /> {saving ? 'Gerando...' : 'Baixar CSV'}
              </button>
            </>
          )}
        </div>
      </header>

      {error && (
        <div className="error-banner">
          <AlertCircle size={20} />
          <span>{error}</span>
          <button onClick={() => setError(null)}><X size={18} /></button>
        </div>
      )}

      {calendarUrl && (
        <div className="success-banner">
          <Check size={20} />
          <span>Agenda pronta! Copie o link ou baixe o arquivo para teste.</span>
          <button className="copy-btn" onClick={() => copyToClipboard(calendarUrl)}>
             <Link size={14} /> Copiar Link
          </button>
          <button className="copy-btn" onClick={downloadIcs}>
             <Download size={14} /> Baixar Arquivo
          </button>
          <button className="close-btn" onClick={() => setCalendarUrl(null)}><X size={18} /></button>
        </div>
      )}

      {googleMessage && (
        <div className="success-banner">
          <Check size={20} />
          <span>{googleMessage}</span>
          <button className="close-btn" onClick={() => setGoogleMessage(null)}><X size={18} /></button>
        </div>
      )}

      {showSettings && (
        <div className="settings-panel">
          <div className="settings-header">
            <h3><Settings2 size={18} /> Configurações de Importação e Sync</h3>
            <button onClick={() => setShowSettings(false)} className="close-btn"><X size={18} /></button>
          </div>
          <div className="settings-grid">
            <div className="settings-group">
              <label>Coluna de Nomes (0=A, 1=B...):</label>
              <input type="number" value={nameColumn} onChange={(e) => setNameColumn(parseInt(e.target.value))} />
              <p className="hint">Índice da coluna na planilha que contém os nomes.</p>
            </div>
            <div className="settings-group">
              <label>GitHub Username:</label>
              <input type="text" placeholder="ex: rysete" value={githubUser} onChange={(e) => setGithubUser(e.target.value)} />
            </div>
            <div className="settings-group">
              <label>GitHub Repository:</label>
              <input type="text" placeholder="ex: calendariano" value={githubRepo} onChange={(e) => setGithubRepo(e.target.value)} />
            </div>
            <div className="settings-group">
              <label>Google OAuth Client JSON:</label>
              <input type="file" accept=".json,application/json" onChange={uploadGoogleCredentials} />
              <p className="hint">Use um OAuth Client do tipo Web Application e cadastre o redirect URI abaixo no Google Cloud.</p>
            </div>
            <div className="settings-group">
              <label>Google Redirect URI:</label>
              <input type="text" readOnly value={googleStatus?.redirect_uri || 'Clique em Atualizar status para carregar do servidor'} />
              <p className="hint">Esta URL vem do backend. Copie exatamente para Authorized redirect URIs no OAuth Client.</p>
            </div>
            <div className="settings-group">
              <label>Status Google:</label>
              <div className={`google-status ${googleStatus?.authenticated ? 'ok' : 'warn'}`}>
                {googleStatus?.authenticated ? 'Conta conectada' : googleStatus?.configured ? 'Credenciais salvas, conta não conectada' : 'Credenciais ausentes'}
              </div>
              {googleStatus?.error && <p className="hint error-text">{googleStatus.error}</p>}
            </div>
            <div className="settings-group">
              <label>Calendário Google:</label>
              <select value={selectedGoogleCalendar} onChange={(e) => setSelectedGoogleCalendar(e.target.value)}>
                {googleCalendars.length === 0 && <option value="primary">Principal</option>}
                {googleCalendars.map(cal => (
                  <option key={cal.id} value={cal.id}>{cal.summary}{cal.primary ? ' (principal)' : ''}</option>
                ))}
              </select>
              <p className="hint">O sync atualiza eventos existentes da escala e remove dias que viraram folga.</p>
            </div>
          </div>
          <div className="settings-footer">
            <p className="sync-info">Para sync direto, use OAuth Web Application. Links webcal continuam disponíveis como alternativa.</p>
            <div className="settings-actions">
              <button className="btn btn-secondary" onClick={loadGoogleStatus}>Atualizar status</button>
              <button className="btn btn-secondary" onClick={connectGoogle} disabled={!googleStatus?.configured || saving}>Conectar Google</button>
              <button className="btn btn-primary" onClick={() => { saveSettings(); setShowSettings(false); }}>Salvar Configurações</button>
            </div>
          </div>
        </div>
      )}

      <main className="app-main">
        <aside className="sidebar">
          {!fileId ? (
            <div className="sidebar-empty">
              <FileText size={32} />
              <p>Arraste um arquivo Excel aqui</p>
            </div>
          ) : (
            <>
              <section className="sidebar-section">
                <h2 className="section-title"><Calendar size={18} /> Meses</h2>
                <div className="month-list">
                  {months.map(m => (
                    <button key={m.id} className={`list-item ${selectedMonth === m.id ? 'active' : ''}`} onClick={() => setSelectedMonth(m.id)}>
                      {m.name}
                    </button>
                  ))}
                </div>
              </section>
              {selectedMonth && (
                <section className="sidebar-section">
                  <h2 className="section-title"><Users size={18} /> Funcionários</h2>
                  <div className="employee-list">
                    {employees.map(e => (
                      <button key={e.id} className={`list-item ${selectedEmployeeId === e.id ? 'active' : ''}`} onClick={() => setSelectedEmployeeId(e.id)}>
                        <div className="emp-info"><span className="emp-name">{e.name}</span><span className="emp-turno">{e.turno}</span></div>
                        <ChevronRight size={16} />
                      </button>
                    ))}
                  </div>
                </section>
              )}
            </>
          )}
        </aside>

        <section className="editor-area">
          {loading ? (
            <div className="loader-container"><div className="spinner"></div><p>Processando dados...</p></div>
          ) : escalaData ? (
            <div className="editor-content">
              <div className="editor-header">
                <div className="header-info"><h2>{escalaData.name}</h2><p className="subtitle">{escalaData.month_name}</p></div>
                <div className="turno-selector-wrapper">
                  <label><Settings2 size={16} /> Editar Turno:</label>
                  <input type="text" value={escalaData.turno} onChange={(e) => handleTurnoChange(e.target.value)} className="turno-input" placeholder="Ex: 14x22" />
                </div>
              </div>
              <div className="calendar-grid">
                {escalaData.escala.map((item, idx) => (
                  <div key={item.date} className={`day-card ${item.status === 'TRABALHO' ? 'status-work' : 'status-off'}`}>
                    <div className="day-header"><span className="day-number">{item.day}</span><span className="day-weekday">{item.weekday.slice(0, 3)}</span></div>
                    <div className="day-controls">
                      <button className={`status-toggle ${item.status === 'TRABALHO' ? 'is-work' : 'is-off'}`} onClick={() => handleStatusToggle(idx)}>
                        {item.status === 'TRABALHO' ? <Check size={16} /> : <X size={16} />} {item.status}
                      </button>
                      {item.status === 'TRABALHO' && (
                        <div className="time-inputs">
                          <div className="time-field"><Clock size={12} /><input type="text" value={item.start_time} onChange={(e) => handleTimeChange(idx, 'start_time', e.target.value)} /></div>
                          <div className="time-field"><Clock size={12} /><input type="text" value={item.end_time} onChange={(e) => handleTimeChange(idx, 'end_time', e.target.value)} /></div>
                        </div>
                      )}
                      {item.status === 'TRABALHO' && item.colegas && item.colegas.length > 0 && (
                        <div className="day-team">
                          <span className="team-label">Com o time:</span>
                          <span className="team-names">{item.colegas.join(', ')}</span>
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <div className={`empty-state-zone ${isDragging ? 'is-active' : ''}`}>
              <Upload size={64} strokeWidth={1} className="floating-icon" />
              <h3>Comece carregando sua planilha</h3>
              <p>Arraste o arquivo Excel para qualquer lugar ou use o botão acima.</p>
              {!fileId && <button className="btn btn-primary btn-large" onClick={() => document.getElementById('fileInput')?.click()}>Selecionar Arquivo</button>}
            </div>
          )}
        </section>
      </main>
      {isDragging && <div className="drag-overlay">Solte seu Excel aqui</div>}
    </div>
  );
}

export default App;
