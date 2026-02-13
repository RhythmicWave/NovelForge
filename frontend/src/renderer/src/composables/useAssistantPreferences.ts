import { useAgentPreferences } from './useAgentPreferences'

// Backward-compatible wrapper: existing imports keep working,
// while the underlying state is now shared Agent preferences.
export function useAssistantPreferences() {
  return useAgentPreferences()
}
