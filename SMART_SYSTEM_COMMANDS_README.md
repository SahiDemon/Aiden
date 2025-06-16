# 🚀 Smart Scheduled System Commands

Aiden AI now features a comprehensive **Smart Scheduled System Commands** system that allows users to schedule, modify, and abort system operations with intelligent verification and safety measures.

## ✨ Features

### 🕐 **Scheduled Commands**
- **Shutdown**: "shutdown in 10 minutes", "turn off computer in 1 hour"
- **Restart**: "restart in 5 minutes", "reboot in 30 minutes" 
- **Sleep**: "sleep in 15 minutes", "put computer to sleep in 2 hours"
- **Hibernate**: "hibernate in 45 minutes"
- **Lock Screen**: "lock computer in 5 minutes"

### 🛡️ **Smart Verification System**
- **Dangerous Commands**: Shutdown and restart always require user confirmation
- **Safe Commands**: Lock and sleep execute immediately or with minimal verification
- **Time-based Scheduling**: Any command with time gets special verification workflow
- **One-shot Mode Compatible**: Even in one-shot mode, dangerous commands ask for confirmation

### ⏱️ **Time Modification**
- **Change Time**: "change to 20 minutes", "make it 1 hour instead"
- **Real-time Updates**: Modify active schedules without canceling and recreating
- **Flexible Parsing**: Supports "minutes", "mins", "hours", "hrs", "seconds", "secs"

### ❌ **Abort Capabilities**
- **Cancel Specific**: "cancel shutdown", "abort restart"
- **Cancel All**: "cancel all schedules", "abort everything"
- **Smart Detection**: Recognizes abort requests even in natural language

### 📊 **Dashboard Integration**
- **Live Countdown Timers**: Real-time countdown display
- **Visual Urgency Indicators**: Color-coded urgency (normal/warning/urgent)
- **Interactive Controls**: Modify and cancel buttons for each schedule
- **Status Overview**: Shows all active schedules at a glance

## 🎯 Usage Examples

### Basic Scheduling
```
User: "Shutdown the computer in 10 minutes"
AI: "I'll turn off the PC in 10 minutes. Is that correct? You can say 'yes' to confirm, 'change to X minutes' to modify the time, or 'cancel' to abort."

User: "Yes"
AI: "Scheduled! I'll shutdown the system in 10 minutes. You can say 'cancel shutdown' or 'abort schedule' to stop it."
```

### Time Modification
```
User: "Shutdown in 10 minutes"
AI: "I'll turn off the PC in 10 minutes. Is that correct?"

User: "Change to 20 minutes"
AI: "Updated! Changed shutdown time from 10 minutes to 20 minutes."
```

### Abort Operations
```
User: "Cancel shutdown"
AI: "Cancelled shutdown schedule."

User: "Cancel all schedules"  
AI: "Cancelled all schedules: shutdown, restart."
```

### Immediate Commands with Verification
```
User: "Shutdown computer"
AI: "Are you sure you want to shutdown the computer right now? Say 'yes' to confirm or 'cancel' to abort."

User: "Yes"
AI: "Shutting down the computer."
```

## 🏗️ Technical Architecture

### Core Components

#### 1. **ScheduledSystemCommands** (`src/utils/scheduled_system_commands.py`)
- **Main Processing Engine**: Handles all scheduling logic
- **Time Parsing**: Extracts time information from natural language
- **Verification Management**: Coordinates user confirmation workflows
- **Schedule Execution**: Manages countdown timers and execution
- **Dashboard Updates**: Sends real-time updates to UI

#### 2. **Enhanced Command Dispatcher** (`src/utils/command_dispatcher.py`)
- **Integration Layer**: Connects scheduled commands to main system
- **Verification Handling**: Processes user confirmation responses
- **Fallback Support**: Handles edge cases and errors gracefully

#### 3. **Updated LLM Connector** (`src/utils/llm_connector.py`)
- **Enhanced Prompts**: Better command classification for scheduling
- **Scheduling Patterns**: Recognizes time-based command patterns
- **Operation Detection**: Identifies modify/abort requests

#### 4. **Dashboard UI** (`dashboard/src/components/ScheduledCommands.jsx`)
- **Real-time Display**: Live countdown timers
- **Interactive Controls**: Modify and cancel buttons
- **Visual Indicators**: Urgency-based color coding and animations

### Data Flow

```
User Command → LLM Processing → Command Dispatcher → Scheduled Commands Manager
                                      ↓
Dashboard Updates ← Schedule Execution ← User Verification ← Verification Request
```

## 📋 Supported Command Patterns

### Time Expressions
- **Minutes**: "in 10 minutes", "in 5 mins", "after 30 minutes"
- **Hours**: "in 1 hour", "in 2 hrs", "after 3 hours"
- **Seconds**: "in 30 seconds", "in 45 secs"

### Operations
- **Shutdown**: "shutdown", "power off", "turn off computer"
- **Restart**: "restart", "reboot"
- **Sleep**: "sleep", "put to sleep"
- **Hibernate**: "hibernate"
- **Lock**: "lock", "lock screen", "lock computer"

### Modifications
- **Time Changes**: "change to X", "make it X", "update to X"
- **Cancel Operations**: "cancel", "abort", "stop", "never mind"

## 🛡️ Safety Features

### 1. **Verification Levels**
- **High Risk** (Shutdown/Restart): Always require explicit confirmation
- **Medium Risk** (Sleep/Hibernate): Confirm for scheduled, immediate for direct
- **Low Risk** (Lock): Minimal verification, immediate execution

### 2. **Time Thresholds**
- **Immediate**: < 1 minute (extra verification)
- **Warning**: 1-5 minutes (visual indicators)
- **Normal**: > 5 minutes (standard flow)

### 3. **Abort Mechanisms**
- **Voice Commands**: "cancel shutdown", "abort schedule"
- **Dashboard Buttons**: Interactive cancel controls
- **Emergency Stop**: "cancel all" stops everything

### 4. **Error Handling**
- **Failed Execution**: Graceful error reporting
- **Invalid Times**: Clear error messages
- **Network Issues**: Local fallback mechanisms

## 🎨 Dashboard Features

### Visual Elements
- **🕐 Countdown Timers**: Real-time MM:SS or HH:MM:SS display
- **⚡ Operation Icons**: Unique icons for each command type
- **🚨 Urgency Indicators**: Color-coded backgrounds and animations
- **📱 Responsive Design**: Works on all screen sizes

### Interactive Controls
- **⏱️ Modify Button**: Change schedule timing
- **❌ Cancel Button**: Cancel individual schedules
- **🚫 Cancel All**: Emergency stop all schedules

### Status Information
- **Execution Time**: When the command will run
- **Original Query**: What the user originally said
- **Countdown Display**: Time remaining in real-time

## 🔧 Configuration

### System Requirements
- **Windows 10/11**: PowerShell commands for system operations
- **Python 3.8+**: Core scheduling engine
- **React Dashboard**: UI components for schedule display

### Customization Options
- **Time Formats**: Modify regex patterns in `_extract_time_info()`
- **Safety Levels**: Adjust verification requirements per operation
- **Dashboard Styling**: Update CSS for different visual themes
- **Voice Responses**: Customize AI response messages

## 🚨 Error Scenarios & Handling

### 1. **Invalid Time Formats**
```
User: "Shutdown in banana minutes"
AI: "I couldn't understand the time. Please specify a valid number like '10 minutes' or '1 hour'."
```

### 2. **Conflicting Schedules**
```
User: "Shutdown in 10 minutes" (while restart in 5 minutes is active)
AI: "You already have a restart scheduled in 5 minutes. Should I cancel that and schedule shutdown instead?"
```

### 3. **System Execution Failures**
```
Schedule executes but PowerShell command fails
→ Logs error, notifies user, removes from active schedules
```

### 4. **Network/Dashboard Issues**
```
Dashboard disconnected during active schedule
→ Schedule continues executing, reconnection shows current state
```

## 📊 Logging & Monitoring

### Log Levels
- **INFO**: Schedule creation, execution, cancellation
- **WARNING**: Verification timeouts, modification attempts
- **ERROR**: Execution failures, system command errors

### Dashboard Analytics
- **Active Schedules**: Real-time count display
- **Execution History**: Recently completed schedules
- **User Patterns**: Most common schedule types and times

## 🔮 Future Enhancements

### Planned Features
- **Recurring Schedules**: "Restart every day at 3 AM"
- **Conditional Execution**: "Shutdown if no activity for 1 hour"
- **Multi-device Support**: Schedule commands across network
- **Advanced Notifications**: Email/SMS alerts before execution
- **Schedule Templates**: Save common schedule patterns

### Possible Integrations
- **Calendar Sync**: Import schedules from Outlook/Google Calendar
- **Smart Home**: Integrate with home automation systems
- **Monitoring Tools**: System health checks before execution
- **Backup Systems**: Auto-backup before dangerous operations

## 🧪 Testing

### Manual Test Cases
1. **Basic Scheduling**: "shutdown in 10 minutes" → Verify countdown and execution
2. **Time Modification**: "change to 20 minutes" → Verify time update
3. **Abort Operations**: "cancel shutdown" → Verify schedule removal
4. **Verification Flow**: Test yes/no/modify responses
5. **Dashboard UI**: Verify real-time updates and interactions

### Automated Testing
- **Unit Tests**: Individual function verification
- **Integration Tests**: Full workflow testing
- **UI Tests**: Dashboard component functionality
- **Performance Tests**: Multiple concurrent schedules

---

## 🎉 Summary

The **Smart Scheduled System Commands** feature transforms Aiden AI into a powerful system management assistant with:

✅ **Safe Scheduling**: Intelligent verification for dangerous operations  
✅ **Flexible Timing**: Natural language time parsing and modification  
✅ **Real-time Control**: Live dashboard with countdown timers  
✅ **Smart Responses**: Context-aware AI interactions  
✅ **Emergency Controls**: Multiple abort mechanisms  
✅ **Visual Feedback**: Urgency indicators and status displays  

This feature makes system management both **powerful and safe**, giving users complete control over their computer's operations while preventing accidental damage through smart verification and abort capabilities. 