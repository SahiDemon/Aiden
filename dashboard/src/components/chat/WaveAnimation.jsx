import React, { useEffect, useRef } from 'react'

// A bounded canvas keeps voice motion inexpensive on phones and large displays.
export default function WaveAnimation({ isActive, isSpeaking, isProcessing = false }) {
  const canvasRef = useRef(null)
  const stateRef = useRef({ isActive, isSpeaking, isProcessing })
  useEffect(() => { stateRef.current = { isActive, isSpeaking, isProcessing } }, [isActive, isSpeaking, isProcessing])
  useEffect(() => {
    const canvas = canvasRef.current
    const context = canvas.getContext('2d')
    if (!context) return
    const motionQuery = window.matchMedia('(prefers-reduced-motion: reduce)')
    let frame, width = 0, height = 0, phase = 0, previous = 0, amplitude = 16
    let visible = true
    let waveColor = getComputedStyle(canvas).getPropertyValue('--amber').trim() || '#d3b071'
    const resize = () => {
      const bounds = canvas.getBoundingClientRect()
      width = bounds.width; height = bounds.height
      const ratio = Math.min(window.devicePixelRatio || 1, 1.5)
      canvas.width = width * ratio; canvas.height = height * ratio
      context.setTransform(ratio, 0, 0, ratio, 0, 0)
    }
    const draw = time => {
      if (!visible || document.hidden) { frame = null; return }
      frame = requestAnimationFrame(draw)
      if (time - previous < 33) return
      const elapsed = Math.min(time - previous, 80) / 1000
      previous = time
      const state = stateRef.current
      const target = state.isActive ? 57 : state.isSpeaking ? 44 : state.isProcessing ? 25 : 17
      amplitude += (target - amplitude) * .08
      phase += elapsed * (state.isActive ? 2.5 : state.isSpeaking ? 1.9 : .55)
      context.clearRect(0, 0, width, height)
      for (let line = 0; line < 7; line++) {
        context.beginPath()
        for (let x = 0; x <= width; x += 4) {
          const envelope = Math.pow(Math.sin(Math.PI * x / width), 1.8)
          const y = height / 2 + envelope * amplitude * (Math.sin(x / width * 12 + phase + line * .32) + .4 * Math.sin(x / width * 21 - phase * .7 + line * .22))
          if (x === 0) context.moveTo(x, y); else context.lineTo(x, y)
        }
        context.strokeStyle = waveColor
        context.globalAlpha = .65 - line * .07
        context.lineWidth = line === 0 ? 1.7 : 1
        context.stroke()
      }
      if (motionQuery.matches) { cancelAnimationFrame(frame); frame = null }
    }
    const start = () => { if (!frame && visible && !document.hidden) frame = requestAnimationFrame(draw) }
    const visibility = () => { if (document.hidden) { cancelAnimationFrame(frame); frame = null } else start() }
    const observer = new ResizeObserver(() => { resize(); start() })
    observer.observe(canvas)
    const intersection = new IntersectionObserver(entries => { visible = entries[0].isIntersecting; if (visible) start(); else { cancelAnimationFrame(frame); frame = null } })
    intersection.observe(canvas)
    document.addEventListener('visibilitychange', visibility)
    motionQuery.addEventListener('change', start)
    const themeChanged = () => { waveColor = getComputedStyle(canvas).getPropertyValue('--amber').trim() || '#d3b071'; start() }
    window.addEventListener('aiden-theme-change', themeChanged)
    resize(); start()
    return () => { window.removeEventListener('aiden-theme-change', themeChanged); cancelAnimationFrame(frame); observer.disconnect(); intersection.disconnect(); document.removeEventListener('visibilitychange', visibility); motionQuery.removeEventListener('change', start) }
  }, [])
  return <canvas ref={canvasRef} className="wave-canvas" aria-hidden="true" />
}
