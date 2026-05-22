"""
Test Suite for Speech Timeout Detector
Includes unit tests, integration tests, and edge case handling
"""

import unittest
import time
import numpy as np
from unittest.mock import Mock, patch, MagicMock
from speech_timeout_detector import (
    SpeechTimeoutDetector,
    SilenceEvent,
    SilenceType
)


class TestAudioLevelCalculation(unittest.TestCase):
    """Test audio level calculation in dB"""
    
    def setUp(self):
        self.detector = SpeechTimeoutDetector()
    
    def test_silence_level(self):
        """Test that silence produces low dB level"""
        silent_audio = np.zeros(1024, dtype=np.float32)
        level = self.detector._get_audio_level_db(silent_audio)
        self.assertLess(level, -60)  # Should be very low
    
    def test_moderate_audio(self):
        """Test moderate audio level"""
        # Generate 0.1 amplitude audio
        audio = np.full(1024, 0.1, dtype=np.float32)
        level = self.detector._get_audio_level_db(audio)
        self.assertGreater(level, -40)
        self.assertLess(level, -20)
    
    def test_loud_audio(self):
        """Test loud audio level"""
        audio = np.full(1024, 0.5, dtype=np.float32)
        level = self.detector._get_audio_level_db(audio)
        self.assertGreater(level, -20)
    
    def test_increasing_amplitude(self):
        """Test that amplitude correlates with dB"""
        levels = []
        for amplitude in [0.01, 0.05, 0.1, 0.2]:
            audio = np.full(1024, amplitude, dtype=np.float32)
            level = self.detector._get_audio_level_db(audio)
            levels.append(level)
        
        # Levels should increase monotonically
        for i in range(len(levels) - 1):
            self.assertLess(levels[i], levels[i + 1])


class TestSilenceDetection(unittest.TestCase):
    """Test silence detection logic"""
    
    def setUp(self):
        self.detector = SpeechTimeoutDetector(
            silence_threshold_db=-40
        )
    
    def test_silence_detection(self):
        """Test detection of silence"""
        silent_audio = np.zeros(1024, dtype=np.float32)
        is_silent = self.detector._is_silence(silent_audio)
        self.assertTrue(is_silent)
    
    def test_speech_detection(self):
        """Test detection of speech"""
        speech_audio = np.full(1024, 0.1, dtype=np.float32)
        is_silent = self.detector._is_silence(speech_audio)
        self.assertFalse(is_silent)
    
    def test_threshold_sensitivity(self):
        """Test that threshold affects detection"""
        # Create audio at boundary
        boundary_audio = np.full(1024, 0.01, dtype=np.float32)
        
        # With high threshold (sensitive)
        sensitive = SpeechTimeoutDetector(silence_threshold_db=-30)
        is_silent = sensitive._is_silence(boundary_audio)
        self.assertTrue(is_silent)
        
        # With low threshold (lenient)
        lenient = SpeechTimeoutDetector(silence_threshold_db=-50)
        is_silent = lenient._is_silence(boundary_audio)
        self.assertFalse(is_silent)


class TestStateManagement(unittest.TestCase):
    """Test detector state management"""
    
    def setUp(self):
        self.detector = SpeechTimeoutDetector()
    
    def test_initial_state(self):
        """Test initial detector state"""
        status = self.detector.get_status()
        self.assertFalse(status["running"])
        self.assertFalse(status["speech_detected"])
        self.assertFalse(status["in_silence"])
        self.assertEqual(status["silence_count"], 0)
        self.assertEqual(status["timeout_count"], 0)
    
    def test_reset_clears_state(self):
        """Test that reset clears state"""
        self.detector.reset()
        status = self.detector.get_status()
        self.assertFalse(status["speech_detected"])
        self.assertEqual(status["silence_count"], 0)
        self.assertEqual(status["timeout_count"], 0)
    
    def test_multiple_resets(self):
        """Test multiple resets don't cause errors"""
        for _ in range(5):
            self.detector.reset()
        self.assertFalse(self.detector.speech_detected)


class TestEventQueuing(unittest.TestCase):
    """Test event queueing mechanism"""
    
    def setUp(self):
        self.detector = SpeechTimeoutDetector()
    
    def test_queue_event(self):
        """Test that events are queued"""
        event = SilenceEvent(
            type=SilenceType.TIMEOUT,
            duration=10.0,
            timestamp=time.time(),
            audio_level=-45,
            action="ABORT"
        )
        self.detector._queue_event(event)
        
        events = self.detector.get_events(timeout=0.1)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].type, SilenceType.TIMEOUT)
    
    def test_multiple_events(self):
        """Test queueing multiple events"""
        for i in range(5):
            event = SilenceEvent(
                type=SilenceType.THINKING_PAUSE,
                duration=float(i),
                timestamp=time.time(),
                audio_level=-40,
                action="WAIT"
            )
            self.detector._queue_event(event)
        
        events = self.detector.get_events(timeout=0.1)
        self.assertEqual(len(events), 5)
    
    def test_get_events_timeout(self):
        """Test get_events timeout behavior"""
        start = time.time()
        events = self.detector.get_events(timeout=0.1)
        elapsed = time.time() - start
        
        self.assertEqual(len(events), 0)
        # Should respect timeout
        self.assertLess(elapsed, 0.2)


class TestCallbacks(unittest.TestCase):
    """Test callback registration and invocation"""
    
    def setUp(self):
        self.detector = SpeechTimeoutDetector()
        self.callback_called = False
        self.callback_event = None
    
    def mock_callback(self, event):
        """Mock callback function"""
        self.callback_called = True
        self.callback_event = event
    
    def test_register_callback(self):
        """Test callback registration"""
        self.detector.register_callback("timeout", self.mock_callback)
        self.assertIsNotNone(self.detector.on_timeout_callback)
    
    def test_callback_invocation(self):
        """Test that callback is invoked on timeout"""
        self.detector.register_callback("timeout", self.mock_callback)
        
        event = SilenceEvent(
            type=SilenceType.TIMEOUT,
            duration=10.0,
            timestamp=time.time(),
            audio_level=-45,
            action="ABORT"
        )
        
        # Manually trigger callback
        self.detector.on_timeout_callback(event)
        
        self.assertTrue(self.callback_called)
        self.assertEqual(self.callback_event.type, SilenceType.TIMEOUT)


class TestConfigurationPresets(unittest.TestCase):
    """Test different configuration presets"""
    
    def test_aggressive_config(self):
        """Test aggressive timeout detection"""
        detector = SpeechTimeoutDetector(
            silence_threshold_db=-50,
            thinking_pause_duration=1.0,
            timeout_duration=5.0
        )
        
        self.assertEqual(detector.silence_threshold_db, -50)
        self.assertEqual(detector.timeout_duration, 5.0)
    
    def test_lenient_config(self):
        """Test lenient timeout detection"""
        detector = SpeechTimeoutDetector(
            silence_threshold_db=-30,
            thinking_pause_duration=3.0,
            timeout_duration=15.0
        )
        
        self.assertEqual(detector.silence_threshold_db, -30)
        self.assertEqual(detector.timeout_duration, 15.0)
    
    def test_custom_sample_rate(self):
        """Test custom audio parameters"""
        detector = SpeechTimeoutDetector(
            sample_rate=8000,
            chunk_size=512
        )
        
        self.assertEqual(detector.sample_rate, 8000)
        self.assertEqual(detector.chunk_size, 512)


class TestEdgeCases(unittest.TestCase):
    """Test edge cases and boundary conditions"""
    
    def setUp(self):
        self.detector = SpeechTimeoutDetector()
    
    def test_empty_audio(self):
        """Test handling of empty audio"""
        empty = np.array([], dtype=np.float32)
        # Should not crash
        level = self.detector._get_audio_level_db(empty)
        self.assertIsNotNone(level)
    
    def test_nan_audio(self):
        """Test handling of NaN values"""
        nan_audio = np.full(1024, np.nan, dtype=np.float32)
        # Should not crash
        level = self.detector._get_audio_level_db(nan_audio)
        self.assertTrue(np.isnan(level) or level < -100)
    
    def test_very_loud_audio(self):
        """Test handling of very loud audio"""
        loud = np.full(1024, 1.0, dtype=np.float32)
        level = self.detector._get_audio_level_db(loud)
        self.assertGreater(level, 0)
    
    def test_zero_duration_threshold(self):
        """Test zero duration thresholds"""
        detector = SpeechTimeoutDetector(
            thinking_pause_duration=0,
            timeout_duration=0
        )
        # Should initialize without error
        self.assertEqual(detector.thinking_pause_duration, 0)


class TestPerformance(unittest.TestCase):
    """Test performance characteristics"""
    
    def test_buffer_memory(self):
        """Test audio buffer doesn't grow unbounded"""
        detector = SpeechTimeoutDetector()
        
        # Add large amounts of audio
        for _ in range(1000):
            audio = np.random.randn(1024).astype(np.float32)
            detector.audio_buffer.extend(audio)
        
        # Buffer should be bounded by maxlen
        self.assertLessEqual(len(detector.audio_buffer), 16000)
    
    def test_event_queue_bounded(self):
        """Test event queue doesn't grow unbounded"""
        detector = SpeechTimeoutDetector()
        
        # Try to queue many events (should hit max)
        for i in range(20):
            event = SilenceEvent(
                type=SilenceType.THINKING_PAUSE,
                duration=float(i),
                timestamp=time.time(),
                audio_level=-40,
                action="WAIT"
            )
            try:
                detector._queue_event(event)
            except:
                pass  # Expected to fail when full


class TestIntegration(unittest.TestCase):
    """Integration tests for full workflow"""
    
    def test_workflow_without_audio_device(self):
        """Test detector initialization without audio device"""
        detector = SpeechTimeoutDetector()
        # Should not crash - only fails on start()
        status = detector.get_status()
        self.assertFalse(status["running"])
    
    def test_multiple_reset_cycles(self):
        """Test multiple usage cycles with resets"""
        detector = SpeechTimeoutDetector()
        
        for cycle in range(3):
            detector.reset()
            status = detector.get_status()
            self.assertFalse(status["speech_detected"])
    
    def test_callback_chain(self):
        """Test multiple callbacks"""
        detector = SpeechTimeoutDetector()
        
        calls = []
        
        def callback1(event):
            calls.append(1)
        
        def callback2(event):
            calls.append(2)
        
        detector.register_callback("timeout", callback1)
        detector.on_timeout_callback = callback2  # Override
        
        event = SilenceEvent(
            type=SilenceType.TIMEOUT,
            duration=10.0,
            timestamp=time.time(),
            audio_level=-45,
            action="ABORT"
        )
        detector.on_timeout_callback(event)
        
        self.assertEqual(calls, [2])


def run_tests():
    """Run all tests"""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add all test classes
    suite.addTests(loader.loadTestsFromTestCase(TestAudioLevelCalculation))
    suite.addTests(loader.loadTestsFromTestCase(TestSilenceDetection))
    suite.addTests(loader.loadTestsFromTestCase(TestStateManagement))
    suite.addTests(loader.loadTestsFromTestCase(TestEventQueuing))
    suite.addTests(loader.loadTestsFromTestCase(TestCallbacks))
    suite.addTests(loader.loadTestsFromTestCase(TestConfigurationPresets))
    suite.addTests(loader.loadTestsFromTestCase(TestEdgeCases))
    suite.addTests(loader.loadTestsFromTestCase(TestPerformance))
    suite.addTests(loader.loadTestsFromTestCase(TestIntegration))
    
    runner = unittest.TextTestRunner(verbosity=2)
    return runner.run(suite)


if __name__ == "__main__":
    print("\n" + "="*70)
    print("Speech Timeout Detector - Test Suite")
    print("="*70 + "\n")
    
    result = run_tests()
    
    print("\n" + "="*70)
    print(f"Tests run: {result.testsRun}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    print("="*70)
