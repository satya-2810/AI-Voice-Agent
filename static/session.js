// Session page: the live voice agent (ready -> active -> ended).

// ============ Guard: bounce back to setup if keys were never saved ============
fetch("/health")
  .then((res) => res.json())
  .then((data) => {
    const keys = data.api_keys || {};
    if (!keys.gemini || !keys.murf || !keys.assemblyai) {
      window.location.href = "/";
    }
  })
  .catch(() => {
    // If the health check itself fails, let the user try anyway rather than
    // trapping them — startSession() will surface a clear error either way.
  });

// ============ Elements ============
const screenReady = document.getElementById("screenReady");
const screenActive = document.getElementById("screenActive");
const screenEnded = document.getElementById("screenEnded");

const editKeysBtn = document.getElementById("editKeysBtn");
const startSessionBtn = document.getElementById("startSessionBtn");
const startNewSessionBtn = document.getElementById("startNewSessionBtn");
const stopMicBtn = document.getElementById("stopMicBtn");
const stopMicLabel = document.getElementById("stopMicLabel");
const endConversationBtn = document.getElementById("endConversationBtn");
const backToSetupBtn = document.getElementById("backToSetupBtn");

const statusLine = document.getElementById("statusLine");
const chatWindow = document.getElementById("chatWindow");
const equalizerEl = document.getElementById("equalizer");

// ============ Screen switching (within this page only) ============
function showScreen(screen) {
  [screenReady, screenActive, screenEnded].forEach((s) => {
    s.hidden = s !== screen;
  });
}

editKeysBtn.addEventListener("click", () => (window.location.href = "/"));
backToSetupBtn.addEventListener("click", () => (window.location.href = "/"));

// ============ Chat window ============
let pendingUserBubble = null;
let activeAssistantBubble = null;

function addSystemMessage(text) {
  const el = document.createElement("div");
  el.className = "msg system";
  el.textContent = text;
  chatWindow.appendChild(el);
  chatWindow.scrollTop = chatWindow.scrollHeight;
}

function upsertUserPartial(text) {
  if (!pendingUserBubble) {
    pendingUserBubble = document.createElement("div");
    pendingUserBubble.className = "msg user pending";
    chatWindow.appendChild(pendingUserBubble);
  }
  pendingUserBubble.textContent = text;
  chatWindow.scrollTop = chatWindow.scrollHeight;
}

function finalizeUserMessage(text) {
  if (!pendingUserBubble) {
    pendingUserBubble = document.createElement("div");
    pendingUserBubble.className = "msg user";
    chatWindow.appendChild(pendingUserBubble);
  }
  pendingUserBubble.textContent = text;
  pendingUserBubble.classList.remove("pending");
  pendingUserBubble = null;
  chatWindow.scrollTop = chatWindow.scrollHeight;
}

function appendAssistantChunk(chunk) {
  if (!activeAssistantBubble) {
    activeAssistantBubble = document.createElement("div");
    activeAssistantBubble.className = "msg assistant pending";
    chatWindow.appendChild(activeAssistantBubble);
  }
  activeAssistantBubble.textContent += chunk;
  chatWindow.scrollTop = chatWindow.scrollHeight;
}

function finalizeAssistantMessage(text) {
  if (!activeAssistantBubble) {
    activeAssistantBubble = document.createElement("div");
    activeAssistantBubble.className = "msg assistant";
    chatWindow.appendChild(activeAssistantBubble);
  }
  activeAssistantBubble.textContent = text;
  activeAssistantBubble.classList.remove("pending");
  activeAssistantBubble = null;
  chatWindow.scrollTop = chatWindow.scrollHeight;
}

function clearChat() {
  chatWindow.innerHTML = "";
  pendingUserBubble = null;
  activeAssistantBubble = null;
}

// ============ Equalizer (real mic-volume reactive) ============
const BAR_COUNT = 24;
let analyser = null;
let freqData = null;
let equalizerRaf = null;

function buildEqualizerBars() {
  equalizerEl.innerHTML = "";
  for (let i = 0; i < BAR_COUNT; i++) {
    const bar = document.createElement("div");
    bar.className = "bar";
    equalizerEl.appendChild(bar);
  }
}

function animateEqualizer() {
  const bars = equalizerEl.children;

  if (isMicMuted || !analyser) {
    for (let i = 0; i < bars.length; i++) {
      bars[i].style.transform = "scaleY(0.08)";
    }
    equalizerRaf = requestAnimationFrame(animateEqualizer);
    return;
  }

  analyser.getByteFrequencyData(freqData);
  const binsPerBar = Math.floor(freqData.length / BAR_COUNT) || 1;

  for (let i = 0; i < bars.length; i++) {
    let sum = 0;
    for (let j = 0; j < binsPerBar; j++) {
      sum += freqData[i * binsPerBar + j];
    }
    const avg = sum / binsPerBar / 255; // 0..1
    const scale = Math.max(0.08, Math.min(1, avg * 1.6));
    bars[i].style.transform = `scaleY(${scale})`;
  }

  equalizerRaf = requestAnimationFrame(animateEqualizer);
}

// ============ Audio capture + playback state ============
let ws = null;
let audioContext = null;
let processor = null;
let micStream = null;
let isMicMuted = false;

let playbackContext = null;
let nextStartTime = 0;
let audioBuffer = [];
let isPlayingAudio = false;
let isBuffering = true;
let currentlyPlaying = [];
const BUFFER_THRESHOLD = 3;

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

function initializePlaybackContext() {
  if (!playbackContext) {
    playbackContext = new (window.AudioContext || window.webkitAudioContext)({
      sampleRate: 44100,
    });
    if (playbackContext.state === "suspended") playbackContext.resume();
    nextStartTime = playbackContext.currentTime;
  }
}

function addToAudioBuffer(base64Audio) {
  const float32Array = base64ToPCMFloat32(base64Audio);
  if (!float32Array || float32Array.length === 0) return;

  audioBuffer.push(float32Array);

  if (audioBuffer.length >= BUFFER_THRESHOLD && isBuffering) {
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
    playAudioChunkBuffered(audioBuffer.shift());
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
  if (nextStartTime <= now) nextStartTime = now + 0.01;

  source.start(nextStartTime);
  nextStartTime += buffer.duration;

  currentlyPlaying.push({ source, endTime: nextStartTime });

  source.onended = () => {
    source.disconnect();
    currentlyPlaying = currentlyPlaying.filter((item) => item.source !== source);
  };
}

function checkForMoreAudio() {
  if (audioBuffer.length > 0) {
    startBufferedPlayback();
    return;
  }
  const now = playbackContext ? playbackContext.currentTime : 0;
  const stillPlaying = currentlyPlaying.some((item) => item.endTime > now);

  if (!stillPlaying) {
    isPlayingAudio = false;
  } else {
    setTimeout(checkForMoreAudio, 50);
  }
}

function playAudioChunk(base64Audio) {
  initializePlaybackContext();
  addToAudioBuffer(base64Audio);
}

function resetAudioPlayback() {
  audioBuffer = [];
  isPlayingAudio = false;
  isBuffering = true;
  currentlyPlaying.forEach((item) => {
    try {
      item.source.stop();
      item.source.disconnect();
    } catch (e) {
      /* already stopped */
    }
  });
  currentlyPlaying = [];
  if (playbackContext) nextStartTime = playbackContext.currentTime;
}

function float32ToInt16(buffer) {
  let l = buffer.length;
  const buf = new Int16Array(l);
  while (l--) {
    buf[l] = Math.max(-1, Math.min(1, buffer[l])) * 0x7fff;
  }
  return buf;
}

// ============ Session lifecycle ============
async function startSession() {
  try {
    ws = new WebSocket(`ws://${window.location.host}/ws`);

    ws.onopen = async () => {
      statusLine.textContent = "Listening…";
      resetAudioPlayback();
      clearChat();
      showScreen(screenActive);
      buildEqualizerBars();

      micStream = await navigator.mediaDevices.getUserMedia({
        audio: {
          sampleRate: 16000,
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
        },
      });

      audioContext = new AudioContext({ sampleRate: 16000 });
      const source = audioContext.createMediaStreamSource(micStream);

      analyser = audioContext.createAnalyser();
      analyser.fftSize = 64;
      freqData = new Uint8Array(analyser.frequencyBinCount);
      source.connect(analyser);

      processor = audioContext.createScriptProcessor(4096, 1, 1);
      processor.onaudioprocess = (event) => {
        if (ws && ws.readyState === WebSocket.OPEN) {
          const inputData = event.inputBuffer.getChannelData(0);
          ws.send(float32ToInt16(inputData).buffer);
        }
      };

      source.connect(processor);
      processor.connect(audioContext.destination);

      isMicMuted = false;
      stopMicLabel.textContent = "Stop mic";
      stopMicBtn.classList.remove("muted");

      equalizerRaf = requestAnimationFrame(animateEqualizer);
    };

    ws.onerror = () => {
      addSystemMessage("Connection error. Please check your keys and try again.");
    };

    ws.onclose = () => {
      statusLine.textContent = "Disconnected";
    };

    ws.onmessage = (event) => {
      let message;
      try {
        message = JSON.parse(event.data);
      } catch (e) {
        return;
      }

      switch (message.type) {
        case "partial_transcription":
          upsertUserPartial(message.transcript);
          break;
        case "final_transcription":
          finalizeUserMessage(message.transcript);
          statusLine.textContent = "Lady Victoria is responding…";
          break;
        case "llm_chunk":
          appendAssistantChunk(message.content);
          break;
        case "llm_final_response":
          finalizeAssistantMessage(message.content);
          break;
        case "tts_audio_chunk":
          if (playbackContext && playbackContext.state === "suspended") {
            playbackContext.resume().then(() => playAudioChunk(message.audio_base64));
          } else {
            playAudioChunk(message.audio_base64);
          }
          break;
        case "tts_done":
          isBuffering = false;
          if (audioBuffer.length > 0 && !isPlayingAudio) startBufferedPlayback();
          statusLine.textContent = isMicMuted ? "Mic paused" : "Listening…";
          break;
        case "error":
          addSystemMessage(message.message || "Something went wrong.");
          break;
      }
    };
  } catch (err) {
    addSystemMessage("Microphone access was denied.");
  }
}

function toggleMicPause() {
  if (!audioContext) return;

  isMicMuted = !isMicMuted;

  if (isMicMuted) {
    audioContext.suspend();
    stopMicLabel.textContent = "Resume mic";
    stopMicBtn.classList.add("muted");
    statusLine.textContent = "Mic paused";
  } else {
    audioContext.resume();
    stopMicLabel.textContent = "Stop mic";
    stopMicBtn.classList.remove("muted");
    statusLine.textContent = "Listening…";
  }
}

function endConversation() {
  if (equalizerRaf) {
    cancelAnimationFrame(equalizerRaf);
    equalizerRaf = null;
  }

  if (processor) {
    processor.disconnect();
    processor = null;
  }
  if (analyser) {
    analyser.disconnect();
    analyser = null;
  }
  if (audioContext) {
    audioContext.close();
    audioContext = null;
  }
  if (micStream) {
    micStream.getTracks().forEach((track) => track.stop());
    micStream = null;
  }
  if (playbackContext) {
    playbackContext.close();
    playbackContext = null;
  }
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.close();
  }
  ws = null;

  resetAudioPlayback();
  clearChat();
  isMicMuted = false;

  showScreen(screenEnded);
}

startSessionBtn.addEventListener("click", startSession);
startNewSessionBtn.addEventListener("click", startSession);
stopMicBtn.addEventListener("click", toggleMicPause);
endConversationBtn.addEventListener("click", endConversation);

// ============ Init ============
window.addEventListener("DOMContentLoaded", () => {
  showScreen(screenReady);
});