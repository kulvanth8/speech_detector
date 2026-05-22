"""
Example usage of Speech Timeout Detector Module
Demonstrates all features and integration patterns
"""

from speech_timeout_detector import SpeechTimeoutDetector, SilenceType
import time


def example_1_basic_usage():
    """Basic example: Start detector and handle events"""
    print("\n" + "="*60)
    print("EXAMPLE 1: Basic Usage")
    print("="*60)
    
    # Initialize detector
    detector = SpeechTimeoutDetector(
        silence_threshold_db=-40,
        thinking_pause_duration=2.0,
        timeout_duration=8.0
    )
    
    # Start listening
    detector.start()
    
    try:
        print("\nListening for speech... (speak now or wait for timeout)")
        print("Demo will run for 30 seconds\n")
        
        start_time = time.time()
        
        while time.time() - start_time < 30:
            # Get any silence events
            events = detector.get_events(timeout=0.5)
            
            for event in events:
                if event.type == SilenceType.THINKING_PAUSE:
                    print(f"✓ THINKING PAUSE detected ({event.duration:.1f}s)")
                    print(f"  → Action: {event.action}")
                
                elif event.type == SilenceType.TIMEOUT:
                    print(f"✗ TIMEOUT detected ({event.duration:.1f}s)")
                    print(f"  → Action: {event.action}")
                    print(f"  → Audio level: {event.audio_level:.1f} dB")
            
            # Show status
            status = detector.get_status()
            if status["speech_detected"]:
                in_silence = " [SILENT]" if status["in_silence"] else " [SPEAKING]"
                print(f"Status: Speech detected{in_silence}")
            
            time.sleep(1)
    
    finally:
        detector.stop()


def example_2_with_callbacks():
    """Example with event callbacks"""
    print("\n" + "="*60)
    print("EXAMPLE 2: Using Callbacks")
    print("="*60)
    
    detector = SpeechTimeoutDetector(
        silence_threshold_db=-40,
        thinking_pause_duration=2.5,
        timeout_duration=5.0  # Shorter timeout for demo
    )
    
    # Define callback functions
    def on_timeout(event):
        print(f"\n🚨 TIMEOUT CALLBACK TRIGGERED!")
        print(f"   Duration: {event.duration:.2f}s")
        print(f"   Action Required: {event.action}")
        # Can trigger additional actions here
        # e.g., send user a prompt, log the event, etc.
    
    def on_thinking_pause(event):
        print(f"\n💭 Thinking pause detected ({event.duration:.2f}s)")
        print(f"   Continuing to listen...")
    
    # Register callbacks
    detector.register_callback("timeout", on_timeout)
    detector.register_callback("thinking_pause", on_thinking_pause)
    
    # Start detector
    detector.start()
    
    try:
        print("\nListening with callbacks enabled...")
        print("(Speak, then go silent to trigger events)\n")
        time.sleep(20)
    
    finally:
        detector.stop()


def example_3_integration_with_stt():
    """Example: Integration with STT Pipeline"""
    print("\n" + "="*60)
    print("EXAMPLE 3: STT Pipeline Integration")
    print("="*60)
    
    class SimpleSTPipeline:
        """Simple STT-like pipeline for demonstration"""
        
        def __init__(self):
            self.detector = SpeechTimeoutDetector(
                silence_threshold_db=-40,
                thinking_pause_duration=2.0,
                timeout_duration=10.0,
                min_speech_duration=0.5
            )
            self.is_processing = False
            self.current_transcript = ""
        
        def start_recording(self):
            """Start recording speech"""
            print("\n🎤 Starting speech recording...")
            self.detector.start()
            self.is_processing = True
            self.current_transcript = ""
            
            # Register timeout handler
            self.detector.register_callback("timeout", self._on_timeout)
            self.detector.register_callback("thinking_pause", self._on_thinking)
        
        def _on_thinking(self, event):
            """Handle thinking pause"""
            print(f"   ⏸ User thinking... waiting for more input")
        
        def _on_timeout(self, event):
            """Handle timeout - stop recording"""
            print(f"\n   ⏹ Timeout reached! Ending recording session")
            self.stop_recording()
            self.process_transcript()
        
        def stop_recording(self):
            """Stop recording"""
            self.is_processing = False
            self.detector.stop()
            print("   Recording stopped")
        
        def process_transcript(self):
            """Process the recorded transcript"""
            print(f"   📝 Processing transcript: '{self.current_transcript}'")
            # Send to STT engine, parse intent, etc.
        
        def run_demo(self):
            """Run the pipeline demo"""
            self.start_recording()
            try:
                print("   (Speak for 3 seconds, then go silent)...\n")
                time.sleep(15)
            finally:
                if self.is_processing:
                    self.stop_recording()
    
    pipeline = SimpleSTPipeline()
    pipeline.run_demo()


def example_4_custom_thresholds():
    """Example with custom sensitivity thresholds"""
    print("\n" + "="*60)
    print("EXAMPLE 4: Custom Thresholds")
    print("="*60)
    
    print("\nConfiguring detector with custom parameters:")
    print("  - Very sensitive to silence (threshold: -50 dB)")
    print("  - Short thinking pause (1.0 sec)")
    print("  - Quick timeout (5.0 sec)")
    
    detector = SpeechTimeoutDetector(
        silence_threshold_db=-50,        # More sensitive
        thinking_pause_duration=1.0,     # Quick thinking pause
        timeout_duration=5.0,            # Fast timeout
        min_speech_duration=0.3          # Responsive
    )
    
    detector.start()
    
    try:
        print("\nListening with aggressive timeout settings...")
        print("(Quick to detect silence and timeout)\n")
        
        for i in range(12):
            status = detector.get_status()
            events = detector.get_events()
            
            if events:
                for evt in events:
                    print(f"Event: {evt.type.value} ({evt.duration:.2f}s)")
            
            print(f"Status [{i}]: {status}")
            time.sleep(1)
    
    finally:
        detector.stop()


def example_5_stress_test():
    """Stress test: Multiple silence detections"""
    print("\n" + "="*60)
    print("EXAMPLE 5: Stress Test")
    print("="*60)
    
    detector = SpeechTimeoutDetector()
    detector.start()
    
    try:
        print("Running stress test for 25 seconds...")
        print("Monitoring event processing and performance\n")
        
        event_count = 0
        start_time = time.time()
        
        while time.time() - start_time < 25:
            events = detector.get_events(timeout=0.1)
            event_count += len(events)
            
            for event in events:
                print(f"Event #{event_count}: {event.type.value}")
            
            time.sleep(0.5)
        
        print(f"\nStress test complete!")
        print(f"Total events processed: {event_count}")
        print(f"Detector status: {detector.get_status()}")
    
    finally:
        detector.stop()


if __name__ == "__main__":
    print("\n" + "#"*60)
    print("# Speech Timeout Detector - Example Usage")
    print("#"*60)
    
    # Choose which example to run
    examples = {
        "1": ("Basic Usage", example_1_basic_usage),
        "2": ("With Callbacks", example_2_with_callbacks),
        "3": ("STT Integration", example_3_integration_with_stt),
        "4": ("Custom Thresholds", example_4_custom_thresholds),
        "5": ("Stress Test", example_5_stress_test),
    }
    
    print("\nAvailable Examples:")
    for key, (name, _) in examples.items():
        print(f"  {key} - {name}")
    print("  0 - Run all examples")
    
    choice = input("\nSelect example (0-5): ").strip()
    
    if choice == "0":
        for _, (_, func) in examples.items():
            try:
                func()
                time.sleep(2)
            except KeyboardInterrupt:
                print("\n\nInterrupted by user")
                break
            except Exception as e:
                print(f"\nError: {e}")
    elif choice in examples:
        try:
            examples[choice][1]()
        except KeyboardInterrupt:
            print("\n\nInterrupted by user")
        except Exception as e:
            print(f"Error: {e}")
    else:
        print("Invalid choice")
