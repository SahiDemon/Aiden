"""
Wake Word Log Analyzer
Analyzes debug logs to identify patterns and provide recommendations
"""
import os
import sys
import re
from collections import Counter, defaultdict
from datetime import datetime
from typing import List, Dict, Tuple

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)


class LogAnalyzer:
    """Analyzes wake word debug logs"""
    
    def __init__(self, log_file: str):
        self.log_file = log_file
        self.detections = []
        self.false_positives = []
        self.true_positives = []
        self.transcriptions = []
        
    def parse_log(self):
        """Parse the log file"""
        try:
            with open(self.log_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Split into events
            events = content.split('\n\n')
            
            current_detection = None
            
            for event in events:
                if not event.strip():
                    continue
                
                # Check if it's a wake word detection
                if 'WAKE WORD DETECTION' in event or '*** WAKE WORD DETECTED ***' in event:
                    # Extract details
                    timestamp_match = re.search(r'\[([\d\-: .]+)\]', event)
                    text_match = re.search(r"Text: '([^']+)'", event)
                    energy_match = re.search(r'Energy: ([\d.]+)', event)
                    
                    if timestamp_match and text_match and energy_match:
                        detection = {
                            'timestamp': timestamp_match.group(1),
                            'text': text_match.group(1),
                            'energy': float(energy_match.group(1)),
                            'is_false_positive': 'FALSE POSITIVE' in event
                        }
                        
                        self.detections.append(detection)
                        
                        if detection['is_false_positive']:
                            self.false_positives.append(detection)
                        else:
                            self.true_positives.append(detection)
                
                # Regular transcription
                elif 'TRANSCRIPTION' in event or 'Transcription' in event:
                    text_match = re.search(r"Text: '([^']+)'", event)
                    energy_match = re.search(r'Energy: ([\d.]+)', event)
                    
                    if text_match and energy_match:
                        self.transcriptions.append({
                            'text': text_match.group(1),
                            'energy': float(energy_match.group(1))
                        })
            
            print(f"✓ Parsed {len(self.detections)} detections ({len(self.false_positives)} false, {len(self.true_positives)} true)")
            print(f"✓ Parsed {len(self.transcriptions)} transcriptions")
            
        except Exception as e:
            print(f"ERROR: Failed to parse log file: {e}")
            sys.exit(1)
    
    def analyze_false_positive_patterns(self) -> Dict:
        """Analyze patterns in false positives"""
        if not self.false_positives:
            return {
                'total': 0,
                'common_words': [],
                'common_phrases': [],
                'avg_energy': 0,
                'min_energy': 0,
                'max_energy': 0
            }
        
        # Count words/phrases that triggered false positives
        fp_texts = [fp['text'].lower() for fp in self.false_positives]
        
        # Extract individual words
        all_words = []
        for text in fp_texts:
            all_words.extend(text.split())
        
        word_counts = Counter(all_words)
        phrase_counts = Counter(fp_texts)
        
        # Analyze energy levels
        fp_energies = [fp['energy'] for fp in self.false_positives]
        avg_fp_energy = sum(fp_energies) / len(fp_energies)
        min_fp_energy = min(fp_energies)
        max_fp_energy = max(fp_energies)
        
        return {
            'total': len(self.false_positives),
            'common_words': word_counts.most_common(10),
            'common_phrases': phrase_counts.most_common(10),
            'avg_energy': avg_fp_energy,
            'min_energy': min_fp_energy,
            'max_energy': max_fp_energy
        }
    
    def analyze_true_positive_patterns(self) -> Dict:
        """Analyze patterns in true positives"""
        if not self.true_positives:
            return {
                'total': 0,
                'avg_energy': 0,
                'min_energy': 0,
                'max_energy': 0
            }
        
        tp_energies = [tp['energy'] for tp in self.true_positives]
        avg_tp_energy = sum(tp_energies) / len(tp_energies)
        min_tp_energy = min(tp_energies)
        max_tp_energy = max(tp_energies)
        
        return {
            'total': len(self.true_positives),
            'avg_energy': avg_tp_energy,
            'min_energy': min_tp_energy,
            'max_energy': max_tp_energy
        }
    
    def generate_recommendations(self, fp_analysis: Dict, tp_analysis: Dict) -> List[str]:
        """Generate recommendations based on analysis"""
        recommendations = []
        
        if not fp_analysis or not tp_analysis:
            return ["Not enough data to generate recommendations"]
        
        # Calculate accuracy
        total = fp_analysis['total'] + tp_analysis['total']
        if total > 0:
            accuracy = (tp_analysis['total'] / total) * 100
            
            if accuracy < 50:
                recommendations.append(f"⚠️ CRITICAL: Accuracy is only {accuracy:.1f}% - major adjustments needed")
            elif accuracy < 70:
                recommendations.append(f"⚠️ WARNING: Accuracy is {accuracy:.1f}% - adjustments recommended")
            elif accuracy < 90:
                recommendations.append(f"✓ Accuracy is {accuracy:.1f}% - minor tuning may help")
            else:
                recommendations.append(f"✓ EXCELLENT: Accuracy is {accuracy:.1f}%")
        
        # Energy-based recommendations
        if fp_analysis['avg_energy'] < 200:
            recommendations.append("💡 False positives have low energy - increase SPEECH_PORCUPINE_MIN_ENERGY to 250")
        
        if fp_analysis['min_energy'] < 150:
            recommendations.append("💡 Some false positives are very quiet - consider increasing min_energy threshold")
        
        # Pattern-based recommendations
        if fp_analysis['common_words']:
            top_words = [word for word, _ in fp_analysis['common_words'][:3]]
            if any(word in ['aid', 'aiding', 'in'] for word in top_words):
                recommendations.append("💡 'aid/aiding' is triggering false positives - lower sensitivity to 0.3-0.4")
            
            if any(word in ['eaten', 'eating', 'eden'] for word in top_words):
                recommendations.append("💡 Similar-sounding words detected - consider custom Porcupine model")
        
        # Frequency-based recommendations
        if fp_analysis['total'] > tp_analysis['total'] * 2:
            recommendations.append("💡 False positives outnumber true positives 2:1 - significantly lower sensitivity")
        
        if fp_analysis['total'] > 10:
            recommendations.append("💡 Many false positives detected - increase debounce to 2.0s")
        
        return recommendations
    
    def print_report(self):
        """Print analysis report"""
        print("\n" + "=" * 80)
        print("WAKE WORD LOG ANALYSIS REPORT")
        print("=" * 80)
        print(f"Log File: {self.log_file}")
        print(f"Analysis Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 80)
        
        # Overall stats
        print("\n📊 OVERALL STATISTICS")
        print("-" * 80)
        total_detections = len(self.detections)
        if total_detections > 0:
            print(f"Total Detections: {total_detections}")
            print(f"  True Positives:  {len(self.true_positives)} ({len(self.true_positives)/total_detections*100:.1f}%)")
            print(f"  False Positives: {len(self.false_positives)} ({len(self.false_positives)/total_detections*100:.1f}%)")
            print(f"Total Transcriptions: {len(self.transcriptions)}")
        else:
            print("No detections found in log file")
            return
        
        # False positive analysis
        fp_analysis = self.analyze_false_positive_patterns()
        if fp_analysis:
            print("\n❌ FALSE POSITIVE ANALYSIS")
            print("-" * 80)
            print(f"Total False Positives: {fp_analysis['total']}")
            print(f"Average Energy: {fp_analysis['avg_energy']:.2f}")
            print(f"Energy Range: {fp_analysis['min_energy']:.2f} - {fp_analysis['max_energy']:.2f}")
            
            print("\nMost Common Words in False Positives:")
            for word, count in fp_analysis['common_words'][:5]:
                print(f"  '{word}': {count} times")
            
            print("\nMost Common Phrases:")
            for phrase, count in fp_analysis['common_phrases'][:5]:
                print(f"  '{phrase}': {count} times")
        
        # True positive analysis
        tp_analysis = self.analyze_true_positive_patterns()
        if tp_analysis:
            print("\n✓ TRUE POSITIVE ANALYSIS")
            print("-" * 80)
            print(f"Total True Positives: {tp_analysis['total']}")
            print(f"Average Energy: {tp_analysis['avg_energy']:.2f}")
            print(f"Energy Range: {tp_analysis['min_energy']:.2f} - {tp_analysis['max_energy']:.2f}")
        
        # Recommendations
        recommendations = self.generate_recommendations(fp_analysis, tp_analysis)
        if recommendations:
            print("\n💡 RECOMMENDATIONS")
            print("-" * 80)
            for i, rec in enumerate(recommendations, 1):
                print(f"{i}. {rec}")
        
        # Suggested settings
        print("\n⚙️ SUGGESTED SETTINGS")
        print("-" * 80)
        
        if fp_analysis['total'] > tp_analysis['total']:
            # Too many false positives - be strict
            print("Add these to your .env file:")
            print("SPEECH_PORCUPINE_SENSITIVITY=0.3")
            print("SPEECH_PORCUPINE_MIN_ENERGY=250")
            print("SPEECH_PORCUPINE_DEBOUNCE_SECONDS=2.0")
            print("SPEECH_PORCUPINE_CONFIRMATION_WINDOW=0.5")
        elif tp_analysis['total'] < 3:
            # Not enough true positives - be lenient
            print("Add these to your .env file:")
            print("SPEECH_PORCUPINE_SENSITIVITY=0.6")
            print("SPEECH_PORCUPINE_MIN_ENERGY=150")
            print("SPEECH_PORCUPINE_DEBOUNCE_SECONDS=1.5")
        else:
            # Balanced
            print("Add these to your .env file:")
            print("SPEECH_PORCUPINE_SENSITIVITY=0.5")
            print("SPEECH_PORCUPINE_MIN_ENERGY=200")
            print("SPEECH_PORCUPINE_DEBOUNCE_SECONDS=1.5")
        
        print("\n" + "=" * 80)
        print("Next Steps:")
        print("1. Update your .env file with suggested settings")
        print("2. Run the debugger again to test: .\\run_wake_word_debug.ps1")
        print("3. Compare results to this run")
        print("=" * 80 + "\n")


def main():
    """Main entry point"""
    print("\n" + "=" * 80)
    print("WAKE WORD LOG ANALYZER")
    print("=" * 80)
    
    # Get log file
    if len(sys.argv) > 1:
        log_file = sys.argv[1]
    else:
        # Find most recent log file
        log_dir = "logs"
        if not os.path.exists(log_dir):
            print(f"ERROR: Logs directory not found: {log_dir}")
            print("Run the debugger first: .\\run_wake_word_debug.ps1")
            sys.exit(1)
        
        log_files = [f for f in os.listdir(log_dir) if f.startswith('wake_word_debug_') and f.endswith('.txt')]
        if not log_files:
            print(f"ERROR: No debug log files found in {log_dir}")
            print("Run the debugger first: .\\run_wake_word_debug.ps1")
            sys.exit(1)
        
        # Get most recent
        log_files.sort(reverse=True)
        log_file = os.path.join(log_dir, log_files[0])
        print(f"Using most recent log file: {log_file}")
    
    if not os.path.exists(log_file):
        print(f"ERROR: Log file not found: {log_file}")
        sys.exit(1)
    
    # Analyze
    analyzer = LogAnalyzer(log_file)
    analyzer.parse_log()
    analyzer.print_report()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nAnalysis interrupted")
        sys.exit(0)
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
