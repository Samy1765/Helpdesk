import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../services/api";

/** GET a resource, with loading/error state and a manual reload. Optional polling interval (ms). */
export function useApi<T>(path: string | null, pollMs?: number) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(!!path);
  const alive = useRef(true);

  const load = useCallback(async (silent = false) => {
    if (!path) return;
    if (!silent) setLoading(true);
    try {
      const d = await api.get<T>(path);
      if (alive.current) { setData(d); setError(null); }
    } catch (e) {
      if (alive.current) setError(e instanceof Error ? e.message : "Failed to load");
    } finally {
      if (alive.current) setLoading(false);
    }
  }, [path]);

  useEffect(() => {
    alive.current = true;
    load();
    let timer: number | undefined;
    if (pollMs) timer = window.setInterval(() => load(true), pollMs);
    return () => { alive.current = false; if (timer) window.clearInterval(timer); };
  }, [load, pollMs]);

  return { data, error, loading, reload: () => load(true), setData };
}
