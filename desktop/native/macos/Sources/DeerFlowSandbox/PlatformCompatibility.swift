import Foundation

public final class PlatformCompatibility {
    public static let shared = PlatformCompatibility()

    private init() {}

    public var currentArchitecture: ChipArchitecture {
        return VirtualizationDetector.shared.detectChipArchitecture()
    }

    public var isAppleSilicon: Bool {
        return currentArchitecture == .appleSilicon
    }

    public var isIntel: Bool {
        return currentArchitecture == .intel
    }

    public var macOSVersion: (major: Int, minor: Int, patch: Int) {
        let v = ProcessInfo.processInfo.operatingSystemVersion
        return (v.majorVersion, v.minorVersion, v.patchVersion)
    }

    public var isBigSurOrLater: Bool { macOSVersion.major >= 11 }
    public var isMontereyOrLater: Bool { macOSVersion.major >= 12 || (macOSVersion.major == 11) }
    public var isVenturaOrLater: Bool { macOSVersion.major >= 13 }
    public var isSonomaOrLater: Bool { macOSVersion.major >= 14 }

    public func recommendedImageSuffix() -> String {
        return isAppleSilicon ? "arm64" : "x86_64"
    }

    public func recommendedMemoryMB() -> Int {
        let totalMemory = ProcessInfo.processInfo.physicalMemory
        let totalGB = Int(totalMemory / (1024 * 1024 * 1024))

        if totalGB >= 32 {
            return 4096
        } else if totalGB >= 16 {
            return 2048
        } else if totalGB >= 8 {
            return 1024
        } else {
            return 512
        }
    }

    public func recommendedCPUCount() -> Int {
        let cpuCount = ProcessInfo.processInfo.processorCount
        return max(1, min(cpuCount - 1, 4))
    }

    public func supportsNativeSnapshots() -> Bool {
        return macOSVersion.major >= 14
    }

    public func snapshotRestoreEstimate() -> String {
        if macOSVersion.major >= 14 {
            return "< 1s (native API)"
        } else if macOSVersion.major >= 12 {
            return "5-10s (file copy)"
        } else {
            return "10-15s (file copy)"
        }
    }

    public func validateImageArchitecture(imagePath: String) -> Bool {
        let expectedSuffix = recommendedImageSuffix()
        return imagePath.contains(expectedSuffix)
    }

    public func defaultVMConfig() -> VMConfig {
        let arch = currentArchitecture
        let homeDir = FileManager.default.homeDirectoryForCurrentUser.path
        let imageSuffix = recommendedImageSuffix()

        return VMConfig(
            imagePath: "\(homeDir)/DeerFlow/images/deerflow-\(imageSuffix).img",
            memoryMB: recommendedMemoryMB(),
            cpuCount: recommendedCPUCount(),
            workspacePath: "\(homeDir)/DeerFlow/workspace",
            architecture: arch
        )
    }
}
