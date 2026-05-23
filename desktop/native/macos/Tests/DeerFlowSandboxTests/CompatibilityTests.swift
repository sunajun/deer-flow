import XCTest
@testable import DeerFlowSandbox

final class CompatibilityTests: XCTestCase {
    func testPlatformCompatibilityShared() {
        let compat = PlatformCompatibility.shared
        XCTAssertTrue(compat.isAppleSilicon || compat.isIntel)
        XCTAssertFalse(compat.isAppleSilicon && compat.isIntel)
    }

    func testCurrentArchitecture() {
        let compat = PlatformCompatibility.shared
        let detector = VirtualizationDetector.shared
        XCTAssertEqual(compat.currentArchitecture, detector.detectChipArchitecture())
    }

    func testMacOSVersion() {
        let compat = PlatformCompatibility.shared
        let version = compat.macOSVersion
        XCTAssertGreaterThanOrEqual(version.major, 10)
    }

    func testBigSurOrLater() {
        let compat = PlatformCompatibility.shared
        let version = compat.macOSVersion
        XCTAssertEqual(compat.isBigSurOrLater, version.major >= 11)
    }

    func testSonomaOrLater() {
        let compat = PlatformCompatibility.shared
        let version = compat.macOSVersion
        XCTAssertEqual(compat.isSonomaOrLater, version.major >= 14)
    }

    func testRecommendedImageSuffix() {
        let compat = PlatformCompatibility.shared
        if compat.isAppleSilicon {
            XCTAssertEqual(compat.recommendedImageSuffix(), "arm64")
        } else {
            XCTAssertEqual(compat.recommendedImageSuffix(), "x86_64")
        }
    }

    func testRecommendedMemoryMB() {
        let compat = PlatformCompatibility.shared
        let mem = compat.recommendedMemoryMB()
        XCTAssertGreaterThanOrEqual(mem, 512)
        XCTAssertLessThanOrEqual(mem, 8192)
    }

    func testRecommendedCPUCount() {
        let compat = PlatformCompatibility.shared
        let cpus = compat.recommendedCPUCount()
        XCTAssertGreaterThanOrEqual(cpus, 1)
        XCTAssertLessThanOrEqual(cpus, ProcessInfo.processInfo.processorCount)
    }

    func testSupportsNativeSnapshots() {
        let compat = PlatformCompatibility.shared
        let version = compat.macOSVersion
        XCTAssertEqual(compat.supportsNativeSnapshots(), version.major >= 14)
    }

    func testSnapshotRestoreEstimate() {
        let compat = PlatformCompatibility.shared
        let estimate = compat.snapshotRestoreEstimate()
        XCTAssertFalse(estimate.isEmpty)

        if compat.macOSVersion.major >= 14 {
            XCTAssertTrue(estimate.contains("native"))
        } else {
            XCTAssertTrue(estimate.contains("file copy"))
        }
    }

    func testDefaultVMConfig() {
        let compat = PlatformCompatibility.shared
        let config = compat.defaultVMConfig()
        XCTAssertFalse(config.imagePath.isEmpty)
        XCTAssertGreaterThanOrEqual(config.memoryMB, 512)
        XCTAssertGreaterThanOrEqual(config.cpuCount, 1)
        XCTAssertEqual(config.architecture, compat.currentArchitecture)
    }

    func testValidateImageArchitecture() {
        let compat = PlatformCompatibility.shared
        if compat.isAppleSilicon {
            XCTAssertTrue(compat.validateImageArchitecture(imagePath: "/path/to/arm64-image.img"))
            XCTAssertFalse(compat.validateImageArchitecture(imagePath: "/path/to/x86_64-image.img"))
        } else {
            XCTAssertTrue(compat.validateImageArchitecture(imagePath: "/path/to/x86_64-image.img"))
            XCTAssertFalse(compat.validateImageArchitecture(imagePath: "/path/to/arm64-image.img"))
        }
    }

    func testSnapshotInfoCodable() {
        let info = SnapshotInfo(
            name: "test-snapshot",
            sizeBytes: 1024,
            description: "Test",
            architecture: "apple_silicon",
            isNative: true
        )
        do {
            let data = try JSONEncoder().encode(info)
            let decoded = try JSONDecoder().decode(SnapshotInfo.self, from: data)
            XCTAssertEqual(decoded.name, info.name)
            XCTAssertEqual(decoded.sizeBytes, info.sizeBytes)
            XCTAssertEqual(decoded.architecture, info.architecture)
            XCTAssertEqual(decoded.isNative, info.isNative)
        } catch {
            XCTFail("SnapshotInfo should be codable: \(error)")
        }
    }

    func testMemoryConfigurations() {
        let configs = [512, 1024, 2048, 4096]
        for memMB in configs {
            let config = VMConfig(memoryMB: memMB, architecture: .appleSilicon)
            XCTAssertEqual(config.memoryMB, memMB)
        }
    }

    func testCPUConfigurations() {
        let cpuCounts = [1, 2, 4]
        for cpuCount in cpuCounts {
            let config = VMConfig(cpuCount: cpuCount, architecture: .appleSilicon)
            XCTAssertEqual(config.cpuCount, cpuCount)
        }
    }

    func testSSHErrorDescriptions() {
        XCTAssertFalse(SSHError.connectionFailed("test").errorDescription?.isEmpty ?? true)
        XCTAssertFalse(SSHError.authenticationFailed("test").errorDescription?.isEmpty ?? true)
        XCTAssertFalse(SSHError.timeout.errorDescription?.isEmpty ?? true)
        XCTAssertFalse(SSHError.disconnected.errorDescription?.isEmpty ?? true)
    }
}
