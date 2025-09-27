let overlayEl: HTMLElement | null = null
let styleEl: HTMLStyleElement | null = null

export function showInterruptOverlay(text: string, onCancel: () => void) {
  if (!styleEl) {
    styleEl = document.createElement('style')
    styleEl.textContent = `
      .nf-interrupt-overlay{position:fixed;inset:0;z-index:300000;display:flex;align-items:center;justify-content:center;pointer-events:auto}
      .nf-interrupt-backdrop{position:absolute;inset:0;background:rgba(0,0,0,.48)}
      .nf-interrupt-box{position:relative;background:#fff;padding:16px 20px;border-radius:8px;min-width:220px;box-shadow:0 8px 24px rgba(0,0,0,.2);text-align:center}
      .nf-interrupt-text{margin-bottom:12px;color:#333;font-size:14px}
      .nf-interrupt-btn{display:inline-block;background:#f56c6c;color:#fff;border:none;border-radius:4px;padding:6px 12px;cursor:pointer}
      .nf-interrupt-btn:disabled{opacity:.6;cursor:not-allowed}
    `
    document.head.appendChild(styleEl)
  }
  if (overlayEl) return
  overlayEl = document.createElement('div')
  overlayEl.className = 'nf-interrupt-overlay'
  overlayEl.innerHTML = `
    <div class="nf-interrupt-backdrop"></div>
    <div class="nf-interrupt-box">
      <div class="nf-interrupt-text">${text || 'AI 生成中…'}</div>
      <button class="nf-interrupt-btn" id="nf-interrupt-btn">中断生成</button>
    </div>
  `
  document.body.appendChild(overlayEl)
  const btn = overlayEl.querySelector('#nf-interrupt-btn') as HTMLButtonElement | null
  if (btn) btn.onclick = () => { try { onCancel() } catch {} }
}

export function hideInterruptOverlay() {
  if (overlayEl && overlayEl.parentNode) overlayEl.parentNode.removeChild(overlayEl)
  overlayEl = null
}


