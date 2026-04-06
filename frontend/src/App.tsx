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

const API_BASE = 'http://localhost:8001/api';

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

    setLoading(true);
    setError(null);
    try {
      const res = await axios.post(`${API_BASE}/upload`, formData);
      setFileId(res.data.file_id);
      setMonths(res.data.months);
      setSelectedMonth(null);
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

  const generateCalendarLink = async () => {
    if (!escalaData) return;
    setSaving(true);
    try {
      const res = await axios.post(`${API_BASE.replace('/api', '')}/api/escala/save-link`, escalaData);
      let fullUrl = res.data.url;
      
      // Converter para webcal:// se for http:// (ajuda o Google)
      const webcalUrl = fullUrl.replace('http://', 'webcal://');
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
          setEmployees(res.data);
          setSelectedEmployeeId(null);
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
          <button className="btn btn-secondary" onClick={() => document.getElementById('fileInput')?.click()}>
            <Upload size={18} /> {fileId ? 'Trocar Planilha' : 'Carregar Excel'}
          </button>
          <input id="fileInput" type="file" onChange={handleFileUpload} accept=".xlsx, .xls" style={{ display: 'none' }} />
          {escalaData && (
            <>
              <button onClick={generateCalendarLink} className="btn btn-secondary">
                <Link size={18} /> {calendarUrl ? 'Link Criado' : 'Link Agenda'}
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
