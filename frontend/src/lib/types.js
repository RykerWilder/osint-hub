// Icon of every data type
export const TYPE_ICON = {
  username: 'user',
  email: 'mail',
  phone: 'phone',
  domain: 'globe',
  ip: 'network',
  file: 'file',
}

export const DEFAULT_TYPES = [
  { id: 'username', label: 'Username', placeholder: 'e.g. john.doe' },
  { id: 'email', label: 'Email', placeholder: 'name@example.com' },
  { id: 'phone', label: 'Phone', placeholder: '+1 202 555 0143' },
  { id: 'domain', label: 'Domain', placeholder: 'example.com' },
  { id: 'ip', label: 'IP', placeholder: '8.8.8.8' },
  { id: 'file', label: 'File', placeholder: 'Drop a file here' },
]

// Guess the type from the typed text (the user can always change it by hand).
// "file" is never guessed: it is chosen by hand or by dropping a file on the page.
export function detectType(raw) {
  const s = (raw || '').trim()
  if (!s) return null
  if (/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(s)) return 'email'
  if (/^\d{1,3}(\.\d{1,3}){3}$/.test(s)) return 'ip'
  if (s.split(':').length > 2 && /^[0-9a-f:]+$/i.test(s)) return 'ip'
  if (/^\+?[\d\s().-]{6,}$/.test(s) && s.replace(/\D/g, '').length >= 6) return 'phone'
  if (/^(https?:\/\/)?([a-z0-9-]+\.)+[a-z]{2,}(\/\S*)?$/i.test(s)) return 'domain'
  return 'username'
}
