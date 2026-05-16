import type { PluginInput, Hooks } from "@opencode-ai/plugin"

/**
 * StatusForwarderPlugin — forwards OpenCode server events into the stdout
 * JSONL stream so that CodeCome's run-agent.py wrapper can render them.
 *
 * Two families of events are handled:
 *   1. session.status (retry / busy / idle) — existing behaviour
 *   2. subagent lifecycle (created / updated / deleted) + heartbeat — NEW
 *
 * The plugin writes directly to process.stdout; each line is a standalone JSON
 * object.  run-agent.py consumes the same stdout pipe, so these lines are
 * interleaved with OpenCode's native --format json output.
 */

// ---------------------------------------------------------------------------
// Tunables (env)
// ---------------------------------------------------------------------------

const HEARTBEAT_INTERVAL_S = parseInt(
  process.env.CODECOME_SUBAGENT_HEARTBEAT_INTERVAL_S || "30",
  10
)
const HEARTBEAT_INTERVAL_MS = HEARTBEAT_INTERVAL_S * 1000

// ---------------------------------------------------------------------------
// Subagent tracker
// ---------------------------------------------------------------------------

interface TrackedSubagent {
  sessionID: string
  parentID: string
  title: string
  createdAt: number
  lastUpdateAt: number
  summary?: { additions: number; deletions: number; files: number }
}

const trackedSubagents = new Map<string, TrackedSubagent>()

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function emitSubagentStatus(
  sessionID: string,
  statusType: string,
  extra?: Record<string, any>
) {
  const payload = {
    type: "subagent.status",
    properties: {
      sessionID,
      statusType,
      ...extra,
    },
  }
  process.stdout.write(JSON.stringify(payload) + "\n")
}

// ---------------------------------------------------------------------------
// Plugin entrypoint
// ---------------------------------------------------------------------------

export default async function StatusForwarderPlugin(
  _input: PluginInput
): Promise<Hooks> {
  if (!process.env._CODECOME_INSIDE_HARNESS) {
    return {}
  }
  // Heartbeat timer: every N seconds, emit a heartbeat for any tracked
  // subagent that has not produced an update in the last interval.
  let heartbeatTimer: ReturnType<typeof setInterval> | null = null

  if (HEARTBEAT_INTERVAL_MS > 0) {
    heartbeatTimer = setInterval(() => {
      const now = Date.now()
      for (const [sessionID, subagent] of trackedSubagents) {
        const elapsedMs = now - subagent.lastUpdateAt
        if (elapsedMs >= HEARTBEAT_INTERVAL_MS) {
          emitSubagentStatus(sessionID, "heartbeat", {
            title: subagent.title,
            elapsedMs,
            summary: subagent.summary,
          })
        }
      }
    }, HEARTBEAT_INTERVAL_MS)
  }

  // The hooks object returned to OpenCode.
  const hooks: Hooks = {
    async event({ event }) {
      // ---------------------------------------------------------------
      // 1. Existing: forward session.status (retry / busy / idle)
      // ---------------------------------------------------------------
      if (event.type === "session.status") {
        process.stdout.write(JSON.stringify(event) + "\n")
        return
      }

      // ---------------------------------------------------------------
      // 2. Subagent lifecycle tracking
      // ---------------------------------------------------------------
      if (
        event.type === "session.created" ||
        event.type === "session.updated" ||
        event.type === "session.deleted"
      ) {
        // Use `any` cast because the Event union does not expose .properties
        // directly; we rely on runtime shape.
        const info = (event as any).properties?.info
        const sessionID: string | undefined = info?.id
        const parentID: string | undefined = info?.parentID

        // Only track sessions that have a parent (i.e. subagents).
        if (!sessionID || !parentID) return

        if (event.type === "session.created") {
          const subagent: TrackedSubagent = {
            sessionID,
            parentID,
            title: info?.title || "(untitled subagent)",
            createdAt: Date.now(),
            lastUpdateAt: Date.now(),
            summary: info?.summary,
          }
          trackedSubagents.set(sessionID, subagent)
          emitSubagentStatus(sessionID, "created", {
            title: subagent.title,
            summary: subagent.summary,
          })
        } else if (event.type === "session.updated") {
          const subagent = trackedSubagents.get(sessionID)
          if (!subagent) return

          const title: string = info?.title || subagent.title
          const summary = info?.summary
          const now = Date.now()

          subagent.title = title
          subagent.lastUpdateAt = now
          if (summary) {
            subagent.summary = summary
          }

          emitSubagentStatus(sessionID, "updated", {
            title: subagent.title,
            summary: subagent.summary,
          })
        } else if (event.type === "session.deleted") {
          const subagent = trackedSubagents.get(sessionID)
          if (!subagent) return

          trackedSubagents.delete(sessionID)
          emitSubagentStatus(sessionID, "finished", {
            title: subagent.title,
            summary: subagent.summary,
          })
        }
      }
    },
  }

  return hooks
}
