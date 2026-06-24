import { useState, useEffect, useCallback } from 'react';
import { auditsApi } from '../services/api';

export function useAudits(refetchInterval = 5000) {
  const [audits, setAudits] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  
  const fetchAudits = useCallback(async () => {
    try {
      const data = await auditsApi.list();
      setAudits(data.audits);
      setTotal(data.total);
    } catch (error) {
      console.error('Failed to fetch audits:', error);
    } finally {
      setLoading(false);
    }
  }, []);
  
  useEffect(() => {
    fetchAudits();
    
    if (refetchInterval > 0) {
      const interval = setInterval(fetchAudits, refetchInterval);
      return () => clearInterval(interval);
    }
  }, [fetchAudits, refetchInterval]);
  
  return { audits, total, loading, refetch: fetchAudits };
}

export function useAudit(id, refetchInterval = 2000) {
  const [audit, setAudit] = useState(null);
  const [loading, setLoading] = useState(true);
  
  const fetchAudit = useCallback(async () => {
    try {
      const data = await auditsApi.get(id);
      setAudit(data);
    } catch (error) {
      console.error('Failed to fetch audit:', error);
    } finally {
      setLoading(false);
    }
  }, [id]);
  
  useEffect(() => {
    fetchAudit();
    
    if (refetchInterval > 0) {
      const interval = setInterval(fetchAudit, refetchInterval);
      return () => clearInterval(interval);
    }
  }, [fetchAudit, refetchInterval]);
  
  return { audit, loading, refetch: fetchAudit };
}
