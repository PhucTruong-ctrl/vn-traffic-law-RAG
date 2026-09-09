import type { HookAPI } from "@oh-my-pi/pi-coding-agent/extensibility/hooks";

export default function formatAfterEdit(pi: HookAPI): void {
  pi.on("tool_result", async (event) => {
    if (event.toolName !== "edit" || event.isError) return;

    const result = await pi.exec("./scripts/format-codebase.sh", {
      timeout: 120_000,
    });

    if (result.code !== 0) {
      pi.logger.warn(`Codebase formatting failed: ${result.stderr}`);
    }
  });
}
