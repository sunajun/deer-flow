import XCTest
@testable import DeerFlowSandbox

final class DetectionTests: XCTestCase {
    func testDetectSupportReturnsResult() {
        let detector = VirtualizationDetector.shared
        let support = detector.detectSupport()
        XCTAssertNotNil(support)
    }

    func testDetectSupportHasRequiredFields() {
        let support = VirtualizationDetector.shared.detectSupport()
        XCTAssertFalse(support.macOSVersionString.isEmpty)
        XCTAssertEqual(support.minimumRequirement, "macOS 11.0 (Big Sur)")
    }

    func testChipArchitectureDetection() {
        let detector = VirtualizationDetector.shared
        let chip = detector.detectChipArchitecture()
        XCTAssertTrue(chip == .appleSilicon || chip == .intel)
    }

    func testDetectSupportOnCurrentMac() {
        let support = VirtualizationDetector.shared.detectSupport()
        let osVersion = ProcessInfo.processInfo.operatingSystemVersion

        if osVersion.majorVersion >= 11 {
            XCTAssertTrue(support.isSupported, "macOS 11+ should be supported")
            XCTAssertNil(support.reason, "Supported systems should not have a reason")
        } else {
            XCTAssertFalse(support.isSupported, "macOS < 11 should not be supported")
            XCTAssertNotNil(support.reason, "Unsupported systems should have a reason")
        }
    }

    func testSupportedFeaturesOnCurrentMac() {
        let support = VirtualizationDetector.shared.detectSupport()
        let osVersion = ProcessInfo.processInfo.operatingSystemVersion

        if osVersion.majorVersion >= 11 {
            XCTAssertTrue(support.supportedFeatures.contains(.basicVM))
            XCTAssertTrue(support.supportedFeatures.contains(.virtiofs))
        }

        if osVersion.majorVersion >= 14 {
            XCTAssertTrue(support.supportedFeatures.contains(.snapshot))
        }
    }

    func testVirtualizationSupportMacOSVersion() {
        let support = VirtualizationDetector.shared.detectSupport()
        let osVersion = ProcessInfo.processInfo.operatingSystemVersion
        XCTAssertEqual(support.macOSVersionMajor, osVersion.majorVersion)
        XCTAssertEqual(support.macOSVersionMinor, osVersion.minorVersion)
        XCTAssertEqual(support.macOSVersionPatch, osVersion.patchVersion)
    }

    func testVirtualizationSupportCodable() {
        let support = VirtualizationDetector.shared.detectSupport()
        do {
            let data = try JSONEncoder().encode(support)
            let decoded = try JSONDecoder().decode(VirtualizationSupport.self, from: data)
            XCTAssertEqual(decoded.isSupported, support.isSupported)
            XCTAssertEqual(decoded.chipArchitecture, support.chipArchitecture)
            XCTAssertEqual(decoded.macOSVersionString, support.macOSVersionString)
        } catch {
            XCTFail("VirtualizationSupport should be codable: \(error)")
        }
    }

    func testChipArchitectureRawValues() {
        XCTAssertEqual(ChipArchitecture.appleSilicon.rawValue, "apple_silicon")
        XCTAssertEqual(ChipArchitecture.intel.rawValue, "intel")
    }

    func testVMFeatureRawValues() {
        XCTAssertEqual(VMFeature.basicVM.rawValue, "basicVM")
        XCTAssertEqual(VMFeature.virtiofs.rawValue, "virtiofs")
        XCTAssertEqual(VMFeature.snapshot.rawValue, "snapshot")
        XCTAssertEqual(VMFeature.nestedVirtualization.rawValue, "nestedVirtualization")
        XCTAssertEqual(VMFeature.rosettaLinux.rawValue, "rosettaLinux")
        XCTAssertEqual(VMFeature.usbPassthrough.rawValue, "usbPassthrough")
    }

    func testIntelVTxDetection() {
        let detector = VirtualizationDetector.shared
        let chip = detector.detectChipArchitecture()

        if chip == .intel {
            let hasVTx = detector.checkIntelVTxSupport()
            XCTAssertTrue(hasVTx, "Running on Intel Mac, VT-x should be supported")
        }
    }
}
