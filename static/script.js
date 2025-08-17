const startBtn = document.getElementById("startBtn");
const stopBtn = document.getElementById("stopBtn");
const audioPlayback = document.getElementById("audioPlayback");
const statusDiv = document.getElementById("statusBox");
const voiceVisualizer = document.getElementById("voiceVisualizer");

let autoRecordAfterPlayback = true;
let audioElement = null;
let mediaRecorder;
let audioChunks = [];
let isRecording = false;
let conversationEnded = false;
let sessionId =
  new URLSearchParams(window.location.search).get("session_id") ||
  Date.now().toString();

// Enhanced UI update functions
function updateButtonText(button, icon, text) {
  const iconSpan = button.querySelector(".btn-icon");
  const textSpan = button.querySelector(".btn-text");

  if (iconSpan && icon) iconSpan.textContent = icon;
  if (textSpan && text) textSpan.textContent = text;
}

function updateStatus(message, type = "default") {
  const statusText = statusDiv.querySelector(".status-text");
  const statusIndicator = statusDiv.querySelector(".status-indicator");
  const glassCard = document.querySelector(".glass-card");

  // Update status text
  if (statusText) {
    statusText.textContent = message;
  }

  // Remove previous state classes
  statusDiv.classList.remove("error", "success", "processing");
  statusIndicator.classList.remove("recording", "processing");
  glassCard.classList.remove("processing");
  startBtn.classList.remove("recording");

  // Apply new state
  switch (type) {
    case "recording":
      statusIndicator.classList.add("recording");
      startBtn.classList.add("recording");
      voiceVisualizer.classList.add("active");
      break;
    case "processing":
      statusIndicator.classList.add("processing");
      statusDiv.classList.add("processing");
      glassCard.classList.add("processing");
      voiceVisualizer.classList.remove("active");
      break;
    case "error":
      statusDiv.classList.add("error");
      voiceVisualizer.classList.remove("active");
      break;
    case "success":
      statusDiv.classList.add("success");
      voiceVisualizer.classList.remove("active");
      break;
    default:
      voiceVisualizer.classList.remove("active");
      break;
  }
}

function resetRecordingState() {
  updateButtonText(startBtn, "🎤", "Start Recording");
  startBtn.classList.remove("recording");
  voiceVisualizer.classList.remove("active");
  isRecording = false;
}

// Auto-start recording function
async function autoStartRecording() {
  if (isRecording || conversationEnded) return;

  try {
    console.log("Auto-starting recording after TTS completion");

    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    mediaRecorder = new MediaRecorder(stream);
    audioChunks = [];
    isRecording = true;

    mediaRecorder.ondataavailable = (event) => {
      if (event.data.size > 0) audioChunks.push(event.data);
    };

    mediaRecorder.onstop = async () => {
      // Stop all audio tracks to release microphone
      stream.getTracks().forEach((track) => track.stop());

      const audioBlob = new Blob(audioChunks, { type: "audio/wav" });
      const formData = new FormData();
      formData.append("file", audioBlob, "recording.wav");

      updateStatus("Processing with AI services...", "processing");

      try {
        const response = await fetch(`/agent/chat/${sessionId}`, {
          method: "POST",
          body: formData,
        });

        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`);
        }

        const data = await response.json();
        console.log("Response data:", data);

        // Display transcription in status (optional)
        if (data.transcription) {
          updateStatus(
            `You said: "${data.transcription.substring(0, 50)}..."`,
            "processing"
          );
          setTimeout(() => {
            updateStatus("AI is responding...", "processing");
          }, 2000);
        }

        // Validate and play audio response
        if (data && data.audio_base64) {
          // Use audio/mp3 since Murf returns MP3 format
          const audioUrl = `data:audio/mp3;base64,${data.audio_base64}`;
          audioPlayback.src = audioUrl;

          // IMPORTANT: Remove existing event listeners to prevent duplicates
          audioPlayback.removeEventListener("ended", handleAudioEnded);
          audioPlayback.addEventListener("ended", handleAudioEnded);

          // Play audio and handle potential errors
          try {
            await audioPlayback.play();
            updateStatus("🔊 Playing AI response...", "success");
          } catch (playError) {
            console.warn("Audio autoplay prevented:", playError);
            updateStatus(
              "Response ready! Click the audio player to hear the response.",
              "success"
            );
          }
        } else {
          console.warn("No audio data received");
          updateStatus(
            "Response processed, but no audio available.",
            "success"
          );
        }
      } catch (err) {
        console.error("Network/Processing error:", err);
        updateStatus("Error processing audio. Please try again.", "error");
      }
    };

    mediaRecorder.onerror = (event) => {
      console.error("MediaRecorder error:", event);
      updateStatus("Recording error occurred.", "error");
      resetRecordingState();
    };

    // Start recording
    mediaRecorder.start();
    updateButtonText(startBtn, "⏹", "Stop Recording");
    updateStatus("Recording... Speak now", "recording");
  } catch (err) {
    console.error("Auto-recording microphone access error:", err);
    updateStatus("Microphone access denied for auto-recording.", "error");
    isRecording = false;
  }
}

// Start/Stop Recording Button
startBtn.addEventListener("click", async () => {
  if (mediaRecorder && mediaRecorder.state === "recording") {
    mediaRecorder.stop();
    resetRecordingState();
    updateStatus("Processing audio...", "processing");
    return;
  }

  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    mediaRecorder = new MediaRecorder(stream);
    audioChunks = [];
    isRecording = true;

    mediaRecorder.ondataavailable = (event) => {
      if (event.data.size > 0) audioChunks.push(event.data);
    };

    mediaRecorder.onstop = async () => {
      // Stop all audio tracks to release microphone
      stream.getTracks().forEach((track) => track.stop());

      const audioBlob = new Blob(audioChunks, { type: "audio/wav" });
      const formData = new FormData();
      formData.append("file", audioBlob, "recording.wav");

      updateStatus("Processing with AI services...", "processing");

      try {
        const response = await fetch(`/agent/chat/${sessionId}`, {
          method: "POST",
          body: formData,
        });

        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`);
        }

        const data = await response.json();
        console.log("Response data:", data);

        // Display transcription in status (optional)
        if (data.transcription) {
          updateStatus(
            `You said: "${data.transcription.substring(0, 50)}..."`,
            "processing"
          );
          setTimeout(() => {
            updateStatus("AI is responding...", "processing");
          }, 2000);
        }

        // Validate and play audio response
        if (data && data.audio_base64) {
          // Use audio/mp3 since Murf returns MP3 format
          const audioUrl = `data:audio/mp3;base64,${data.audio_base64}`;
          audioPlayback.src = audioUrl;

          // IMPORTANT: Remove existing event listeners to prevent duplicates
          audioPlayback.removeEventListener("ended", handleAudioEnded);
          audioPlayback.addEventListener("ended", handleAudioEnded);

          // Play audio and handle potential errors
          try {
            await audioPlayback.play();
            updateStatus("🔊 Playing AI response...", "success");
          } catch (playError) {
            console.warn("Audio autoplay prevented:", playError);
            updateStatus(
              "Response ready! Click the audio player to hear the response.",
              "success"
            );
          }
        } else {
          console.warn("No audio data received");
          updateStatus(
            "Response processed, but no audio available.",
            "success"
          );
        }
      } catch (err) {
        console.error("Network/Processing error:", err);
        updateStatus("Error processing audio. Please try again.", "error");
      }
    };

    mediaRecorder.onerror = (event) => {
      console.error("MediaRecorder error:", event);
      updateStatus("Recording error occurred.", "error");
      resetRecordingState();
    };

    // Start recording
    mediaRecorder.start();
    updateButtonText(startBtn, "⏹", "Stop Recording");
    updateStatus("Recording... Speak now", "recording");
  } catch (err) {
    console.error("Microphone access error:", err);
    updateStatus(
      "Microphone access denied. Please allow microphone access and try again.",
      "error"
    );
  }
});

// End Conversation Button
stopBtn.addEventListener("click", () => {
  // Set conversation as ended to prevent auto-recording
  conversationEnded = true;

  // Stop recording if active
  if (mediaRecorder && mediaRecorder.state === "recording") {
    mediaRecorder.stop();
    resetRecordingState();
  }

  // Generate new session ID
  sessionId = Date.now().toString();

  // Clear audio
  audioPlayback.src = "";
  audioPlayback.load(); // Reset audio player

  // Reset status and allow new conversation
  updateStatus("Conversation ended. Ready for new session.");
  setTimeout(() => {
    conversationEnded = false; // Reset for new conversation
  }, 1000);

  console.log("New session started:", sessionId);
});

// Audio player event listeners with enhanced feedback
audioPlayback.addEventListener("loadstart", () => {
  console.log("Audio loading started");
  updateStatus("Loading audio...", "processing");
});

audioPlayback.addEventListener("canplay", () => {
  console.log("Audio ready to play");
});

audioPlayback.addEventListener("play", () => {
  updateStatus("🔊 Playing AI response...", "success");
});

audioPlayback.addEventListener("error", (e) => {
  console.error("Audio playback error:", e);
  console.error("Audio error details:", {
    error: e.target.error,
    networkState: e.target.networkState,
    readyState: e.target.readyState,
    src: e.target.src,
  });
  updateStatus(
    "Audio playback error. The audio format may not be supported.",
    "error"
  );
});

// UPDATED: Auto-recording after audio ends
audioPlayback.addEventListener("ended", () => {
  updateStatus("Ready for next recording...");

  // Auto-start recording after a short delay if enabled
  if (autoRecordAfterPlayback && !conversationEnded) {
    setTimeout(() => {
      autoStartRecording();
    }, 1000); // 1 second delay for better UX
  }
});

// Keyboard shortcuts
document.addEventListener("keydown", (event) => {
  // Space bar to toggle recording
  if (
    event.code === "Space" &&
    event.target.tagName !== "INPUT" &&
    event.target.tagName !== "TEXTAREA"
  ) {
    event.preventDefault();
    startBtn.click();
  }

  // Escape to end conversation
  if (event.code === "Escape") {
    event.preventDefault();
    stopBtn.click();
  }
});

// Prevent space bar from scrolling when focused on buttons
startBtn.addEventListener("keydown", (event) => {
  if (event.code === "Space") {
    event.preventDefault();
  }
});

stopBtn.addEventListener("keydown", (event) => {
  if (event.code === "Space") {
    event.preventDefault();
  }
});

// Page visibility handling - pause recording when page is hidden
document.addEventListener("visibilitychange", () => {
  if (document.hidden && mediaRecorder && mediaRecorder.state === "recording") {
    console.log("Page hidden, stopping recording");
    mediaRecorder.stop();
    resetRecordingState();
    updateStatus("Recording stopped due to page being hidden.", "error");
  }
});

// Initialize status
updateStatus("Ready to listen...");

// Add visual feedback for user interactions
startBtn.addEventListener("mousedown", () => {
  startBtn.style.transform = "translateY(1px) scale(0.98)";
});

startBtn.addEventListener("mouseup", () => {
  startBtn.style.transform = "";
});

stopBtn.addEventListener("mousedown", () => {
  stopBtn.style.transform = "translateY(1px) scale(0.98)";
});

stopBtn.addEventListener("mouseup", () => {
  stopBtn.style.transform = "";
});

// Enhanced error handling and retry functionality
function handleRetry() {
  updateStatus("Retrying...", "processing");
  // Could implement automatic retry logic here
}

// Debug logging for development
if (
  window.location.hostname === "localhost" ||
  window.location.hostname === "127.0.0.1"
) {
  console.log("AI Voice Chat Agent loaded");
  console.log("Session ID:", sessionId);
  console.log("Controls: Space = Toggle Recording, Escape = End Conversation");
  console.log("Auto-recording after TTS:", autoRecordAfterPlayback);

  // Enhanced debugging for audio issues
  audioPlayback.addEventListener("loadeddata", () => {
    console.log("Audio data loaded successfully");
  });

  audioPlayback.addEventListener("progress", () => {
    console.log("Audio loading progress");
  });
}
