/**
 * Converte erros de fetch/API em mensagens amigáveis em português.
 * Trata erros de rede (servidor offline) separadamente de erros HTTP.
 */
export function parseApiError(err, fallback = 'Ocorreu um erro inesperado.') {
  const msg = err?.message || ''
  if (
    msg === 'Failed to fetch' ||
    msg === 'Load failed' ||
    msg === 'NetworkError when attempting to fetch resource.' ||
    msg.includes('fetch')
  ) {
    return 'Servidor indisponível. Verifique se o backend está em execução.'
  }
  return msg || fallback
}

/**
 * Wrapper de fetch que extrai `detail` do JSON de erro automaticamente.
 * Lança um Error com a mensagem já em português.
 */
export async function apiFetch(url, options = {}) {
  let res
  try {
    res = await fetch(url, options)
  } catch (err) {
    throw new Error(parseApiError(err))
  }

  if (!res.ok) {
    let detail = `Erro ${res.status}`
    try {
      const data = await res.json()
      detail = data.detail || detail
    } catch {}
    throw new Error(detail)
  }

  return res
}
