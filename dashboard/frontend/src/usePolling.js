import { useCallback, useEffect, useState } from 'react'

// Calls fetcher() now and then every `ms` milliseconds. fetcher must be a stable function.
export default function usePolling(fetcher, ms, enabled = true) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(false)

  const run = useCallback(async () => {
    try {
      setData(await fetcher())
      setError(false)
    } catch {
      setError(true)
    }
  }, [fetcher])

  useEffect(() => {
    if (!enabled) return undefined
    run()
    const id = setInterval(run, ms)
    return () => clearInterval(id)
  }, [run, ms, enabled])

  return { data, error, refresh: run }
}
