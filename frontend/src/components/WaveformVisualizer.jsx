import { useEffect, useRef } from 'react'

export default function WaveformVisualizer() {
  const canvasRef = useRef(null)
  const animationRef = useRef(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    const dpr = window.devicePixelRatio || 1

    const resize = () => {
      const rect = canvas.getBoundingClientRect()
      canvas.width = rect.width * dpr
      canvas.height = rect.height * dpr
      ctx.scale(dpr, dpr)
    }

    resize()
    window.addEventListener('resize', resize)

    let time = 0
    const bars = 60

    const draw = () => {
      const w = canvas.getBoundingClientRect().width
      const h = canvas.getBoundingClientRect().height

      ctx.clearRect(0, 0, w, h)

      const barWidth = w / bars
      const gap = 2

      for (let i = 0; i < bars; i++) {
        const x = i * barWidth
        const progress = i / bars

        const wave1 = Math.sin(progress * Math.PI * 2 + time * 0.02) * 0.5
        const wave2 = Math.sin(progress * Math.PI * 4 + time * 0.03) * 0.3
        const wave3 = Math.sin(progress * Math.PI * 6 + time * 0.015) * 0.2
        const combined = (wave1 + wave2 + wave3) * 0.5 + 0.5

        const barHeight = Math.max(2, combined * h * 0.8)

        const gradient = ctx.createLinearGradient(x, h / 2 - barHeight / 2, x, h / 2 + barHeight / 2)
        gradient.addColorStop(0, 'rgba(229, 62, 62, 0)')
        gradient.addColorStop(0.3, `rgba(229, 62, 62, ${0.3 + combined * 0.5})`)
        gradient.addColorStop(0.5, `rgba(229, 62, 62, ${0.5 + combined * 0.4})`)
        gradient.addColorStop(0.7, `rgba(229, 62, 62, ${0.3 + combined * 0.5})`)
        gradient.addColorStop(1, 'rgba(229, 62, 62, 0)')

        ctx.fillStyle = gradient
        ctx.beginPath()
        ctx.roundRect(
          x + gap / 2,
          h / 2 - barHeight / 2,
          barWidth - gap,
          barHeight,
          1
        )
        ctx.fill()
      }

      time++
      animationRef.current = requestAnimationFrame(draw)
    }

    draw()

    return () => {
      window.removeEventListener('resize', resize)
      if (animationRef.current) {
        cancelAnimationFrame(animationRef.current)
      }
    }
  }, [])

  return (
    <div className="waveform-visualizer">
      <canvas ref={canvasRef} />
    </div>
  )
}
