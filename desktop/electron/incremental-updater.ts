import { app } from "electron";
import { Logger } from "./logger";

export interface IncrementalUpdateStats {
  timestamp: number;
  fromVersion: string;
  toVersion: string;
  incrementalSize: number;
  fullSize: number;
  usedIncremental: boolean;
}

const STATS_FILE = "update-stats.json";

export class IncrementalUpdater {
  private logger: Logger;
  private statsDir: string;

  constructor(logger: Logger) {
    this.logger = logger;
    this.statsDir = app.getPath("userData");
  }

  getPlatformConfig(): {
    supportsIncremental: boolean;
    method: string;
    fallbackToFull: boolean;
  } {
    switch (process.platform) {
      case "darwin":
        return {
          supportsIncremental: true,
          method: "blockmap",
          fallbackToFull: true,
        };
      case "win32":
        return {
          supportsIncremental: true,
          method: "nsis-differential",
          fallbackToFull: true,
        };
      case "linux":
        return {
          supportsIncremental: true,
          method: "appimage-zsync",
          fallbackToFull: false,
        };
      default:
        return {
          supportsIncremental: false,
          method: "none",
          fallbackToFull: true,
        };
    }
  }

  recordUpdateStats(stats: IncrementalUpdateStats): void {
    this.logger.info("electron", "Recording update stats", stats);

    const allStats = this.loadStats();
    allStats.push(stats);

    const recentStats = allStats.slice(-50);

    try {
      const fs = require("fs");
      const path = require("path");
      const statsPath = path.join(this.statsDir, STATS_FILE);
      fs.writeFileSync(statsPath, JSON.stringify(recentStats, null, 2), "utf-8");
    } catch (err) {
      this.logger.error("electron", "Failed to save update stats", err);
    }
  }

  loadStats(): IncrementalUpdateStats[] {
    try {
      const fs = require("fs");
      const path = require("path");
      const statsPath = path.join(this.statsDir, STATS_FILE);
      if (!fs.existsSync(statsPath)) return [];
      const content = fs.readFileSync(statsPath, "utf-8");
      return JSON.parse(content) as IncrementalUpdateStats[];
    } catch {
      return [];
    }
  }

  getIncrementalEfficiency(): { averageRatio: number; sampleCount: number } {
    const stats = this.loadStats();
    const incrementalStats = stats.filter((s) => s.usedIncremental && s.fullSize > 0);

    if (incrementalStats.length === 0) {
      return { averageRatio: 1, sampleCount: 0 };
    }

    const totalRatio = incrementalStats.reduce((sum, s) => {
      return sum + (s.incrementalSize / s.fullSize);
    }, 0);

    return {
      averageRatio: totalRatio / incrementalStats.length,
      sampleCount: incrementalStats.length,
    };
  }

  shouldUseIncremental(fromVersion: string, toVersion: string): boolean {
    const config = this.getPlatformConfig();
    if (!config.supportsIncremental) return false;

    const fromParts = fromVersion.replace(/^v/, "").split(".").map(Number);
    const toParts = toVersion.replace(/^v/, "").split(".").map(Number);

    if (fromParts[0] !== toParts[0]) {
      this.logger.info("electron", "Major version change, using full update");
      return false;
    }

    return true;
  }

  getLinuxUpdateInstructions(): string {
    return [
      "Linux (AppImage) auto-update is not supported directly.",
      "To update, you can:",
      "1. Download the latest AppImage from GitHub Releases",
      "2. Use AppImageUpdate tool for incremental updates:",
      "   AppImageUpdate DeerFlow-x.x.x.AppImage",
      "3. Or use the built-in update check to get notified of new versions",
    ].join("\n");
  }
}
