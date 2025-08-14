export function useRouteHashQuery(): Record<string, string> {
  const hash = window.location.hash || ''
  const idx = hash.indexOf('?')
  if (idx === -1) return {}
  const query = hash.substring(idx + 1)
  const params = new URLSearchParams(query)
  const out: Record<string, string> = {}
  params.forEach((v, k) => { out[k] = v })
  return out
} 