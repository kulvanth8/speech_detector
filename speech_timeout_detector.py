"""
Speech Timeout Detector Module
Detects silence/no-response scenarios in STT Pipeline
Distinguishes thinking pauses from user abandonment
"""

import numpy as np
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Callable, Optional
from enum import Enum
import pyaudio
import queue


class SilenceType(Enum):
    """Types of silence detected"""
    THINKING_PAUSE = "thinking_pause"      # Brief silence (user thinking)
    TIMEOUT = "timeout"                    # Prolonged silence (user abandoned)
    SPEECH_ENDED = "speech_ended"          # Normal end of speech


@dataclass
class SilenceEvent:
    """Event data for silence detection"""
    type: SilenceType
    duration: float                         # Duration in seconds
    timestamp: float
    audio_level: float                      # Average audio level during silence
    action: str                             # Recommended action


class SpeechTimeoutDetector:
    """
    Detects speech timeout and silence scenarios in real-time audio stream.
    
    Key Features:
    - Real-time silence detection from microphone
    - Distinguishes thinking pauses from user abandonment
    - Configurable thresholds for silence detection
    - Callbacks for timeout/silence events
    """
    
    def __init__(
        self,
        sample_rate: int = 16000,
        chunk_size: int = 1024,
        silence_threshold_db: float = -40,
        thinking_pause_duration: float = 2.0,      # 2 seconds for thinking pause
        timeout_duration: float = 8.0,              # 8 seconds for timeout
        min_speech_duration: float = 0.5,           # Minimum speech to start listening
    ):
        """
        Initialize the Speech Timeout Detector.
        
        Args:
            sample_rate: Audio sample rate (Hz)
            chunk_size: Audio chunk size for processing
            silence_threshold_db: dB level below which audio is considered silence
            thinking_pause_duration: Max duration (sec) considered a thinking pause
            timeout_duration: Duration (sec) before declaring user abandoned
            min_speech_duration: Minimum speech duration to start timeout tracking
        """
        self.sample_rate = sample_rate
        self.chunk_size = chunk_size
        self.silence_threshold_db = silence_threshold_db
        self.thinking_pause_duration = thinking_pause_duration
        self.timeout_duration = timeout_duration
        self.min_speech_duration = min_speech_duration
        
        # Audio stream management
        self.audio = None
        self.stream = None
        self.is_running = False
        
        # Silence tracking
        self.silence_start_time = None
        self.speech_detected = False
        self.speech_start_time = None
        self.audio_buffer = deque(maxlen=self.sample_rate)  # 1 second buffer
        
        # Thread-safe queue for events
        self.event_queue = queue.Queue()
        self.audio_queue = queue.Queue(maxsize=10)
        
        # Callbacks
        self.on_silence_callback: Optional[Callable] = None
        self.on_timeout_callback: Optional[Callable] = None
        self.on_thinking_pause_callback: Optional[Callable] = None
        
        # Statistics
        self.silence_count = 0
        self.timeout_count = 0
        
    def _init_audio(self):
        """Initialize PyAudio stream"""
        self.audio = pyaudio.PyAudio()
        self.stream = self.audio.open(
            format=pyaudio.paFloat32,
            channels=1,
            rate=self.sample_rate,
            input=True,
            frames_per_buffer=self.chunk_size,
            stream_callback=self._audio_callback,
            start=False
        )
    
    def _audio_callback(self, in_data, frame_count, time_info, status):
        """Callback for audio stream"""
        if status:
            print(f"Audio stream status: {status}")
        
        audio_chunk = np.frombuffer(in_data, dtype=np.float32)
        self.audio_queue.put(audio_chunk)
        return (in_data, pyaudio.paContinue)
    
    def _get_audio_level_db(self, audio_chunk: np.ndarray) -> float:
        """
        Calculate audio level in dB.
        
        Args:
            audio_chunk: Audio data as numpy array
            
        Returns:
            Audio level in dB
        """
        rms = np.sqrt(np.mean(audio_chunk ** 2))
        
        # Avoid log(0)
        if rms < 1e-10:
            return -100
        
        db = 20 * np.log10(rms)
        return db
    
    def _is_silence(self, audio_chunk: np.ndarray) -> bool:
        """
        Determine if audio chunk is silence.
        
        Args:
            audio_chunk: Audio data as numpy array
            
        Returns:
            True if audio level is below threshold
        """
        level_db = self._get_audio_level_db(audio_chunk)
        return level_db < self.silence_threshold_db
    
    def _process_audio_chunk(self, audio_chunk: np.ndarray):
        """Process incoming audio chunk for silence detection"""
        self.audio_buffer.extend(audio_chunk)
        
        is_silent = self._is_silence(audio_chunk)
        current_time = time.time()
        
        # Speech detection
        if not is_silent:
            if not self.speech_detected:
                self.speech_detected = True
                self.speech_start_time = current_time
                self.silence_start_time = None
                print("[DETECTOR] Speech detected")
            else:
                self.silence_start_time = None  # Reset silence timer
        
        else:  # Silence detected
            if self.speech_detected:
                # Only track silence after speech has been detected
                if self.silence_start_time is None:
                    self.silence_start_time = current_time
                
                silence_duration = current_time - self.silence_start_time
                speech_duration = current_time - self.speech_start_time
                
                # Only process if minimum speech was detected
                if speech_duration >= self.min_speech_duration:
                    self._handle_silence(silence_duration, audio_chunk)
    
    def _handle_silence(self, silence_duration: float, audio_chunk: np.ndarray):
        """
        Handle detected silence based on duration.
        
        Args:
            silence_duration: How long silence has persisted (seconds)
            audio_chunk: Current audio chunk
        """
        audio_level = self._get_audio_level_db(audio_chunk)
        
        # Timeout scenario
        if silence_duration >= self.timeout_duration:
            if self.timeout_count == 0:  # First timeout detection
                event = SilenceEvent(
                    type=SilenceType.TIMEOUT,
                    duration=silence_duration,
                    timestamp=time.time(),
                    audio_level=audio_level,
                    action="ABORT_AND_RESET"
                )
                self._queue_event(event)
                self.timeout_count += 1
                
                if self.on_timeout_callback:
                    self.on_timeout_callback(event)
        
        # Thinking pause (brief silence)
        elif (self.thinking_pause_duration * 0.5 <= silence_duration <= 
              self.thinking_pause_duration):
            event = SilenceEvent(
                type=SilenceType.THINKING_PAUSE,
                duration=silence_duration,
                timestamp=time.time(),
                audio_level=audio_level,
                action="WAIT_AND_LISTEN"
            )
            self._queue_event(event)
            
            if self.on_thinking_pause_callback:
                self.on_thinking_pause_callback(event)
    
    def _queue_event(self, event: SilenceEvent):
        """Queue event for consumption"""
        try:
            self.event_queue.put_nowait(event)
        except queue.Full:
            print("[WARNING] Event queue full, dropping event")
    
    def _audio_processing_loop(self):
        """Main loop for processing audio chunks"""
        while self.is_running:
            try:
                audio_chunk = self.audio_queue.get(timeout=0.1)
                self._process_audio_chunk(audio_chunk)
            except queue.Empty:
                continue
            except Exception as e:
                print(f"[ERROR] Audio processing error: {e}")
    
    def start(self):
        """Start listening for speech and detecting timeouts"""
        if self.is_running:
            print("[WARNING] Detector already running")
            return
        
        self._init_audio()
        self.is_running = True
        self.stream.start_stream()
        
        # Start audio processing thread
        self.processing_thread = threading.Thread(
            target=self._audio_processing_loop,
            daemon=True
        )
        self.processing_thread.start()
        
        print("[DETECTOR] Started listening...")
    
    def stop(self):
        """Stop listening"""
        self.is_running = False
        
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
        
        if self.audio:
            self.audio.terminate()
        
        print("[DETECTOR] Stopped")
    
    def reset(self):
        """Reset detection state"""
        self.speech_detected = False
        self.silence_start_time = None
        self.speech_start_time = None
        self.silence_count = 0
        self.timeout_count = 0
        self.audio_buffer.clear()
        print("[DETECTOR] Reset state")
    
    def get_events(self, timeout: float = 0.1) -> list:
        """
        Get all queued silence events.
        
        Args:
            timeout: Max time to wait for events (seconds)
            
        Returns:
            List of SilenceEvent objects
        """
        events = []
        deadline = time.time() + timeout
        
        while time.time() < deadline:
            try:
                event = self.event_queue.get_nowait()
                events.append(event)
            except queue.Empty:
                break
        
        return events
    
    def register_callback(self, event_type: str, callback: Callable):
        """
        Register callback for specific event type.
        
        Args:
            event_type: 'silence', 'timeout', or 'thinking_pause'
            callback: Function to call on event
        """
        if event_type == "silence":
            self.on_silence_callback = callback
        elif event_type == "timeout":
            self.on_timeout_callback = callback
        elif event_type == "thinking_pause":
            self.on_thinking_pause_callback = callback
    
    def get_status(self) -> dict:
        """Get current detector status"""
        return {
            "running": self.is_running,
            "speech_detected": self.speech_detected,
            "in_silence": self.silence_start_time is not None,
            "silence_count": self.silence_count,
            "timeout_count": self.timeout_count,
            "buffer_size": len(self.audio_buffer)
        }
