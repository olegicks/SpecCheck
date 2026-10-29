import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { setupServer } from 'msw/node'
import { afterAll, afterEach, beforeAll } from 'vitest'
import { handlers } from '../mocks/handlers'

export const server = setupServer(...handlers)

beforeAll(() => server.listen({ onUnhandledFrame: 'error' }))
afterEach(() => {
  server.resetHandlers()
  cleanup()
  FakeEventSource.instances = []
})
afterAll(() => server.close())

/** Minimal EventSource stand-in (jsdom has none). Tests push events via `emit`. */
export class FakeEventSource {
  static instances: FakeEventSource[] = []
  static readonly CLOSED = 2
  readonly url: string
  readyState = 1
  onerror: (() => void) | null = null
  private listeners = new Map<string, ((e: MessageEvent) => void)[]>()

  constructor(url: string) {
    this.url = url
    FakeEventSource.instances.push(this)
  }

  addEventListener(type: string, listener: (e: MessageEvent) => void) {
    this.listeners.set(type, [...(this.listeners.get(type) ?? []), listener])
  }

  emit(type: string, data: unknown) {
    const event = new MessageEvent(type, { data: JSON.stringify(data) })
    this.listeners.get(type)?.forEach((l) => l(event))
  }

  close() {
    this.readyState = FakeEventSource.CLOSED
  }
}

Object.defineProperty(globalThis, 'EventSource', { value: FakeEventSource, writable: true })

// jsdom lacks these browser APIs used by the download helper.
URL.createObjectURL = () => 'blob:mock'
URL.revokeObjectURL = () => undefined
