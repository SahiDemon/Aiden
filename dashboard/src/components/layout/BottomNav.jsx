import React from 'react';
import { Home, MessageSquare, Settings, Activity } from 'lucide-react';
import { motion } from 'framer-motion';

const BottomNav = ({ activeTab, setActiveTab, onShowSettings }) => {
  const navItems = [
    { id: 'chat', icon: MessageSquare, label: 'Chat' },
    { id: 'activity', icon: Activity, label: 'System' },
    { id: 'settings', icon: Settings, label: 'Settings' }
  ];

  return (
    <div className="md:hidden fixed bottom-0 left-0 right-0 bg-[#080b12]/95 backdrop-blur-xl border-t border-white/10 z-50 px-2 py-2.5 pb-safe flex justify-between items-center">
      {navItems.map((item) => {
        const Icon = item.icon;
        const isActive = activeTab === item.id;
        
        return (
          <button
            key={item.id}
            onClick={() => {
              if (item.id === 'settings') {
                onShowSettings();
              } else {
                setActiveTab(item.id);
              }
            }}
            className="relative flex-1 py-2.5 mx-1 rounded-2xl flex flex-col items-center justify-center gap-1 transition-all duration-300 select-none"
          >
            {isActive && (
              <motion.div
                layoutId="bottomNavIndicator"
                className="absolute inset-0 bg-gradient-to-r from-blue-600/30 via-blue-500/20 to-sky-500/20 border border-blue-400/30 rounded-2xl shadow-lg shadow-blue-500/20 z-0"
                transition={{ type: "spring", bounce: 0.15, duration: 0.4 }}
              />
            )}
            <Icon className={`w-6 h-6 relative z-10 transition-colors ${isActive ? 'text-blue-300' : 'text-slate-400'}`} strokeWidth={1.5} />
            <span className={`text-[11px] font-medium tracking-wider relative z-10 transition-colors ${isActive ? 'text-blue-200 font-semibold' : 'text-slate-400'}`}>
              {item.label}
            </span>
          </button>
        );
      })}
    </div>
  );
};

export default BottomNav;
