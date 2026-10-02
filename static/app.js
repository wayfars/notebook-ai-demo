const list = document.querySelector("#source-list");
const answer = document.querySelector("#answer");
const escapeHTML = (value) => value.replace(/[&<>"']/g, (ch) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
}[ch]));

fetch("/api/sources").then((r) => r.json()).then((sources) => {
  list.innerHTML = sources.map((s) => `<li>${escapeHTML(s.title)}</li>`).join("");
}).catch(() => { list.textContent = "Could not load sample sources."; });

document.querySelector("#ask-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  answer.className = "answer";
  answer.textContent = "Retrieving sources and asking the configured model…";
  const question = document.querySelector("#question").value;
  try {
    const response = await fetch("/api/ask", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question })
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || "Request failed");
    const citations = (payload.citations || []).map((c) => `[${c.marker}] ${c.title}`);
    const sources = (payload.sources || []).map((s) =>
      `<li><strong>[${escapeHTML(s.marker)}] ${escapeHTML(s.title)}</strong><p>${escapeHTML(s.excerpt)}</p></li>`
    ).join("");
    const validation = payload.citation_validation || {};
    const checks = [];
    if (validation.missing_citations) checks.push("No citation marker was returned for this answer.");
    if ((validation.unknown_markers || []).length) checks.push(`Unknown markers: ${validation.unknown_markers.map((marker) => escapeHTML(marker)).join(", ")}`);
    answer.innerHTML = `<strong>Answer</strong><p>${escapeHTML(payload.answer)}</p>` +
      (checks.length ? `<p class="error">${checks.join(" ")}</p>` : "") +
      (sources ? `<strong>Retrieved excerpts</strong><ol>${sources}</ol>` : "");
  } catch (error) {
    answer.className = "answer error";
    answer.textContent = `Could not answer: ${error.message}`;
  }
});
