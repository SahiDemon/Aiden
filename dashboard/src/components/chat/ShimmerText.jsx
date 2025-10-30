import React from 'react'
import { motion } from 'framer-motion'
import './ShimmerText.css'

const ShimmerText = ({ text, isActive, className = "" }) => {
  return (
    <motion.div
      className={`shimmer-text ${isActive ? 'active' : ''} relative ${className}`}
      initial={{ opacity: 0.7 }}
      animate={{ opacity: 1 }}
    >
      <span className="shimmer-content relative z-10">{text}</span>
      {isActive && <div className="shimmer-gradient absolute inset-0 z-0" />}
    </motion.div>
  )
}

export default ShimmerText
