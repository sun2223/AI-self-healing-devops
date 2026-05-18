import React, { useState, useEffect, useRef } from 'react';
import { io } from 'socket.io-client';
import {
  Play,
  Loader2,
  ShieldAlert,
  CheckCircle2,
  XCircle,
  Terminal,
  FileCode,
  Folder,
  AlertCircle,
  Info,
  History,
  Search,
  Filter,
  GitBranch,
  ExternalLink,
  User,
  ChevronDown,
  ChevronUp,
  BarChart3,
  RefreshCw,
  FolderOpen
} from 'lucide-react';

// Custom GitHub SVG component replacing the missing lucide brand icon
const Github = ({ className = "w-5 h-5" }: { className?: string }) => (
  <svg
    className={className}
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <path d="M15 22v-4a4.8 4.8 0 0 0-1-3.5c3 0 6-2 6-5.5.08-1.25-.27-2.48-1-3.5.28-1.15.28-2.35 0-3.5 0 0-1 0-3 1.5-2.64-.5-5.36-.5-8 0C6 2 5 2 5 2c-.3 1.15-.3 2.35 0 3.5A5.403 5.403 0 0 0 4 9c0 3.5 3 5.5 6 5.5-.39.49-.68 1.05-.85 1.65-.17.6-.22 1.23-.15 1.85v4" />
    <path d="M9 18c-4.51 2-5-2-7-2" />
  </svg>
);

// ── Types & Interfaces ────────────────────────────────────────────────────────

interface Issue {
  id: string;
  file_path: string;
  line: number;
  line_number: number;
  column: number;
  column_number: number;
  bug_type: string;
  severity: 'critical' | 'high' | 'medium' | 'low' | 'info';
  severity_score: number;
  message: string;
  code_snippet?: string;
  reasoning?: string;
  source: string;
  fixed: boolean;
  symbol: string;
}

interface HealthScore {
  score: number;
  grade: string;
  label: string;
  total_issues: number;
  critical_count: number;
  high_count: number;
  medium_count: number;
  low_count: number;
  info_count: number;
  top_problem_files: string[];
}

interface ScanRun {
  scan_id: string;
  status: 'pending' | 'running' | 'success' | 'failed';
  current_stage: string;
  progress: number;
  repository_url: string;
  repository_name: string;
  author_name: string;
  branch_name: string;
  created_at: string;
  started_at?: string;
  completed_at?: string;
  duration_seconds?: number;
  total_issues_found: number;
  health_score?: HealthScore;
  bug_heatmap?: Record<string, number>;
  file_tree?: any;
  fixes?: any[];
  rolled_back?: boolean;
  error_message?: string;
}

interface LogEntry {
  timestamp: string;
  stage: string;
  message: string;
  progress: number;
}

// ── Main Component ────────────────────────────────────────────────────────────

function App() {
  // Navigation & Tabs
  const [currentTab, setCurrentTab] = useState<'scan' | 'history'>('scan');
  
  // Connection states
  const [health, setHealth] = useState<any>(null);
  const [loadingHealth, setLoadingHealth] = useState(true);
  const [socket, setSocket] = useState<any>(null);
  const [socketConnected, setSocketConnected] = useState(false);

  // Form inputs
  const [repositoryUrl, setRepositoryUrl] = useState('');
  const [authorName, setAuthorName] = useState('Developer');
  const [branchName, setBranchName] = useState('');
  const [enableAiFixes, setEnableAiFixes] = useState(true); // Default true to showcase AI capabilities
  const [offlineMode, setOfflineMode] = useState(false); // Default false to enable online healing mode

  // Active scan state
  const [activeScanId, setActiveScanId] = useState<string | null>(null);
  const [scanStatus, setScanStatus] = useState<'idle' | 'pending' | 'running' | 'success' | 'failed'>('idle');
  const [scanProgress, setScanProgress] = useState(0);
  const [scanStage, setScanStage] = useState('');
  const [scanMessage, setScanMessage] = useState('');
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [scanResults, setScanResults] = useState<ScanRun | null>(null);
  
  // Scans history
  const [scansList, setScansList] = useState<ScanRun[]>([]);
  const [loadingHistory, setLoadingHistory] = useState(false);

  // Details & Filtering
  const [expandedIssueId, setExpandedIssueId] = useState<string | null>(null);
  const [severityFilter, setSeverityFilter] = useState<string>('all');
  const [searchQuery, setSearchQuery] = useState('');
  
  // Phase 3 Healer Agent states
  const [fixingIssueId, setFixingIssueId] = useState<string | null>(null);
  const [rollingBack, setRollingBack] = useState(false);

  // Terminal scroll ref
  const terminalEndRef = useRef<HTMLDivElement>(null);

  // ── Backend Connection & Socket.IO Setup ──────────────────────────────────────

  // Fetch backend status
  const checkBackendHealth = () => {
    setLoadingHealth(true);
    fetch('http://localhost:8000/health')
      .then(res => res.json())
      .then(data => {
        setHealth(data);
        setLoadingHealth(false);
      })
      .catch(err => {
        console.error("Backend offline:", err);
        setHealth(null);
        setLoadingHealth(false);
      });
  };

  useEffect(() => {
    checkBackendHealth();

    // Setup Socket.IO connection
    const newSocket = io('http://localhost:8000', {
      transports: ['websocket'],
      reconnectionAttempts: 5,
    });

    newSocket.on('connect', () => {
      console.log('Socket.IO Connected:', newSocket.id);
      setSocketConnected(true);
    });

    newSocket.on('disconnect', () => {
      console.log('Socket.IO Disconnected');
      setSocketConnected(false);
    });

    setSocket(newSocket);

    return () => {
      newSocket.close();
    };
  }, []);

  // Listen to Socket.IO scan updates
  useEffect(() => {
    if (!socket) return;

    const handleScanUpdate = (payload: any) => {
      const { scan_id, data } = payload;
      
      // If we are actively tracking this scan
      if (scan_id === activeScanId) {
        setScanProgress(data.progress || 0);
        setScanStage(data.stage || '');
        setScanMessage(data.message || '');
        
        if (data.status) {
          setScanStatus(data.status);
        }

        // Add to live timeline logs
        setLogs(prev => [
          ...prev,
          {
            timestamp: new Date().toLocaleTimeString(),
            stage: data.stage || 'scanning',
            message: data.message || '',
            progress: data.progress || 0
          }
        ]);

        // Scroll terminal to bottom
        setTimeout(() => {
          terminalEndRef.current?.scrollIntoView({ behavior: 'smooth' });
        }, 100);

        // Fetch completed results if finished
        if (data.status === 'success') {
          setScanStatus('success');
          fetchResults(scan_id);
          fetchHistory();
        } else if (data.status === 'failed') {
          setScanStatus('failed');
          fetchResults(scan_id);
          fetchHistory();
        } else if (data.stage === 'healed' || data.stage === 'healing_failed') {
          setFixingIssueId(null);
          fetchResults(scan_id);
          fetchHistory();
        }
      }
    };

    socket.on('scan_update', handleScanUpdate);

    return () => {
      socket.off('scan_update', handleScanUpdate);
    };
  }, [socket, activeScanId]);

  // Scroll terminal when logs update
  useEffect(() => {
    terminalEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [logs]);

  // Fetch recent scans history
  const fetchHistory = () => {
    setLoadingHistory(true);
    fetch('http://localhost:8000/api/v1/scans?page_size=30')
      .then(res => res.json())
      .then(data => {
        setScansList(data.scans || []);
        setLoadingHistory(false);
      })
      .catch(err => {
        console.error("Failed to fetch history:", err);
        setLoadingHistory(false);
      });
  };

  useEffect(() => {
    if (currentTab === 'history') {
      fetchHistory();
    }
  }, [currentTab]);

  // Fetch scan results
  const fetchResults = (scanId: string) => {
    fetch(`http://localhost:8000/api/v1/scans/${scanId}/results`)
      .then(res => {
        if (res.status === 202) {
          // Still processing, poll again in 2 seconds
          setTimeout(() => fetchResults(scanId), 2000);
          return null;
        }
        return res.json();
      })
      .then(data => {
        if (data) {
          setScanResults(data);
          setScanStatus(data.status);
        }
      })
      .catch(err => {
        console.error("Error fetching results:", err);
      });
  };

  // ── Event Handlers ────────────────────────────────────────────────────────────

  // Trigger scan
  const handleStartScan = (e: React.FormEvent) => {
    e.preventDefault();
    if (!repositoryUrl.trim()) return;

    // Reset and initialize states
    setActiveScanId(null);
    setScanStatus('pending');
    setScanProgress(0);
    setScanStage('initializing');
    setScanMessage('Queueing scan in background worker...');
    setScanResults(null);
    setExpandedIssueId(null);
    setLogs([
      {
        timestamp: new Date().toLocaleTimeString(),
        stage: 'initializing',
        message: 'Queueing scan request...',
        progress: 0
      }
    ]);

    const payload = {
      repository_url: repositoryUrl.trim(),
      author_name: authorName.trim(),
      branch_name: branchName.trim() || undefined,
      enable_ai_fixes: enableAiFixes,
      offline_mode: offlineMode
    };

    fetch('http://localhost:8000/api/v1/scans', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
    })
      .then(res => {
        if (!res.ok) {
          return res.json().then(err => { throw new Error(err.detail || 'Failed to start scan') });
        }
        return res.json();
      })
      .then(data => {
        setActiveScanId(data.scan_id);
        setScanStatus('running');
        
        // Subscribe to updates via Socket.IO immediately
        if (socket && socketConnected) {
          socket.emit('subscribe_scan', { scan_id: data.scan_id });
        }
      })
      .catch(err => {
        console.error(err);
        setScanStatus('failed');
        setScanMessage(err.message || 'API Server Error.');
        setLogs(prev => [
          ...prev,
          {
            timestamp: new Date().toLocaleTimeString(),
            stage: 'failed',
            message: `Error: ${err.message}`,
            progress: 100
          }
        ]);
      });
  };

  // Select a past scan to view results
  const handleSelectPastScan = (scan: ScanRun) => {
    setActiveScanId(scan.scan_id);
    setScanStatus(scan.status);
    setScanProgress(scan.progress);
    setScanStage(scan.current_stage);
    setScanMessage(scan.status === 'success' ? 'Finished' : scan.error_message || 'Scan failed');
    setScanResults(scan);
    setExpandedIssueId(null);
    setCurrentTab('scan');
  };

  // Reset/Start fresh scan
  const handleResetScanner = () => {
    setActiveScanId(null);
    setScanStatus('idle');
    setScanProgress(0);
    setScanStage('');
    setScanMessage('');
    setScanResults(null);
    setLogs([]);
    setExpandedIssueId(null);
  };

  // Trigger AI healing for a specific issue
  const handleFixIssue = (scanId: string, issueId: string) => {
    setFixingIssueId(issueId);
    
    // Add temporary log
    setLogs(prev => [
      ...prev,
      {
        timestamp: new Date().toLocaleTimeString(),
        stage: 'healing',
        message: `AI Healer triggered for issue: ${issueId}...`,
        progress: 50
      }
    ]);

    fetch(`http://localhost:8000/api/v1/scans/${scanId}/fix`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ issue_id: issueId })
    })
      .then(res => {
        if (!res.ok) throw new Error("Failed to queue fix task");
        return res.json();
      })
      .catch(err => {
        console.error(err);
        setFixingIssueId(null);
        alert("Fix failed: " + err.message);
      });
  };

  // Rollback all fixes applied to a scan
  const handleRollback = (scanId: string) => {
    if (!window.confirm("Are you sure you want to rollback all applied fixes? This will discard your local changes.")) return;
    setRollingBack(true);

    fetch(`http://localhost:8000/api/v1/scans/${scanId}/rollback`, {
      method: 'POST'
    })
      .then(res => {
        if (!res.ok) throw new Error("Failed to rollback changes");
        return res.json();
      })
      .then(data => {
        setRollingBack(false);
        alert(data.message);
        fetchResults(scanId); // Reload results
        fetchHistory(); // Reload history
      })
      .catch(err => {
        console.error(err);
        setRollingBack(false);
        alert("Rollback failed: " + err.message);
      });
  };

  // ── Helper Rendering Functions ───────────────────────────────────────────────

  const getSeverityColor = (sev: string) => {
    switch (sev.toLowerCase()) {
      case 'critical': return { bg: 'bg-red-500/10 border-red-500/30 text-red-400', badge: 'bg-red-500 text-slate-950 font-bold', glow: 'shadow-red-500/10 border-red-500/30' };
      case 'high': return { bg: 'bg-orange-500/10 border-orange-500/30 text-orange-400', badge: 'bg-orange-500 text-slate-950 font-semibold', glow: 'shadow-orange-500/10 border-orange-500/30' };
      case 'medium': return { bg: 'bg-yellow-500/10 border-yellow-500/30 text-yellow-400', badge: 'bg-yellow-500 text-slate-950 font-semibold', glow: 'shadow-yellow-500/10 border-yellow-500/30' };
      case 'low': return { bg: 'bg-teal-500/10 border-teal-500/30 text-teal-400', badge: 'bg-teal-500 text-slate-950', glow: 'shadow-teal-500/10 border-teal-500/30' };
      default: return { bg: 'bg-slate-800 border-slate-700 text-slate-400', badge: 'bg-slate-700 text-slate-200', glow: 'border-slate-800' };
    }
  };

  const getHealthScoreColor = (score: number) => {
    if (score >= 90) return { text: 'text-teal-400', stroke: 'stroke-teal-400', bg: 'bg-teal-500/10', glow: 'shadow-teal-500/20' };
    if (score >= 75) return { text: 'text-blue-400', stroke: 'stroke-blue-400', bg: 'bg-blue-500/10', glow: 'shadow-blue-500/20' };
    if (score >= 60) return { text: 'text-yellow-400', stroke: 'stroke-yellow-400', bg: 'bg-yellow-500/10', glow: 'shadow-yellow-500/20' };
    return { text: 'text-red-400', stroke: 'stroke-red-400', bg: 'bg-red-500/10', glow: 'shadow-red-500/20' };
  };

  // Render a simple file tree
  const renderFileTree = (node: any, depth = 0) => {
    if (!node) return null;
    const isDir = node.isDir;
    
    return (
      <div key={node.name} style={{ paddingLeft: `${depth * 12}px` }} className="py-1">
        <div className="flex items-center gap-2 text-sm text-slate-300 hover:text-white cursor-pointer select-none">
          {isDir ? (
            <>
              <Folder className="w-4 h-4 text-teal-500 fill-teal-500/20" />
              <span className="font-medium text-slate-300">{node.name}</span>
            </>
          ) : (
            <>
              <FileCode className="w-4 h-4 text-blue-400" />
              <span className="text-slate-400">{node.name}</span>
            </>
          )}
        </div>
        {isDir && node.children && node.children.map((child: any) => renderFileTree(child, depth + 1))}
      </div>
    );
  };

  // Filter issues based on search and selected severity
  const getFilteredIssues = () => {
    if (!scanResults) return [];
    
    return scanResults.issues.filter(issue => {
      const matchesSearch = 
        issue.file_path.toLowerCase().includes(searchQuery.toLowerCase()) || 
        issue.message.toLowerCase().includes(searchQuery.toLowerCase()) ||
        issue.bug_type.toLowerCase().includes(searchQuery.toLowerCase());
        
      const matchesSeverity = 
        severityFilter === 'all' || 
        issue.severity.toLowerCase() === severityFilter.toLowerCase();
        
      return matchesSearch && matchesSeverity;
    });
  };

  const filteredIssues = getFilteredIssues();

  return (
    <div className="min-h-screen bg-slate-950 text-slate-200 antialiased font-sans relative overflow-x-hidden pb-12">
      {/* Background glow effects */}
      <div className="fixed top-[-10%] left-[-10%] w-[50%] h-[50%] bg-teal-600/10 rounded-full blur-[140px] pointer-events-none z-0" />
      <div className="fixed bottom-[-10%] right-[-10%] w-[50%] h-[50%] bg-blue-600/10 rounded-full blur-[140px] pointer-events-none z-0" />

      {/* Navigation Header */}
      <nav className="border-b border-slate-900 bg-slate-950/80 backdrop-blur-md sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
          <div className="flex items-center gap-3 cursor-pointer" onClick={handleResetScanner}>
            <div className="h-10 w-10 rounded-xl bg-gradient-to-br from-teal-400 to-blue-500 flex items-center justify-center shadow-lg shadow-teal-500/20 active:scale-95 transition-all">
              <Terminal className="w-5 h-5 text-slate-950 stroke-[2.5]" />
            </div>
            <div>
              <span className="text-xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-teal-400 to-blue-400 tracking-tight">
                PULSE DEVOPS
              </span>
              <span className="text-xs text-slate-500 block leading-3 font-semibold">SCANNER AGENT</span>
            </div>
          </div>

          <div className="flex items-center gap-6">
            <button
              onClick={() => setCurrentTab('scan')}
              className={`text-sm font-semibold transition-all px-3 py-1.5 rounded-lg ${
                currentTab === 'scan' ? 'bg-teal-500/10 text-teal-400' : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              Scanner Dashboard
            </button>
            <button
              onClick={() => setCurrentTab('history')}
              className={`text-sm font-semibold flex items-center gap-2 transition-all px-3 py-1.5 rounded-lg ${
                currentTab === 'history' ? 'bg-teal-500/10 text-teal-400' : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <History className="w-4 h-4" />
              Scan History
            </button>
            
            {/* Health status badge */}
            <div className="flex items-center gap-2 pl-4 border-l border-slate-800">
              <span className={`w-2 h-2 rounded-full ${health ? 'bg-teal-400 animate-pulse' : 'bg-red-500'}`} />
              <span className="text-xs text-slate-500 font-medium">
                {loadingHealth ? 'Checking...' : health ? 'Server Connected' : 'Server Offline'}
              </span>
              <button 
                onClick={checkBackendHealth} 
                className="text-slate-500 hover:text-slate-300 active:rotate-185 transition-all duration-300"
                title="Refresh Status"
              >
                <RefreshCw className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>
        </div>
      </nav>

      {/* Main Container */}
      <main className="max-w-7xl mx-auto px-6 mt-8 relative z-10">
        
        {/* Tab 1: SCANNER DASHBOARD */}
        {currentTab === 'scan' && (
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
            
            {/* LEFT PANEL: CONFIG FORM (when Idle) or RUNNING STATUS / TIMELINE (when Scanning) */}
            <div className="lg:col-span-4 space-y-6">
              
              {/* Form Input (Idle State) */}
              {scanStatus === 'idle' && (
                <div className="glass-panel p-6 border-slate-800 bg-slate-900/40 relative overflow-hidden">
                  <div className="absolute top-0 right-0 w-24 h-24 bg-teal-500/5 rounded-full blur-xl pointer-events-none" />
                  
                  <h3 className="text-lg font-bold text-slate-200 mb-6 flex items-center gap-2">
                    <Play className="w-4 h-4 text-teal-400 fill-teal-400/20" />
                    Configure New Scan
                  </h3>

                  <form onSubmit={handleStartScan} className="space-y-5">
                    <div>
                      <label className="block text-xs font-bold uppercase tracking-wider text-slate-400 mb-2">
                        GitHub Repository URL
                      </label>
                      <input
                        type="url"
                        value={repositoryUrl}
                        onChange={e => setRepositoryUrl(e.target.value)}
                        placeholder="https://github.com/username/repo"
                        className="input-field text-sm"
                        required
                      />
                      <span className="text-[10px] text-slate-500 mt-1 block">
                        Supports both public and private repositories.
                      </span>
                    </div>

                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <label className="block text-xs font-bold uppercase tracking-wider text-slate-400 mb-2">
                          Author Name
                        </label>
                        <div className="relative">
                          <User className="absolute left-3 top-2.5 w-4 h-4 text-slate-500" />
                          <input
                            type="text"
                            value={authorName}
                            onChange={e => setAuthorName(e.target.value)}
                            placeholder="Developer"
                            className="input-field pl-9 text-sm"
                          />
                        </div>
                      </div>
                      <div>
                        <label className="block text-xs font-bold uppercase tracking-wider text-slate-400 mb-2">
                          Branch Name (Opt)
                        </label>
                        <div className="relative">
                          <GitBranch className="absolute left-3 top-2.5 w-4 h-4 text-slate-500" />
                          <input
                            type="text"
                            value={branchName}
                            onChange={e => setBranchName(e.target.value)}
                            placeholder="main"
                            className="input-field pl-9 text-sm"
                          />
                        </div>
                      </div>
                    </div>

                    <div className="space-y-3 pt-3 border-t border-slate-900">
                      <div className="flex items-center justify-between">
                        <div className="flex flex-col">
                          <span className="text-xs font-bold uppercase text-slate-300">Local Offline Scanner</span>
                          <span className="text-[10px] text-slate-500">Run statics tools (pylint, flake8, mypy)</span>
                        </div>
                        <input
                          type="checkbox"
                          checked={offlineMode}
                          onChange={e => setOfflineMode(e.target.checked)}
                          className="h-4 w-4 rounded border-slate-700 bg-slate-950 text-teal-600 focus:ring-teal-500 focus:ring-offset-slate-950"
                        />
                      </div>
                      
                      <div className="flex items-center justify-between">
                        <div className="flex flex-col">
                          <span className="text-xs font-bold uppercase text-slate-300">Auto AI Fix Generator</span>
                          <span className="text-[10px] text-slate-500">Drafts fixes for detected bugs (Phase 3)</span>
                        </div>
                        <input
                          type="checkbox"
                          checked={enableAiFixes}
                          onChange={e => setEnableAiFixes(e.target.checked)}
                          className="h-4 w-4 rounded border-slate-700 bg-slate-950 text-teal-600 focus:ring-teal-500 focus:ring-offset-slate-950"
                        />
                      </div>
                    </div>

                    <button
                      type="submit"
                      disabled={!health}
                      className="btn-primary w-full mt-6 py-3 font-semibold text-sm flex items-center justify-center gap-2 text-slate-950 bg-gradient-to-r from-teal-400 to-blue-500 hover:from-teal-300 hover:to-blue-400 shadow-teal-500/20 disabled:from-slate-800 disabled:to-slate-800 disabled:text-slate-500 disabled:cursor-not-allowed"
                    >
                      <Play className="w-4 h-4 fill-slate-950" />
                      Trigger Pulse Scanner
                    </button>
                  </form>
                </div>
              )}

              {/* Progress Terminal (Running / Processing / Completed State) */}
              {scanStatus !== 'idle' && (
                <div className="space-y-6">
                  
                  {/* Progress Header Card */}
                  <div className="glass-panel p-6 border-slate-800 bg-slate-900/40">
                    <div className="flex items-center justify-between mb-4">
                      <h4 className="text-sm font-bold uppercase tracking-wider text-slate-400">
                        Scan Queue Status
                      </h4>
                      <span className={`px-2 py-0.5 rounded text-xs uppercase font-bold ${
                        scanStatus === 'running' ? 'bg-blue-500/10 text-blue-400 border border-blue-500/20 animate-pulse' :
                        scanStatus === 'pending' ? 'bg-yellow-500/10 text-yellow-400 border border-yellow-500/20' :
                        scanStatus === 'success' ? 'bg-teal-500/10 text-teal-400 border border-teal-500/20' :
                        'bg-red-500/10 text-red-400 border border-red-500/20'
                      }`}>
                        {scanStatus}
                      </span>
                    </div>

                    <div className="space-y-3">
                      <div className="flex justify-between text-xs text-slate-400">
                        <span className="font-semibold capitalize">Stage: {scanStage}</span>
                        <span className="font-bold">{scanProgress}%</span>
                      </div>
                      {/* Premium Progress Bar */}
                      <div className="w-full bg-slate-950 h-2.5 rounded-full overflow-hidden border border-slate-900">
                        <div
                          className="h-full bg-gradient-to-r from-teal-400 to-blue-500 rounded-full transition-all duration-300"
                          style={{ width: `${scanProgress}%` }}
                        />
                      </div>
                      <p className="text-[11px] text-slate-500 italic mt-1 truncate">
                        {scanMessage}
                      </p>
                    </div>

                    {(scanStatus === 'success' || scanStatus === 'failed') && (
                      <button
                        onClick={handleResetScanner}
                        className="btn-secondary w-full text-xs py-2 mt-4 font-semibold hover:bg-slate-800 border-slate-800 flex items-center justify-center gap-1.5"
                      >
                        Start Fresh Scan
                      </button>
                    )}
                  </div>

                  {/* Terminal Live Logger */}
                  <div className="glass-panel border-slate-800 bg-slate-900/60 overflow-hidden flex flex-col h-[280px]">
                    <div className="bg-slate-950/80 px-4 py-2 border-b border-slate-900 flex items-center justify-between">
                      <span className="text-xs font-bold text-slate-400 flex items-center gap-2">
                        <Terminal className="w-3.5 h-3.5 text-teal-400" />
                        Live Pipeline Guard Logs
                      </span>
                      <div className="flex gap-1">
                        <span className="w-2.5 h-2.5 rounded-full bg-red-500/70" />
                        <span className="w-2.5 h-2.5 rounded-full bg-yellow-500/70" />
                        <span className="w-2.5 h-2.5 rounded-full bg-teal-500/70" />
                      </div>
                    </div>
                    
                    <div className="p-4 font-mono text-[11px] text-slate-400 overflow-y-auto flex-1 space-y-1 bg-slate-950/20">
                      {logs.map((log, index) => (
                        <div key={index} className="flex gap-2 leading-relaxed">
                          <span className="text-slate-600 select-none">[{log.timestamp}]</span>
                          <span className="text-teal-500 font-bold select-none capitalize">[{log.stage}]</span>
                          <span className="text-slate-300">{log.message}</span>
                        </div>
                      ))}
                      {scanStatus === 'running' && (
                        <div className="flex gap-2 animate-pulse mt-1">
                          <span className="text-slate-600 select-none">[{new Date().toLocaleTimeString()}]</span>
                          <span className="text-blue-400 font-semibold select-none capitalize">[{scanStage}]</span>
                          <span className="text-slate-400 flex items-center gap-1.5">
                            <Loader2 className="w-3 h-3 animate-spin" />
                            Executing background tasks...
                          </span>
                        </div>
                      )}
                      <div ref={terminalEndRef} />
                    </div>
                  </div>

                  {/* Sidebar Heatmap & Problem files (Available on success) */}
                  {scanResults && scanResults.health_score && (
                    <div className="glass-panel p-5 border-slate-800 bg-slate-900/40 space-y-5">
                      <div>
                        <h4 className="text-xs font-bold uppercase tracking-wider text-slate-400 mb-3 flex items-center gap-1.5">
                          <BarChart3 className="w-4 h-4 text-teal-400" />
                          Top Problem Files
                        </h4>
                        
                        {scanResults.health_score.top_problem_files.length > 0 ? (
                          <div className="space-y-3">
                            {scanResults.health_score.top_problem_files.map((file, i) => {
                              const issueCount = scanResults.bug_heatmap?.[file] || 0;
                              return (
                                <div key={file} className="space-y-1">
                                  <div className="flex justify-between text-[11px] font-medium text-slate-300">
                                    <span className="truncate max-w-[200px]" title={file}>{file.split('/').pop()}</span>
                                    <span className="text-red-400 font-bold">{issueCount} issues</span>
                                  </div>
                                  <div className="w-full bg-slate-950 h-1.5 rounded-full overflow-hidden border border-slate-900">
                                    <div
                                      className="h-full bg-gradient-to-r from-orange-400 to-red-500 rounded-full"
                                      style={{ width: `${Math.min(100, (issueCount / scanResults.total_issues_found) * 100)}%` }}
                                    />
                                  </div>
                                </div>
                              );
                            })}
                          </div>
                        ) : (
                          <p className="text-xs text-slate-500 italic">No issues reported inside repository files.</p>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* RIGHT PANEL: SUMMARY METRICS & ISSUE LIST (Success State) */}
            <div className="lg:col-span-8 space-y-6">
              
              {/* Idle State welcome banner */}
              {scanStatus === 'idle' && (
                <div className="glass-panel p-8 border-slate-800 bg-slate-900/20 text-center flex flex-col items-center justify-center min-h-[400px]">
                  <div className="h-16 w-16 rounded-2xl bg-gradient-to-br from-teal-500/20 to-blue-500/20 border border-teal-500/30 flex items-center justify-center text-teal-400 mb-6 shadow-xl shadow-teal-500/5">
                    <Github className="w-8 h-8 stroke-[1.5]" />
                  </div>
                  <h2 className="text-2xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-teal-200 to-blue-200 mb-3 tracking-tight">
                    Analyze & Secure Repository Health
                  </h2>
                  <p className="text-slate-400 text-sm max-w-md leading-relaxed mb-8">
                    Provide a GitHub URL and trigger our custom local Scanner Agent to clone, audit codebases, compute detailed severity scores, and analyze project health.
                  </p>
                  
                  {/* Visual Features Row */}
                  <div className="grid grid-cols-3 gap-6 max-w-xl w-full text-left">
                    <div className="p-4 rounded-xl bg-slate-900/40 border border-slate-900/60">
                      <span className="text-xs font-bold text-teal-400 uppercase tracking-wide block mb-1">Static Scanners</span>
                      <span className="text-[11px] text-slate-500 leading-normal">Runs pylint, flake8, mypy, and bandit in a secure sandbox.</span>
                    </div>
                    <div className="p-4 rounded-xl bg-slate-900/40 border border-slate-900/60">
                      <span className="text-xs font-bold text-teal-400 uppercase tracking-wide block mb-1">Severity Scoring</span>
                      <span className="text-[11px] text-slate-500 leading-normal">Assigns 0-10 severity metrics based on syntax, logic, and security.</span>
                    </div>
                    <div className="p-4 rounded-xl bg-slate-900/40 border border-slate-900/60">
                      <span className="text-xs font-bold text-teal-400 uppercase tracking-wide block mb-1">WebSockets updates</span>
                      <span className="text-[11px] text-slate-500 leading-normal">Streams real-time terminal output logs as pipelines compile.</span>
                    </div>
                  </div>
                </div>
              )}

              {/* Pending / Running loading placeholder */}
              {(scanStatus === 'pending' || (scanStatus === 'running' && !scanResults)) && (
                <div className="glass-panel p-8 border-slate-800 bg-slate-900/20 text-center flex flex-col items-center justify-center min-h-[400px]">
                  <Loader2 className="w-10 h-10 text-teal-400 animate-spin mb-4" />
                  <h3 className="text-lg font-bold text-slate-300">Scan Pipeline Compiling</h3>
                  <p className="text-slate-500 text-sm mt-1 max-w-sm">
                    Please hold on as our background worker clones and parses your repository structure...
                  </p>
                </div>
              )}

              {/* Success Scan Dashboard Results */}
              {scanResults && (
                <div className="space-y-6 animate-in fade-in duration-500">
                  
                  {/* Dashboard Hero Header */}
                  <div className="glass-panel p-6 border-slate-800 bg-slate-900/40 flex flex-col md:flex-row md:items-center justify-between gap-6 relative overflow-hidden">
                    <div className="absolute top-0 right-0 w-48 h-48 bg-teal-500/5 rounded-full blur-2xl pointer-events-none" />
                    
                    <div className="space-y-3">
                      <div className="flex items-center gap-2">
                        <Github className="w-5 h-5 text-teal-400" />
                        <h2 className="text-xl font-bold text-slate-100 leading-none">
                          {scanResults.repository_name}
                        </h2>
                        <a
                          href={scanResults.repository_url}
                          target="_blank"
                          rel="noreferrer"
                          className="text-slate-500 hover:text-slate-300 ml-1"
                        >
                          <ExternalLink className="w-3.5 h-3.5" />
                        </a>
                      </div>
                      
                      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-xs text-slate-400">
                        <span className="flex items-center gap-1.5">
                          <GitBranch className="w-3.5 h-3.5 text-slate-500" />
                          {scanResults.branch_name}
                        </span>
                        <span className="flex items-center gap-1.5">
                          <User className="w-3.5 h-3.5 text-slate-500" />
                          {scanResults.author_name}
                        </span>
                        <span>
                          Scan Date: {new Date(scanResults.created_at).toLocaleString()}
                        </span>
                        {scanResults.duration_seconds !== undefined && (
                          <span className="bg-slate-950 px-2 py-0.5 rounded text-slate-500 font-semibold border border-slate-900">
                            Duration: {scanResults.duration_seconds}s
                          </span>
                        )}
                        {scanResults.fixes && scanResults.fixes.length > 0 && (
                          <button
                            onClick={() => handleRollback(scanResults.scan_id)}
                            disabled={rollingBack}
                            className="bg-red-500/10 border border-red-500/30 text-red-400 hover:bg-red-500/20 active:scale-95 transition-all text-xs font-bold px-3 py-1 rounded-lg flex items-center gap-1.5"
                          >
                            {rollingBack ? (
                              <>
                                <Loader2 className="w-3.5 h-3.5 animate-spin" />
                                Rolling back...
                              </>
                            ) : (
                              <>
                                <XCircle className="w-3.5 h-3.5" />
                                Rollback {scanResults.fixes.length} Fixes
                              </>
                            )}
                          </button>
                        )}
                      </div>
                    </div>

                    {/* Circular Health Score gauge */}
                    {scanResults.health_score && (
                      <div className="flex items-center gap-4 bg-slate-950/40 p-3 rounded-2xl border border-slate-900 pr-5">
                        <div className="relative w-20 h-20 flex items-center justify-center">
                          {/* Radial Score Gauge SVG */}
                          <svg className="w-full h-full transform -rotate-90" viewBox="0 0 100 100">
                            <circle
                              cx="50"
                              cy="50"
                              r="40"
                              className="stroke-slate-900 stroke-[8] fill-none"
                            />
                            <circle
                              cx="50"
                              cy="50"
                              r="40"
                              className={`${getHealthScoreColor(scanResults.health_score.score).stroke} stroke-[8] fill-none transition-all duration-1000 ease-out`}
                              strokeDasharray="251.2"
                              strokeDashoffset={251.2 - (251.2 * scanResults.health_score.score) / 100}
                              strokeLinecap="round"
                            />
                          </svg>
                          <div className="absolute flex flex-col items-center justify-center">
                            <span className="text-xl font-black text-slate-100 tracking-tighter">
                              {Math.round(scanResults.health_score.score)}
                            </span>
                            <span className="text-[9px] text-slate-500 font-bold uppercase tracking-wider mt-[-2px]">
                              /100
                            </span>
                          </div>
                        </div>

                        <div>
                          <div className="flex items-center gap-1.5">
                            <span className={`text-2xl font-black ${getHealthScoreColor(scanResults.health_score.score).text}`}>
                              Grade {scanResults.health_score.grade}
                            </span>
                          </div>
                          <span className="text-xs font-semibold text-slate-400">
                            {scanResults.health_score.label}
                          </span>
                        </div>
                      </div>
                    )}
                  </div>

                  {/* Summary Severity Counters */}
                  {scanResults.health_score && (
                    <div className="grid grid-cols-2 sm:grid-cols-5 gap-4">
                      
                      {/* Critical Card */}
                      <div
                        onClick={() => setSeverityFilter(severityFilter === 'critical' ? 'all' : 'critical')}
                        className={`p-4 rounded-xl border transition-all cursor-pointer select-none ${
                          severityFilter === 'critical' 
                            ? 'bg-red-500/10 border-red-500 shadow-md shadow-red-500/5' 
                            : 'bg-slate-900/30 border-slate-900 hover:border-slate-800'
                        }`}
                      >
                        <span className="text-[10px] font-bold uppercase tracking-wider text-slate-500 block mb-1">Critical</span>
                        <div className="flex items-baseline gap-2">
                          <span className="text-2xl font-black text-red-500">{scanResults.health_score.critical_count}</span>
                          <span className="text-xs text-slate-500">blocking</span>
                        </div>
                      </div>

                      {/* High Card */}
                      <div
                        onClick={() => setSeverityFilter(severityFilter === 'high' ? 'all' : 'high')}
                        className={`p-4 rounded-xl border transition-all cursor-pointer select-none ${
                          severityFilter === 'high' 
                            ? 'bg-orange-500/10 border-orange-500 shadow-md shadow-orange-500/5' 
                            : 'bg-slate-900/30 border-slate-900 hover:border-slate-800'
                        }`}
                      >
                        <span className="text-[10px] font-bold uppercase tracking-wider text-slate-500 block mb-1">High</span>
                        <div className="flex items-baseline gap-2">
                          <span className="text-2xl font-black text-orange-400">{scanResults.health_score.high_count}</span>
                          <span className="text-xs text-slate-500">errors</span>
                        </div>
                      </div>

                      {/* Medium Card */}
                      <div
                        onClick={() => setSeverityFilter(severityFilter === 'medium' ? 'all' : 'medium')}
                        className={`p-4 rounded-xl border transition-all cursor-pointer select-none ${
                          severityFilter === 'medium' 
                            ? 'bg-yellow-500/10 border-yellow-500 shadow-md shadow-yellow-500/5' 
                            : 'bg-slate-900/30 border-slate-900 hover:border-slate-800'
                        }`}
                      >
                        <span className="text-[10px] font-bold uppercase tracking-wider text-slate-500 block mb-1">Medium</span>
                        <div className="flex items-baseline gap-2">
                          <span className="text-2xl font-black text-yellow-400">{scanResults.health_score.medium_count}</span>
                          <span className="text-xs text-slate-500">warning</span>
                        </div>
                      </div>

                      {/* Low Card */}
                      <div
                        onClick={() => setSeverityFilter(severityFilter === 'low' ? 'all' : 'low')}
                        className={`p-4 rounded-xl border transition-all cursor-pointer select-none ${
                          severityFilter === 'low' 
                            ? 'bg-teal-500/10 border-teal-500 shadow-md shadow-teal-500/5' 
                            : 'bg-slate-900/30 border-slate-900 hover:border-slate-800'
                        }`}
                      >
                        <span className="text-[10px] font-bold uppercase tracking-wider text-slate-500 block mb-1">Low</span>
                        <div className="flex items-baseline gap-2">
                          <span className="text-2xl font-black text-teal-400">{scanResults.health_score.low_count}</span>
                          <span className="text-xs text-slate-500">linting</span>
                        </div>
                      </div>

                      {/* Info Card */}
                      <div
                        onClick={() => setSeverityFilter(severityFilter === 'info' ? 'all' : 'info')}
                        className={`p-4 rounded-xl border transition-all cursor-pointer select-none col-span-2 sm:col-span-1 ${
                          severityFilter === 'info' 
                            ? 'bg-slate-800 border-slate-500 shadow-md' 
                            : 'bg-slate-900/30 border-slate-900 hover:border-slate-800'
                        }`}
                      >
                        <span className="text-[10px] font-bold uppercase tracking-wider text-slate-500 block mb-1">Info</span>
                        <div className="flex items-baseline gap-2">
                          <span className="text-2xl font-black text-slate-300">{scanResults.health_score.info_count}</span>
                          <span className="text-xs text-slate-500">suggs</span>
                        </div>
                      </div>

                    </div>
                  )}

                  {/* Filter & Search Bar */}
                  <div className="glass-panel p-4 border-slate-800 bg-slate-900/30 flex flex-col md:flex-row md:items-center gap-4">
                    <div className="relative flex-1">
                      <Search className="absolute left-3.5 top-3 w-4.5 h-4.5 text-slate-500" />
                      <input
                        type="text"
                        value={searchQuery}
                        onChange={e => setSearchQuery(e.target.value)}
                        placeholder="Search issues by filename, linter code, or keywords..."
                        className="input-field pl-10 text-sm py-2.5 bg-slate-955/40"
                      />
                    </div>

                    <div className="flex items-center gap-3">
                      <span className="text-xs font-bold text-slate-500 uppercase flex items-center gap-1.5">
                        <Filter className="w-3.5 h-3.5" />
                        Linter severity:
                      </span>
                      <select
                        value={severityFilter}
                        onChange={e => setSeverityFilter(e.target.value)}
                        className="bg-slate-950 border border-slate-850 text-xs px-3 py-2 rounded-lg text-slate-300 focus:outline-none focus:ring-1 focus:ring-teal-500"
                      >
                        <option value="all">All Severities</option>
                        <option value="critical">Critical Only</option>
                        <option value="high">High Only</option>
                        <option value="medium">Medium Only</option>
                        <option value="low">Low Only</option>
                        <option value="info">Info Only</option>
                      </select>
                    </div>
                  </div>

                  {/* Detailed Issues List Accordion */}
                  <div className="space-y-4">
                    <div className="flex items-center justify-between px-2">
                      <h4 className="text-xs font-bold uppercase tracking-wider text-slate-400">
                        Audit Findings ({filteredIssues.length} matches)
                      </h4>
                      {severityFilter !== 'all' && (
                        <button
                          onClick={() => setSeverityFilter('all')}
                          className="text-xs text-teal-400 hover:underline font-semibold"
                        >
                          Clear severity filter
                        </button>
                      )}
                    </div>

                    {filteredIssues.length > 0 ? (
                      <div className="space-y-3">
                        {filteredIssues.map((issue) => {
                          const isExpanded = expandedIssueId === issue.id;
                          const colors = getSeverityColor(issue.severity);
                          
                          return (
                            <div
                              key={issue.id}
                              className={`glass-panel border overflow-hidden transition-all duration-300 ${colors.glow} ${
                                isExpanded ? 'bg-slate-900/50' : 'bg-slate-900/10 hover:bg-slate-900/30'
                              }`}
                            >
                              {/* Header Trigger */}
                              <div
                                onClick={() => setExpandedIssueId(isExpanded ? null : issue.id)}
                                className="p-4 flex items-center justify-between gap-4 cursor-pointer select-none"
                              >
                                <div className="flex items-start gap-3 min-w-0">
                                  {/* Severity Score Metric */}
                                  <div className={`h-9 w-9 rounded-lg flex flex-col items-center justify-center shrink-0 border ${colors.bg}`}>
                                    <span className="text-xs font-black tracking-tighter">
                                      {issue.severity_score.toFixed(1)}
                                    </span>
                                    <span className="text-[7px] font-bold uppercase tracking-wider leading-none">
                                      score
                                    </span>
                                  </div>

                                  <div className="space-y-1 min-w-0">
                                    <div className="flex items-center gap-2 flex-wrap">
                                      <span className={`text-[9px] uppercase px-1.5 py-0.5 rounded font-black ${colors.badge}`}>
                                        {issue.severity}
                                      </span>
                                      <span className="text-[10px] font-bold uppercase tracking-wider px-1.5 py-0.5 bg-slate-950 border border-slate-900 text-slate-400 rounded">
                                        {issue.source}
                                      </span>
                                      <span className="text-slate-400 text-xs font-mono font-medium truncate max-w-[200px]" title={issue.file_path}>
                                        {issue.file_path.split('/').pop()}:{issue.line}
                                      </span>
                                    </div>
                                    <p className="text-slate-200 text-xs font-semibold leading-relaxed truncate" title={issue.message}>
                                      {issue.message}
                                    </p>
                                  </div>
                                </div>

                                <div className="text-slate-500 hover:text-slate-300 pr-1">
                                  {isExpanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                                </div>
                              </div>

                              {/* Accordion Expand Details */}
                              {isExpanded && (
                                <div className="px-4 pb-4 pt-2 border-t border-slate-900/60 space-y-4 animate-in slide-in-from-top-2 duration-300">
                                  
                                  {/* Issue metadata details */}
                                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-[11px] text-slate-400">
                                    <div className="space-y-2">
                                      <p>
                                        <span className="font-semibold text-slate-500 uppercase">File Path:</span>{' '}
                                        <code className="text-slate-300 font-mono select-all bg-slate-950 px-1.5 py-0.5 rounded border border-slate-900">
                                          {issue.file_path}
                                        </code>
                                      </p>
                                      <p>
                                        <span className="font-semibold text-slate-500 uppercase">Bug Category:</span>{' '}
                                        <span className="text-slate-300 font-bold bg-slate-900 px-2 py-0.5 rounded">
                                          {issue.bug_type}
                                        </span>
                                      </p>
                                    </div>
                                    <div className="space-y-2">
                                      <p>
                                        <span className="font-semibold text-slate-500 uppercase">Coordinates:</span>{' '}
                                        <span className="text-slate-300 font-medium">
                                          Line {issue.line}, Column {issue.column}
                                        </span>
                                      </p>
                                      <p>
                                        <span className="font-semibold text-slate-500 uppercase">Audit Tool:</span>{' '}
                                        <span className="text-slate-300 font-medium capitalize">
                                          {issue.source} Analyzer
                                        </span>
                                      </p>
                                    </div>
                                  </div>

                                  {/* Severity Reasoning Alert */}
                                  {issue.reasoning && (
                                    <div className="p-3.5 rounded-lg bg-teal-500/5 border border-teal-500/10 flex gap-2 text-xs leading-relaxed text-teal-300/90">
                                      <Info className="w-4 h-4 text-teal-400 shrink-0 mt-0.5" />
                                      <div>
                                        <span className="font-bold uppercase tracking-wider text-[10px] text-teal-400 block mb-0.5">
                                          AI Severity Scoring Breakdown
                                        </span>
                                        {issue.reasoning}
                                      </div>
                                    </div>
                                  )}

                                  {/* Monospace Code Snippet Block */}
                                  {issue.code_snippet && (
                                    <div className="space-y-1.5">
                                      <span className="text-[10px] font-bold uppercase tracking-wider text-slate-500">
                                        Affected Code Line
                                      </span>
                                      <div className="p-4 rounded-lg bg-slate-950 border border-slate-900 font-mono text-xs overflow-x-auto text-slate-300 flex gap-4 relative">
                                        <span className="text-slate-600 select-none text-right w-6 border-r border-slate-900 pr-3">
                                          {issue.line}
                                        </span>
                                        <code className="text-teal-400 font-semibold">{issue.code_snippet}</code>
                                        
                                        <span className="absolute top-2 right-2 text-[9px] font-bold text-slate-700 bg-slate-900 border border-slate-950 px-1.5 py-0.5 rounded select-none">
                                          READ ONLY
                                        </span>
                                      </div>
                                    </div>
                                  )}

                                  {/* AI Auto-Fix section */}
                                  {issue.fixed && (
                                    <div className="space-y-3 pt-3 border-t border-slate-900/60 animate-in fade-in duration-350">
                                      <div className="flex items-center justify-between">
                                        <span className="text-xs font-bold uppercase tracking-wider text-teal-400 flex items-center gap-1.5">
                                          <CheckCircle2 className="w-4 h-4 text-teal-400" />
                                          AI Healing Solution Applied
                                        </span>
                                        <span className="text-[10px] bg-teal-500/10 border border-teal-500/20 text-teal-400 font-bold px-2.5 py-0.5 rounded">
                                          Confidence: 95%
                                        </span>
                                      </div>
                                      
                                      {(() => {
                                        const fix = scanResults.fixes?.find(f => f.file_path === issue.file_path && f.line_number === issue.line);
                                        if (!fix) return null;
                                        return (
                                          <div className="space-y-2">
                                            <p className="text-xs text-slate-400 font-medium">{fix.description}</p>
                                            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs font-mono">
                                              <div className="bg-red-950/20 border border-red-900/20 p-3.5 rounded-lg overflow-x-auto text-red-400">
                                                <span className="text-[9px] font-bold uppercase tracking-wider block mb-1 text-red-500/60">Original Line</span>
                                                <code>- {fix.before_code}</code>
                                              </div>
                                              <div className="bg-teal-950/25 border border-teal-900/30 p-3.5 rounded-lg overflow-x-auto text-teal-400">
                                                <span className="text-[9px] font-bold uppercase tracking-wider block mb-1 text-teal-500/60">AI Patch Applied</span>
                                                <code>+ {fix.after_code}</code>
                                              </div>
                                            </div>
                                          </div>
                                        );
                                      })()}
                                    </div>
                                  )}

                                  {!issue.fixed && (
                                    <div className="pt-2 border-t border-slate-900/60 flex items-center justify-between">
                                      <div className="text-xs text-slate-500 font-medium">
                                        Detect an issue? Let PULSE AI heal it automatically.
                                      </div>
                                      <button
                                        onClick={() => handleFixIssue(scanResults.scan_id, issue.id)}
                                        disabled={fixingIssueId !== null}
                                        className="btn-primary py-2 px-4.5 text-xs font-bold text-slate-950 bg-gradient-to-r from-teal-400 to-blue-500 hover:from-teal-300 hover:to-blue-400 shadow-md shadow-teal-500/10 flex items-center gap-1.5 disabled:from-slate-800 disabled:to-slate-800 disabled:text-slate-500 disabled:cursor-not-allowed transition-all active:scale-95"
                                      >
                                        {fixingIssueId === issue.id ? (
                                          <>
                                            <Loader2 className="w-3.5 h-3.5 animate-spin" />
                                            Healer compiling fix...
                                          </>
                                        ) : (
                                          <>
                                            <RefreshCw className="w-3.5 h-3.5 animate-spin-slow" />
                                            Heal Issue with AI Healer
                                          </>
                                        )}
                                      </button>
                                    </div>
                                  )}

                                </div>
                              )}
                            </div>
                          );
                        })}
                      </div>
                    ) : (
                      <div className="glass-panel p-8 border-slate-800 bg-slate-900/10 text-center text-slate-500 italic text-sm">
                        No code audit findings match your current filters.
                      </div>
                    )}
                  </div>
                  
                  {/* File tree explorer (Success scan state) */}
                  {scanResults.file_tree && scanResults.file_tree.children && scanResults.file_tree.children.length > 0 && (
                    <div className="glass-panel p-6 border-slate-800 bg-slate-900/40 space-y-4">
                      <h4 className="text-xs font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
                        <FolderOpen className="w-4 h-4 text-teal-400" />
                        Scanned Repository Structure Explorer
                      </h4>
                      <div className="border border-slate-900 bg-slate-950/40 p-4 rounded-lg max-h-[300px] overflow-y-auto">
                        {renderFileTree(scanResults.file_tree)}
                      </div>
                    </div>
                  )}

                </div>
              )}

            </div>

          </div>
        )}

        {/* Tab 2: SCAN HISTORY DRAWER */}
        {currentTab === 'history' && (
          <div className="glass-panel p-6 border-slate-800 bg-slate-900/40 space-y-6 animate-in fade-in duration-500">
            <div className="flex items-center justify-between border-b border-slate-900 pb-4">
              <div>
                <h2 className="text-xl font-bold text-slate-200 flex items-center gap-2">
                  <History className="w-5 h-5 text-teal-400" />
                  Recent Scan Audits
                </h2>
                <p className="text-xs text-slate-500">List of repository scans executed on this system</p>
              </div>
              <button 
                onClick={fetchHistory}
                className="btn-secondary text-xs flex items-center gap-1.5 py-1.5 hover:bg-slate-800 border-slate-800"
              >
                <RefreshCw className="w-3.5 h-3.5" />
                Refresh History
              </button>
            </div>

            {loadingHistory ? (
              <div className="py-20 text-center flex flex-col items-center justify-center">
                <Loader2 className="w-8 h-8 text-teal-400 animate-spin mb-3" />
                <p className="text-slate-500 text-sm">Querying scan logs database...</p>
              </div>
            ) : scansList.length > 0 ? (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm border-collapse">
                  <thead>
                    <tr className="border-b border-slate-900 text-slate-500 font-semibold text-xs uppercase tracking-wider">
                      <th className="py-3 px-4">Repository</th>
                      <th className="py-3 px-4">Author</th>
                      <th className="py-3 px-4">Target Branch</th>
                      <th className="py-3 px-4">Date</th>
                      <th className="py-3 px-4">Health score</th>
                      <th className="py-3 px-4">Issues Found</th>
                      <th className="py-3 px-4">Status</th>
                      <th className="py-3 px-4 text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-900/60">
                    {scansList.map((scan) => {
                      const date = new Date(scan.created_at).toLocaleString();
                      const hasHealth = scan.health_score !== undefined && scan.health_score !== null;
                      
                      return (
                        <tr key={scan.scan_id} className="hover:bg-slate-900/20 text-slate-300">
                          <td className="py-3.5 px-4 font-semibold text-slate-200">
                            <span className="flex items-center gap-2">
                              <Github className="w-4 h-4 text-slate-500" />
                              {scan.repository_name}
                            </span>
                          </td>
                          <td className="py-3.5 px-4 text-xs text-slate-400">{scan.author_name}</td>
                          <td className="py-3.5 px-4 font-mono text-xs text-slate-400">
                            <span className="flex items-center gap-1">
                              <GitBranch className="w-3.5 h-3.5 text-slate-600" />
                              {scan.branch_name}
                            </span>
                          </td>
                          <td className="py-3.5 px-4 text-xs text-slate-400">{date}</td>
                          <td className="py-3.5 px-4 font-bold">
                            {hasHealth ? (
                              <span className={`flex items-center gap-1.5 ${getHealthScoreColor(scan.health_score!.score).text}`}>
                                {Math.round(scan.health_score!.score)}/100 ({scan.health_score!.grade})
                              </span>
                            ) : (
                              <span className="text-slate-500">—</span>
                            )}
                          </td>
                          <td className="py-3.5 px-4 text-xs font-semibold text-slate-400">
                            {scan.total_issues_found} issues
                          </td>
                          <td className="py-3.5 px-4">
                            <span className={`px-2 py-0.5 rounded text-[10px] font-black uppercase ${
                              scan.status === 'success' ? 'bg-teal-500/10 text-teal-400 border border-teal-500/20' :
                              scan.status === 'running' ? 'bg-blue-500/10 text-blue-400 border border-blue-500/20 animate-pulse' :
                              scan.status === 'pending' ? 'bg-yellow-500/10 text-yellow-400 border border-yellow-500/20' :
                              'bg-red-500/10 text-red-400 border border-red-500/20'
                            }`}>
                              {scan.status}
                            </span>
                          </td>
                          <td className="py-3.5 px-4 text-right">
                            <button
                              onClick={() => handleSelectPastScan(scan)}
                              className="text-xs font-semibold px-3 py-1.5 rounded-lg bg-teal-500/10 hover:bg-teal-500 hover:text-slate-950 text-teal-400 transition-all active:scale-95"
                            >
                              Load Audit
                            </button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="py-20 text-center text-slate-500 italic text-sm">
                No scan history found inside database. Start a new scan in the Dashboard!
              </div>
            )}
          </div>
        )}

      </main>
    </div>
  );
}

export default App;
