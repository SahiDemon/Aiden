import React, { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { ChevronLeft, ChevronRight, Activity, Home, Settings, History } from 'lucide-react'
import { Button } from '../ui/button'
import SystemStats from '../system/SystemStats'
import SmartDeviceCard from '../smart-home/SmartDeviceCard'

const CollapsibleSidebar = ({ 
  connected, 
  systemMetrics, 
  deviceUpdates, 
  onShowHistory, 
  onShowSettings 
}) => {
  const [isCollapsed, setIsCollapsed] = useState(true)

  const toggleSidebar = () => {
    setIsCollapsed(!isCollapsed)
  }

  return (
    <>

      {/* Sidebar */}
      <motion.div
        initial={{ width: 60 }}
        animate={{ width: isCollapsed ? 60 : 320 }}
        transition={{ duration: 0.3, ease: "easeInOut" }}
        className="fixed left-0 top-16 h-[calc(100vh-4rem)] liquid-glass-sidebar z-40 flex flex-col overflow-hidden"
      >
        {/* Logo/Header Section */}
        <div className="p-3 border-b border-white/10">
          <AnimatePresence mode="wait">
            {isCollapsed ? (
              <motion.div
                key="collapsed-logo"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="flex items-center justify-center"
              >
                <div className="w-9 h-9 rounded-xl bg-blue-500/20 flex items-center justify-center">
                  <span className="text-blue-400 font-bold text-lg">A</span>
                </div>
              </motion.div>
            ) : (
              <motion.div
                key="expanded-logo"
                initial={{ opacity: 0, x: -20 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -20 }}
                transition={{ duration: 0.2 }}
                className="flex items-center gap-3"
              >
                <div className="w-9 h-9 rounded-xl bg-blue-500/20 flex items-center justify-center flex-shrink-0">
                  <span className="text-blue-400 font-bold text-lg">A</span>
                </div>
                <span className="text-white font-semibold text-base">Aiden AI</span>
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        {/* Navigation Items */}
        <div className="flex-1 p-3 space-y-2 overflow-y-auto overflow-x-hidden">
          <AnimatePresence mode="wait">
            {isCollapsed ? (
              <motion.div
                key="collapsed"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.2 }}
                className="space-y-3"
              >
                <Button
                  variant="ghost"
                  size="sm"
                  className="w-full h-10 p-0 text-white/70 hover:text-white hover:bg-white/10"
                  title="Dashboard"
                >
                  <Home className="w-5 h-5" />
                </Button>
                
                <Button
                  variant="ghost"
                  size="sm"
                  className="w-full h-10 p-0 text-white/70 hover:text-white hover:bg-white/10"
                  title="System Status"
                >
                  <Activity className="w-5 h-5" />
                </Button>
                
                <Button
                  onClick={onShowHistory}
                  variant="ghost"
                  size="sm"
                  className="w-full h-10 p-0 text-white/70 hover:text-white hover:bg-white/10"
                  title="History"
                >
                  <History className="w-5 h-5" />
                </Button>
                
                <Button
                  onClick={onShowSettings}
                  variant="ghost"
                  size="sm"
                  className="w-full h-10 p-0 text-white/70 hover:text-white hover:bg-white/10"
                  title="Settings"
                >
                  <Settings className="w-5 h-5" />
                </Button>
              </motion.div>
            ) : (
              <motion.div
                key="expanded"
                initial={{ opacity: 0, x: -20 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -20 }}
                transition={{ duration: 0.3, delay: 0.1 }}
                className="space-y-4 w-full"
              >
                {/* Navigation Buttons */}
                <div className="space-y-2 w-full">
                  <Button
                    variant="ghost"
                    className="w-full justify-start text-white/70 hover:text-white hover:bg-white/10"
                  >
                    <Home className="w-5 h-5 mr-3 flex-shrink-0" />
                    <span className="truncate">Dashboard</span>
                  </Button>
                  
                  <Button
                    onClick={onShowHistory}
                    variant="ghost"
                    className="w-full justify-start text-white/70 hover:text-white hover:bg-white/10"
                  >
                    <History className="w-5 h-5 mr-3 flex-shrink-0" />
                    <span className="truncate">History</span>
                  </Button>
                  
                  <Button
                    onClick={onShowSettings}
                    variant="ghost"
                    className="w-full justify-start text-white/70 hover:text-white hover:bg-white/10"
                  >
                    <Settings className="w-5 h-5 mr-3 flex-shrink-0" />
                    <span className="truncate">Settings</span>
                  </Button>
                </div>

                {/* System Stats with Blue Accents */}
                <div className="space-y-3 w-full">
                  <div className="text-xs font-semibold text-blue-300/60 px-1">
                    SYSTEM STATUS
                  </div>
                  <div className="liquid-glass-card p-3 rounded-xl border-blue-400/20 shadow-lg shadow-blue-500/5">
                    <SystemStats 
                      connected={connected} 
                      systemMetrics={systemMetrics}
                      compact={true}
                    />
                  </div>
                  
                  <div className="text-xs font-semibold text-blue-300/60 px-1 mt-4">
                    SMART FAN
                  </div>
                  <div className="liquid-glass-card p-3 rounded-xl border-blue-400/20 shadow-lg shadow-blue-500/5">
                    <SmartDeviceCard
                      connected={connected}
                      deviceUpdates={deviceUpdates}
                      compact={true}
                    />
                  </div>
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        {/* Toggle Button at Bottom */}
        <div className="p-3 border-t border-white/10">
          <Button
            onClick={toggleSidebar}
            variant="ghost"
            size="sm"
            className="w-full h-10 text-white/70 hover:text-white hover:bg-white/10"
          >
            {isCollapsed ? (
              <ChevronRight className="w-4 h-4" />
            ) : (
              <ChevronLeft className="w-4 h-4" />
            )}
          </Button>
        </div>
      </motion.div>

      {/* Backdrop overlay when expanded */}
      <AnimatePresence>
        {!isCollapsed && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.3 }}
            className="fixed inset-0 bg-black/20 backdrop-blur-sm z-40 lg:hidden"
            onClick={toggleSidebar}
          />
        )}
      </AnimatePresence>
    </>
  )
}

export default CollapsibleSidebar
