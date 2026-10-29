import { useCallback, useEffect, useRef, useState } from 'react'
import { api, subscribeToEvents } from '../api/client'
import type { AgentEvent, CheckRun, Requirement, RequirementResult } from '../api/types'

/** Starts a check, streams its agent events over SSE and loads the final result. */
export function useCheckRun() {
  const [run, setRun] = useState<CheckRun | null>(null)
  const [events, setEvents] = useState<AgentEvent[]>([])
  const [running, setRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const unsubscribe = useRef<(() => void) | null>(null)

  useEffect(() => () => unsubscribe.current?.(), [])

  const loadResult = useCallback(async (id: string) => {
    try {
      setRun(await api.getCheck(id))
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setRunning(false)
    }
  }, [])

  const start = useCallback(
    async (datasheetId: string, requirements: Requirement[]) => {
      unsubscribe.current?.()
      setError(null)
      setEvents([])
      setRun(null)
      setRunning(true)
      let created: CheckRun
      try {
        created = await api.startCheck(datasheetId, requirements)
      } catch (e) {
        setError((e as Error).message)
        setRunning(false)
        return
      }
      setRun(created)
      unsubscribe.current = subscribeToEvents(
        created.id,
        (event) => setEvents((prev) => (prev.some((p) => p.seq === event.seq) ? prev : [...prev, event])),
        () => void loadResult(created.id),
        () => void loadResult(created.id),
      )
    },
    [loadResult],
  )

  const applyUpdate = useCallback(
    async (updated: RequirementResult) => {
      setRun((prev) =>
        prev
          ? { ...prev, results: prev.results.map((r) => (r.requirement.id === updated.requirement.id ? updated : r)) }
          : prev,
      )
      if (run) {
        try {
          setRun(await api.getCheck(run.id)) // refresh server-computed summary
        } catch {
          /* keep optimistic state */
        }
      }
    },
    [run],
  )

  return { run, events, running, error, start, applyUpdate, clearError: () => setError(null) }
}
