(() => {
  const content = document.querySelector("#display-content");
  const clock = document.querySelector("#display-clock");
  let renderedId = null;

  function escapeHtml(value) {
    const element = document.createElement("span");
    element.textContent = value ?? "";
    return element.innerHTML;
  }

  function updateClock() {
    clock.textContent = new Intl.DateTimeFormat("th-TH", { dateStyle: "medium", timeStyle: "medium" }).format(new Date());
  }

  function render(member) {
    if (!member || member.id === renderedId) return;
    renderedId = member.id;
    const memberships = member.memberships.length
      ? member.memberships.map((item) => `${escapeHtml(item.package)} · ถึง ${escapeHtml(item.expire_date)} (${escapeHtml(item.status)})`).join("<br>")
      : "ยังไม่มีข้อมูลแพ็กเกจ";
    content.innerHTML = `<p class="eyebrow">CHECK-IN SUCCESS / ${escapeHtml(member.member_code)}</p><h1>ยินดีต้อนรับ${member.nickname ? ` คุณ${escapeHtml(member.nickname)}` : ` ${escapeHtml(member.name)}`}</h1><div class="display-meta"><span>${escapeHtml(member.name)}</span><span>${escapeHtml(member.phone)}</span><span>${escapeHtml(member.checked_in_at)}</span></div><div class="display-package">${memberships}</div>`;
    content.classList.remove("display-content");
    requestAnimationFrame(() => content.classList.add("display-content"));
  }

  async function refresh() {
    try {
      const response = await fetch("/staff/display/latest/", { headers: { "Accept": "application/json" }, cache: "no-store" });
      if (!response.ok) return;
      const data = await response.json();
      render(data.checkin);
    } catch (error) {
      clock.textContent = "กำลังเชื่อมต่อ...";
    }
  }

  updateClock();
  refresh();
  window.setInterval(updateClock, 1000);
  window.setInterval(refresh, 2000);
})();