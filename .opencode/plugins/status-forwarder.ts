import type { PluginInput, Hooks } from "@opencode-ai/plugin"

export default async function StatusForwarderPlugin(_input: PluginInput): Promise<Hooks> {
  return {
    async event({ event }) {
      if (event.type === "session.status") {
        // We write directly to stdout. This injects the event into the 
        // line-by-line JSON stream that CodeCome's run-agent.py is reading!
        process.stdout.write(JSON.stringify(event) + "\n")
      }
    }
  }
}
