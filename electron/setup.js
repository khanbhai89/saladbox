// Setup Wizard MCP Presets
const MCP_PRESETS = {
  github: {
    name: "github",
    command: "npx",
    args: ["-y", "@modelcontextprotocol/server-github"],
    env: { GITHUB_PERSONAL_ACCESS_TOKEN: "" },
  },
  "brave-search": {
    name: "brave-search",
    command: "npx",
    args: ["-y", "@modelcontextprotocol/server-brave-search"],
    env: { BRAVE_API_KEY: "" },
  },
  filesystem: {
    name: "filesystem",
    command: "npx",
    args: ["-y", "@modelcontextprotocol/server-filesystem", "{placeholder_home}"],
    env: {},
  },
  memory: {
    name: "memory",
    command: "npx",
    args: ["-y", "@modelcontextprotocol/server-memory"],
    env: {},
  },
  opencode: {
    name: "opencode",
    command: "npx",
    args: ["-y", "opencode-mcp-tool"],
    env: { OPENCODE_MODEL: "anthropic/claude-sonnet-4-5", OPENCODE_API_KEY: "" },
  },
};

let selectedMcpServers = [];
let homeDir = "";

async function initSetupWizard() {
  const setupWizard = document.getElementById("setup-wizard");
  if (!setupWizard) return;

  try {
    homeDir = await window.saladbox.getHomeDir();
  } catch (e) {
    console.error("Failed to get home directory:", e);
  }

  const mcpPresetBtns = document.querySelectorAll(".mcp-preset-btn");
  mcpPresetBtns.forEach((btn) => {
    btn.addEventListener("click", () => {
      const mcpType = btn.dataset.mcp;
      const preset = MCP_PRESETS[mcpType];
      if (preset) {
        const finalPreset = JSON.parse(JSON.stringify(preset));
        if (finalPreset.args && homeDir) {
          finalPreset.args = finalPreset.args.map(arg => 
            arg === "{placeholder_home}" ? homeDir : arg
          );
        }
        addMcpServer(finalPreset);
        btn.disabled = true;
        btn.classList.add("selected");
      }
    });
  });

  document.getElementById("setup-add-mcp")?.addEventListener("click", () => {
    const name = document.getElementById("mcp-name")?.value;
    const command = document.getElementById("mcp-command")?.value;
    const args = document.getElementById("mcp-args")?.value.split(",").map((a) => a.trim());

    if (name && command) {
      addMcpServer({ name, command, args, env: {} });
    }
  });
}

function addMcpServer(preset) {
  selectedMcpServers.push(preset);
  renderMcpList();
}

function removeMcpServer(index) {
  selectedMcpServers.splice(index, 1);
  renderMcpList();

  const btn = document.querySelector(`.mcp-preset-btn[data-mcp="${selectedMcpServers[index]?.name}"]`);
  if (btn) {
    btn.disabled = false;
    btn.classList.remove("selected");
  }
}

function renderMcpList() {
  const list = document.getElementById("setup-mcp-list");
  if (!list) return;

  list.innerHTML = selectedMcpServers
    .map(
      (server, index) => `
    <div class="mcp-server-item">
      <span>${server.name}</span>
      <button class="remove-btn" onclick="removeMcpServer(${index})">×</button>
    </div>
  `
    )
    .join("");
}

async function runSetup(config) {
  config.mcp_servers = {};
  selectedMcpServers.forEach((server) => {
    config.mcp_servers[server.name] = {
      command: server.command,
      args: server.args,
      env: server.env,
      enabled: true,
    };
  });

  return fetch("http://127.0.0.1:8765/setup/run", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(config),
  }).then((r) => r.json());
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", initSetupWizard);
} else {
  initSetupWizard();
}
