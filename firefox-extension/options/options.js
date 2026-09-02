// options/options.js — stores the backend auth token in browser.storage.local
// under the "apiToken" key, which background.js's apiFetch() reads on every request.

const input = document.getElementById("api-token");
const statusEl = document.getElementById("status");

async function load() {
  const { apiToken } = await browser.storage.local.get("apiToken");
  if (apiToken) input.value = apiToken;
}

document.getElementById("options-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  await browser.storage.local.set({ apiToken: input.value.trim() });
  statusEl.textContent = "Saved.";
  setTimeout(() => { statusEl.textContent = ""; }, 2000);
});

load();
