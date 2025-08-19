const startBtn = document.getElementById("startBtn");
const stopBtn = document.getElementById("stopBtn");
const statusDiv = document.getElementById("statusBox");
const voiceVisualizer = document.getElementById("voiceVisualizer");

let mediaRecorder;
let isRecording = false;
let ws = null;
let audioContext = null;
let processor = null;

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

  if (statusText) statusText.textContent = message;

  statusDiv.classList.remove("error", "success", "processing");
  statusIndicator.classList.remove("recording", "processing");
  glassCard.classList.remove("processing");
  startBtn.classList.remove("recording");

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

// Convert float32 audio to int16 PCM
function float32ToInt16(buffer) {
  let l = buffer.length;
  let buf = new Int16Array(l);
  while (l--) {
    buf[l] = Math.max(-1, Math.min(1, buffer[l])) * 0x7fff;
  }
  return buf;
}

// Start Recording
startBtn.addEventListener("click", async () => {
  if (isRecording) {
    // Stop recording
    if (processor) {
      processor.disconnect();
      processor = null;
    }
    if (audioContext) {
      audioContext.close();
      audioContext = null;
    }
    if (ws) ws.close();
    resetRecordingState();
    updateStatus("Stopping and saving audio...", "processing");
    return;
  }

  try {
    // Open WebSocket to backend
    ws = new WebSocket(`ws://${window.location.host}/ws`);

    ws.onopen = async () => {
      console.log("✅ WebSocket connected");
      updateStatus("Recording... Speak now", "recording");

      // Get microphone stream with specific constraints
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          sampleRate: 16000,
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
        },
      });

      // Create AudioContext for processing raw audio
      audioContext = new AudioContext({ sampleRate: 16000 });
      const source = audioContext.createMediaStreamSource(stream);

      // Create ScriptProcessor for real-time audio processing
      processor = audioContext.createScriptProcessor(4096, 1, 1);

      processor.onaudioprocess = (event) => {
        if (ws && ws.readyState === WebSocket.OPEN) {
          const inputBuffer = event.inputBuffer;
          const inputData = inputBuffer.getChannelData(0);

          // Convert float32 to int16 PCM
          const pcmData = float32ToInt16(inputData);

          // Send raw PCM data to WebSocket
          ws.send(pcmData.buffer);
        }
      };

      // Connect audio processing chain
      source.connect(processor);
      processor.connect(audioContext.destination);

      isRecording = true;
      updateButtonText(startBtn, "⏹", "Stop Recording");
    };

    ws.onerror = (err) => {
      console.error("WebSocket error:", err);
      updateStatus("WebSocket error. Check backend.", "error");
      resetRecordingState();
    };

    ws.onclose = () => {
      console.log("⚠️ WebSocket closed");
      resetRecordingState();
    };

    ws.onmessage = (event) => {
      console.log("📩 Received from server:", event.data);
    };
  } catch (err) {
    console.error("Microphone access error:", err);
    updateStatus("Microphone access denied.", "error");
    isRecording = false;
  }
});

// End Conversation Button
stopBtn.addEventListener("click", () => {
  if (processor) {
    processor.disconnect();
    processor = null;
  }
  if (audioContext) {
    audioContext.close();
    audioContext = null;
  }
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.close();
  }
  resetRecordingState();
  updateStatus("Conversation ended. Ready for new session.");
});

// Initialize status
updateStatus("Ready to listen...");

// Debug logging
if (
  window.location.hostname === "localhost" ||
  window.location.hostname === "127.0.0.1"
) {
  console.log("AI Voice Chat Agent (Strict Mode) loaded");
  console.log("Controls: Space = Toggle Recording, Escape = End Conversation");
}
