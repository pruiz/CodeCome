import { useState, useEffect, useCallback } from 'react';
import { findingsApi } from '../services/api';

export function useFindings(auditId, params = {}, refetchInterval = 5000) {
  const [findings, setFindings] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  
  const fetchFindings = useCallback(async () => {
    if (!auditId) return;
    try {
      const data = await findingsApi.list(auditId, params);
      setFindings(data.findings);
      setTotal(data.total);
    } catch (error) {
      console.error('Failed to fetch findings:', error);
    } finally {
      setLoading(false);
    }
  }, [auditId, params]);
  
  useEffect(() => {
    fetchFindings();
    
    if (refetchInterval > 0) {
      const interval = setInterval(fetchFindings, refetchInterval);
      return () => clearInterval(interval);
    }
  }, [fetchFindings, refetchInterval]);
  
  return { findings, total, loading, refetch: fetchFindings };
}
