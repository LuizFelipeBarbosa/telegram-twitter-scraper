import { useEffect, useState } from "react";

interface AsyncState<T> {
  data: T | null;
  error: Error | null;
  loading: boolean;
}

export function useAsyncResource<T>(loader: () => Promise<T>, deps: ReadonlyArray<unknown>): AsyncState<T> {
  const [state, setState] = useState<AsyncState<T>>({
    data: null,
    error: null,
    loading: true,
  });

  useEffect(() => {
    let cancelled = false;
    setState((previous) => ({ ...previous, loading: true, error: null }));
    loader()
      .then((data) => {
        if (!cancelled) {
          setState({ data, error: null, loading: false });
        }
      })
      .catch((error: Error) => {
        if (!cancelled) {
          setState({ data: null, error, loading: false });
        }
      });

    return () => {
      cancelled = true;
    };
  }, deps);

  return state;
}
