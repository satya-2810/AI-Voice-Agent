const startBtn = document.getElementById("startBtn");
const stopBtn = document.getElementById("stopBtn");
const statusDiv = document.getElementById("statusBox");
const voiceVisualizer = document.getElementById("voiceVisualizer");
const transcriptionDisplay = document.getElementById("transcriptionDisplay");

let mediaRecorder;
let isRecording = false;
let ws = null;
let audioContext = null;
let processor = null;

let ttsChunks = [];

// Audio Buffering for Seamless Playback
let playbackContext;
let playheadTime = 0;
let audioQueue = [];
let audioBuffer = [];
let isPlayingAudio = false;
let nextStartTime = 0;
let bufferThreshold = 3;
let isBuffering = true;
let currentlyPlaying = [];

function base64ToPCMFloat32(base64) {
  const binary = atob(base64);
  let offset = 0;

  if (binary.length > 44 && binary.slice(0, 4) === "RIFF") {
    offset = 44;
  }

  const length = binary.length - offset;
  const byteArray = new Uint8Array(length);

  for (let i = 0; i < length; i++) {
    byteArray[i] = binary.charCodeAt(i + offset);
  }

  const view = new DataView(byteArray.buffer);
  const sampleCount = byteArray.length / 2;
  const float32Array = new Float32Array(sampleCount);

  for (let i = 0; i < sampleCount; i++) {
    const int16 = view.getInt16(i * 2, true);
    float32Array[i] = int16 / 32768;
  }

  return float32Array;
}

function initializeAudioContext() {
  if (!playbackContext) {
    playbackContext = new (window.AudioContext || window.webkitAudioContext)({
      sampleRate: 44100,
    });

    if (playbackContext.state === "suspended") {
      playbackContext.resume();
    }

    nextStartTime = playbackContext.currentTime;
  }
}

function addToAudioBuffer(base64Audio) {
  const float32Array = base64ToPCMFloat32(base64Audio);
  if (!float32Array || float32Array.length === 0) return;

  audioBuffer.push(float32Array);

  if (audioBuffer.length >= bufferThreshold && isBuffering) {
    isBuffering = false;
    startBufferedPlayback();
  } else if (!isBuffering && !isPlayingAudio) {
    startBufferedPlayback();
  }
}

function startBufferedPlayback() {
  if (!playbackContext || audioBuffer.length === 0) return;

  isPlayingAudio = true;

  while (audioBuffer.length > 0) {
    const float32Array = audioBuffer.shift();
    playAudioChunkBuffered(float32Array);
  }

  setTimeout(checkForMoreAudio, 50);
}

function playAudioChunkBuffered(float32Array) {
  if (!playbackContext) return;

  const buffer = playbackContext.createBuffer(1, float32Array.length, 44100);
  buffer.copyToChannel(float32Array, 0);

  const source = playbackContext.createBufferSource();
  source.buffer = buffer;
  source.connect(playbackContext.destination);

  const now = playbackContext.currentTime;

  if (nextStartTime <= now) {
    nextStartTime = now + 0.01;
  }

  source.start(nextStartTime);
  nextStartTime += buffer.duration;

  currentlyPlaying.push({
    source: source,
    endTime: nextStartTime,
  });

  source.onended = () => {
    source.disconnect();
    currentlyPlaying = currentlyPlaying.filter(
      (item) => item.source !== source
    );
  };
}

function checkForMoreAudio() {
  if (audioBuffer.length > 0) {
    startBufferedPlayback();
  } else {
    const now = playbackContext ? playbackContext.currentTime : 0;
    const stillPlaying = currentlyPlaying.some((item) => item.endTime > now);

    if (!stillPlaying) {
      isPlayingAudio = false;
    } else {
      setTimeout(checkForMoreAudio, 50);
    }
  }
}

function playAudioChunk(base64Audio) {
  initializeAudioContext();
  addToAudioBuffer(base64Audio);
}

// Helpers
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

// Display final transcription
function displayTranscription(transcript) {
  if (transcriptionDisplay) {
    const finalTranscript = document.createElement("div");
    finalTranscript.className = "final-transcript";
    finalTranscript.textContent = transcript;
    transcriptionDisplay.appendChild(finalTranscript);
    transcriptionDisplay.scrollTop = transcriptionDisplay.scrollHeight;
  }
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

// Reset audio playback state for new conversation turn
function resetAudioPlayback() {
  audioQueue = [];
  audioBuffer = [];
  isPlayingAudio = false;
  isBuffering = true;
  currentlyPlaying.forEach((item) => {
    if (item.source) {
      try {
        item.source.stop();
        item.source.disconnect();
      } catch (e) {}
    }
  });
  currentlyPlaying = [];

  if (playbackContext) {
    nextStartTime = playbackContext.currentTime;
  }
}

// Start Recording
async function beginRecording() {
  try {
    ws = new WebSocket(`ws://${window.location.host}/ws`);

    ws.onopen = async () => {
      console.log("✅ WebSocket connected");
      updateStatus("Recording... Speak now", "recording");

      ttsChunks = [];
      resetAudioPlayback();

      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          sampleRate: 16000,
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
        },
      });

      audioContext = new AudioContext({ sampleRate: 16000 });
      const source = audioContext.createMediaStreamSource(stream);
      processor = audioContext.createScriptProcessor(4096, 1, 1);

      processor.onaudioprocess = (event) => {
        if (ws && ws.readyState === WebSocket.OPEN) {
          const inputBuffer = event.inputBuffer;
          const inputData = inputBuffer.getChannelData(0);
          const pcmData = float32ToInt16(inputData);
          ws.send(pcmData.buffer);
        }
      };

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
      try {
        const message = JSON.parse(event.data);

        if (message.type === "final_transcription") {
          displayTranscription(message.transcript);
          updateStatus("Turn completed ✓", "success");
        } else if (message.type === "llm_chunk") {
          console.log("LLM chunk:", message.content);
        } else if (message.type === "tts_audio_chunk") {
          if (playbackContext && playbackContext.state === "suspended") {
            playbackContext.resume().then(() => {
              playAudioChunk(message.audio_base64);
            });
          } else {
            playAudioChunk(message.audio_base64);
          }
          console.log("🎧 Buffering TTS audio chunk");
        } else if (message.type === "tts_done") {
          console.log(
            "✅ Client ACK: TTS stream complete. Total chunks =",
            ttsChunks.length
          );
          isBuffering = false;
          if (audioBuffer.length > 0 && !isPlayingAudio) {
            startBufferedPlayback();
          }
        } else if (message.type === "turn_end") {
          updateStatus("Turn ended - ready for next turn", "default");

          if (!isRecording) {
            setTimeout(() => {
              beginRecording();
            }, 500);
          }
        }
      } catch (e) {
        console.log("Plain message:", event.data);
      }
    };
  } catch (err) {
    console.error("Microphone access error:", err);
    updateStatus("Microphone access denied.", "error");
    isRecording = false;
  }
}

startBtn.addEventListener("click", async () => {
  if (isRecording) {
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

  beginRecording();
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
  if (playbackContext) {
    playbackContext.close();
    playbackContext = null;
  }
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.close();
  }

  resetRecordingState();
  resetAudioPlayback();
  updateStatus("Conversation ended. Ready for new session.");
  if (transcriptionDisplay) transcriptionDisplay.innerHTML = "";
});

// API Key Config
function saveApiKeys() {
  const murfKey = document.getElementById("murfKey").value.trim();
  const assemblyKey = document.getElementById("assemblyKey").value.trim();
  const geminiKey = document.getElementById("geminiKey").value.trim();
  const tavilyKey = document.getElementById("tavilyKey").value.trim();

  const keys = { murfKey, assemblyKey, geminiKey, tavilyKey };
  localStorage.setItem("apiKeys", JSON.stringify(keys));

  fetch("/config", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(keys),
  })
    .then(() => {
      updateStatus("API Keys saved ✓", "success");
    })
    .catch(() => {
      updateStatus("Failed to send API keys", "error");
    });
}

function loadApiKeys() {
  const saved = localStorage.getItem("apiKeys");
  if (saved) {
    const { murfKey, assemblyKey, geminiKey, tavilyKey } = JSON.parse(saved);
    document.getElementById("murfKey").value = murfKey || "";
    document.getElementById("assemblyKey").value = assemblyKey || "";
    document.getElementById("geminiKey").value = geminiKey || "";
    document.getElementById("tavilyKey").value = tavilyKey || "";
  }
}

window.addEventListener("DOMContentLoaded", loadApiKeys);

updateStatus("Ready to listen...");
