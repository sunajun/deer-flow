import XCTest
@testable import DeerFlowSandbox

final class IntegrationTests: XCTestCase {

    private static var vmImageAvailable: Bool = {
        let compat = PlatformCompatibility.shared
        let config = compat.defaultVMConfig()
        return !config.imagePath.isEmpty
            && FileManager.default.fileExists(atPath: config.imagePath)
    }()

    private func skipIfNoVMImage() throws {
        try XCTSkipUnless(
            Self.vmImageAvailable,
            "VM image not available — skipping integration test. "
                + "Place a VM image at ~/DeerFlow/images/ to enable these tests."
        )
    }

    private func makeConfig() -> VMConfig {
        let compat = PlatformCompatibility.shared
        return compat.defaultVMConfig()
    }

    private func createAndStartVM() async throws -> DeerFlowVirtualMachine {
        let config = makeConfig()
        let vm = DeerFlowVirtualMachine(config: config)
        XCTAssertEqual(vm.state, .stopped)
        try await vm.start()
        XCTAssertEqual(vm.state, .running)
        return vm
    }

    // MARK: - VM Lifecycle

    func testVMLifecycle() async throws {
        try skipIfNoVMImage()

        let vm = DeerFlowVirtualMachine(config: makeConfig())
        XCTAssertEqual(vm.state, .stopped)

        try await vm.start()
        XCTAssertEqual(vm.state, .running)

        let result = try await vm.execute(command: "echo hello", timeout: 30)
        XCTAssertEqual(result.exitCode, 0)
        XCTAssertTrue(result.stdout.trimmingCharacters(in: .whitespacesAndNewlines).contains("hello"))

        try await vm.stop()
        XCTAssertEqual(vm.state, .stopped)
    }

    func testCreateAndStopViaAPI() async throws {
        try skipIfNoVMImage()

        let config = makeConfig()
        let configDict: [String: Any] = [
            "imagePath": config.imagePath,
            "memoryMB": config.memoryMB,
            "cpuCount": config.cpuCount,
            "workspacePath": config.workspacePath,
            "sshPort": config.sshPort,
            "architecture": config.architecture.rawValue
        ]

        let id = DeerFlowSandboxAPI.createSandbox(config: configDict)
        XCTAssertFalse(id.isEmpty)

        let started = DeerFlowSandboxAPI.startSandbox(id: id)
        XCTAssertTrue(started)

        let executeResult = DeerFlowSandboxAPI.executeInSandbox(
            id: id,
            command: "echo api-test",
            timeout: 30
        )
        XCTAssertEqual(executeResult["exitCode"] as? Int, 0)

        let stopped = DeerFlowSandboxAPI.stopSandbox(id: id)
        XCTAssertTrue(stopped)
    }

    // MARK: - Command Execution

    func testExecuteWhoami() async throws {
        try skipIfNoVMImage()

        let vm = try await createAndStartVM()
        defer { try? await vm.stop() }

        let result = try await vm.execute(command: "whoami", timeout: 30)
        XCTAssertEqual(result.exitCode, 0)
        XCTAssertTrue(result.stdout.trimmingCharacters(in: .whitespacesAndNewlines).contains("sandbox"))
    }

    func testExecutePython3Version() async throws {
        try skipIfNoVMImage()

        let vm = try await createAndStartVM()
        defer { try? await vm.stop() }

        let result = try await vm.execute(command: "python3 --version", timeout: 30)
        XCTAssertEqual(result.exitCode, 0)
        XCTAssertTrue(
            result.stdout.trimmingCharacters(in: .whitespacesAndNewlines).contains("Python"),
            "Expected Python version string, got: \(result.stdout)"
        )
    }

    func testExecuteNodeVersion() async throws {
        try skipIfNoVMImage()

        let vm = try await createAndStartVM()
        defer { try? await vm.stop() }

        let result = try await vm.execute(command: "node --version", timeout: 30)
        XCTAssertEqual(result.exitCode, 0)
        let version = result.stdout.trimmingCharacters(in: .whitespacesAndNewlines)
        XCTAssertTrue(
            version.hasPrefix("v"),
            "Expected Node version starting with 'v', got: \(version)"
        )
    }

    func testExecuteGitVersion() async throws {
        try skipIfNoVMImage()

        let vm = try await createAndStartVM()
        defer { try? await vm.stop() }

        let result = try await vm.execute(command: "git --version", timeout: 30)
        XCTAssertEqual(result.exitCode, 0)
        XCTAssertTrue(
            result.stdout.trimmingCharacters(in: .whitespacesAndNewlines).contains("git version"),
            "Expected git version string, got: \(result.stdout)"
        )
    }

    func testExecuteFailingCommand() async throws {
        try skipIfNoVMImage()

        let vm = try await createAndStartVM()
        defer { try? await vm.stop() }

        let result = try await vm.execute(command: "ls /nonexistent_dir_xyz", timeout: 30)
        XCTAssertNotEqual(result.exitCode, 0)
        XCTAssertFalse(result.stderr.isEmpty)
    }

    // MARK: - Pause / Resume

    func testPauseAndResume() async throws {
        try skipIfNoVMImage()

        let vm = try await createAndStartVM()
        defer { try? await vm.stop() }

        try await vm.pause()
        XCTAssertEqual(vm.state, .paused)

        try await vm.resume()
        XCTAssertEqual(vm.state, .running)

        let result = try await vm.execute(command: "echo after-resume", timeout: 30)
        XCTAssertEqual(result.exitCode, 0)
        XCTAssertTrue(
            result.stdout.trimmingCharacters(in: .whitespacesAndNewlines).contains("after-resume")
        )
    }

    func testPauseViaAPI() async throws {
        try skipIfNoVMImage()

        let config = makeConfig()
        let configDict: [String: Any] = [
            "imagePath": config.imagePath,
            "memoryMB": config.memoryMB,
            "cpuCount": config.cpuCount,
            "workspacePath": config.workspacePath,
            "sshPort": config.sshPort,
            "architecture": config.architecture.rawValue
        ]

        let id = DeerFlowSandboxAPI.createSandbox(config: configDict)
        _ = DeerFlowSandboxAPI.startSandbox(id: id)

        let paused = DeerFlowSandboxAPI.pauseSandbox(id: id)
        XCTAssertTrue(paused)

        let resumed = DeerFlowSandboxAPI.resumeSandbox(id: id)
        XCTAssertTrue(resumed)

        _ = DeerFlowSandboxAPI.stopSandbox(id: id)
    }

    func testExecuteOnPausedVMThrows() async throws {
        try skipIfNoVMImage()

        let vm = try await createAndStartVM()
        defer { try? await vm.stop() }

        try await vm.pause()
        XCTAssertEqual(vm.state, .paused)

        do {
            _ = try await vm.execute(command: "echo should-fail", timeout: 30)
            XCTFail("Executing on a paused VM should throw")
        } catch {
            XCTAssertTrue(error is VMError, "Expected VMError, got \(type(of: error))")
        }

        try await vm.resume()
    }

    // MARK: - Snapshots

    func testSaveAndRestoreSnapshot() async throws {
        try skipIfNoVMImage()

        let vm = try await createAndStartVM()
        defer { try? await vm.stop() }

        guard let snapshotMgr = vm.getSnapshotManager() else {
            XCTFail("SnapshotManager should be available when VM is running")
            return
        }

        let snapshotName = "integration-test-\(Int(Date().timeIntervalSince1970))"
        let saved = try await snapshotMgr.saveSnapshot(name: snapshotName)
        XCTAssertTrue(saved, "Snapshot save should succeed")

        let snapshots = snapshotMgr.listSnapshots()
        XCTAssertTrue(
            snapshots.contains { $0.name == snapshotName },
            "Snapshot list should contain the saved snapshot"
        )

        let restored = try await snapshotMgr.restoreSnapshot(name: snapshotName)
        XCTAssertTrue(restored, "Snapshot restore should succeed")

        let deleted = try snapshotMgr.deleteSnapshot(name: snapshotName)
        XCTAssertTrue(deleted, "Snapshot delete should succeed")

        let snapshotsAfterDelete = snapshotMgr.listSnapshots()
        XCTAssertFalse(
            snapshotsAfterDelete.contains { $0.name == snapshotName },
            "Snapshot list should not contain the deleted snapshot"
        )
    }

    func testSnapshotViaAPI() async throws {
        try skipIfNoVMImage()

        let config = makeConfig()
        let configDict: [String: Any] = [
            "imagePath": config.imagePath,
            "memoryMB": config.memoryMB,
            "cpuCount": config.cpuCount,
            "workspacePath": config.workspacePath,
            "sshPort": config.sshPort,
            "architecture": config.architecture.rawValue
        ]

        let id = DeerFlowSandboxAPI.createSandbox(config: configDict)
        _ = DeerFlowSandboxAPI.startSandbox(id: id)

        let snapshotName = "api-snapshot-\(Int(Date().timeIntervalSince1970))"

        let saved = DeerFlowSandboxAPI.saveSnapshot(id: id, name: snapshotName)
        XCTAssertTrue(saved)

        let snapshots = DeerFlowSandboxAPI.listSnapshots(id: id)
        XCTAssertTrue(snapshots.contains { $0["name"] as? String == snapshotName })

        let restored = DeerFlowSandboxAPI.restoreSnapshot(id: id, name: snapshotName)
        XCTAssertTrue(restored)

        let deleted = DeerFlowSandboxAPI.deleteSnapshot(id: id, name: snapshotName)
        XCTAssertTrue(deleted)

        _ = DeerFlowSandboxAPI.stopSandbox(id: id)
    }

    func testDeleteNonexistentSnapshot() async throws {
        try skipIfNoVMImage()

        let vm = try await createAndStartVM()
        defer { try? await vm.stop() }

        guard let snapshotMgr = vm.getSnapshotManager() else {
            XCTFail("SnapshotManager should be available")
            return
        }

        let deleted = try snapshotMgr.deleteSnapshot(name: "nonexistent-snapshot-xyz")
        XCTAssertFalse(deleted, "Deleting a nonexistent snapshot should return false")
    }

    // MARK: - Version Info

    func testReadDeerFlowVersion() async throws {
        try skipIfNoVMImage()

        let vm = try await createAndStartVM()
        defer { try? await vm.stop() }

        let result = try await vm.execute(command: "cat /etc/deerflow-version", timeout: 30)
        XCTAssertEqual(result.exitCode, 0, "Reading /etc/deerflow-version should succeed")
        let version = result.stdout.trimmingCharacters(in: .whitespacesAndNewlines)
        XCTAssertFalse(version.isEmpty, "DeerFlow version should not be empty")
    }

    // MARK: - Compatibility Check

    func testReadCompatVersion() async throws {
        try skipIfNoVMImage()

        let vm = try await createAndStartVM()
        defer { try? await vm.stop() }

        let result = try await vm.execute(
            command: "cat /etc/deerflow-compat 2>/dev/null || echo NOT_FOUND",
            timeout: 30
        )
        XCTAssertEqual(result.exitCode, 0)

        let output = result.stdout.trimmingCharacters(in: .whitespacesAndNewlines)
        if output != "NOT_FOUND" {
            let lines = output.components(separatedBy: .newlines)
            var compatVersion: String?
            var minAppVersion: String?

            for line in lines {
                let parts = line.components(separatedBy: "=")
                guard parts.count == 2 else { continue }
                let key = parts[0].trimmingCharacters(in: .whitespaces)
                let value = parts[1].trimmingCharacters(in: .whitespaces)
                if key == "COMPAT_VERSION" { compatVersion = value }
                if key == "MIN_APP_VERSION" { minAppVersion = value }
            }

            if let compatVersion = compatVersion {
                XCTAssertFalse(compatVersion.isEmpty, "COMPAT_VERSION should not be empty")
            }
            if let minAppVersion = minAppVersion {
                XCTAssertFalse(minAppVersion.isEmpty, "MIN_APP_VERSION should not be empty")
            }
        }
    }

    func testImageArchitectureMatchesHost() async throws {
        try skipIfNoVMImage()

        let config = makeConfig()
        let detector = VirtualizationDetector.shared
        let hostArch = detector.detectChipArchitecture()

        if hostArch == .appleSilicon {
            XCTAssertTrue(
                config.imagePath.contains("arm64"),
                "Apple Silicon host should use arm64 image, got: \(config.imagePath)"
            )
        } else {
            XCTAssertTrue(
                config.imagePath.contains("x86_64"),
                "Intel host should use x86_64 image, got: \(config.imagePath)"
            )
        }
    }

    // MARK: - Error Handling

    func testStartWhenAlreadyRunningThrows() async throws {
        try skipIfNoVMImage()

        let vm = try await createAndStartVM()
        defer { try? await vm.stop() }

        do {
            try await vm.start()
            XCTFail("Starting an already running VM should throw")
        } catch {
            XCTAssertTrue(error is VMError, "Expected VMError, got \(type(of: error))")
        }
    }

    func testStopWhenNotRunningIsNoop() async throws {
        try skipIfNoVMImage()

        let vm = DeerFlowVirtualMachine(config: makeConfig())
        XCTAssertEqual(vm.state, .stopped)

        try await vm.stop()
        XCTAssertEqual(vm.state, .stopped)
    }

    func testResumeWhenNotPausedThrows() async throws {
        try skipIfNoVMImage()

        let vm = try await createAndStartVM()
        defer { try? await vm.stop() }

        do {
            try await vm.resume()
            XCTFail("Resuming a running (non-paused) VM should throw")
        } catch {
            XCTAssertTrue(error is VMError, "Expected VMError, got \(type(of: error))")
        }
    }
}
