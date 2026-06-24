import React, { useState, useEffect, useRef } from 'react';
import { useWebSocket } from '../hooks/useWebSocket';
import { formatSpainTime } from '../utils/dates';

function cleanTerminalText(value) {
  return String(value || '')
    .replace(/\u001b\[[0-?]*[ -/]*[@-~]/g, '')
    .replace(/\x1b\[[0-?]*[ -/]*[@-~]/g, '')
    .replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/g, '');
}

function LogEntry({ log }) {
  const levelColors = {
    'INFO': 'text-blue-400',
    'DEBUG': 'text-gray-400',
    'WARN': 'text-yellow-400',
    'ERROR': 'text-red-400',
  };
  
  const message = cleanTerminalText(log.message || log.text);

  return (
    <div className={`font-mono text-xs py-0.5 ${levelColors[log.level] || 'text-gray-300'}`}>
      <span className="text-gray-500">[{formatSpainTime(log.timestamp || log.time)}]</span>
      <span className="font-bold mr-2 ml-2">{log.level}</span>
      {log.phase && <span className="text-purple-400 bg-purple-400/10 px-1 rounded mr-2">{log.phase}</span>}
      <span className="ml-2">{message}</span>
    </div>
  );
}

export default function LiveLogs({ auditId }) {
  const [logs, setLogs] = useState([]);
  const logsEndRef = useRef(null);
  
  useWebSocket(`/ws/audits/${auditId}/logs`, (message) => {
    setLogs(prev => {
      const newLogs = [...prev, message];
      return newLogs.length > 1000 ? newLogs.slice(-1000) : newLogs;
    });
  });
  
  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [logs]);
  
  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold">Live Logs</h3>
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-green-400 animate-pulse"></div>
          <span className="text-sm text-green-400">Streaming</span>
        </div>
      </div>
      
      <div className="bg-gray-950 rounded-lg border border-gray-700 p-4 h-96 overflow-y-auto scrollbar">
        {logs.length === 0 ? (
          <div className="text-gray-500 py-8 text-center">
            No logs yet. Start an audit phase to see logs stream here.
          </div>
        ) : (
          <div className="space-y-0.5">
            {logs.map((log, i) => (
              <LogEntry key={i} log={log} />
            ))}
            <div ref={logsEndRef} />
          </div>
        )}
      </div>
    </div>
  );
}
