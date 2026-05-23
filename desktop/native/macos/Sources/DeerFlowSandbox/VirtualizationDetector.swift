import Foundation

public enum ChipArchitecture: String, Codable {
    case appleSilicon = "apple_silicon"
    case intel = "intel"
}

public enum VMFeature: String, Codable, CaseIterable {
    case basicVM
    case virtiofs
    case snapshot
    case nestedVirtualization
    case rosettaLinux
    case usbPassthrough
}

public struct VirtualizationSupport: Codable {
    public let isSupported: Bool
    public let chipArchitecture: ChipArchitecture
    public let macOSVersionMajor: Int
    public let macOSVersionMinor: Int
    public let macOSVersionPatch: Int
    public let minimumRequirement: String
    public let reason: String?
    public let supportedFeatures: Set<VMFeature>

    public var macOSVersionString: String {
        "\(macOSVersionMajor).\(macOSVersionMinor).\(macOSVersionPatch)"
    }

    private enum CodingKeys: String, CodingKey {
        case isSupported, chipArchitecture, macOSVersionMajor,
             macOSVersionMinor, macOSVersionPatch,
             minimumRequirement, reason, supportedFeatures
    }

    public init(
        isSupported: Bool,
        chipArchitecture: ChipArchitecture,
        macOSVersionMajor: Int,
        macOSVersionMinor: Int,
        macOSVersionPatch: Int,
        minimumRequirement: String = "macOS 11.0 (Big Sur)",
        reason: String? = nil,
        supportedFeatures: Set<VMFeature> = []
    ) {
        self.isSupported = isSupported
        self.chipArchitecture = chipArchitecture
        self.macOSVersionMajor = macOSVersionMajor
        self.macOSVersionMinor = macOSVersionMinor
        self.macOSVersionPatch = macOSVersionPatch
        self.minimumRequirement = minimumRequirement
        self.reason = reason
        self.supportedFeatures = supportedFeatures
    }
}

public final class VirtualizationDetector {
    public static let shared = VirtualizationDetector()

    private init() {}

    public func detectSupport() -> VirtualizationSupport {
        let osVersion = ProcessInfo.processInfo.operatingSystemVersion
        let major = osVersion.majorVersion
        let minor = osVersion.minorVersion
        let patch = osVersion.patchVersion

        let chip = detectChipArchitecture()

        if major < 11 {
            return VirtualizationSupport(
                isSupported: false,
                chipArchitecture: chip,
                macOSVersionMajor: major,
                macOSVersionMinor: minor,
                macOSVersionPatch: patch,
                reason: "DeerFlow 虚拟化沙箱需要 macOS 11 (Big Sur) 或更高版本。当前系统为 macOS \(major).\(minor).\(patch)。将降级到本地模式运行。"
            )
        }

        if chip == .intel {
            if !checkIntelVTxSupport() {
                return VirtualizationSupport(
                    isSupported: false,
                    chipArchitecture: chip,
                    macOSVersionMajor: major,
                    macOSVersionMinor: minor,
                    macOSVersionPatch: patch,
                    reason: "此 Mac 的 CPU 不支持 VT-x + EPT 虚拟化扩展，无法运行虚拟机。将降级到本地模式运行。"
                )
            }
        }

        if !checkVirtualizationFrameworkAvailable() {
            return VirtualizationSupport(
                isSupported: false,
                chipArchitecture: chip,
                macOSVersionMajor: major,
                macOSVersionMinor: minor,
                macOSVersionPatch: patch,
                reason: "Virtualization.framework 不可用。请确认系统版本为 macOS 11+ 且应用未被沙盒限制。"
            )
        }

        let features = detectSupportedFeatures(major: major, minor: minor, chip: chip)

        return VirtualizationSupport(
            isSupported: true,
            chipArchitecture: chip,
            macOSVersionMajor: major,
            macOSVersionMinor: minor,
            macOSVersionPatch: patch,
            supportedFeatures: features
        )
    }

    public func detectChipArchitecture() -> ChipArchitecture {
        var sysinfo = utsname()
        uname(&sysinfo)
        let machine = withUnsafePointer(to: &sysinfo.machine) {
            $0.withMemoryRebound(to: CChar.self, capacity: 1) {
                String(cString: $0)
            }
        }

        if machine.hasPrefix("arm64") {
            return .appleSilicon
        }

        if machine.hasPrefix("x86_64") {
            return .intel
        }

        let cpuBrand = getCpuBrandString()
        if cpuBrand.contains("Apple") {
            return .appleSilicon
        }

        return .intel
    }

    public func checkIntelVTxSupport() -> Bool {
        let features = getSysctlString("machdep.cpu.features")
        let hasVMX = features.contains("VMX")
        let hasEPT = features.contains("EPT")
        return hasVMX && hasEPT
    }

    private func detectSupportedFeatures(
        major: Int,
        minor: Int,
        chip: ChipArchitecture
    ) -> Set<VMFeature> {
        var features: Set<VMFeature> = []

        if major >= 11 {
            features.insert(.basicVM)
            features.insert(.virtiofs)
        }

        if major >= 14 {
            features.insert(.snapshot)
        }

        if major >= 14 && chip == .appleSilicon {
            features.insert(.nestedVirtualization)
        }

        if major >= 12 && chip == .appleSilicon {
            features.insert(.rosettaLinux)
        }

        if major >= 13 {
            features.insert(.usbPassthrough)
        }

        return features
    }

    private func checkVirtualizationFrameworkAvailable() -> Bool {
        #if canImport(Virtualization)
        return true
        #else
        return false
        #endif
    }

    private func getCpuBrandString() -> String {
        return getSysctlString("machdep.cpu.brand_string")
    }

    private func getSysctlString(_ name: String) -> String {
        var size = 0
        sysctlbyname(name, nil, &size, nil, 0)
        guard size > 0 else { return "" }
        var buffer = [CChar](repeating: 0, count: size)
        sysctlbyname(name, &buffer, &size, nil, 0)
        return String(cString: buffer)
    }
}
