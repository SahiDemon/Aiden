import React, { useEffect, useRef } from 'react'

const WaveAnimation = ({ isActive, isSpeaking }) => {
  const canvasRef = useRef(null)
  const animationRef = useRef(null)
  const phaseRef = useRef(0)
  const transitionRef = useRef({ waves: 4, amplitude: 20, opacity: 0.4, baseY: 0 })

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return

    const ctx = canvas.getContext('2d')
    
    // Resize canvas to full viewport
    const resizeCanvas = () => {
      canvas.width = window.innerWidth
      canvas.height = window.innerHeight
      transitionRef.current.baseY = canvas.height - 120
    }
    
    resizeCanvas()
    window.addEventListener('resize', resizeCanvas)

    const draw = () => {
      const width = canvas.width
      const height = canvas.height
      
      ctx.clearRect(0, 0, width, height)

      // Define target values based on state
      let targetWaves, targetAmplitude, targetOpacity, targetBaseY, targetFrequency, targetSpeed
      
      if (!isActive && !isSpeaking) {
        // Idle state - subtle waves at bottom
        targetWaves = 4
        targetAmplitude = 20
        targetOpacity = 0.3
        targetBaseY = height - 120
        targetFrequency = 0.004
        targetSpeed = 0.015
      } else if (isActive && !isSpeaking) {
        // Listening state - moderate waves
        targetWaves = 8
        targetAmplitude = 50
        targetOpacity = 0.4
        targetBaseY = height - 200
        targetFrequency = 0.005
        targetSpeed = 0.06
      } else {
        // Speaking state - gentle waves (toned down)
        targetWaves = 10
        targetAmplitude = 40
        targetOpacity = 0.35
        targetBaseY = height - 180
        targetFrequency = 0.005
        targetSpeed = 0.05
      }

      // Smoothly transition to target values
      const transition = transitionRef.current
      const lerpSpeed = 0.08 // Increased for faster, smoother transitions
      
      transition.waves += (targetWaves - transition.waves) * lerpSpeed
      transition.amplitude += (targetAmplitude - transition.amplitude) * lerpSpeed
      transition.opacity += (targetOpacity - transition.opacity) * lerpSpeed
      transition.baseY += (targetBaseY - transition.baseY) * lerpSpeed
      
      const waves = Math.round(transition.waves)
      const baseAmplitude = transition.amplitude
      const baseOpacity = transition.opacity
      const baseY = transition.baseY

      // Draw waves
      for (let i = 0; i < waves; i++) {
        ctx.beginPath()
        
        for (let x = 0; x <= width; x += 2) {
          const offset = i * Math.PI / (waves / 2)
          const amplitude = baseAmplitude * (1 - i / (waves * 1.5))
          
          // Simpler wave calculation for smoother effect
          const y = baseY + 
            Math.sin(x * targetFrequency + phaseRef.current + offset) * amplitude +
            Math.sin(x * targetFrequency * 1.5 + phaseRef.current * 0.8) * (amplitude * 0.4)
          
          if (x === 0) {
            ctx.moveTo(x, y)
          } else {
            ctx.lineTo(x, y)
          }
        }

        // Color based on state
        let baseColor
        const opacity = baseOpacity * (1 - i / (waves * 2))
        
        if (isActive && !isSpeaking) {
          // Emerald/cyan gradient for listening
          const hue = 160 + i * 10
          baseColor = `hsla(${hue}, 70%, 55%, ${opacity})`
        } else if (isSpeaking) {
          // Subtle blue/purple gradient for speaking (toned down)
          const hue = 200 + i * 15
          baseColor = `hsla(${hue}, 65%, 60%, ${opacity})`
        } else {
          // Idle blue waves
          const hue = 210 + i * 20
          baseColor = `hsla(${hue}, 70%, 60%, ${opacity})`
        }
        
        ctx.strokeStyle = baseColor
        ctx.lineWidth = 2.5 - i * 0.15
        ctx.shadowBlur = 15
        ctx.shadowColor = baseColor
        ctx.stroke()
      }

      phaseRef.current += targetSpeed

      animationRef.current = requestAnimationFrame(draw)
    }

    draw()

    return () => {
      window.removeEventListener('resize', resizeCanvas)
      if (animationRef.current) {
        cancelAnimationFrame(animationRef.current)
      }
    }
  }, [isActive, isSpeaking])

  return (
    <canvas
      ref={canvasRef}
      className="absolute inset-0 w-full h-full pointer-events-none"
      style={{ 
        imageRendering: 'crisp-edges',
        zIndex: 1
      }}
    />
  )
}

export default WaveAnimation