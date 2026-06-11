import React, { useState, useEffect, useRef } from 'react';
import {
  TrendingUp,
  TrendingDown,
  Coins,
  LineChart,
  DollarSign,
  Cpu,
  Send,
  Settings,
  Activity,
  ArrowUpRight,
  ArrowDownRight,
  ShieldCheck,
  RefreshCw,
  MessageSquare,
  Bell,
  Trash2,
  AlertCircle
} from 'lucide-react';

const API_BASE = import.meta.env.VITE_API_BASE || '';

function MT5PriceTag({ symbol, apiBase }) {
  const [price, setPrice] = React.useState(null);
  React.useEffect(() => {
    let cancelled = false;
    const fetch_ = async () => {
      try {
        const res = await fetch(`${apiBase}/api/mt5/price/${symbol}`);
        const d = await res.json();
        if (!cancelled && d.mt5_status === 'online') setPrice(d);
      } catch {}
    };
    fetch_();
    const id = setInterval(fetch_, 5000);
    return () => { cancelled = true; clearInterval(id); };
  }, [symbol, apiBase]);
  if (!price) return null;
  return (
    <div style={{ background: '#1f2937', borderRadius: '6px', padding: '8px 12px', fontSize: '13px' }}>
      <span style={{ color: '#6b7280', marginRight: '8px' }}>{symbol}</span>
      <span style={{ color: '#34d399' }}>{price.bid?.toFixed(5)}</span>
      <span style={{ color: '#6b7280', margin: '0 4px' }}>/</span>
      <span style={{ color: '#f87171' }}>{price.ask?.toFixed(5)}</span>
    </div>
  );
}

function HealthPill({ health, mt5Status }) {
  const serverStatus = health?.status || 'loading';
  const portfolioStatus = health?.portfolio?.status || 'loading';
  const mt5 = health?.mt5?.status || mt5Status || 'unknown';
  const isHealthy = serverStatus === 'ok' && portfolioStatus === 'ok' && mt5 === 'online';
  return (
    <div className={`health-strip ${isHealthy ? 'ok' : 'degraded'}`}>
      <span className="health-dot" />
      <span>API {serverStatus}</span>
      <span>Portfolio {portfolioStatus}</span>
      <span>MT5 {mt5}</span>
      {health?.mt5?.cachedAt && (
        <span className="health-muted">
          cache {new Date(health.mt5.cachedAt).toLocaleTimeString('th-TH', { timeZone: 'Asia/Bangkok' })}
        </span>
      )}
    </div>
  );
}

export default function App() {
  const [activeTab, setActiveTab] = useState('overview');
  const [portfolio, setPortfolio] = useState(null);
  const [settings, setSettings] = useState(null);
  const [aiRecommend, setAiRecommend] = useState(null);
  
  // Simulated Ticker & Flashing State
  const [prevPrices, setPrevPrices] = useState({});
  const [priceFlash, setPriceFlash] = useState({}); // { id: 'up' | 'down' }

  // Transaction Form State
  const [txType, setTxType] = useState('funds'); // funds | crypto | forex
  const [txAssetId, setTxAssetId] = useState('');
  const [txAction, setTxAction] = useState('buy');
  const [txUnits, setTxUnits] = useState('');
  const [txPrice, setTxPrice] = useState('');
  const [txSuccess, setTxSuccess] = useState(false);
  const [txError, setTxError] = useState('');

  // AI Rebalancing State
  const [rebalancingProgress, setRebalancingProgress] = useState(false);

  // AI Chat State
  const [chatMessages, setChatMessages] = useState([
    { sender: 'ai', text: '🤖 สวัสดีครับ! ผมคือ **AI Wealth Advisor** ยินดีต้อนรับสู่ระบบริหารความมั่งคั่งส่วนตัวครับ วันนี้อยากให้ผมช่วยวิเคราะห์พอร์ตการลงทุน จัดสัดส่วนสินทรัพย์ หรือเปิดระบบแจ้งเตือน Telegram ดีครับ?' }
  ]);
  const [chatInput, setChatInput] = useState('');
  const [aiTyping, setAiTyping] = useState(false);
  const chatBottomRef = useRef(null);

  // Telegram Settings State
  const [botToken, setBotToken] = useState('');
  const [chatId, setChatId] = useState('');
  const [lineChannelAccessToken, setLineChannelAccessToken] = useState('');
  const [lineTargetId, setLineTargetId] = useState('');
  const [lineNotifyToken, setLineNotifyToken] = useState('');
  const [teleStatus, setTeleStatus] = useState({ loading: false, msg: '', type: '' }); // type: success | error

  // Trading Control Plane State
  const [tradingOverview, setTradingOverview] = useState(null);
  const [tradingRecommendations, setTradingRecommendations] = useState([]);
  const [tradingReportStatus, setTradingReportStatus] = useState({ loading: false, msg: '', type: '' });
  const [closeConfirmTicket, setCloseConfirmTicket] = useState(null);
  const [aiAnalystReport, setAiAnalystReport] = useState(null);
  const [aiAnalystStatus, setAiAnalystStatus] = useState({ loading: false, msg: '', type: '' });

  // LLM Settings State
  const [llmProvider, setLlmProvider] = useState('Gemini');
  const [llmApiKey, setLlmApiKey] = useState('');
  const [llmModel, setLlmModel] = useState('gemini-1.5-flash');
  const [llmEndpoint, setLlmEndpoint] = useState('');
  const [llmVerifyStatus, setLlmVerifyStatus] = useState({ loading: false, msg: '', type: '' }); // success | error
  const [fetchedModels, setFetchedModels] = useState([]);
  const [fetchingModels, setFetchingModels] = useState(false);

  // MCP Settings State
  const [mcpEnabled, setMcpEnabled] = useState(false);
  const [mcpServerUrl, setMcpServerUrl] = useState('');
  const [mcpConnectors, setMcpConnectors] = useState({ yahoo: true, binance: false, forex: true });

  // New Alert State
  const [newAlertAssetId, setNewAlertAssetId] = useState('BTC');
  const [newAlertCondition, setNewAlertCondition] = useState('above');
  const [newAlertValue, setNewAlertValue] = useState('');

  // MT5 State
  const [mt5Account, setMt5Account] = useState(null);
  const [mt5Positions, setMt5Positions] = useState([]);
  const [mt5Status, setMt5Status] = useState('unknown'); // 'online' | 'offline' | 'unknown'
  const [mt5CachedAt, setMt5CachedAt] = useState(null);
  const [health, setHealth] = useState(null);

  // 1. Fetch initial configuration & data
  useEffect(() => {
    fetchPortfolio();
    fetchSettings();
    fetchAIRecommendations();

    // 3-second interval to fetch live simulation ticks
    const interval = setInterval(() => {
      fetchPortfolio(true);
    }, 3000);

    return () => clearInterval(interval);
  }, []);

  // Sync transactional asset selector
  useEffect(() => {
    if (portfolio) {
      const firstAsset = portfolio.categories[txType]?.items[0]?.id || '';
      setTxAssetId(firstAsset);
      // Auto-populate price
      const price = portfolio.categories[txType]?.items.find(i => i.id === firstAsset)?.currentPrice || '';
      setTxPrice(price);
    }
  }, [txType]);

  useEffect(() => {
    if (chatBottomRef.current) {
      chatBottomRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [chatMessages, aiTyping]);

  useEffect(() => {
    let cancelled = false;
    const pollMT5 = async () => {
      try {
        const [acctRes, posRes] = await Promise.all([
          fetch(`${API_BASE}/api/mt5/account`),
          fetch(`${API_BASE}/api/mt5/positions`)
        ]);
        if (cancelled) return;
        const acct = await acctRes.json();
        const pos = await posRes.json();
        if (cancelled) return;
        setMt5Account(acct);
        setMt5Positions(pos.positions ?? []);
        setMt5Status(acct.mt5_status ?? 'offline');
        setMt5CachedAt(acct.cached_at);
      } catch {
        if (!cancelled) setMt5Status('offline');
      }
    };
    pollMT5();
    const id = setInterval(pollMT5, 5000);
    return () => { cancelled = true; clearInterval(id); };
  }, []);

  useEffect(() => {
    let cancelled = false;
    const pollHealth = async () => {
      try {
        const res = await fetch(`${API_BASE}/api/health`);
        const data = await res.json();
        if (!cancelled) setHealth(data);
      } catch {
        if (!cancelled) setHealth({ status: 'down', portfolio: { status: 'unknown' }, mt5: { status: 'unknown' } });
      }
    };
    pollHealth();
    const id = setInterval(pollHealth, 10000);
    return () => { cancelled = true; clearInterval(id); };
  }, []);

  useEffect(() => {
    let cancelled = false;
    const pollTradingControl = async () => {
      try {
        const [overviewRes, recRes] = await Promise.all([
          fetch(`${API_BASE}/api/trading/overview`),
          fetch(`${API_BASE}/api/trading/recommendations`),
          fetch(`${API_BASE}/api/trading/ai/latest`)
        ]);
        const overviewData = await overviewRes.json();
        const recData = await recRes.json();
        const aiData = await aiRes.json();
        if (!cancelled) {
          if (overviewRes.ok) setTradingOverview(overviewData);
          if (recRes.ok) setTradingRecommendations(recData.items || []);
          if (aiRes.ok) setAiAnalystReport(aiData.report?.payload || aiData.report || null);
        }
      } catch (err) {
        if (!cancelled) {
          setTradingReportStatus({ loading: false, msg: `Trading Control offline: ${err.message}`, type: 'error' });
        }
      }
    };
    pollTradingControl();
    const id = setInterval(pollTradingControl, 10000);
    return () => { cancelled = true; clearInterval(id); };
  }, []);

  const fetchTradingControl = async () => {
    try {
      const [overviewRes, recRes] = await Promise.all([
        fetch(`${API_BASE}/api/trading/overview`),
        fetch(`${API_BASE}/api/trading/recommendations`),
        fetch(`${API_BASE}/api/trading/ai/latest`)
      ]);
      const overviewData = await overviewRes.json();
      const recData = await recRes.json();
      const aiData = await aiRes.json();
      if (overviewRes.ok) setTradingOverview(overviewData);
      if (recRes.ok) setTradingRecommendations(recData.items || []);
      if (aiRes.ok) setAiAnalystReport(aiData.report?.payload || aiData.report || null);
    } catch (err) {
      setTradingReportStatus({ loading: false, msg: `Refresh failed: ${err.message}`, type: 'error' });
    }
  };

  const sendTradingReport = async () => {
    setTradingReportStatus({ loading: true, msg: 'Sending hedge fund report...', type: '' });
    try {
      const res = await fetch(`${API_BASE}/api/trading/report`, { method: 'POST' });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Report failed');
      setTradingOverview(data.overview);
      setTradingReportStatus({
        loading: false,
        msg: `Report sent: Telegram ${data.telegram ? 'ok' : 'not configured'}, LINE ${data.line ? 'ok' : 'not configured'}`,
        type: 'success'
      });
      setTimeout(() => setTradingReportStatus({ loading: false, msg: '', type: '' }), 5000);
    } catch (err) {
      setTradingReportStatus({ loading: false, msg: err.message, type: 'error' });
    }
  };

  const sendTradingControl = async (engineId, action, extraPayload = {}) => {
    setTradingReportStatus({ loading: true, msg: `${action} ${engineId}...`, type: '' });
    try {
      const res = await fetch(`${API_BASE}/api/trading/control`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          engineId,
          action,
          reason: 'dashboard control',
          payload: { reason: 'dashboard control', ...extraPayload }
        })
      });
      const data = await res.json();
      if (!res.ok || !data.success) throw new Error(data.result?.error || data.error || 'Control command failed');
      setTradingReportStatus({ loading: false, msg: `${engineId} ${action} command accepted`, type: 'success' });
      setCloseConfirmTicket(null);
      await fetchTradingControl();
      setTimeout(() => setTradingReportStatus({ loading: false, msg: '', type: '' }), 5000);
    } catch (err) {
      setTradingReportStatus({ loading: false, msg: err.message, type: 'error' });
    }
  };

  const runAiAnalyst = async () => {
    setAiAnalystStatus({ loading: true, msg: 'Analyzing trading systems...', type: '' });
    try {
      const res = await fetch(`${API_BASE}/api/trading/ai/analyze`, { method: 'POST' });
      const data = await res.json();
      if (!res.ok || !data.success) throw new Error(data.error || 'AI analysis failed');
      setAiAnalystReport(data.report);
      setAiAnalystStatus({ loading: false, msg: `AI Analyst completed via ${data.report.source}`, type: 'success' });
      setTimeout(() => setAiAnalystStatus({ loading: false, msg: '', type: '' }), 5000);
    } catch (err) {
      setAiAnalystStatus({ loading: false, msg: err.message, type: 'error' });
    }
  };

  const applyAiSafeActions = async () => {
    setAiAnalystStatus({ loading: true, msg: 'Applying safe AI actions...', type: '' });
    try {
      const res = await fetch(`${API_BASE}/api/trading/ai/apply`, { method: 'POST' });
      const data = await res.json();
      if (!res.ok || !data.success) throw new Error(data.error || 'AI apply failed');
      setAiAnalystStatus({ loading: false, msg: `Applied ${data.applied?.length || 0} safe actions`, type: 'success' });
      await fetchTradingControl();
      setTimeout(() => setAiAnalystStatus({ loading: false, msg: '', type: '' }), 5000);
    } catch (err) {
      setAiAnalystStatus({ loading: false, msg: err.message, type: 'error' });
    }
  };

  const sendAiAnalystReport = async () => {
    setAiAnalystStatus({ loading: true, msg: 'Sending AI analyst report...', type: '' });
    try {
      const res = await fetch(`${API_BASE}/api/trading/ai/send-report`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ forceAnalyze: false })
      });
      const data = await res.json();
      if (!res.ok || !data.success) throw new Error(data.error || 'Send report failed');
      setAiAnalystReport(data.report);
      setAiAnalystStatus({
        loading: false,
        msg: `AI report sent: Telegram ${data.telegram ? 'ok' : 'not configured'}, LINE ${data.line ? 'ok' : 'not configured'}`,
        type: 'success'
      });
      setTimeout(() => setAiAnalystStatus({ loading: false, msg: '', type: '' }), 5000);
    } catch (err) {
      setAiAnalystStatus({ loading: false, msg: err.message, type: 'error' });
    }
  };

  const fetchPortfolio = async (isPoll = false) => {
    try {
      const res = await fetch(`${API_BASE}/api/portfolio`);
      const data = await res.json();
      
      if (isPoll && portfolio) {
        // Compute price fluctuations for flashing UI
        const flashes = {};
        const currentPrices = {};

        // Helper to map prices
        const processList = (items) => {
          items.forEach(item => {
            currentPrices[item.id] = item.currentPrice;
            const prev = prevPrices[item.id];
            if (prev !== undefined) {
              if (item.currentPrice > prev) flashes[item.id] = 'up';
              else if (item.currentPrice < prev) flashes[item.id] = 'down';
            }
          });
        };

        processList(data.categories.funds.items);
        processList(data.categories.crypto.items);
        processList(data.categories.forex.items);

        setPriceFlash(flashes);
        setPrevPrices(currentPrices);

        // Clear flashes after 1 second
        setTimeout(() => {
          setPriceFlash({});
        }, 1200);
      } else {
        // Initial setup
        const initialPrices = {};
        const processInit = (items) => {
          items.forEach(item => { initialPrices[item.id] = item.currentPrice; });
        };
        processInit(data.categories.funds.items);
        processInit(data.categories.crypto.items);
        processInit(data.categories.forex.items);
        setPrevPrices(initialPrices);
      }

      setPortfolio(data);
    } catch (err) {
      console.error("Error fetching portfolio:", err);
    }
  };

  const fetchSettings = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/settings`);
      const data = await res.json();
      setSettings(data);
      setBotToken(data.telegramBotToken);
      setChatId(data.telegramChatId);
      setLineChannelAccessToken(data.lineChannelAccessToken || '');
      setLineTargetId(data.lineTargetId || '');
      setLineNotifyToken(data.lineNotifyToken || '');
      if (data.llmConfig) {
        setLlmProvider(data.llmConfig.provider || 'Gemini');
        setLlmApiKey(data.llmConfig.apiKey || '');
        setLlmModel(data.llmConfig.model || 'gemini-1.5-flash');
        setLlmEndpoint(data.llmConfig.endpoint || '');
      }
      if (data.mcpConfig) {
        setMcpEnabled(data.mcpConfig.enabled || false);
        setMcpServerUrl(data.mcpConfig.serverUrl || '');
        setMcpConnectors(data.mcpConfig.connectors || { yahoo: true, binance: false, forex: true });
      }
    } catch (err) {
      console.error("Error fetching settings:", err);
    }
  };

  const fetchAIRecommendations = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/ai/recommend`);
      const data = await res.json();
      setAiRecommend(data);
    } catch (err) {
      console.error("Error fetching AI recommendations:", err);
    }
  };

  // 2. Handle transaction submissions
  const handleTransactionSubmit = async (e) => {
    e.preventDefault();
    setTxSuccess(false);
    setTxError('');

    if (txType === 'forex') {
      if (mt5Status === 'offline') {
        setTxError('MT5 is offline — cannot place order');
        return;
      }
      if (!txAssetId || !txUnits || parseFloat(txUnits) <= 0) {
        setTxError('Symbol and valid volume required');
        return;
      }
      try {
        const res = await fetch(`${API_BASE}/api/mt5/order`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            symbol: txAssetId,
            action: txAction === 'buy' ? 'buy' : 'sell',
            volume: parseFloat(txUnits),
          })
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'Order failed');
        setTxSuccess(true);
        setTxError('');
        setTxUnits('');
        setTimeout(() => setTxSuccess(false), 5000);
      } catch (err) {
        setTxError(err.message);
      }
      return;
    }

    if (!txUnits || parseFloat(txUnits) <= 0 || !txPrice || parseFloat(txPrice) <= 0) {
      setTxError('กรุณากรอกจำนวนหน่วยและราคาให้ถูกต้อง');
      return;
    }

    try {
      const res = await fetch(`${API_BASE}/api/portfolio/transaction`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          type: txType,
          assetId: txAssetId,
          action: txAction,
          units: parseFloat(txUnits),
          price: parseFloat(txPrice)
        })
      });

      const result = await res.json();
      if (!res.ok) {
        setTxError(result.error || 'เกิดข้อผิดพลาดในการทำรายการ');
      } else {
        setTxSuccess(true);
        setTxUnits('');
        fetchPortfolio();
        fetchAIRecommendations();
        setTimeout(() => setTxSuccess(false), 5000);
      }
    } catch (err) {
      setTxError('ไม่สามารถเชื่อมต่อเซิร์ฟเวอร์ได้');
    }
  };

  // 3. Handle saving telegram settings
  const handleSaveTelegram = async () => {
    setTeleStatus({ loading: true, msg: '', type: '' });
    try {
      const res = await fetch(`${API_BASE}/api/settings`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          telegramBotToken: botToken,
          telegramChatId: chatId,
          lineChannelAccessToken,
          lineTargetId,
          lineNotifyToken
        })
      });
      const data = await res.json();
      setSettings(data.settings);
      setTeleStatus({ loading: false, msg: 'บันทึกการตั้งค่าสำเร็จ!', type: 'success' });
      setTimeout(() => setTeleStatus({ loading: false, msg: '', type: '' }), 4000);
    } catch (err) {
      setTeleStatus({ loading: false, msg: 'ไม่สามารถบันทึกข้อมูลได้', type: 'error' });
    }
  };

  // 4. Handle connection testing
  const handleTestTelegram = async () => {
    if (!botToken || !chatId) {
      setTeleStatus({ loading: false, msg: 'กรุณากรอก Bot Token และ Chat ID ก่อนทดสอบ', type: 'error' });
      return;
    }

    setTeleStatus({ loading: true, msg: 'กำลังส่งข้อความทดสอบไปยัง Telegram...', type: '' });
    try {
      const res = await fetch(`${API_BASE}/api/telegram/test`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          telegramBotToken: botToken,
          telegramChatId: chatId
        })
      });

      const data = await res.json();
      if (res.ok) {
        setTeleStatus({ loading: false, msg: 'ส่งสัญญาณแจ้งเตือนสำเร็จ! กรุณาเช็คห้องแชท Telegram ของคุณ', type: 'success' });
      } else {
        setTeleStatus({ loading: false, msg: data.error || 'การเชื่อมต่อล้มเหลว กรุณาเช็คความถูกต้องของ Token', type: 'error' });
      }
    } catch (err) {
      setTeleStatus({ loading: false, msg: 'ล้มเหลวในการเชื่อมต่อ Telegram API', type: 'error' });
    }
  };

  // Handle LLM Config saving
  const handleSaveLLM = async () => {
    setLlmVerifyStatus({ loading: true, msg: 'กำลังบันทึกการตั้งค่า LLM...', type: '' });
    try {
      const res = await fetch(`${API_BASE}/api/settings`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          llmConfig: {
            provider: llmProvider,
            apiKey: llmApiKey,
            model: llmModel,
            endpoint: llmEndpoint
          }
        })
      });
      const data = await res.json();
      if (res.ok) {
        setSettings(data.settings);
        setLlmVerifyStatus({ loading: false, msg: 'บันทึกการตั้งค่าสมองกล AI สำเร็จ!', type: 'success' });
        setTimeout(() => setLlmVerifyStatus({ loading: false, msg: '', type: '' }), 4000);
      } else {
        setLlmVerifyStatus({ loading: false, msg: data.error || 'บันทึกล้มเหลว', type: 'error' });
      }
    } catch (err) {
      setLlmVerifyStatus({ loading: false, msg: 'การเชื่อมต่อขัดข้อง: ' + err.message, type: 'error' });
    }
  };

  // Handle LLM Verification
  const handleVerifyLLM = async () => {
    setLlmVerifyStatus({ loading: true, msg: `กำลังส่งคำขอทดสอบไปที่ ${llmProvider}...`, type: '' });
    try {
      const res = await fetch(`${API_BASE}/api/ai/verify`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          provider: llmProvider,
          apiKey: llmApiKey,
          model: llmModel,
          endpoint: llmEndpoint
        })
      });
      const data = await res.json();
      if (res.ok) {
        setLlmVerifyStatus({ loading: false, msg: `เชื่อมต่อสำเร็จ! ${data.message}`, type: 'success' });
      } else {
        setLlmVerifyStatus({ loading: false, msg: `เชื่อมต่อล้มเหลว: ${data.error}`, type: 'error' });
      }
    } catch (err) {
      setLlmVerifyStatus({ loading: false, msg: `เชื่อมต่อขัดข้อง: ${err.message}`, type: 'error' });
    }
  };

  // Handle Dynamic Model Discovery from Custom proxy or Ollama
  const handleFetchModels = async () => {
    if (!llmEndpoint) {
      setLlmVerifyStatus({ loading: false, msg: 'กรุณากรอก Base URL ก่อนดึงข้อมูลรุ่น', type: 'error' });
      return;
    }
    setFetchingModels(true);
    setLlmVerifyStatus({ loading: true, msg: 'กำลังเรียกข้อมูลรุ่นจากเซิร์ฟเวอร์...', type: '' });
    try {
      const res = await fetch(`${API_BASE}/api/ai/models`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          provider: llmProvider,
          endpoint: llmEndpoint,
          apiKey: llmApiKey
        })
      });
      const data = await res.json();
      if (res.ok && data.success && Array.isArray(data.models)) {
        setFetchedModels(data.models);
        if (data.models.length > 0) {
          setLlmModel(data.models[0]);
          setLlmVerifyStatus({ loading: false, msg: `ดึงข้อมูลสำเร็จ! พบทั้งหมด ${data.models.length} รุ่น`, type: 'success' });
        } else {
          setLlmVerifyStatus({ loading: false, msg: 'เชื่อมต่อสำเร็จแต่ไม่พบโมเดลใดๆ เปิดใช้งานอยู่', type: 'error' });
        }
      } else {
        setLlmVerifyStatus({ loading: false, msg: data.error || 'ดึงข้อมูลรุ่นล้มเหลว ตรวจสอบความถูกต้องของ URL/Key', type: 'error' });
      }
    } catch (err) {
      setLlmVerifyStatus({ loading: false, msg: 'ดึงข้อมูลรุ่นขัดข้อง: ' + err.message, type: 'error' });
    } finally {
      setFetchingModels(false);
    }
  };

  // Handle MCP saving
  const handleSaveMCP = async (updatedEnabled = mcpEnabled, updatedUrl = mcpServerUrl, updatedConns = mcpConnectors) => {
    try {
      const res = await fetch(`${API_BASE}/api/settings`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          mcpConfig: {
            enabled: updatedEnabled,
            serverUrl: updatedUrl,
            connectors: updatedConns
          }
        })
      });
      const data = await res.json();
      if (res.ok) {
        setSettings(data.settings);
      }
    } catch (err) {
      console.error("Error saving MCP configuration:", err);
    }
  };

  // 5. Handle AI chatbot submission
  const handleSendMessage = async (e) => {
    e.preventDefault();
    if (!chatInput.trim()) return;

    const userText = chatInput;
    setChatMessages(prev => [...prev, { sender: 'user', text: userText }]);
    setChatInput('');
    setAiTyping(true);

    try {
      const res = await fetch(`${API_BASE}/api/ai/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: userText })
      });
      const data = await res.json();
      setChatMessages(prev => [...prev, { sender: 'ai', text: data.reply }]);
    } catch (err) {
      setChatMessages(prev => [...prev, { sender: 'ai', text: '❌ ไม่สามารถเชื่อมต่อกับ AI Advisor ได้ในขณะนี้ ขออภัยในความไม่สะดวกครับ' }]);
    } finally {
      setAiTyping(false);
    }
  };

  // 6. Handle risk profile sliders & automatic Rebalancing trigger
  const handleRiskChange = async (profile) => {
    try {
      const res = await fetch(`${API_BASE}/api/settings`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ riskProfile: profile })
      });
      const data = await res.json();
      setSettings(data.settings);
      fetchAIRecommendations();
    } catch (err) {
      console.error("Error setting risk profile:", err);
    }
  };

  // AI Smart Rebalancer Action
  const triggerSmartRebalance = async () => {
    if (!aiRecommend) return;
    setRebalancingProgress(true);

    try {
      // Simulate smart execution by adjusting assets to meet the target
      for (const rec of aiRecommend.recommendations) {
        if (rec.action === 'HOLD') continue;
        
        // Find an asset in this category to buy/sell
        const categoryAssets = portfolio.categories[rec.category].items;
        if (categoryAssets.length === 0) continue;
        
        const targetAsset = categoryAssets[0]; // Trade first asset in category
        const price = targetAsset.currentPrice;
        const targetAction = rec.action === 'BUY_MORE' ? 'buy' : 'sell';
        
        // Absolute weight adjust unit volume
        const adjustUnits = Math.abs(rec.amount / price);

        if (adjustUnits > 0) {
          await fetch(`${API_BASE}/api/portfolio/transaction`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              type: rec.category,
              assetId: targetAsset.id,
              action: targetAction,
              units: parseFloat(adjustUnits.toFixed(4)),
              price: parseFloat(price.toFixed(4))
            })
          });
        }
      }

      await fetchPortfolio();
      await fetchAIRecommendations();
      
      // Update chat
      setChatMessages(prev => [...prev, {
        sender: 'ai',
        text: '⚙️ *ดำเนินการปรับปรุงพอร์ตอัตโนมัติ (AI Rebalanced) สำเร็จ!* ปัจจุบันสัดส่วนพอร์ตการลงทุนรวมของคุณได้รับการจัดสรรสอดคล้องตามระดับความเสี่ยงเป้าหมายที่คุณเลือกเรียบร้อยแล้ว บันทึกข้อมูลและแจ้งเตือนเข้าแอปพลิเคชัน Telegram แล้วครับ 🚀'
      }]);
    } catch (err) {
      console.error("Rebalancing failure", err);
    } finally {
      setRebalancingProgress(false);
    }
  };

  // 7. Add Alert trigger configuration
  const handleAddAlert = async (e) => {
    e.preventDefault();
    if (!newAlertValue || parseFloat(newAlertValue) <= 0) return;

    const newAlert = {
      id: `alert-${Date.now()}`,
      assetId: newAlertAssetId,
      condition: newAlertCondition,
      value: parseFloat(newAlertValue),
      active: true
    };

    const updatedAlerts = [...(settings.alerts || []), newAlert];
    
    try {
      const res = await fetch(`${API_BASE}/api/settings`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ alerts: updatedAlerts })
      });
      const data = await res.json();
      setSettings(data.settings);
      setNewAlertValue('');
    } catch (err) {
      console.error("Failed to add alert", err);
    }
  };

  // Remove alert
  const handleRemoveAlert = async (alertId) => {
    const updatedAlerts = settings.alerts.filter(a => a.id !== alertId);
    try {
      const res = await fetch(`${API_BASE}/api/settings`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ alerts: updatedAlerts })
      });
      const data = await res.json();
      setSettings(data.settings);
    } catch (err) {
      console.error("Failed to delete alert", err);
    }
  };

  if (!portfolio || !settings) {
    return (
      <div style={{ display: 'flex', height: '100vh', justifyContent: 'center', alignItems: 'center', backgroundColor: '#07090e', flexDirection: 'column', gap: '1rem' }}>
        <RefreshCw style={{ animation: 'spin 1.5s linear infinite', color: '#8b5cf6' }} size={40} />
        <p style={{ color: '#94a3b8', fontFamily: 'Outfit', fontWeight: 300, fontSize: '1.2rem', letterSpacing: '0.05em' }}>CONNECTING AI WEALTH ENGINE...</p>
        <style>{`@keyframes spin { 100% { transform: rotate(360deg); } }`}</style>
      </div>
    );
  }

  // Format currencies helper
  const fmt = (val) => new Intl.NumberFormat('th-TH', { style: 'currency', currency: 'THB', minimumFractionDigits: 2 }).format(val);
  const fmtUsd = (val) => new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', minimumFractionDigits: 2 }).format(val);

  // SVG Allocation Pie Chart calculation
  const totalValue = portfolio.netWorth;
  const fundsVal = portfolio.categories.funds.value;
  const cryptoVal = portfolio.categories.crypto.value;
  const forexVal = portfolio.categories.forex.value;

  const fundsPct = totalValue > 0 ? (fundsVal / totalValue) * 100 : 0;
  const cryptoPct = totalValue > 0 ? (cryptoVal / totalValue) * 100 : 0;
  const forexPct = totalValue > 0 ? (forexVal / totalValue) * 100 : 0;

  // Render markdown helper for AI chatbot answers
  const renderBotText = (text) => {
    return text.split('\n').map((line, i) => {
      let content = line;
      // Bold rendering **text**
      content = content.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
      // Bullet list replacement
      if (line.trim().startsWith('•')) {
        return <div key={i} style={{ paddingLeft: '1rem', margin: '0.25rem 0' }} dangerouslySetInnerHTML={{ __html: content }} />;
      }
      return <p key={i} style={{ margin: '0.4rem 0', minHeight: '1rem' }} dangerouslySetInnerHTML={{ __html: content }} />;
    });
  };

  return (
    <div className="app-container">
      {mt5Status === 'offline' && (
        <div style={{
          background: '#7f1d1d', color: '#fca5a5',
          padding: '8px 16px', textAlign: 'center', fontSize: '13px',
          display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px'
        }}>
          <AlertCircle size={14} />
          MT5 Offline — showing stale data
          {mt5CachedAt && ` (last updated: ${new Date(mt5CachedAt).toLocaleTimeString()})`}
        </div>
      )}

      {/* SIDEBAR NAVIGATION */}
      <aside className="sidebar">
        <div className="sidebar-logo">
          <img src="/fox_logo.jpg" alt="Fox" className="sidebar-fox-icon" />
          <div className="sidebar-logo-text">
            <div className="sidebar-logo-main">
              <span className="sidebar-logo-ai">Ai</span>
              <span className="sidebar-logo-trade"> เทรด </span>
              <span className="sidebar-logo-deo">..เด้อ</span>
            </div>
            <div className="sidebar-logo-sub">Wealth Hub</div>
          </div>
        </div>

        <nav style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', flexGrow: 1 }}>
          {[
            { id: 'overview', label: 'ภาพรวมพอร์ต', icon: Activity },
            { id: 'funds', label: 'กองทุนรวม (Funds)', icon: LineChart },
            { id: 'crypto', label: 'คริปโตเคอเรนซี', icon: Coins },
            { id: 'forex', label: 'ตลาด Forex', icon: DollarSign },
            { id: 'mt5', label: 'MT5 Positions', icon: Activity },
            { id: 'trading-control', label: 'Trading Control', icon: ShieldCheck },
            { id: 'ai-advisor', label: 'AI Optimizer', icon: Cpu },
            { id: 'settings', label: 'ตั้งค่า & แจ้งเตือน', icon: Settings },
          ].map(tab => {
            const Icon = tab.icon;
            const active = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '1rem',
                  width: '100%',
                  padding: '0.9rem 1.2rem',
                  background: active ? 'rgba(240, 185, 11, 0.08)' : 'transparent',
                  border: 'none',
                  borderLeft: active ? '3px solid var(--accent-purple)' : '3px solid transparent',
                  color: active ? '#ffffff' : 'var(--text-secondary)',
                  borderRadius: '0 10px 10px 0',
                  cursor: 'pointer',
                  fontSize: '0.925rem',
                  fontWeight: active ? 600 : 400,
                  transition: 'all 0.2s ease',
                  textAlign: 'left'
                }}
              >
                <Icon size={18} style={{ color: active ? 'var(--accent-purple)' : 'var(--text-muted)' }} />
                {tab.label}
              </button>
            );
          })}
        </nav>

        {/* Telegram mini indicator */}
        <div className="glass-panel" style={{ padding: '1rem', borderRadius: '12px', background: 'rgba(255, 255, 255, 0.02)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.4rem' }}>
            <Bell size={14} style={{ color: settings.telegramBotToken ? 'var(--accent-emerald)' : 'var(--accent-rose)' }} />
            <span style={{ fontSize: '0.75rem', fontWeight: 600, color: '#f8fafc' }}>Telegram Notification</span>
          </div>
          <span style={{ fontSize: '0.7rem', color: 'var(--text-secondary)' }}>
            สถานะ: {settings.telegramBotToken ? <span style={{ color: 'var(--accent-emerald)', fontWeight: 600 }}>เปิดใช้งาน</span> : <span style={{ color: 'var(--accent-rose)' }}>ปิดใช้งาน</span>}
          </span>
        </div>
      </aside>

      {/* MAIN LAYOUT */}
      <main className="main-content">
        
        {/* OVERVIEW TAB */}
        {activeTab === 'overview' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '2rem' }}>
            {/* Header section */}
            <header style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div>
                <h1 style={{ fontSize: '2.2rem', fontWeight: 800, fontFamily: 'var(--font-display)' }}>ภาพรวมความมั่งคั่งส่วนตัว</h1>
                <p style={{ color: 'var(--text-secondary)', fontSize: '0.95rem', marginTop: '0.2rem' }}>อัปเดตราคาแบบจำลอง Real-Time วิเคราะห์สัดส่วนและความผันผวนด้วยเทคโนโลยี AI</p>
              </div>
              <div className="glass-panel" style={{ padding: '0.5rem 1rem', display: 'flex', alignItems: 'center', gap: '0.5rem', background: 'rgba(16, 185, 129, 0.08)', borderColor: 'rgba(16, 185, 129, 0.2)' }}>
                <div style={{ width: '8px', height: '8px', borderRadius: '50%', backgroundColor: 'var(--accent-emerald)', boxShadow: '0 0 10px #10b981', animation: 'pulseGlow 2s infinite' }} />
                <span style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--accent-emerald)', letterSpacing: '0.05em' }}>LIVE FEEDS</span>
              </div>
              <HealthPill health={health} mt5Status={mt5Status} />
            </header>

            {/* Total Net Worth Glow Card */}
            <section className="glass-panel glow-purple" style={{ padding: '2.5rem', borderRadius: '20px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: 'radial-gradient(circle at 10% 20%, rgba(240, 185, 11, 0.06) 0%, rgba(18, 18, 30, 0.35) 100%)' }}>
              <div>
                <span style={{ color: 'var(--text-secondary)', textTransform: 'uppercase', fontSize: '0.75rem', fontWeight: 600, letterSpacing: '0.15em' }}>มูลค่าพอร์ตทรัพย์สินสุทธิ (Net Worth)</span>
                <h1 style={{ fontSize: '3.5rem', fontWeight: 800, fontFamily: 'var(--font-display)', margin: '0.5rem 0 0.8rem 0', letterSpacing: '-0.02em', background: 'linear-gradient(to right, #f0f0f5 30%, #f0b90b)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>
                  {fmt(totalValue)}
                </h1>
                <div style={{ display: 'flex', alignItems: 'center', gap: '1.25rem' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.3rem', color: portfolio.totalProfitLoss >= 0 ? 'var(--accent-emerald)' : 'var(--accent-rose)' }}>
                    {portfolio.totalProfitLoss >= 0 ? <ArrowUpRight size={18} /> : <ArrowDownRight size={18} />}
                    <span style={{ fontWeight: 600, fontSize: '1.1rem' }}>
                      {portfolio.totalProfitLoss >= 0 ? '+' : ''}{fmt(portfolio.totalProfitLoss)} ({portfolio.totalProfitLossPct}%)
                    </span>
                  </div>
                  <span style={{ color: 'var(--text-muted)', fontSize: '0.9rem' }}>ต้นทุนรวม: {fmt(portfolio.totalCost)}</span>
                </div>
              </div>

              {/* Quick AI Mini Alert box inside Net Worth Banner */}
              <div className="glass-panel" style={{ padding: '1.2rem', maxWidth: '380px', background: 'rgba(139, 92, 246, 0.05)', borderColor: 'rgba(139, 92, 246, 0.15)' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.5rem' }}>
                  <Cpu size={16} style={{ color: 'var(--accent-purple)' }} />
                  <span style={{ fontSize: '0.8rem', fontWeight: 600, color: '#f8fafc', textTransform: 'uppercase' }}>คำแนะนำเร่งด่วนจาก AI</span>
                </div>
                <p style={{ fontSize: '0.825rem', color: 'var(--text-secondary)', lineHeight: 1.4 }}>
                  สัดส่วนความเสี่ยงปัจจุบัน: <strong style={{ color: 'white' }}>{settings.riskProfile}</strong>. {aiRecommend ? aiRecommend.aiInsights : 'กำลังประมวลผลดัชนี...'}
                </p>
              </div>
            </section>

            {/* Asset Allocation Grid */}
            <section style={{ display: 'grid', gridTemplateColumns: '1.5fr 1fr', gap: '2rem' }}>
              
              {/* Asset Class Cards */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
                <h3 style={{ fontSize: '1.3rem', fontWeight: 600, fontFamily: 'var(--font-display)' }}>สรุปสัดส่วนตามประเภททรัพย์สิน</h3>
                
                {[
                  { id: 'funds', label: 'กองทุนรวม (Funds)', val: fundsVal, pct: fundsPct, color: '#8b5cf6', textGlow: 'text-gradient-purple', desc: 'กองทุน SCBUSA, B-CARE, K-SET50 สหรัฐฯและหุ้นไทย' },
                  { id: 'crypto', label: 'คริปโตเคอเรนซี (Crypto)', val: cryptoVal, pct: cryptoPct, color: '#06b6d4', textGlow: 'text-gradient-cyan', desc: 'บิตคอยน์ อีเธอเรียม โซลานา สำหรับตลาดผลตอบแทนเชิงรุก' },
                  { id: 'forex', label: 'ฟอเร็กซ์ (Forex)', val: forexVal, pct: forexPct, color: '#f59e0b', textGlow: 'text-gradient-gold', desc: 'การถือครองคู่เงินสากลหลัก EUR/USD, USD/JPY, GBP/USD' },
                ].map(assetClass => (
                  <div 
                    key={assetClass.id} 
                    className="glass-panel" 
                    onClick={() => setActiveTab(assetClass.id)}
                    style={{ padding: '1.25rem 1.5rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center', cursor: 'pointer' }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                      <div style={{ width: '12px', height: '12px', borderRadius: '3px', backgroundColor: assetClass.color, boxShadow: `0 0 10px ${assetClass.color}` }} />
                      <div>
                        <h4 className={assetClass.textGlow} style={{ fontSize: '1.1rem', fontWeight: 700 }}>{assetClass.label}</h4>
                        <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginTop: '0.1rem' }}>{assetClass.desc}</p>
                      </div>
                    </div>
                    <div style={{ textAlign: 'right' }}>
                      <span style={{ fontSize: '1.2rem', fontWeight: 700, fontFamily: 'var(--font-display)' }}>{fmt(assetClass.val)}</span>
                      <div style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-secondary)', marginTop: '0.1rem' }}>
                        สัดส่วนพอร์ต: <span style={{ color: '#fff' }}>{assetClass.pct.toFixed(1)}%</span>
                      </div>
                    </div>
                  </div>
                ))}
              </div>

              {/* Dynamic SVG Donut Chart Card */}
              <div className="glass-panel" style={{ padding: '2rem', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center' }}>
                <h3 style={{ fontSize: '1.15rem', fontWeight: 600, fontFamily: 'var(--font-display)', marginBottom: '1.5rem', width: '100%', textAlign: 'left' }}>Asset Allocation</h3>
                
                {/* SVG Radial Progress */}
                <div style={{ position: 'relative', width: '160px', height: '160px', display: 'flex', justifyContent: 'center', alignItems: 'center' }}>
                  <svg width="100%" height="100%" viewBox="0 0 42 42" style={{ transform: 'rotate(-90deg)' }}>
                    {/* Background Circle */}
                    <circle cx="21" cy="21" r="15.915" fill="transparent" stroke="rgba(255,255,255,0.03)" strokeWidth="4" />
                    
                    {/* Circle slices calculation */}
                    {/* Slice 1: Funds */}
                    <circle 
                      cx="21" cy="21" r="15.915" 
                      fill="transparent" 
                      stroke="#8b5cf6" 
                      strokeWidth="4.2" 
                      strokeDasharray={`${fundsPct} ${100 - fundsPct}`} 
                      strokeDashoffset="0" 
                      style={{ transition: 'stroke-dasharray 0.5s ease' }}
                    />
                    {/* Slice 2: Crypto */}
                    <circle 
                      cx="21" cy="21" r="15.915" 
                      fill="transparent" 
                      stroke="#06b6d4" 
                      strokeWidth="4.2" 
                      strokeDasharray={`${cryptoPct} ${100 - cryptoPct}`} 
                      strokeDashoffset={-fundsPct} 
                      style={{ transition: 'stroke-dasharray 0.5s ease' }}
                    />
                    {/* Slice 3: Forex */}
                    <circle 
                      cx="21" cy="21" r="15.915" 
                      fill="transparent" 
                      stroke="#f59e0b" 
                      strokeWidth="4.2" 
                      strokeDasharray={`${forexPct} ${100 - forexPct}`} 
                      strokeDashoffset={-(fundsPct + cryptoPct)} 
                      style={{ transition: 'stroke-dasharray 0.5s ease' }}
                    />
                  </svg>
                  <div style={{ position: 'absolute', display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
                    <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>ประเภททรัพย์สิน</span>
                    <span style={{ fontSize: '1.25rem', fontWeight: 800, fontFamily: 'var(--font-display)' }}>3 หมวด</span>
                  </div>
                </div>

                {/* Donut Legend */}
                <div style={{ display: 'flex', gap: '1rem', marginTop: '1.5rem', width: '100%', justifyContent: 'center', flexWrap: 'wrap' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                    <div style={{ width: '8px', height: '8px', borderRadius: '50%', backgroundColor: '#8b5cf6' }} />
                    <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>Funds ({fundsPct.toFixed(0)}%)</span>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                    <div style={{ width: '8px', height: '8px', borderRadius: '50%', backgroundColor: '#06b6d4' }} />
                    <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>Crypto ({cryptoPct.toFixed(0)}%)</span>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                    <div style={{ width: '8px', height: '8px', borderRadius: '50%', backgroundColor: '#f59e0b' }} />
                    <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>Forex ({forexPct.toFixed(0)}%)</span>
                  </div>
                </div>
              </div>
            </section>

            {/* Active Alerts in the system */}
            <section className="glass-panel" style={{ padding: '1.5rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1rem' }}>
                <Bell size={18} style={{ color: 'var(--accent-purple)' }} />
                <h3 style={{ fontSize: '1.15rem', fontWeight: 600, fontFamily: 'var(--font-display)' }}>สัญญาณดักราคาทํางานแบบเรียลไทม์ (Active Real-time Alert Triggers)</h3>
              </div>
              <div style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap' }}>
                {settings.alerts && settings.alerts.length > 0 ? (
                  settings.alerts.map(al => {
                    const priceUnit = al.assetId === 'USD_JPY' ? '¥' : al.assetId.includes('_') ? '$' : '$';
                    return (
                      <div key={al.id} className="glass-panel" style={{ padding: '0.75rem 1rem', display: 'flex', alignItems: 'center', gap: '0.75rem', background: 'rgba(255, 255, 255, 0.01)', borderRadius: '10px' }}>
                        <span style={{ fontSize: '0.8rem', fontWeight: 600, color: '#f8fafc' }}>{al.assetId}</span>
                        <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                          {al.condition === 'above' ? 'สูงกว่า 📈' : 'ต่ำกว่า 📉'} {al.value.toLocaleString()}
                        </span>
                        <div style={{ width: '6px', height: '6px', borderRadius: '50%', backgroundColor: 'var(--accent-purple)', animation: 'pulseGlow 1.5s infinite' }} />
                      </div>
                    );
                  })
                ) : (
                  <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>ไม่มีตัวดักราคาเปิดใช้งานอยู่ในขณะนี้ สามารถเพิ่มได้ในแถบการตั้งค่า</p>
                )}
              </div>
            </section>

            {mt5Account && mt5Status !== 'unknown' && (
              <div style={{ marginTop: '24px' }}>
                <h3 style={{ fontSize: '14px', color: '#9ca3af', marginBottom: '12px', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                  MT5 Account
                </h3>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: '12px' }}>
                  {[
                    { label: 'Balance', value: mt5Account.balance },
                    { label: 'Equity', value: mt5Account.equity },
                    { label: 'Margin', value: mt5Account.margin },
                    { label: 'Free Margin', value: mt5Account.margin_free },
                    { label: 'Profit', value: mt5Account.profit },
                  ].map(({ label, value }) => (
                    <div key={label} style={{ background: '#1f2937', borderRadius: '8px', padding: '12px 16px' }}>
                      <div style={{ fontSize: '12px', color: '#6b7280', marginBottom: '4px' }}>{label}</div>
                      <div style={{ fontSize: '18px', fontWeight: '600', color: value >= 0 ? '#34d399' : '#f87171' }}>
                        {value != null ? value.toFixed(2) : '—'}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* MUTUAL FUNDS DASHBOARD */}
        {activeTab === 'funds' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '2rem' }}>
            <header>
              <h1 style={{ fontSize: '2.2rem', fontWeight: 800, fontFamily: 'var(--font-display)', display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                <LineChart style={{ color: 'var(--accent-purple)' }} size={32} />
                ระบบจัดการกองทุนรวม (Mutual Funds Portfolio)
              </h1>
              <p style={{ color: 'var(--text-secondary)', fontSize: '0.95rem', marginTop: '0.2rem' }}>บริหารพอร์ตกองทุน หุ้นเติบโต กองทุนเทคโนโลยี และกองทุนอ้างอิงดัชนี</p>
            </header>

            <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: '2rem' }}>
              
              {/* Asset table list */}
              <div className="glass-panel" style={{ padding: '1.5rem' }}>
                <h3 style={{ fontSize: '1.15rem', fontWeight: 600, fontFamily: 'var(--font-display)', marginBottom: '1.25rem' }}>รายการถือครองกองทุน</h3>
                
                <table className="custom-table">
                  <thead>
                    <tr>
                      <th>ชื่อกองทุน / โค้ด</th>
                      <th style={{ textAlign: 'right' }}>จํานวนหน่วย</th>
                      <th style={{ textAlign: 'right' }}>ราคาเฉลี่ย</th>
                      <th style={{ textAlign: 'right' }}>ราคาปัจจุบัน</th>
                      <th style={{ textAlign: 'right' }}>มูลค่าปัจจุบัน</th>
                      <th style={{ textAlign: 'right' }}>กำไร / ขาดทุน</th>
                    </tr>
                  </thead>
                  <tbody>
                    {portfolio.categories.funds.items.map(item => {
                      const flash = priceFlash[item.id];
                      return (
                        <tr key={item.id}>
                          <td style={{ fontWeight: 600 }}>
                            <div>{item.name}</div>
                            <span style={{ fontSize: '0.7rem', color: 'var(--accent-purple)', fontWeight: 600, background: 'rgba(139,92,246,0.1)', padding: '0.1rem 0.4rem', borderRadius: '4px', marginTop: '0.2rem', display: 'inline-block' }}>{item.id}</span>
                          </td>
                          <td style={{ textAlign: 'right', fontFamily: 'var(--font-display)', fontWeight: 500 }}>{item.units.toLocaleString()}</td>
                          <td style={{ textAlign: 'right' }}>{fmt(item.avgBuyPrice)}</td>
                          <td 
                            style={{ textAlign: 'right', fontWeight: 700 }}
                            className={flash === 'up' ? 'flash-green' : flash === 'down' ? 'flash-red' : ''}
                          >
                            {fmt(item.currentPrice)}
                          </td>
                          <td style={{ textAlign: 'right', fontWeight: 700 }}>{fmt(item.currentValue)}</td>
                          <td style={{ textAlign: 'right', fontWeight: 700, color: item.pnl >= 0 ? 'var(--accent-emerald)' : 'var(--accent-rose)' }}>
                            <div>{item.pnl >= 0 ? '+' : ''}{fmt(item.pnl)}</div>
                            <span style={{ fontSize: '0.75rem', fontWeight: 600 }}>({item.pnlPct >= 0 ? '+' : ''}{item.pnlPct}%)</span>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>

              {/* Transaction Trading form panel */}
              <div className="glass-panel" style={{ padding: '1.75rem', height: 'fit-content' }}>
                <h3 style={{ fontSize: '1.25rem', fontWeight: 600, fontFamily: 'var(--font-display)', marginBottom: '1.25rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <Activity size={18} style={{ color: 'var(--accent-purple)' }} />
                  ส่งคำสั่งธุรกรรมกองทุน
                </h3>
                
                {txSuccess && (
                  <div className="glass-panel" style={{ padding: '1rem', marginBottom: '1rem', background: 'rgba(16,185,129,0.08)', borderColor: 'rgba(16,185,129,0.25)', display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                    <ShieldCheck size={18} style={{ color: 'var(--accent-emerald)' }} />
                    <span style={{ fontSize: '0.8rem', color: '#f8fafc', fontWeight: 500 }}>ทำรายการซื้อ/ขายกองทุนและบันทึกข้อมูลเรียบร้อย!</span>
                  </div>
                )}

                {txError && (
                  <div className="glass-panel" style={{ padding: '1rem', marginBottom: '1rem', background: 'rgba(244,63,94,0.08)', borderColor: 'rgba(244,63,94,0.25)', display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                    <AlertCircle size={18} style={{ color: 'var(--accent-rose)' }} />
                    <span style={{ fontSize: '0.8rem', color: '#f8fafc' }}>{txError}</span>
                  </div>
                )}

                <form onSubmit={handleTransactionSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '1.2rem' }}>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                    <label style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-secondary)' }}>กองทุนเป้าหมาย</label>
                    <select 
                      value={txAssetId} 
                      onChange={(e) => {
                        setTxAssetId(e.target.value);
                        const p = portfolio.categories.funds.items.find(i => i.id === e.target.value)?.currentPrice || '';
                        setTxPrice(p);
                      }}
                      style={{ width: '100%' }}
                    >
                      {portfolio.categories.funds.items.map(i => (
                        <option key={i.id} value={i.id}>{i.name} ({i.id})</option>
                      ))}
                    </select>
                  </div>

                  <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                    <label style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-secondary)' }}>ประเภทคำสั่ง</label>
                    <div style={{ display: 'flex', gap: '1rem' }}>
                      <label style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', cursor: 'pointer', fontSize: '0.85rem' }}>
                        <input type="radio" checked={txAction === 'buy'} onChange={() => setTxAction('buy')} style={{ width: 'auto' }} />
                        🟢 ซื้อ (BUY)
                      </label>
                      <label style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', cursor: 'pointer', fontSize: '0.85rem' }}>
                        <input type="radio" checked={txAction === 'sell'} onChange={() => setTxAction('sell')} style={{ width: 'auto' }} />
                        🔴 ขาย (SELL)
                      </label>
                    </div>
                  </div>

                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1.2fr', gap: '1rem' }}>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                      <label style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-secondary)' }}>จำนวนหน่วย</label>
                      <input 
                        type="number" 
                        step="0.0001"
                        placeholder="0.00" 
                        value={txUnits} 
                        onChange={(e) => setTxUnits(e.target.value)} 
                        style={{ width: '100%' }} 
                      />
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                      <label style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-secondary)' }}>ราคาเฉลี่ยต่อหน่วย</label>
                      <input 
                        type="number" 
                        step="0.01"
                        placeholder="0.00" 
                        value={txPrice} 
                        onChange={(e) => setTxPrice(e.target.value)} 
                        style={{ width: '100%' }} 
                      />
                    </div>
                  </div>

                  <button type="submit" className="btn-primary" style={{ width: '100%', justifyContent: 'center', marginTop: '0.5rem' }}>
                    ยืนยันการทำธุรกรรม
                  </button>
                </form>
              </div>

            </div>

            {/* Custom SVG valuation Chart */}
            <section className="glass-panel" style={{ padding: '2rem' }}>
              <h3 style={{ fontSize: '1.15rem', fontWeight: 600, fontFamily: 'var(--font-display)', marginBottom: '1rem' }}>ประวัติการเติบโตเชิงสถิติของพอร์ตกองทุน (12 เดือนที่ผ่านมา)</h3>
              
              <div style={{ width: '100%', height: '140px', marginTop: '1rem' }}>
                <svg width="100%" height="100%" viewBox="0 0 1000 140" preserveAspectRatio="none">
                  <defs>
                    <linearGradient id="fundGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#8b5cf6" stopOpacity="0.4" />
                      <stop offset="100%" stopColor="#8b5cf6" stopOpacity="0.0" />
                    </linearGradient>
                  </defs>
                  
                  {/* Grid Lines */}
                  <line x1="0" y1="20" x2="1000" y2="20" stroke="rgba(255,255,255,0.02)" />
                  <line x1="0" y1="60" x2="1000" y2="60" stroke="rgba(255,255,255,0.02)" />
                  <line x1="0" y1="100" x2="1000" y2="100" stroke="rgba(255,255,255,0.02)" />

                  {/* Area fill path */}
                  <path 
                    d="M 0 120 Q 150 110 200 95 T 400 70 T 600 50 T 800 35 T 1000 25 L 1000 140 L 0 140 Z" 
                    fill="url(#fundGrad)" 
                  />

                  {/* Stroke path */}
                  <path 
                    d="M 0 120 Q 150 110 200 95 T 400 70 T 600 50 T 800 35 T 1000 25" 
                    fill="none" 
                    stroke="#8b5cf6" 
                    strokeWidth="3.5" 
                    style={{ strokeDasharray: '1500', strokeDashoffset: '0', transition: 'stroke-dashoffset 2s' }}
                  />
                  
                  {/* Dynamic glow circles */}
                  <circle cx="1000" cy="25" r="5" fill="#8b5cf6" style={{ filter: 'drop-shadow(0 0 5px #8b5cf6)' }} />
                </svg>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', color: 'var(--text-muted)', fontSize: '0.75rem', marginTop: '0.5rem' }}>
                <span>ม.ค.</span>
                <span>มี.ค.</span>
                <span>พ.ค.</span>
                <span>ก.ค.</span>
                <span>ก.ย.</span>
                <span>พ.ย.</span>
                <span>ปัจจุบัน (พอร์ตกองทุนโตขึ้นอย่างมั่นคง)</span>
              </div>
            </section>
          </div>
        )}

        {/* CRYPTO DASHBOARD */}
        {activeTab === 'crypto' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '2rem' }}>
            <header>
              <h1 style={{ fontSize: '2.2rem', fontWeight: 800, fontFamily: 'var(--font-display)', display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                <Coins style={{ color: 'var(--accent-cyan)' }} size={32} />
                บริหารสินทรัพย์ดิจิทัล (Crypto Suite)
              </h1>
              <p style={{ color: 'var(--text-secondary)', fontSize: '0.95rem', marginTop: '0.2rem' }}>แดชบอร์ดติดตามราคาเหรียญบูลชิพ คริปโตเคอเรนซี และโทเคนเชิงลึก</p>
            </header>

            <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: '2rem' }}>
              
              {/* Table holding crypto */}
              <div className="glass-panel" style={{ padding: '1.5rem' }}>
                <h3 style={{ fontSize: '1.15rem', fontWeight: 600, fontFamily: 'var(--font-display)', marginBottom: '1.25rem' }}>พอร์ตโฟลิโอคริปโตของคุณ</h3>
                
                <table className="custom-table">
                  <thead>
                    <tr>
                      <th>สินทรัพย์ / สัญลักษณ์</th>
                      <th style={{ textAlign: 'right' }}>จํานวนเหรียญ</th>
                      <th style={{ textAlign: 'right' }}>ราคาซื้อเฉลี่ย</th>
                      <th style={{ textAlign: 'right' }}>ราคาตลาดปัจจุบัน</th>
                      <th style={{ textAlign: 'right' }}>มูลค่าตลาดรวม</th>
                      <th style={{ textAlign: 'right' }}>กำไร / ขาดทุน</th>
                    </tr>
                  </thead>
                  <tbody>
                    {portfolio.categories.crypto.items.map(item => {
                      const flash = priceFlash[item.id];
                      return (
                        <tr key={item.id}>
                          <td style={{ fontWeight: 600 }}>
                            <div>{item.name}</div>
                            <span style={{ fontSize: '0.7rem', color: 'var(--accent-cyan)', fontWeight: 600, background: 'rgba(6,182,212,0.1)', padding: '0.1rem 0.4rem', borderRadius: '4px', marginTop: '0.2rem', display: 'inline-block' }}>{item.id}</span>
                          </td>
                          <td style={{ textAlign: 'right', fontFamily: 'var(--font-display)', fontWeight: 500 }}>{item.units.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 4 })}</td>
                          <td style={{ textAlign: 'right' }}>{fmtUsd(item.avgBuyPrice)}</td>
                          <td 
                            style={{ textAlign: 'right', fontWeight: 700 }}
                            className={flash === 'up' ? 'flash-green' : flash === 'down' ? 'flash-red' : ''}
                          >
                            {fmtUsd(item.currentPrice)}
                          </td>
                          <td style={{ textAlign: 'right', fontWeight: 700 }}>{fmtUsd(item.currentValue)}</td>
                          <td style={{ textAlign: 'right', fontWeight: 700, color: item.pnl >= 0 ? 'var(--accent-emerald)' : 'var(--accent-rose)' }}>
                            <div>{item.pnl >= 0 ? '+' : ''}{fmtUsd(item.pnl)}</div>
                            <span style={{ fontSize: '0.75rem', fontWeight: 600 }}>({item.pnlPct >= 0 ? '+' : ''}{item.pnlPct}%)</span>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>

              {/* Crypto trading form panel */}
              <div className="glass-panel" style={{ padding: '1.75rem', height: 'fit-content' }}>
                <h3 style={{ fontSize: '1.25rem', fontWeight: 600, fontFamily: 'var(--font-display)', marginBottom: '1.25rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <Activity size={18} style={{ color: 'var(--accent-cyan)' }} />
                  ส่งคำสั่งซื้อขายคริปโต
                </h3>
                
                {txSuccess && (
                  <div className="glass-panel" style={{ padding: '1rem', marginBottom: '1rem', background: 'rgba(16,185,129,0.08)', borderColor: 'rgba(16,185,129,0.25)', display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                    <ShieldCheck size={18} style={{ color: 'var(--accent-emerald)' }} />
                    <span style={{ fontSize: '0.8rem', color: '#f8fafc', fontWeight: 500 }}>บันทึกธุรกรรม ซื้อ/ขาย คริปโตเรียบร้อยแล้ว!</span>
                  </div>
                )}

                {txError && (
                  <div className="glass-panel" style={{ padding: '1rem', marginBottom: '1rem', background: 'rgba(244,63,94,0.08)', borderColor: 'rgba(244,63,94,0.25)', display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                    <AlertCircle size={18} style={{ color: 'var(--accent-rose)' }} />
                    <span style={{ fontSize: '0.8rem', color: '#f8fafc' }}>{txError}</span>
                  </div>
                )}

                <form onSubmit={(e) => {
                  setTxType('crypto');
                  handleTransactionSubmit(e);
                }} style={{ display: 'flex', flexDirection: 'column', gap: '1.2rem' }}>
                  
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                    <label style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-secondary)' }}>เหรียญคริปโต</label>
                    <select 
                      value={txAssetId} 
                      onChange={(e) => {
                        setTxAssetId(e.target.value);
                        const p = portfolio.categories.crypto.items.find(i => i.id === e.target.value)?.currentPrice || '';
                        setTxPrice(p);
                      }}
                      style={{ width: '100%' }}
                    >
                      {portfolio.categories.crypto.items.map(i => (
                        <option key={i.id} value={i.id}>{i.name} ({i.id})</option>
                      ))}
                    </select>
                  </div>

                  <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                    <label style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-secondary)' }}>ประเภทคำสั่ง</label>
                    <div style={{ display: 'flex', gap: '1rem' }}>
                      <label style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', cursor: 'pointer', fontSize: '0.85rem' }}>
                        <input type="radio" name="crypto-act" checked={txAction === 'buy'} onChange={() => setTxAction('buy')} style={{ width: 'auto' }} />
                        🟢 ซื้อ (BUY)
                      </label>
                      <label style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', cursor: 'pointer', fontSize: '0.85rem' }}>
                        <input type="radio" name="crypto-act" checked={txAction === 'sell'} onChange={() => setTxAction('sell')} style={{ width: 'auto' }} />
                        🔴 ขาย (SELL)
                      </label>
                    </div>
                  </div>

                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1.2fr', gap: '1rem' }}>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                      <label style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-secondary)' }}>จำนวนเหรียญ</label>
                      <input 
                        type="number" 
                        step="0.0001"
                        placeholder="0.000" 
                        value={txUnits} 
                        onChange={(e) => setTxUnits(e.target.value)} 
                        style={{ width: '100%' }} 
                      />
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                      <label style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-secondary)' }}>ราคาซื้อต่อเหรียญ ($)</label>
                      <input 
                        type="number" 
                        step="0.01"
                        placeholder="0.00" 
                        value={txPrice} 
                        onChange={(e) => setTxPrice(e.target.value)} 
                        style={{ width: '100%' }} 
                      />
                    </div>
                  </div>

                  <button type="submit" className="btn-primary" style={{ width: '100%', justifyContent: 'center', marginTop: '0.5rem', background: 'linear-gradient(135deg, #06b6d4 0%, #0891b2 100%)', boxShadow: '0 4px 15px rgba(6, 182, 212, 0.3)' }}>
                    ส่งธุรกรรมส่งออกบล็อกเชน
                  </button>
                </form>
              </div>

            </div>

            {/* Custom SVG area chart for crypto */}
            <section className="glass-panel" style={{ padding: '2rem' }}>
              <h3 style={{ fontSize: '1.15rem', fontWeight: 600, fontFamily: 'var(--font-display)', marginBottom: '1rem' }}>ประวัติการเคลื่อนไหวความผันผวนคริปโต (12 เดือนที่ผ่านมา)</h3>
              
              <div style={{ width: '100%', height: '140px', marginTop: '1rem' }}>
                <svg width="100%" height="100%" viewBox="0 0 1000 140" preserveAspectRatio="none">
                  <defs>
                    <linearGradient id="cryptoGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#06b6d4" stopOpacity="0.4" />
                      <stop offset="100%" stopColor="#06b6d4" stopOpacity="0.0" />
                    </linearGradient>
                  </defs>
                  
                  <line x1="0" y1="20" x2="1000" y2="20" stroke="rgba(255,255,255,0.02)" />
                  <line x1="0" y1="60" x2="1000" y2="60" stroke="rgba(255,255,255,0.02)" />
                  <line x1="0" y1="100" x2="1000" y2="100" stroke="rgba(255,255,255,0.02)" />

                  <path 
                    d="M 0 130 Q 150 90 200 110 T 400 40 T 600 80 T 800 20 T 1000 35 L 1000 140 L 0 140 Z" 
                    fill="url(#cryptoGrad)" 
                  />

                  <path 
                    d="M 0 130 Q 150 90 200 110 T 400 40 T 600 80 T 800 20 T 1000 35" 
                    fill="none" 
                    stroke="#06b6d4" 
                    strokeWidth="3.5" 
                  />
                  
                  <circle cx="1000" cy="35" r="5" fill="#06b6d4" style={{ filter: 'drop-shadow(0 0 5px #06b6d4)' }} />
                </svg>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', color: 'var(--text-muted)', fontSize: '0.75rem', marginTop: '0.5rem' }}>
                <span>ม.ค.</span>
                <span>มี.ค.</span>
                <span>พ.ค.</span>
                <span>ก.ค.</span>
                <span>ก.ย.</span>
                <span>พ.ย.</span>
                <span>ปัจจุบัน (พอร์ตคริปโตเติบโตเชิงรุกด้วย Alpha สูง)</span>
              </div>
            </section>
          </div>
        )}

        {/* FOREX DASHBOARD */}
        {activeTab === 'forex' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '2rem' }}>
            <header>
              <h1 style={{ fontSize: '2.2rem', fontWeight: 800, fontFamily: 'var(--font-display)', display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                <DollarSign style={{ color: 'var(--accent-amber)' }} size={32} />
                แดชบอร์ดค่าเงินต่างประเทศ (Forex Management)
              </h1>
              <p style={{ color: 'var(--text-secondary)', fontSize: '0.95rem', marginTop: '0.2rem' }}>ระบบเทรดและถือครองเงินสากลสกุลเงินหลัก ทํากำไรส่วนต่างอัตราแลกเปลี่ยน</p>
            </header>

            {mt5Status === 'online' && (
              <div style={{ display: 'flex', gap: '16px', marginBottom: '16px', flexWrap: 'wrap' }}>
                {['EURUSD', 'USDJPY', 'GBPUSD'].map(sym => (
                  <MT5PriceTag key={sym} symbol={sym} apiBase={API_BASE} />
                ))}
              </div>
            )}

            <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: '2rem' }}>
              
              {/* Asset table forex */}
              <div className="glass-panel" style={{ padding: '1.5rem' }}>
                <h3 style={{ fontSize: '1.15rem', fontWeight: 600, fontFamily: 'var(--font-display)', marginBottom: '1.25rem' }}>รายการถือครองสกุลเงิน Forex</h3>
                
                <table className="custom-table">
                  <thead>
                    <tr>
                      <th>คู่เงิน / คู่ค้า</th>
                      <th style={{ textAlign: 'right' }}>จำนวนหน่วยถือครอง</th>
                      <th style={{ textAlign: 'right' }}>ราคาเข้าซื้อเฉลี่ย</th>
                      <th style={{ textAlign: 'right' }}>อัตราแลกเปลี่ยนปัจจุบัน</th>
                      <th style={{ textAlign: 'right' }}>มูลค่าตลาดสุทธิ ($)</th>
                      <th style={{ textAlign: 'right' }}>กำไร / ขาดทุน</th>
                    </tr>
                  </thead>
                  <tbody>
                    {portfolio.categories.forex.items.map(item => {
                      const flash = priceFlash[item.id];
                      return (
                        <tr key={item.id}>
                          <td style={{ fontWeight: 600 }}>
                            <div>{item.name}</div>
                            <span style={{ fontSize: '0.7rem', color: 'var(--accent-amber)', fontWeight: 600, background: 'rgba(245,158,11,0.1)', padding: '0.1rem 0.4rem', borderRadius: '4px', marginTop: '0.2rem', display: 'inline-block' }}>{item.id}</span>
                          </td>
                          <td style={{ textAlign: 'right', fontFamily: 'var(--font-display)', fontWeight: 500 }}>{item.units.toLocaleString()}</td>
                          <td style={{ textAlign: 'right' }}>{item.avgBuyPrice}</td>
                          <td 
                            style={{ textAlign: 'right', fontWeight: 700 }}
                            className={flash === 'up' ? 'flash-green' : flash === 'down' ? 'flash-red' : ''}
                          >
                            {item.currentPrice}
                          </td>
                          <td style={{ textAlign: 'right', fontWeight: 700 }}>{fmtUsd(item.currentValue)}</td>
                          <td style={{ textAlign: 'right', fontWeight: 700, color: item.pnl >= 0 ? 'var(--accent-emerald)' : 'var(--accent-rose)' }}>
                            <div>{item.pnl >= 0 ? '+' : ''}{fmtUsd(item.pnl)}</div>
                            <span style={{ fontSize: '0.75rem', fontWeight: 600 }}>({item.pnlPct >= 0 ? '+' : ''}{item.pnlPct}%)</span>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>

              {/* Forex trading form panel */}
              <div className="glass-panel" style={{ padding: '1.75rem', height: 'fit-content' }}>
                <h3 style={{ fontSize: '1.25rem', fontWeight: 600, fontFamily: 'var(--font-display)', marginBottom: '1.25rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <Activity size={18} style={{ color: 'var(--accent-amber)' }} />
                  ส่งคำสั่งซื้อขายคู่เงิน
                </h3>
                
                {txSuccess && (
                  <div className="glass-panel" style={{ padding: '1rem', marginBottom: '1rem', background: 'rgba(16,185,129,0.08)', borderColor: 'rgba(16,185,129,0.25)', display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                    <ShieldCheck size={18} style={{ color: 'var(--accent-emerald)' }} />
                    <span style={{ fontSize: '0.8rem', color: '#f8fafc', fontWeight: 500 }}>ทำรายการสั่งซื้อ/ขายคู่เงินเสร็จสมบูรณ์!</span>
                  </div>
                )}

                {txError && (
                  <div className="glass-panel" style={{ padding: '1rem', marginBottom: '1rem', background: 'rgba(244,63,94,0.08)', borderColor: 'rgba(244,63,94,0.25)', display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                    <AlertCircle size={18} style={{ color: 'var(--accent-rose)' }} />
                    <span style={{ fontSize: '0.8rem', color: '#f8fafc' }}>{txError}</span>
                  </div>
                )}

                <form onSubmit={(e) => {
                  setTxType('forex');
                  handleTransactionSubmit(e);
                }} style={{ display: 'flex', flexDirection: 'column', gap: '1.2rem' }}>
                  
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                    <label style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-secondary)' }}>คู่เงิน Forex</label>
                    <select 
                      value={txAssetId} 
                      onChange={(e) => {
                        setTxAssetId(e.target.value);
                        const p = portfolio.categories.forex.items.find(i => i.id === e.target.value)?.currentPrice || '';
                        setTxPrice(p);
                      }}
                      style={{ width: '100%' }}
                    >
                      {portfolio.categories.forex.items.map(i => (
                        <option key={i.id} value={i.id}>{i.name} ({i.id})</option>
                      ))}
                    </select>
                  </div>

                  <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                    <label style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-secondary)' }}>ประเภทคำสั่ง</label>
                    <div style={{ display: 'flex', gap: '1rem' }}>
                      <label style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', cursor: 'pointer', fontSize: '0.85rem' }}>
                        <input type="radio" name="forex-act" checked={txAction === 'buy'} onChange={() => setTxAction('buy')} style={{ width: 'auto' }} />
                        🟢 ซื้อ (BUY)
                      </label>
                      <label style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', cursor: 'pointer', fontSize: '0.85rem' }}>
                        <input type="radio" name="forex-act" checked={txAction === 'sell'} onChange={() => setTxAction('sell')} style={{ width: 'auto' }} />
                        🔴 ขาย (SELL)
                      </label>
                    </div>
                  </div>

                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1.2fr', gap: '1rem' }}>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                      <label style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-secondary)' }}>ขนาดสัญญา (Units)</label>
                      <input 
                        type="number" 
                        step="1"
                        placeholder="1000" 
                        value={txUnits} 
                        onChange={(e) => setTxUnits(e.target.value)} 
                        style={{ width: '100%' }} 
                      />
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                      <label style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-secondary)' }}>ราคาอัตราแลกเปลี่ยน</label>
                      <input 
                        type="number" 
                        step="0.0001"
                        placeholder="1.0000" 
                        value={txPrice} 
                        onChange={(e) => setTxPrice(e.target.value)} 
                        style={{ width: '100%' }} 
                      />
                    </div>
                  </div>

                  <button
                    type="submit"
                    className="btn-primary"
                    style={{ width: '100%', justifyContent: 'center', marginTop: '0.5rem', background: 'linear-gradient(135deg, #f59e0b 0%, #d97706 100%)', boxShadow: '0 4px 15px rgba(245, 158, 11, 0.3)' }}
                    disabled={txType === 'forex' && mt5Status === 'offline'}
                    title={txType === 'forex' && mt5Status === 'offline' ? 'MT5 offline — cannot place order' : undefined}
                  >
                    ยืนยันคำสั่งซื้อขาย Forex
                  </button>
                </form>
              </div>

            </div>

            {/* Custom SVG forex chart */}
            <section className="glass-panel" style={{ padding: '2rem' }}>
              <h3 style={{ fontSize: '1.15rem', fontWeight: 600, fontFamily: 'var(--font-display)', marginBottom: '1rem' }}>ประวัติการเคลื่อนไหวตลาดอัตราแลกเปลี่ยน (12 เดือนที่ผ่านมา)</h3>
              
              <div style={{ width: '100%', height: '140px', marginTop: '1rem' }}>
                <svg width="100%" height="100%" viewBox="0 0 1000 140" preserveAspectRatio="none">
                  <defs>
                    <linearGradient id="forexGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#f59e0b" stopOpacity="0.4" />
                      <stop offset="100%" stopColor="#f59e0b" stopOpacity="0.0" />
                    </linearGradient>
                  </defs>
                  
                  <line x1="0" y1="20" x2="1000" y2="20" stroke="rgba(255,255,255,0.02)" />
                  <line x1="0" y1="60" x2="1000" y2="60" stroke="rgba(255,255,255,0.02)" />
                  <line x1="0" y1="100" x2="1000" y2="100" stroke="rgba(255,255,255,0.02)" />

                  <path 
                    d="M 0 60 Q 150 40 200 50 T 400 80 T 600 40 T 800 70 T 1000 55 L 1000 140 L 0 140 Z" 
                    fill="url(#forexGrad)" 
                  />

                  <path 
                    d="M 0 60 Q 150 40 200 50 T 400 80 T 600 40 T 800 70 T 1000 55" 
                    fill="none" 
                    stroke="#f59e0b" 
                    strokeWidth="3.5" 
                  />
                  
                  <circle cx="1000" cy="55" r="5" fill="#f59e0b" style={{ filter: 'drop-shadow(0 0 5px #f59e0b)' }} />
                </svg>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', color: 'var(--text-muted)', fontSize: '0.75rem', marginTop: '0.5rem' }}>
                <span>ม.ค.</span>
                <span>มี.ค.</span>
                <span>พ.ค.</span>
                <span>ก.ค.</span>
                <span>ก.ย.</span>
                <span>พ.ย.</span>
                <span>ปัจจุบัน (พอร์ตสกุลเงินหลักมีความผันผวนต่ำมั่นคงสูง)</span>
              </div>
            </section>
          </div>
        )}

        {/* MT5 POSITIONS TAB */}
        {activeTab === 'mt5' && (
          <div>
            <h2 style={{ fontSize: '20px', fontWeight: '700', marginBottom: '16px' }}>MT5 Open Positions</h2>
            {mt5Positions.length === 0 ? (
              <div style={{ color: '#6b7280', textAlign: 'center', padding: '40px' }}>
                {mt5Status === 'offline' ? 'MT5 offline — no position data' : 'No open positions'}
              </div>
            ) : (
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '14px' }}>
                <thead>
                  <tr style={{ color: '#6b7280', borderBottom: '1px solid #374151' }}>
                    {['Ticket', 'Symbol', 'Type', 'Volume', 'Open Price', 'Current Price', 'SL', 'TP', 'P&L'].map(h => (
                      <th key={h} style={{ padding: '8px 12px', textAlign: 'right', fontWeight: '500' }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {mt5Positions.map(pos => (
                    <tr key={pos.ticket} style={{ borderBottom: '1px solid #1f2937' }}>
                      <td style={{ padding: '8px 12px', textAlign: 'right', color: '#9ca3af' }}>{pos.ticket}</td>
                      <td style={{ padding: '8px 12px', textAlign: 'right', fontWeight: '600' }}>{pos.symbol}</td>
                      <td style={{ padding: '8px 12px', textAlign: 'right', color: pos.type === 0 ? '#34d399' : '#f87171' }}>
                        {pos.type === 0 ? 'BUY' : 'SELL'}
                      </td>
                      <td style={{ padding: '8px 12px', textAlign: 'right' }}>{pos.volume}</td>
                      <td style={{ padding: '8px 12px', textAlign: 'right' }}>{pos.price_open?.toFixed(5)}</td>
                      <td style={{ padding: '8px 12px', textAlign: 'right' }}>{pos.price_current?.toFixed(5)}</td>
                      <td style={{ padding: '8px 12px', textAlign: 'right', color: '#6b7280' }}>{pos.sl > 0 ? pos.sl : '—'}</td>
                      <td style={{ padding: '8px 12px', textAlign: 'right', color: '#6b7280' }}>{pos.tp > 0 ? pos.tp : '—'}</td>
                      <td style={{ padding: '8px 12px', textAlign: 'right', color: pos.profit >= 0 ? '#34d399' : '#f87171', fontWeight: '600' }}>
                        {pos.profit?.toFixed(2)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        )}

        {/* TRADING CONTROL PLANE TAB */}
        {activeTab === 'trading-control' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
            <header style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '1rem', flexWrap: 'wrap' }}>
              <div>
                <h1 style={{ fontSize: '2.2rem', fontWeight: 800, fontFamily: 'var(--font-display)', display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                  <ShieldCheck style={{ color: 'var(--accent-emerald)' }} size={32} />
                  Hedge Fund Trading Control
                </h1>
                <p style={{ color: 'var(--text-secondary)', fontSize: '0.95rem', marginTop: '0.2rem' }}>
                  ศูนย์รวม MTAI Forex และ Crypto AI สำหรับดู guard, PnL, position และสรุปคำแนะนำรายวัน
                </p>
              </div>
              <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap' }}>
                <button onClick={fetchTradingControl} className="btn-secondary" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <RefreshCw size={16} />
                  Refresh
                </button>
                <button onClick={sendTradingReport} disabled={tradingReportStatus.loading} className="btn-primary" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <Send size={16} />
                  {tradingReportStatus.loading ? 'Sending...' : 'Send LINE/Telegram'}
                </button>
              </div>
            </header>

            {tradingReportStatus.msg && (
              <div className="glass-panel" style={{
                padding: '1rem',
                background: tradingReportStatus.type === 'success' ? 'rgba(16,185,129,0.08)' : tradingReportStatus.type === 'error' ? 'rgba(244,63,94,0.08)' : 'rgba(255,255,255,0.02)',
                borderColor: tradingReportStatus.type === 'success' ? 'rgba(16,185,129,0.25)' : tradingReportStatus.type === 'error' ? 'rgba(244,63,94,0.25)' : 'var(--glass-border)'
              }}>
                {tradingReportStatus.msg}
              </div>
            )}

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '1rem' }}>
              {[
                ['Guard Mode', tradingOverview?.portfolio?.guardMode || 'LOADING'],
                ['Daily PnL', fmtUsd(tradingOverview?.portfolio?.dailyPnl || 0)],
                ['Floating PnL', fmtUsd(tradingOverview?.portfolio?.floatingPnl || 0)],
                ['Open Positions', tradingOverview?.portfolio?.openPositions ?? 0],
                ['Recommendations', tradingOverview?.portfolio?.recommendationCount ?? 0],
              ].map(([label, value]) => (
                <div key={label} className="glass-panel" style={{ padding: '1.2rem' }}>
                  <div style={{ color: 'var(--text-muted)', fontSize: '0.78rem', textTransform: 'uppercase' }}>{label}</div>
                  <div style={{ fontSize: '1.45rem', fontWeight: 800, marginTop: '0.35rem' }}>{value}</div>
                </div>
              ))}
            </div>

            <section className="glass-panel" style={{ padding: '1.25rem', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '1rem', flexWrap: 'wrap' }}>
                <div>
                  <h3 style={{ fontSize: '1.15rem', fontWeight: 800, display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    <Cpu size={18} style={{ color: 'var(--accent-purple)' }} />
                    Hedge Fund AI Analyst
                  </h3>
                  <p style={{ color: 'var(--text-secondary)', fontSize: '0.85rem', marginTop: '0.25rem' }}>
                    วิเคราะห์ภาพรวมจาก MTAI, crypto-ai, guard, positions และ control audit โดย LLM หรือ fallback policy
                  </p>
                </div>
                <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap' }}>
                  <button onClick={runAiAnalyst} disabled={aiAnalystStatus.loading} className="btn-secondary" style={{ display: 'flex', alignItems: 'center', gap: '0.45rem' }}>
                    <RefreshCw size={15} />
                    Analyze Now
                  </button>
                  <button
                    onClick={applyAiSafeActions}
                    disabled={aiAnalystStatus.loading || !(aiAnalystReport?.safe_actions || []).length}
                    className="btn-primary"
                    style={{ display: 'flex', alignItems: 'center', gap: '0.45rem' }}
                  >
                    <ShieldCheck size={15} />
                    Apply Safe Actions
                  </button>
                  <button onClick={sendAiAnalystReport} disabled={aiAnalystStatus.loading || !aiAnalystReport} className="btn-secondary" style={{ display: 'flex', alignItems: 'center', gap: '0.45rem' }}>
                    <Send size={15} />
                    Send AI Report
                  </button>
                </div>
              </div>

              {aiAnalystStatus.msg && (
                <div style={{
                  padding: '0.85rem',
                  border: '1px solid',
                  borderColor: aiAnalystStatus.type === 'success' ? 'rgba(16,185,129,0.25)' : aiAnalystStatus.type === 'error' ? 'rgba(244,63,94,0.25)' : 'var(--glass-border)',
                  borderRadius: '8px',
                  color: aiAnalystStatus.type === 'error' ? 'var(--accent-rose)' : 'var(--text-secondary)',
                  background: aiAnalystStatus.type === 'success' ? 'rgba(16,185,129,0.08)' : aiAnalystStatus.type === 'error' ? 'rgba(244,63,94,0.08)' : 'rgba(255,255,255,0.02)',
                  fontSize: '0.85rem'
                }}>
                  {aiAnalystStatus.msg}
                </div>
              )}

              {aiAnalystReport ? (
                <>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))', gap: '0.75rem' }}>
                    <div>
                      <div style={{ color: 'var(--text-muted)', fontSize: '0.75rem' }}>Mode</div>
                      <div style={{ fontWeight: 800 }}>{aiAnalystReport.market_mode || 'UNKNOWN'}</div>
                    </div>
                    <div>
                      <div style={{ color: 'var(--text-muted)', fontSize: '0.75rem' }}>Source</div>
                      <div style={{ fontWeight: 800 }}>{aiAnalystReport.source || '-'}</div>
                    </div>
                    <div>
                      <div style={{ color: 'var(--text-muted)', fontSize: '0.75rem' }}>Safe Actions</div>
                      <div style={{ fontWeight: 800 }}>{(aiAnalystReport.safe_actions || []).length}</div>
                    </div>
                    <div>
                      <div style={{ color: 'var(--text-muted)', fontSize: '0.75rem' }}>Rejected</div>
                      <div style={{ fontWeight: 800 }}>{(aiAnalystReport.rejected_actions || []).length}</div>
                    </div>
                  </div>
                  {aiAnalystReport.llm_error && (
                    <div style={{ color: 'var(--accent-rose)', fontSize: '0.82rem' }}>
                      LLM fallback: {aiAnalystReport.llm_error}
                    </div>
                  )}
                  <div style={{ whiteSpace: 'pre-wrap', color: 'var(--text-secondary)', fontSize: '0.88rem', lineHeight: 1.55 }}>
                    {aiAnalystReport.report_th || aiAnalystReport.summary || 'No report text.'}
                  </div>
                  {(aiAnalystReport.safe_actions || []).length > 0 && (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.55rem' }}>
                      {(aiAnalystReport.safe_actions || []).map((action, idx) => (
                        <div key={`${action.engineId}-${action.action}-${idx}`} style={{ padding: '0.75rem', border: '1px solid rgba(16,185,129,0.2)', borderRadius: '8px', background: 'rgba(16,185,129,0.06)' }}>
                          <div style={{ fontSize: '0.8rem', fontWeight: 800, color: 'var(--accent-emerald)' }}>{action.engineId} • {action.action} • {(action.confidence * 100).toFixed(0)}%</div>
                          <div style={{ color: 'var(--text-secondary)', fontSize: '0.82rem', marginTop: '0.25rem' }}>{action.reason}</div>
                        </div>
                      ))}
                    </div>
                  )}
                </>
              ) : (
                <div style={{ color: 'var(--text-muted)', fontSize: '0.88rem' }}>No AI analyst report yet.</div>
              )}
            </section>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '1rem' }}>
              {(tradingOverview?.engines || []).map(engine => (
                <section key={engine.id} className="glass-panel" style={{ padding: '1.25rem', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '1rem' }}>
                    <div>
                      <h3 style={{ fontSize: '1.1rem', fontWeight: 700 }}>{engine.name}</h3>
                      <div style={{ color: 'var(--text-muted)', fontSize: '0.8rem' }}>{engine.type?.toUpperCase()} • {engine.status}</div>
                    </div>
                    <span style={{
                      padding: '0.35rem 0.7rem',
                      borderRadius: '999px',
                      background: engine.guardMode === 'NORMAL' ? 'rgba(16,185,129,0.12)' : engine.guardMode === 'CAUTION' ? 'rgba(245,158,11,0.14)' : 'rgba(244,63,94,0.12)',
                      color: engine.guardMode === 'NORMAL' ? 'var(--accent-emerald)' : engine.guardMode === 'CAUTION' ? '#f59e0b' : 'var(--accent-rose)',
                      fontSize: '0.75rem',
                      fontWeight: 700
                    }}>
                      {engine.guardMode || 'UNKNOWN'}
                    </span>
                  </div>
                  <div style={{ display: 'flex', gap: '0.6rem', flexWrap: 'wrap' }}>
                    <button
                      onClick={() => sendTradingControl(engine.id, 'pause')}
                      disabled={tradingReportStatus.loading}
                      className="btn-secondary"
                      style={{ padding: '0.55rem 0.85rem', fontSize: '0.8rem' }}
                    >
                      Pause Entries
                    </button>
                    <button
                      onClick={() => sendTradingControl(engine.id, 'resume')}
                      disabled={tradingReportStatus.loading}
                      className="btn-secondary"
                      style={{ padding: '0.55rem 0.85rem', fontSize: '0.8rem' }}
                    >
                      Resume Entries
                    </button>
                    {engine.control?.entries_paused && (
                      <span style={{ alignSelf: 'center', color: 'var(--accent-rose)', fontSize: '0.8rem', fontWeight: 700 }}>
                        Paused: {engine.control.pause_reason || 'manual'}
                      </span>
                    )}
                  </div>
                  {engine.error ? (
                    <div style={{ color: 'var(--accent-rose)', fontSize: '0.9rem' }}>{engine.error}</div>
                  ) : (
                    <>
                      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '0.75rem' }}>
                        <div>
                          <div style={{ color: 'var(--text-muted)', fontSize: '0.75rem' }}>Daily</div>
                          <div style={{ color: (engine.daily?.value || 0) >= 0 ? 'var(--accent-emerald)' : 'var(--accent-rose)', fontWeight: 700 }}>
                            {fmtUsd(engine.daily?.value || 0)}
                          </div>
                        </div>
                        <div>
                          <div style={{ color: 'var(--text-muted)', fontSize: '0.75rem' }}>Floating</div>
                          <div style={{ color: (engine.floatingPnl || 0) >= 0 ? 'var(--accent-emerald)' : 'var(--accent-rose)', fontWeight: 700 }}>
                            {fmtUsd(engine.floatingPnl || 0)}
                          </div>
                        </div>
                        <div>
                          <div style={{ color: 'var(--text-muted)', fontSize: '0.75rem' }}>Open</div>
                          <div style={{ fontWeight: 700 }}>{engine.openPositions || 0}</div>
                        </div>
                      </div>
                      {(engine.positions || []).length > 0 && (
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.55rem' }}>
                          {(engine.positions || []).slice(0, 5).map(pos => {
                            const ticket = pos.ticket;
                            const confirmKey = `${engine.id}:${ticket}`;
                            const side = typeof pos.type === 'number' ? (pos.type === 0 ? 'BUY' : 'SELL') : String(pos.type || '').toUpperCase();
                            return (
                              <div key={confirmKey} style={{ display: 'grid', gridTemplateColumns: '1fr auto', gap: '0.75rem', alignItems: 'center', padding: '0.7rem', border: '1px solid var(--glass-border)', borderRadius: '8px', background: 'rgba(255,255,255,0.02)' }}>
                                <div style={{ minWidth: 0 }}>
                                  <div style={{ fontWeight: 700, fontSize: '0.85rem' }}>
                                    {pos.symbol} <span style={{ color: side === 'BUY' ? 'var(--accent-emerald)' : 'var(--accent-rose)' }}>{side}</span>
                                  </div>
                                  <div style={{ color: 'var(--text-secondary)', fontSize: '0.78rem', marginTop: '0.25rem' }}>
                                    Ticket {ticket} • Vol {pos.volume ?? pos.qty ?? '-'} • PnL {fmtUsd(pos.profit ?? pos.pnl ?? 0)}
                                  </div>
                                </div>
                                {closeConfirmTicket === confirmKey ? (
                                  <button
                                    onClick={() => sendTradingControl(engine.id, 'close-position', { ticket, confirm: true })}
                                    disabled={tradingReportStatus.loading}
                                    className="btn-primary"
                                    style={{ padding: '0.5rem 0.75rem', fontSize: '0.78rem', background: 'linear-gradient(135deg, #f43f5e 0%, #be123c 100%)' }}
                                  >
                                    Confirm Close
                                  </button>
                                ) : (
                                  <button
                                    onClick={() => setCloseConfirmTicket(confirmKey)}
                                    disabled={tradingReportStatus.loading}
                                    className="btn-secondary"
                                    style={{ padding: '0.5rem 0.75rem', fontSize: '0.78rem' }}
                                  >
                                    Close
                                  </button>
                                )}
                              </div>
                            );
                          })}
                        </div>
                      )}
                      <div style={{ color: 'var(--text-secondary)', fontSize: '0.85rem' }}>
                        Recent W/L: <strong>{engine.recentWins || 0}/{engine.recentLosses || 0}</strong>
                        {' '}Net: <strong>{fmtUsd(engine.recentNetPnl || 0)}</strong>
                      </div>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                        {(engine.recommendations || []).slice(0, 3).map((rec, idx) => (
                          <div key={`${engine.id}-${rec.action}-${idx}`} style={{ padding: '0.75rem', border: '1px solid var(--glass-border)', borderRadius: '8px', background: 'rgba(255,255,255,0.02)' }}>
                            <div style={{ fontSize: '0.78rem', fontWeight: 700, color: rec.severity === 'high' || rec.severity === 'critical' ? 'var(--accent-rose)' : 'var(--accent-cyan)' }}>{rec.action}</div>
                            <div style={{ color: 'var(--text-secondary)', fontSize: '0.82rem', marginTop: '0.25rem' }}>{rec.reason}</div>
                          </div>
                        ))}
                        {(engine.recommendations || []).length === 0 && (
                          <div style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>No active recommendations.</div>
                        )}
                      </div>
                    </>
                  )}
                </section>
              ))}
            </div>

            <section className="glass-panel" style={{ padding: '1.25rem' }}>
              <h3 style={{ fontSize: '1.1rem', fontWeight: 700, marginBottom: '1rem' }}>Agent Recommendation Log</h3>
              {tradingRecommendations.length === 0 ? (
                <div style={{ color: 'var(--text-muted)', textAlign: 'center', padding: '1rem' }}>No recommendations stored yet.</div>
              ) : (
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.86rem' }}>
                  <thead>
                    <tr style={{ color: 'var(--text-muted)', borderBottom: '1px solid var(--glass-border)' }}>
                      {['Time', 'Engine', 'Severity', 'Action', 'Reason'].map(h => (
                        <th key={h} style={{ padding: '0.65rem', textAlign: 'left', fontWeight: 600 }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {tradingRecommendations.slice(0, 12).map(rec => (
                      <tr key={rec.id} style={{ borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
                        <td style={{ padding: '0.65rem', color: 'var(--text-muted)' }}>{new Date(rec.created_at).toLocaleTimeString('th-TH', { timeZone: 'Asia/Bangkok' })}</td>
                        <td style={{ padding: '0.65rem' }}>{rec.engine_id}</td>
                        <td style={{ padding: '0.65rem', color: rec.severity === 'high' || rec.severity === 'critical' ? 'var(--accent-rose)' : 'var(--accent-cyan)', fontWeight: 700 }}>{rec.severity}</td>
                        <td style={{ padding: '0.65rem', fontWeight: 700 }}>{rec.action}</td>
                        <td style={{ padding: '0.65rem', color: 'var(--text-secondary)' }}>{rec.reason}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </section>
          </div>
        )}

        {/* AI OPTIMIZER & WEALTH COACH */}
        {activeTab === 'ai-advisor' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '2rem' }}>
            <header>
              <h1 style={{ fontSize: '2.2rem', fontWeight: 800, fontFamily: 'var(--font-display)', display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                <Cpu style={{ color: 'var(--accent-purple)' }} size={32} />
                AI Advisory & Portfolio Optimizer Suite
              </h1>
              <p style={{ color: 'var(--text-secondary)', fontSize: '0.95rem', marginTop: '0.2rem' }}>เครื่องมือวิเคราะห์ระดับมืออาชีพสากล ปรับสัดส่วนตามระดับความเสี่ยงด้วย Smart Rebalance</p>
            </header>

            <div style={{ display: 'grid', gridTemplateColumns: '1.2fr 1fr', gap: '2rem' }}>
              
              {/* Risk Slider & Rebalancer */}
              <div className="glass-panel glow-purple" style={{ padding: '2rem', display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
                <h3 style={{ fontSize: '1.25rem', fontWeight: 600, fontFamily: 'var(--font-display)' }}>1. ปรับสมดุลพอร์ตความเสี่ยงเป้าหมาย</h3>
                
                {/* Risk Selector Buttons */}
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                  <label style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-secondary)' }}>ระดับความเสี่ยงเป้าหมาย</label>
                  <div style={{ display: 'flex', gap: '0.75rem', marginTop: '0.25rem' }}>
                    {['Conservative', 'Balanced', 'Aggressive'].map(prof => (
                      <button
                        key={prof}
                        onClick={() => handleRiskChange(prof)}
                        style={{
                          flex: 1,
                          padding: '0.75rem',
                          background: settings.riskProfile === prof ? 'linear-gradient(135deg, #8b5cf6 0%, #6d28d9 100%)' : 'rgba(255,255,255,0.03)',
                          border: settings.riskProfile === prof ? 'none' : '1px solid var(--glass-border)',
                          borderRadius: '8px',
                          color: '#fff',
                          fontWeight: 600,
                          cursor: 'pointer',
                          transition: 'all 0.2s ease',
                          fontSize: '0.85rem'
                        }}
                      >
                        {prof === 'Conservative' ? '🛡️ Conservative' : prof === 'Balanced' ? '⚖️ Balanced' : '🚀 Aggressive'}
                      </button>
                    ))}
                  </div>
                </div>

                {/* Weight Comparison bars */}
                {aiRecommend && (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '1.2rem', marginTop: '0.5rem' }}>
                    <label style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-secondary)', display: 'block', marginBottom: '0.2rem' }}>เปรียบเทียบสัดส่วน: ปัจจุบัน vs เป้าหมาย</label>
                    
                    {aiRecommend.recommendations.map(rec => {
                      const color = rec.category === 'funds' ? '#8b5cf6' : rec.category === 'crypto' ? '#06b6d4' : '#f59e0b';
                      const label = rec.category === 'funds' ? 'Mutual Funds' : rec.category === 'crypto' ? 'Crypto' : 'Forex';
                      return (
                        <div key={rec.category} style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.8rem' }}>
                            <span style={{ fontWeight: 600 }}>{label}</span>
                            <span style={{ color: 'var(--text-secondary)' }}>ปัจจุบัน: {rec.currentWeight}% | เป้าหมาย: {rec.targetWeight}%</span>
                          </div>
                          
                          {/* visual progress bar */}
                          <div style={{ height: '8px', width: '100%', backgroundColor: 'rgba(255,255,255,0.03)', borderRadius: '4px', overflow: 'hidden', position: 'relative' }}>
                            {/* Current weight bar */}
                            <div style={{ height: '100%', width: `${rec.currentWeight}%`, backgroundColor: color, borderRadius: '4px', position: 'absolute', left: 0, top: 0, opacity: 0.65 }} />
                            {/* Target pointer line */}
                            <div style={{ height: '100%', width: '3px', backgroundColor: '#fff', position: 'absolute', left: `${rec.targetWeight}%`, top: 0, zIndex: 10, boxShadow: '0 0 5px #fff' }} />
                          </div>

                          {/* Action advice */}
                          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem', marginTop: '0.1rem' }}>
                            <span style={{ color: 'var(--text-muted)' }}>ผลต่าง: {rec.difference > 0 ? `ขาด ${rec.difference}%` : `เกิน ${Math.abs(rec.difference)}%`}</span>
                            <span style={{ 
                              fontWeight: 700, 
                              color: rec.action === 'BUY_MORE' ? 'var(--accent-emerald)' : rec.action === 'TAKE_PROFIT' ? 'var(--accent-rose)' : 'var(--text-muted)' 
                            }}>
                              {rec.action === 'BUY_MORE' ? '🟢 แนะนำสะสมเพิ่ม (BUY)' : rec.action === 'TAKE_PROFIT' ? '🔴 แนะนำขายทำกำไร (SELL)' : '⚖️ สัดส่วนสมดุลแล้ว (HOLD)'}
                            </span>
                          </div>
                        </div>
                      );
                    })}

                    <div className="glass-panel" style={{ padding: '1rem', background: 'rgba(139,92,246,0.03)', borderColor: 'rgba(139,92,246,0.1)' }}>
                      <p style={{ fontSize: '0.825rem', color: 'var(--text-secondary)', lineHeight: 1.4 }}>
                        💡 <strong>มุมมอง AI:</strong> {aiRecommend.aiInsights}
                      </p>
                    </div>

                    <button 
                      onClick={triggerSmartRebalance}
                      disabled={rebalancingProgress}
                      className="btn-primary glow-purple" 
                      style={{ width: '100%', justifyContent: 'center', padding: '1rem', marginTop: '0.5rem' }}
                    >
                      {rebalancingProgress ? (
                        <>
                          <RefreshCw style={{ animation: 'spin 1.5s linear infinite' }} size={18} />
                          กำลังปรับโครงสร้างพอร์ต...
                        </>
                      ) : (
                        <>
                          <Cpu size={18} />
                          ปรับโครงสร้างพอร์ตอัจฉริยะ (AI Smart Rebalance)
                        </>
                      )}
                    </button>
                  </div>
                )}
              </div>

              {/* AI Chatbot Wealth Coach */}
              <div className="glass-panel" style={{ padding: '2rem', display: 'flex', flexDirection: 'column', height: '530px' }}>
                <h3 style={{ fontSize: '1.25rem', fontWeight: 600, fontFamily: 'var(--font-display)', marginBottom: '1rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <MessageSquare size={18} style={{ color: 'var(--accent-purple)' }} />
                  สนทนากับ AI Wealth Coach ส่วนตัว
                </h3>

                {/* Messages log */}
                <div style={{ flexGrow: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '1rem', paddingRight: '0.5rem', marginBottom: '1rem', borderBottom: '1px solid var(--glass-border)' }}>
                  {chatMessages.map((msg, i) => (
                    <div 
                      key={i} 
                      style={{ 
                        alignSelf: msg.sender === 'user' ? 'flex-end' : 'flex-start',
                        maxWidth: '85%',
                        background: msg.sender === 'user' ? 'linear-gradient(135deg, #8b5cf6 0%, #6d28d9 100%)' : 'rgba(255,255,255,0.03)',
                        border: msg.sender === 'user' ? 'none' : '1px solid var(--glass-border)',
                        padding: '0.85rem 1.1rem',
                        borderRadius: msg.sender === 'user' ? '14px 14px 0 14px' : '14px 14px 14px 0',
                        fontSize: '0.875rem',
                        lineHeight: 1.45,
                        boxShadow: msg.sender === 'user' ? '0 4px 12px rgba(139, 92, 246, 0.15)' : 'none'
                      }}
                    >
                      {msg.sender === 'ai' ? renderBotText(msg.text) : msg.text}
                    </div>
                  ))}
                  
                  {aiTyping && (
                    <div style={{ alignSelf: 'flex-start', display: 'flex', alignItems: 'center', gap: '0.5rem', background: 'rgba(255,255,255,0.02)', padding: '0.75rem 1rem', borderRadius: '14px 14px 14px 0', border: '1px solid var(--glass-border)' }}>
                      <div style={{ width: '6px', height: '6px', borderRadius: '50%', backgroundColor: 'var(--accent-purple)', animation: 'bounce 1s infinite alternate' }} />
                      <div style={{ width: '6px', height: '6px', borderRadius: '50%', backgroundColor: 'var(--accent-purple)', animation: 'bounce 1s infinite alternate 0.2s' }} />
                      <div style={{ width: '6px', height: '6px', borderRadius: '50%', backgroundColor: 'var(--accent-purple)', animation: 'bounce 1s infinite alternate 0.4s' }} />
                      <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>AI กำลังคิดเชิงลึก...</span>
                    </div>
                  )}
                  <div ref={chatBottomRef} />
                </div>

                {/* Input box */}
                <form onSubmit={handleSendMessage} style={{ display: 'flex', gap: '0.5rem' }}>
                  <input 
                    type="text" 
                    placeholder="ถาม AI เช่น 'วิเคราะห์พอร์ตให้หน่อย' หรือ 'แนวโน้มคริปโต'" 
                    value={chatInput}
                    onChange={(e) => setChatInput(e.target.value)}
                    style={{ flexGrow: 1 }}
                  />
                  <button type="submit" className="btn-primary" style={{ padding: '0.75rem 1rem' }}>
                    <Send size={16} />
                  </button>
                </form>
              </div>

            </div>

            {/* Bounce animation helper */}
            <style>{`
              @keyframes bounce {
                from { transform: translateY(0); }
                to { transform: translateY(-4px); }
              }
            `}</style>
          </div>
        )}

        {/* SETTINGS AND TELEGRAM TAB */}
        {activeTab === 'settings' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '2rem' }}>
            <header>
              <h1 style={{ fontSize: '2.2rem', fontWeight: 800, fontFamily: 'var(--font-display)', display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                <Settings style={{ color: 'var(--accent-purple)' }} size={32} />
                ตั้งค่าระบบ & การแจ้งเตือน Telegram
              </h1>
              <p style={{ color: 'var(--text-secondary)', fontSize: '0.95rem', marginTop: '0.2rem' }}>เชื่อมต่อบอทความมั่งคั่งส่วนตัวเพื่อรับสัญญาณแจ้งเตือนราคาและความเคลื่อนไหวพอร์ตแบบเรียลไทม์</p>
            </header>

            <div style={{ display: 'grid', gridTemplateColumns: '1.2fr 1fr', gap: '2rem' }}>
              
              {/* Telegram Form Setup */}
              <div className="glass-panel" style={{ padding: '2rem', height: 'fit-content' }}>
                <h3 style={{ fontSize: '1.25rem', fontWeight: 600, fontFamily: 'var(--font-display)', marginBottom: '1rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <Send size={18} style={{ color: 'var(--accent-cyan)' }} />
                  ตั้งค่าความปลอดภัย Telegram Bot
                </h3>

                {teleStatus.msg && (
                  <div className="glass-panel" style={{ 
                    padding: '1rem', 
                    marginBottom: '1rem', 
                    background: teleStatus.type === 'success' ? 'rgba(16,185,129,0.08)' : teleStatus.type === 'error' ? 'rgba(244,63,94,0.08)' : 'rgba(255,255,255,0.02)',
                    borderColor: teleStatus.type === 'success' ? 'rgba(16,185,129,0.25)' : teleStatus.type === 'error' ? 'rgba(244,63,94,0.25)' : 'var(--glass-border)',
                    fontSize: '0.825rem',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '0.5rem'
                  }}>
                    {teleStatus.type === 'success' ? <ShieldCheck size={16} style={{ color: 'var(--accent-emerald)' }} /> : <AlertCircle size={16} style={{ color: 'var(--accent-rose)' }} />}
                    <span>{teleStatus.msg}</span>
                  </div>
                )}

                <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
                  
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                    <label style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-secondary)' }}>Telegram Bot Token</label>
                    <input 
                      type="password" 
                      placeholder="กรอก Bot Token ของคุณที่ได้จาก @BotFather" 
                      value={botToken}
                      onChange={(e) => setBotToken(e.target.value)}
                      style={{ width: '100%' }}
                    />
                  </div>

                  <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                    <label style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-secondary)' }}>Telegram Chat ID</label>
                    <input 
                      type="text" 
                      placeholder="กรอก Chat ID ของคุณจาก @userinfobot" 
                      value={chatId}
                      onChange={(e) => setChatId(e.target.value)}
                      style={{ width: '100%' }}
                    />
                  </div>

                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                      <label style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-secondary)' }}>LINE Channel Access Token</label>
                      <input
                        type="password"
                        placeholder="Messaging API token"
                        value={lineChannelAccessToken}
                        onChange={(e) => setLineChannelAccessToken(e.target.value)}
                        style={{ width: '100%' }}
                      />
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                      <label style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-secondary)' }}>LINE Target ID</label>
                      <input
                        type="text"
                        placeholder="User / Group / Room ID"
                        value={lineTargetId}
                        onChange={(e) => setLineTargetId(e.target.value)}
                        style={{ width: '100%' }}
                      />
                    </div>
                  </div>

                  <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                    <label style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-secondary)' }}>LINE Notify Token (Legacy fallback)</label>
                    <input
                      type="password"
                      placeholder="ใช้เมื่อยังไม่มี Messaging API target"
                      value={lineNotifyToken}
                      onChange={(e) => setLineNotifyToken(e.target.value)}
                      style={{ width: '100%' }}
                    />
                  </div>

                  {/* Flow Steps instructions */}
                  <div className="glass-panel" style={{ padding: '1rem', background: 'rgba(255,255,255,0.01)', fontSize: '0.8rem', lineHeight: 1.5, color: 'var(--text-secondary)' }}>
                    <strong style={{ color: '#fff', display: 'block', marginBottom: '0.4rem' }}>💡 ขั้นตอนการสร้าง Telegram Bot และรับแจ้งเตือน:</strong>
                    1. เข้าแอป Telegram ค้นหาบอทชื่อ <strong>@BotFather</strong> พิมพ์ส่งข้อความ <code>/newbot</code><br />
                    2. ทำตามขั้นตอน ตั้งชื่อบอท จะได้รับ <strong>Token</strong> ยาวๆ คัดลอกมาวางด้านบน<br />
                    3. พิมพ์ค้นหาแชทบอท <strong>@userinfobot</strong> พิมพ์ส่งข้อความอะไรก็ได้ จะได้เลข <strong>Chat ID</strong> (เช่น <code>987654321</code>)<br />
                    4. <strong>สำคัญที่สุด:</strong> ต้องกดเริ่มใช้งาน (Start) บอทที่คุณเพิ่งสร้างขึ้นมาในแชทก่อนจะทำการทดสอบ!
                  </div>

                  <div style={{ display: 'flex', gap: '1rem', marginTop: '0.5rem' }}>
                    <button onClick={handleSaveTelegram} className="btn-secondary" style={{ flex: 1, justifyContent: 'center' }}>
                      บันทึกการตั้งค่า
                    </button>
                    <button onClick={handleTestTelegram} disabled={teleStatus.loading} className="btn-primary" style={{ flex: 1.3, justifyContent: 'center', background: 'linear-gradient(135deg, #06b6d4 0%, #0891b2 100%)', boxShadow: '0 4px 15px rgba(6, 182, 212, 0.3)' }}>
                      {teleStatus.loading ? 'กำลังเชื่อมต่อ...' : '🚀 ทดสอบส่ง Alert จริง'}
                    </button>
                  </div>

                </div>
              </div>

              {/* LLM SERVER & ENGINE CONFIGURATION CARD */}
              <div className="glass-panel" style={{ padding: '2rem', height: 'fit-content' }}>
                <h3 style={{ fontSize: '1.25rem', fontWeight: 600, fontFamily: 'var(--font-display)', marginBottom: '1rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <Cpu size={18} style={{ color: 'var(--accent-purple)' }} />
                  ตั้งค่าสมองกล AI (LLM Connection Hub)
                </h3>

                {llmVerifyStatus.msg && (
                  <div className="glass-panel" style={{ 
                    padding: '1rem', 
                    marginBottom: '1rem', 
                    background: llmVerifyStatus.type === 'success' ? 'rgba(16,185,129,0.08)' : llmVerifyStatus.type === 'error' ? 'rgba(244,63,94,0.08)' : 'rgba(255,255,255,0.02)',
                    borderColor: llmVerifyStatus.type === 'success' ? 'rgba(16,185,129,0.25)' : llmVerifyStatus.type === 'error' ? 'rgba(244,63,94,0.25)' : 'var(--glass-border)',
                    fontSize: '0.825rem',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '0.5rem'
                  }}>
                    {llmVerifyStatus.type === 'success' ? <ShieldCheck size={16} style={{ color: 'var(--accent-emerald)' }} /> : <AlertCircle size={16} style={{ color: 'var(--accent-rose)' }} />}
                    <span>{llmVerifyStatus.msg}</span>
                  </div>
                )}

                <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
                  
                  <div style={{ display: 'grid', gridTemplateColumns: '1.2fr 1fr', gap: '1rem' }}>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                      <label style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-secondary)' }}>ผู้ให้บริการ AI Engine</label>
                      <select 
                        value={llmProvider} 
                        onChange={(e) => {
                          const p = e.target.value;
                          setLlmProvider(p);
                          if (p === 'Gemini') setLlmModel('gemini-1.5-flash');
                          else if (p === 'OpenAI') setLlmModel('gpt-4o-mini');
                          else if (p === 'Ollama') setLlmModel('llama3');
                          else if (p === 'Claude') setLlmModel('claude-3-5-sonnet');
                          else if (p === 'Custom') setLlmModel('default');
                        }}
                      >
                        <option value="Gemini">Google Gemini API</option>
                        <option value="OpenAI">OpenAI API</option>
                        <option value="Claude">Anthropic Claude</option>
                        <option value="Ollama">Ollama / Local (เครื่องเรา)</option>
                        <option value="Custom">⚡ Custom (OpenAI-compatible Proxy)</option>
                      </select>
                    </div>

                    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                      <label style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-secondary)' }}>รหัสรุ่น (Model ID)</label>
                      {fetchedModels && fetchedModels.length > 0 ? (
                        <div style={{ display: 'flex', gap: '0.5rem' }}>
                          <select 
                            value={llmModel} 
                            onChange={(e) => setLlmModel(e.target.value)}
                            style={{ flexGrow: 1 }}
                          >
                            {fetchedModels.map(m => (
                              <option key={m} value={m}>{m}</option>
                            ))}
                          </select>
                          <button 
                            type="button" 
                            onClick={() => setFetchedModels([])}
                            className="btn-secondary"
                            style={{ padding: '0.5rem 0.75rem', fontSize: '0.75rem', whiteSpace: 'nowrap' }}
                          >
                            พิมพ์เอง ✏️
                          </button>
                        </div>
                      ) : (
                        <input 
                          type="text" 
                          placeholder="e.g. gemini-1.5-flash"
                          value={llmModel}
                          onChange={(e) => setLlmModel(e.target.value)}
                          style={{ width: '100%' }}
                        />
                      )}
                    </div>
                  </div>

                  {llmProvider !== 'Ollama' && llmProvider !== 'Custom' && (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                      <label style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-secondary)' }}>API Secret Key ของ {llmProvider}</label>
                      <input 
                        type="password" 
                        placeholder={`กรอก API Key เพื่อขับเคลื่อนสมองกล ${llmProvider}`} 
                        value={llmApiKey}
                        onChange={(e) => setLlmApiKey(e.target.value)}
                        style={{ width: '100%' }}
                      />
                    </div>
                  )}

                  {(llmProvider === 'Ollama' || llmProvider === 'OpenAI') && (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                      <label style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-secondary)' }}>Custom Server API Endpoint (ถ้ามี)</label>
                      <div style={{ display: 'flex', gap: '0.5rem' }}>
                        <input 
                          type="text" 
                          placeholder={llmProvider === 'Ollama' ? "http://localhost:11434" : "https://api.openai.com/v1"} 
                          value={llmEndpoint}
                          onChange={(e) => setLlmEndpoint(e.target.value)}
                          style={{ flexGrow: 1 }}
                        />
                        {llmProvider === 'Ollama' && (
                          <button
                            type="button"
                            onClick={handleFetchModels}
                            disabled={fetchingModels}
                            className="btn-secondary"
                            style={{ whiteSpace: 'nowrap', display: 'flex', alignItems: 'center', gap: '0.3rem' }}
                          >
                            <RefreshCw size={12} style={{ animation: fetchingModels ? 'spin 1.5s linear infinite' : 'none' }} />
                            ดึงข้อมูลรุ่น
                          </button>
                        )}
                      </div>
                    </div>
                  )}

                  {/* Custom OpenAI-compatible proxy fields */}
                  {llmProvider === 'Custom' && (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem', padding: '1.25rem', background: 'rgba(6,182,212,0.04)', border: '1px solid rgba(6,182,212,0.15)', borderRadius: '10px' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.25rem' }}>
                        <div style={{ width: '6px', height: '6px', borderRadius: '50%', backgroundColor: 'var(--accent-cyan)', boxShadow: '0 0 6px #06b6d4' }} />
                        <span style={{ fontSize: '0.8rem', fontWeight: 700, color: 'var(--accent-cyan)' }}>OpenAI-Compatible Proxy Config</span>
                      </div>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                        <label style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-secondary)' }}>Server Base URL <span style={{ color: 'var(--accent-rose)' }}>*</span> (required)</label>
                        <div style={{ display: 'flex', gap: '0.5rem' }}>
                          <input 
                            type="text" 
                            placeholder="e.g. http://localhost:20128  หรือ  https://openrouter.ai/api" 
                            value={llmEndpoint}
                            onChange={(e) => setLlmEndpoint(e.target.value)}
                            style={{ flexGrow: 1, borderColor: llmEndpoint ? 'var(--glass-border)' : 'rgba(244,63,94,0.4)' }}
                          />
                          <button
                            type="button"
                            onClick={handleFetchModels}
                            disabled={fetchingModels}
                            className="btn-secondary"
                            style={{ whiteSpace: 'nowrap', display: 'flex', alignItems: 'center', gap: '0.3rem', borderColor: 'rgba(6,182,212,0.3)', color: 'var(--accent-cyan)' }}
                          >
                            <RefreshCw size={12} style={{ animation: fetchingModels ? 'spin 1.5s linear infinite' : 'none' }} />
                            ดึงข้อมูลรุ่น
                          </button>
                        </div>
                        <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>ระบบจะเชื่อมต่อ <code style={{ color: 'var(--accent-cyan)' }}>{llmEndpoint || 'http://your-server'}/v1/models</code> เพื่อโหลดรุ่นโมเดล</span>
                      </div>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                        <label style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-secondary)' }}>API Key / Bearer Token (ถ้า proxy ต้องการ auth)</label>
                        <input 
                          type="password" 
                          placeholder="กรอก NINEROUTER_KEY หรือ API Key (ว่างไว้ได้ถ้า proxy ไม่ต้องการ auth)"
                          value={llmApiKey}
                          onChange={(e) => setLlmApiKey(e.target.value)}
                          style={{ width: '100%' }}
                        />
                      </div>
                      <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', lineHeight: 1.5, borderTop: '1px solid var(--glass-border)', paddingTop: '0.75rem' }}>
                        ✅ รองรับ: <strong style={{ color: 'var(--text-secondary)' }}>9Router (http://localhost:20128) ⚡</strong>, LM Studio, vLLM, Groq, Together AI, OpenRouter, LiteLLM และทุก server ที่เปิด <code>/v1/chat/completions</code>
                      </div>
                    </div>
                  )}

                  <div className="glass-panel" style={{ padding: '1rem', background: 'rgba(255,255,255,0.01)', fontSize: '0.8rem', lineHeight: 1.45, color: 'var(--text-secondary)' }}>
                    🤖 <strong>การตั้งค่าสมองกล AI:</strong> เมื่อเปิดใช้โมเดลจริง ระบบห้องแชทวิเคราะห์และการให้คำแนะนำในการจัดสัดส่วนพอร์ตจะส่งข้อมูลจริงตรงไปประมวลผลทันที ทำให้อภิปรายสไตล์พอร์ตและการลงทุนด้วยขีดความสามารถขั้นสูงอย่างถูกต้องแม่นยำครับ
                  </div>

                  <div style={{ display: 'flex', gap: '1rem', marginTop: '0.5rem' }}>
                    <button onClick={handleSaveLLM} className="btn-secondary" style={{ flex: 1, justifyContent: 'center' }}>
                      บันทึกคีย์
                    </button>
                    <button onClick={handleVerifyLLM} disabled={llmVerifyStatus.loading} className="btn-primary" style={{ flex: 1.3, justifyContent: 'center', background: 'linear-gradient(135deg, #8b5cf6 0%, #7c3aed 100%)', boxShadow: '0 4px 15px rgba(139, 92, 246, 0.3)' }}>
                      {llmVerifyStatus.loading ? 'กำลังเชื่อมโยง...' : '🧠 Verify Connection'}
                    </button>
                  </div>

                </div>
              </div>

              {/* Price Alerts limits Configuration */}
              <div className="glass-panel" style={{ padding: '2rem' }}>
                <h3 style={{ fontSize: '1.25rem', fontWeight: 600, fontFamily: 'var(--font-display)', marginBottom: '1.25rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <Bell size={18} style={{ color: 'var(--accent-purple)' }} />
                  ตั้งค่าดักสัญญาณแจ้งเตือนราคา (Price Alert Trigger)
                </h3>

                {/* Create Alert Form */}
                <form onSubmit={handleAddAlert} style={{ display: 'flex', flexDirection: 'column', gap: '1rem', marginBottom: '1.5rem', paddingBottom: '1.5rem', borderBottom: '1px solid var(--glass-border)' }}>
                  
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                      <label style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-secondary)' }}>สินทรัพย์</label>
                      <select value={newAlertAssetId} onChange={(e) => setNewAlertAssetId(e.target.value)}>
                        <optgroup label="คริปโต">
                          <option value="BTC">BTC (Bitcoin)</option>
                          <option value="ETH">ETH (Ethereum)</option>
                          <option value="SOL">SOL (Solana)</option>
                        </optgroup>
                        <optgroup label="กองทุนรวม">
                          <option value="SCBUSA">SCBUSA</option>
                          <option value="B-CARE">B-CARE</option>
                          <option value="K-SET50">K-SET50</option>
                        </optgroup>
                        <optgroup label="Forex">
                          <option value="EUR_USD">EUR/USD</option>
                          <option value="USD_JPY">USD/JPY</option>
                          <option value="GBP_USD">GBP/USD</option>
                        </optgroup>
                      </select>
                    </div>

                    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                      <label style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-secondary)' }}>เงื่อนไขเกณฑ์</label>
                      <select value={newAlertCondition} onChange={(e) => setNewAlertCondition(e.target.value)}>
                        <option value="above">ราคาสูงกว่า หรือเท่ากับ (📈)</option>
                        <option value="below">ราคาต่ำกว่า หรือเท่ากับ (📉)</option>
                      </select>
                    </div>
                  </div>

                  <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                    <label style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-secondary)' }}>มูลค่าเป้าหมาย ($ หรือ บาท หรือ อัตราแลกเปลี่ยน)</label>
                    <div style={{ display: 'flex', gap: '0.5rem' }}>
                      <input 
                        type="number" 
                        step="0.0001" 
                        placeholder="70000 หรือ 150" 
                        value={newAlertValue}
                        onChange={(e) => setNewAlertValue(e.target.value)}
                        style={{ flexGrow: 1 }}
                      />
                      <button type="submit" className="btn-primary" style={{ whiteSpace: 'nowrap' }}>
                        + เพิ่มเกณฑ์แจ้งเตือน
                      </button>
                    </div>
                  </div>

                </form>

                {/* List of Active Price Alerts */}
                <h4 style={{ fontSize: '0.95rem', fontWeight: 600, color: 'var(--text-secondary)', marginBottom: '0.75rem' }}>เกณฑ์ดักราคาที่ทำงานอยู่:</h4>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', maxHeight: '180px', overflowY: 'auto' }}>
                  {settings.alerts && settings.alerts.length > 0 ? (
                    settings.alerts.map(al => (
                      <div key={al.id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '0.75rem 1rem', background: 'rgba(255, 255, 255, 0.02)', border: '1px solid var(--glass-border)', borderRadius: '8px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                          <span style={{ fontSize: '0.85rem', fontWeight: 700, color: '#f8fafc' }}>{al.assetId}</span>
                          <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                            เมื่อราคา {al.condition === 'above' ? 'ทะลุสูงกว่า' : 'ดิ่งต่ำกว่า'} <strong>{al.value.toLocaleString()}</strong>
                          </span>
                        </div>
                        <button 
                          onClick={() => handleRemoveAlert(al.id)}
                          style={{ background: 'none', border: 'none', color: 'var(--accent-rose)', cursor: 'pointer', padding: '0.2rem', transition: 'transform 0.2s' }}
                          onMouseOver={(e) => e.currentTarget.style.transform = 'scale(1.15)'}
                          onMouseOut={(e) => e.currentTarget.style.transform = 'scale(1.0)'}
                        >
                          <Trash2 size={16} />
                        </button>
                      </div>
                    ))
                  ) : (
                    <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>ไม่มีเกณฑ์ตรวจจับราคาทำงานในขณะนี้</p>
                  )}
                </div>

              </div>

              {/* MCP & CONNECTORS CONFIGURATION HUB CARD */}
              <div className="glass-panel" style={{ padding: '2rem', height: 'fit-content' }}>
                <h3 style={{ fontSize: '1.25rem', fontWeight: 600, fontFamily: 'var(--font-display)', marginBottom: '1.25rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <Activity size={18} style={{ color: 'var(--accent-cyan)' }} />
                  ตั้งค่าดึงข้อมูลภายนอก (MCP & Connectors)
                </h3>

                {/* Blinking Live Connection Status Panel */}
                <div className="glass-panel" style={{ 
                  padding: '1.25rem', 
                  marginBottom: '1.5rem', 
                  background: mcpEnabled ? 'rgba(16,185,129,0.04)' : 'rgba(244,63,94,0.04)',
                  borderColor: mcpEnabled ? 'rgba(16,185,129,0.2)' : 'rgba(244,63,94,0.2)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between'
                }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                    <div style={{ 
                      width: '10px', 
                      height: '10px', 
                      borderRadius: '50%', 
                      backgroundColor: mcpEnabled ? 'var(--accent-emerald)' : 'var(--accent-rose)', 
                      boxShadow: mcpEnabled ? '0 0 10px #10b981' : '0 0 10px #f43f5e',
                      animation: mcpEnabled ? 'pulseGlow 2s infinite' : 'none' 
                    }} />
                    <div>
                      <span style={{ fontSize: '0.85rem', fontWeight: 700, color: '#f8fafc' }}>
                        สถานะ MCP: {mcpEnabled ? 'LIVE CONNECTED' : 'OFFLINE (DISCONNECTED)'}
                      </span>
                      <p style={{ fontSize: '0.725rem', color: 'var(--text-secondary)', marginTop: '0.15rem', lineHeight: 1.3 }}>
                        {mcpEnabled ? 'บอทกำลังสตรีมดัชนีผ่าน Model Context Protocol (MCP)' : 'บอททำงานในโหมดจัดสเปกจำลองออฟไลน์'}
                      </p>
                    </div>
                  </div>
                  <label className="switch-container" style={{ position: 'relative', display: 'inline-block', width: '44px', height: '24px' }}>
                    <input 
                      type="checkbox" 
                      checked={mcpEnabled} 
                      onChange={(e) => {
                        const v = e.target.checked;
                        setMcpEnabled(v);
                        handleSaveMCP(v, mcpServerUrl, mcpConnectors);
                      }} 
                      style={{ opacity: 0, width: 0, height: 0 }}
                    />
                    <span style={{
                      position: 'absolute', cursor: 'pointer', top: 0, left: 0, right: 0, bottom: 0,
                      backgroundColor: mcpEnabled ? 'var(--accent-emerald)' : 'rgba(255,255,255,0.08)',
                      transition: '.3s ease', borderRadius: '24px',
                      boxShadow: mcpEnabled ? '0 0 8px rgba(16, 185, 129, 0.4)' : 'none'
                    }}>
                      <span style={{
                        position: 'absolute', content: '""', height: '18px', width: '18px', left: '3px', bottom: '3px',
                        backgroundColor: 'white', transition: '.3s ease', borderRadius: '50%',
                        transform: mcpEnabled ? 'translateX(20px)' : 'none'
                      }} />
                    </span>
                  </label>
                </div>

                {mcpEnabled && (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem', marginBottom: '1.5rem' }}>
                    <label style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-secondary)' }}>MCP Host / Server URL</label>
                    <div style={{ display: 'flex', gap: '0.5rem' }}>
                      <input 
                        type="text" 
                        placeholder="e.g. http://localhost:3000/mcp"
                        value={mcpServerUrl}
                        onChange={(e) => setMcpServerUrl(e.target.value)}
                        style={{ flexGrow: 1 }}
                      />
                      <button 
                        onClick={() => handleSaveMCP(mcpEnabled, mcpServerUrl, mcpConnectors)} 
                        className="btn-secondary" 
                        style={{ padding: '0.75rem 1rem' }}
                      >
                        เชื่อมโยง Host
                      </button>
                    </div>
                  </div>
                )}

                <h4 style={{ fontSize: '0.9rem', fontWeight: 600, color: 'var(--text-secondary)', marginBottom: '0.75rem' }}>พอร์ทัล Data Connectors ที่เปิดใช้งาน:</h4>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.65rem' }}>
                  {[
                    { key: 'yahoo', label: 'Yahoo Finance Feed (กองทุนรวมหลัก)', desc: 'ดึงระดับปิดราคา SCB, Bualuang และกองทุนดัชนีอัตโนมัติ' },
                    { key: 'binance', label: 'Binance Live Ticker (บิตคอยน์/คริปโต)', desc: 'เชื่อมต่อเว็บบลูชิพดึงอัตราเทรด BTC/ETH สดผ่าน WebSocket' },
                    { key: 'forex', label: 'Open Exchange Rates Feed (ตลาดฟอเร็กซ์)', desc: 'สตรีมราคา EUR/USD และคู่เงินสากลตรงตามอัตราตลาดเสรี' }
                  ].map(conn => (
                    <div key={conn.key} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '0.75rem 1rem', background: 'rgba(255, 255, 255, 0.01)', border: '1px solid var(--glass-border)', borderRadius: '10px' }}>
                      <div>
                        <span style={{ fontSize: '0.85rem', fontWeight: 700, color: '#f8fafc' }}>{conn.label}</span>
                        <p style={{ fontSize: '0.725rem', color: 'var(--text-muted)', marginTop: '0.15rem' }}>{conn.desc}</p>
                      </div>
                      <label className="switch-container" style={{ position: 'relative', display: 'inline-block', width: '38px', height: '20px' }}>
                        <input 
                          type="checkbox" 
                          checked={mcpConnectors[conn.key]} 
                          onChange={(e) => {
                            const updated = { ...mcpConnectors, [conn.key]: e.target.checked };
                            setMcpConnectors(updated);
                            handleSaveMCP(mcpEnabled, mcpServerUrl, updated);
                          }} 
                          style={{ opacity: 0, width: 0, height: 0 }}
                        />
                        <span style={{
                          position: 'absolute', cursor: 'pointer', top: 0, left: 0, right: 0, bottom: 0,
                          backgroundColor: mcpConnectors[conn.key] ? 'var(--accent-cyan)' : 'rgba(255,255,255,0.05)',
                          transition: '.3s ease', borderRadius: '20px'
                        }}>
                          <span style={{
                            position: 'absolute', content: '""', height: '14px', width: '14px', left: '3px', bottom: '3px',
                            backgroundColor: 'white', transition: '.3s ease', borderRadius: '50%',
                            transform: mcpConnectors[conn.key] ? 'translateX(18px)' : 'none'
                          }} />
                        </span>
                      </label>
                    </div>
                  ))}
                </div>

              </div>

            </div>
          </div>
        )}

      </main>

    </div>
  );
}
