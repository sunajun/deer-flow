import XCTest
@testable import DeerFlowSandbox

final class VirtualMachineTests: XCTestCase {
    func testVMConfigAppleSiliconDefault() {
        let config = VMConfig.appleSiliconDefault()
        XCTAssertEqual(config.architecture, .appleSilicon)
        XCTAssertEqual(config.memoryMB, 2048)
        XCTAssertEqual(config.cpuCount, 2)
    }

    func testVMConfigIntelDefault() {
        let config = VMConfig.intelDefault()
        XCTAssertEqual(config.architecture, .intel)
        XCTAssertEqual(config.memoryMB, 2048)
        XCTAssertEqual(config.cpuCount, 2)
    }

    func testVMConfigCustom() {
        let config = VMConfig(
            imagePath: "/tmp/test.img",
            kernelPath: "/tmp/vmlinuz",
            memoryMB: 4096,
            cpuCount: 4,
            workspacePath: "/tmp/workspace",
            sshPort: 2222,
            architecture: .appleSilicon
        )
        XCTAssertEqual(config.imagePath, "/tmp/test.img")
        XCTAssertEqual(config.kernelPath, "/tmp/vmlinuz")
        XCTAssertEqual(config.memoryMB, 4096)
        XCTAssertEqual(config.cpuCount, 4)
        XCTAssertEqual(config.workspacePath, "/tmp/workspace")
        XCTAssertEqual(config.sshPort, 2222)
        XCTAssertEqual(config.architecture, .appleSilicon)
    }

    func testVMStateValues() {
        XCTAssertEqual(VMState.stopped.rawValue, "stopped")
        XCTAssertEqual(VMState.starting.rawValue, "starting")
        XCTAssertEqual(VMState.running.rawValue, "running")
        XCTAssertEqual(VMState.paused.rawValue, "paused")
        XCTAssertEqual(VMState.error.rawValue, "error")
    }

    func testCommandResult() {
        let result = CommandResult(exitCode: 0, stdout: "hello", stderr: "")
        XCTAssertEqual(result.exitCode, 0)
        XCTAssertEqual(result.stdout, "hello")
        XCTAssertEqual(result.stderr, "")
    }

    func testCommandResultFailure() {
        let result = CommandResult(exitCode: 1, stdout: "", stderr: "error msg")
        XCTAssertEqual(result.exitCode, 1)
        XCTAssertEqual(result.stderr, "error msg")
    }

    func testVMErrorDescriptions() {
        XCTAssertFalse(VMError.alreadyRunning.errorDescription?.isEmpty ?? true)
        XCTAssertFalse(VMError.notRunning.errorDescription?.isEmpty ?? true)
        XCTAssertFalse(VMError.notPaused.errorDescription?.isEmpty ?? true)
        XCTAssertFalse(VMError.sshNotConnected.errorDescription?.isEmpty ?? true)
        XCTAssertFalse(VMError.sshTimeout.errorDescription?.isEmpty ?? true)
        XCTAssertFalse(VMError.insufficientMemory.errorDescription?.isEmpty ?? true)
        XCTAssertFalse(VMError.permissionDenied.errorDescription?.isEmpty ?? true)
        XCTAssertFalse(VMError.imageCorrupted.errorDescription?.isEmpty ?? true)
        XCTAssertFalse(VMError.architectureMismatch.errorDescription?.isEmpty ?? true)
    }

    func testVMErrorKernelNotFound() {
        let error = VMError.kernelNotFound("test kernel")
        XCTAssertEqual(error.errorDescription, "test kernel")
    }

    func testVMErrorVZError() {
        let error = VMError.vzError("test vz error")
        XCTAssertTrue(error.errorDescription?.contains("test vz error") ?? false)
    }

    func testVMErrorConfigurationError() {
        let error = VMError.configurationError("bad config")
        XCTAssertTrue(error.errorDescription?.contains("bad config") ?? false)
    }

    func testDeerFlowVirtualMachineInit() {
        let config = VMConfig.appleSiliconDefault()
        let vm = DeerFlowVirtualMachine(config: config)
        XCTAssertEqual(vm.state, .stopped)
        XCTAssertEqual(vm.chipArchitecture, .appleSilicon)
        XCTAssertEqual(vm.config.memoryMB, 2048)
    }

    func testDeerFlowVirtualMachineIntelInit() {
        let config = VMConfig.intelDefault()
        let vm = DeerFlowVirtualMachine(config: config)
        XCTAssertEqual(vm.state, .stopped)
        XCTAssertEqual(vm.chipArchitecture, .intel)
    }
}
