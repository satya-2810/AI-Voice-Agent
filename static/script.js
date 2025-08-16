const startBtn = document.getElementById("startBtn");
const stopBtn = document.getElementById("stopBtn");
const audioPlayback = document.getElementById("audioPlayback");
const statusDiv = document.getElementById("statusBox");

let mediaRecorder;
let audioChunks = [];

const sessionId =
  new URLSearchParams(window.location.search).get("session_id") ||
  Date.now().toString();

// Start Recording
startBtn.addEventListener("click", async () => {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    mediaRecorder = new MediaRecorder(stream);
    audioChunks = [];

    mediaRecorder.ondataavailable = (event) => {
      if (event.data.size > 0) audioChunks.push(event.data);
    };

    mediaRecorder.onstop = async () => {
      const audioBlob = new Blob(audioChunks, { type: "audio/wav" });
      const formData = new FormData();
      formData.append("file", audioBlob, "recording.wav");

      statusDiv.textContent = "Sending audio to pipeline...";

      try {
        const response = await fetch(`/agent/chat/${sessionId}`, {
          method: "POST",
          body: formData,
        });

        if (!response.ok) {
          statusDiv.textContent = "Error processing audio.";
          return;
        }

        const data = await response.json();

        // Play audio from base64
        const audioUrl = `data:audio/mpeg;base64,${data.audio_base64}`;
        audioPlayback.src = audioUrl;
        audioPlayback.play().catch(() => {});

        statusDiv.textContent = "Response ready!";
      } catch (err) {
        console.error(err);
        statusDiv.textContent = "Network error.";
      }
    };

    mediaRecorder.start();
    startBtn.textContent = "⏹ Stop Recording";
    statusDiv.textContent = "Recording...";
  } catch (err) {
    console.error(err);
    statusDiv.textContent = "Microphone access denied.";
  }
});

// Stop Recording
stopBtn.addEventListener("click", () => {
  if (mediaRecorder && mediaRecorder.state !== "inactive") {
    mediaRecorder.stop();
    startBtn.textContent = "🎤 Start Recording"; // revert text
  }
});
