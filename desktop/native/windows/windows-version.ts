export interface WindowsVersion {
  major: number;
  minor: number;
  build: number;
  isWindows10: boolean;
  isWindows11: boolean;
  isWSL2Supported: boolean;
  installMethod: "wsl_install" | "dism";
  needsRestart: boolean;
  supportsWSLg: boolean;
  supportsSystemd: boolean;
}

export interface CommandOutput {
  exitCode: number;
  stdout: string;
  stderr: string;
}

export async function runCommand(
  command: string,
  timeout: number = 30000
): Promise<CommandOutput> {
  const { spawn } = await import("child_process");
  return new Promise((resolve) => {
    const isCmd = command.startsWith("cmd ") || command.startsWith("wmic ") || command.startsWith("dism");
    const shell = isCmd ? "cmd.exe" : undefined;
    const shellArgs = isCmd ? ["/c", command] : undefined;

    const child = shell
      ? spawn(shell, shellArgs!, { stdio: ["pipe", "pipe", "pipe"] })
      : spawn(command, [], { stdio: ["pipe", "pipe", "pipe"], shell: true });

    let stdout = "";
    let stderr = "";

    child.stdout.on("data", (data: Buffer) => {
      stdout += data.toString();
    });

    child.stderr.on("data", (data: Buffer) => {
      stderr += data.toString();
    });

    const timer = setTimeout(() => {
      child.kill();
      resolve({ exitCode: -1, stdout, stderr: "Command timed out" });
    }, timeout);

    child.on("close", (code) => {
      clearTimeout(timer);
      resolve({ exitCode: code ?? -1, stdout, stderr });
    });

    child.on("error", (err) => {
      clearTimeout(timer);
      resolve({ exitCode: -1, stdout, stderr: err.message });
    });
  });
}

function parseBuildNumber(output: string): number {
  const match = output.match(/Build\s+(\d+)/i);
  if (match) return parseInt(match[1], 10);

  const versionMatch = output.match(/(\d+)\.(\d+)\.(\d+)/);
  if (versionMatch) return parseInt(versionMatch[3], 10);

  return 0;
}

export async function detectWindowsVersion(): Promise<WindowsVersion> {
  const result = await runCommand("cmd /c ver");
  const build = parseBuildNumber(result.stdout);

  return {
    major: 10,
    minor: 0,
    build,
    isWindows10: build > 0 && build < 22000,
    isWindows11: build >= 22000,
    isWSL2Supported: build >= 19041,
    installMethod: build >= 22000 ? "wsl_install" : "dism",
    needsRestart: true,
    supportsWSLg: build >= 22621,
    supportsSystemd: build >= 22000,
  };
}

export async function isAdmin(): Promise<boolean> {
  const result = await runCommand("net session", 5000);
  return result.exitCode === 0;
}

export async function getShortPath(longPath: string): Promise<string> {
  const result = await runCommand(
    `cmd /c for %I in ("${longPath}") do @echo %~sI`,
    5000
  );
  if (result.exitCode === 0 && result.stdout.trim()) {
    return result.stdout.trim().split("\n").pop()!.trim();
  }
  return longPath;
}
