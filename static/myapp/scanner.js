(() => {
  const video = document.querySelector("#camera");
  const startButton = document.querySelector("#start-camera");
  const status = document.querySelector("#scan-status");
  const placeholder = document.querySelector("#camera-placeholder");
  const result = document.querySelector("#scan-result-content");
  const csrfToken = document.querySelector("#csrf-form input[name=csrfmiddlewaretoken]").value;
  const canvas = document.createElement("canvas");
  const canvasContext = canvas.getContext("2d", { willReadFrequently: true });
  let stream;
  let detector;
  let active = false;
  let submitting = false;
  let useNativeDetector = false;

  const escapeHtml = (value) => {
    const element = document.createElement("span");
    element.textContent = value ?? "";
    return element.innerHTML;
  };

  function stopCamera() {
    active = false;
    if (stream) stream.getTracks().forEach((track) => track.stop());
    stream = undefined;
    video.srcObject = null;
    placeholder.hidden = false;
    startButton.disabled = false;
    startButton.textContent = "เปิดกล้อง";
  }

  function showMember(member) {
    result.innerHTML = `<div class="result-success"><span class="result-badge">เช็คอินสำเร็จ</span><strong>${escapeHtml(member.nickname || member.name)}</strong><p>${escapeHtml(member.name)} · ${escapeHtml(member.member_code)}</p><p>${escapeHtml(member.phone)}</p><p>${escapeHtml(member.checked_in_at)}</p></div>`;
  }

  async function submitToken(token) {
    if (submitting) return;
    submitting = true;
    status.textContent = "กำลังตรวจสอบ QR...";
    try {
      const response = await fetch("/staff/scan/", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken },
        body: JSON.stringify({ token }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "สแกนไม่สำเร็จ");
      showMember(data.member);
      status.textContent = "เช็คอินสำเร็จ · QR นี้ใช้ได้ครั้งเดียว";
    } catch (error) {
      status.textContent = error.message;
    } finally {
      stopCamera();
      submitting = false;
    }
  }

  async function scanFrame() {
    if (!active) return;
    try {
      let token = "";
      if (useNativeDetector) {
        const codes = await detector.detect(video);
        token = codes[0]?.rawValue || "";
      } else if (video.readyState >= HTMLMediaElement.HAVE_ENOUGH_DATA && video.videoWidth) {
        const scale = Math.min(1, 640 / video.videoWidth);
        canvas.width = Math.round(video.videoWidth * scale);
        canvas.height = Math.round(video.videoHeight * scale);
        canvasContext.drawImage(video, 0, 0, canvas.width, canvas.height);
        const frame = canvasContext.getImageData(0, 0, canvas.width, canvas.height);
        token = window.jsQR(frame.data, frame.width, frame.height, { inversionAttempts: "dontInvert" })?.data || "";
      }
      if (token) {
        await submitToken(token.trim());
        return;
      }
    } catch (error) {
      status.textContent = "อ่านภาพจากกล้องไม่สำเร็จ กรุณาปิดกล้องแล้วลองใหม่";
      stopCamera();
      return;
    }
    requestAnimationFrame(scanFrame);
  }

  startButton.addEventListener("click", async () => {
    if (!navigator.mediaDevices?.getUserMedia) {
      status.textContent = "เบราว์เซอร์ไม่อนุญาตกล้องในที่อยู่นี้ กรุณาเปิดผ่าน localhost หรือ HTTPS";
      return;
    }
    if (!("BarcodeDetector" in window) && typeof window.jsQR !== "function") {
      status.textContent = "โหลดตัวอ่าน QR ไม่สำเร็จ กรุณารีเฟรชหน้าเว็บ";
      return;
    }
    status.textContent = "กำลังตรวจสอบสิทธิ์กล้อง...";
    if (navigator.permissions?.query) {
      try {
        const permission = await navigator.permissions.query({ name: "camera" });
        if (permission.state === "denied") {
          status.textContent = "กล้องถูกบล็อก: กดไอคอนข้าง URL → การตั้งค่าเว็บไซต์ → กล้อง → อนุญาต แล้วรีเฟรชหน้า";
          return;
        }
      } catch (error) {
      }
    }
    try {
      useNativeDetector = "BarcodeDetector" in window;
      if (useNativeDetector) {
        try {
          detector = new BarcodeDetector({ formats: ["qr_code"] });
        } catch (error) {
          useNativeDetector = false;
        }
      }
      stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: "environment" } }, audio: false });
      video.srcObject = stream;
      await video.play();
      placeholder.hidden = true;
      active = true;
      startButton.disabled = true;
      startButton.textContent = "กำลังสแกน";
      status.textContent = useNativeDetector ? "จัด QR ให้อยู่ในกรอบกล้อง" : "กล้องพร้อมแล้ว · จัด QR ให้อยู่ในกรอบ";
      scanFrame();
    } catch (error) {
      const messages = {
        NotAllowedError: "เบราว์เซอร์ปฏิเสธสิทธิ์กล้อง กรุณาอนุญาต Camera ให้เว็บไซต์นี้แล้วลองอีกครั้ง",
        PermissionDeniedError: "เบราว์เซอร์ปฏิเสธสิทธิ์กล้อง กรุณาอนุญาต Camera ให้เว็บไซต์นี้แล้วลองอีกครั้ง",
        NotFoundError: "ไม่พบกล้องในอุปกรณ์นี้",
        NotReadableError: "กล้องกำลังถูกใช้งานโดยแอปอื่น กรุณาปิดแอปนั้นแล้วลองใหม่",
        OverconstrainedError: "เปิดกล้องหลังไม่ได้ กรุณาตรวจสอบกล้องของอุปกรณ์",
        SecurityError: "ที่อยู่นี้ไม่ปลอดภัยสำหรับการใช้กล้อง กรุณาเปิดผ่าน localhost หรือ HTTPS",
      };
      status.textContent = messages[error.name] || `เปิดกล้องไม่สำเร็จ (${error.name || "CameraError"}) กรุณาตรวจสิทธิ์กล้องและลองใหม่`;
      stopCamera();
    }
  });

  window.addEventListener("pagehide", stopCamera);
})();