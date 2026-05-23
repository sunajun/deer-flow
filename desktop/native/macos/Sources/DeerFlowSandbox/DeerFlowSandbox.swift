import Foundation

@objc public class DeerFlowSandboxAPI: NSObject {
    private static var sandboxes: [String: DeerFlowVirtualMachine] = [:]
    private static let lock = NSLock()

    @objc public static func detectSupport() -> [String: Any] {
        let detector = VirtualizationDetector.shared
        let support = detector.detectSupport()

        return [
            "isSupported": support.isSupported,
            "chipArchitecture": support.chipArchitecture.rawValue,
            "macOSVersion": support.macOSVersionString,
            "minimumRequirement": support.minimumRequirement,
            "reason": support.reason ?? NSNull(),
            "supportedFeatures": support.supportedFeatures.map { $0.rawValue }
        ]
    }

    @objc public static func createSandbox(config: [String: Any]) -> String {
        let vmConfig = parseVMConfig(config)
        let id = UUID().uuidString

        let vm = DeerFlowVirtualMachine(config: vmConfig)

        lock.lock()
        sandboxes[id] = vm
        lock.unlock()

        return id
    }

    @objc public static func startSandbox(id: String) -> Bool {
        guard let vm = getSandbox(id: id) else { return false }

        let semaphore = DispatchSemaphore(value: 0)
        let resultBox = LockedBool()

        Task {
            do {
                try await vm.start()
                resultBox.setValue(true)
            } catch {
                resultBox.setValue(false)
            }
            semaphore.signal()
        }

        semaphore.wait()
        return resultBox.value
    }

    @objc public static func stopSandbox(id: String) -> Bool {
        guard let vm = getSandbox(id: id) else { return false }

        let semaphore = DispatchSemaphore(value: 0)
        let resultBox = LockedBool()

        Task {
            do {
                try await vm.stop()
                resultBox.setValue(true)
            } catch {
                resultBox.setValue(false)
            }
            semaphore.signal()
        }

        semaphore.wait()

        lock.lock()
        sandboxes.removeValue(forKey: id)
        lock.unlock()

        return resultBox.value
    }

    @objc public static func executeInSandbox(
        id: String,
        command: String,
        timeout: Int
    ) -> [String: Any] {
        guard let vm = getSandbox(id: id) else {
            return ["error": "Sandbox not found", "exitCode": -1]
        }

        let semaphore = DispatchSemaphore(value: 0)
        let resultBox = LockedDict()

        Task {
            do {
                let cmdResult = try await vm.execute(
                    command: command,
                    timeout: TimeInterval(timeout)
                )
                resultBox.setValue([
                    "exitCode": cmdResult.exitCode,
                    "stdout": cmdResult.stdout,
                    "stderr": cmdResult.stderr
                ])
            } catch {
                resultBox.setValue([
                    "error": error.localizedDescription,
                    "exitCode": -1
                ])
            }
            semaphore.signal()
        }

        semaphore.wait()
        return resultBox.value
    }

    @objc public static func pauseSandbox(id: String) -> Bool {
        guard let vm = getSandbox(id: id) else { return false }

        let semaphore = DispatchSemaphore(value: 0)
        let resultBox = LockedBool()

        Task {
            do {
                try await vm.pause()
                resultBox.setValue(true)
            } catch {
                resultBox.setValue(false)
            }
            semaphore.signal()
        }

        semaphore.wait()
        return resultBox.value
    }

    @objc public static func resumeSandbox(id: String) -> Bool {
        guard let vm = getSandbox(id: id) else { return false }

        let semaphore = DispatchSemaphore(value: 0)
        let resultBox = LockedBool()

        Task {
            do {
                try await vm.resume()
                resultBox.setValue(true)
            } catch {
                resultBox.setValue(false)
            }
            semaphore.signal()
        }

        semaphore.wait()
        return resultBox.value
    }

    @objc public static func saveSnapshot(id: String, name: String) -> Bool {
        guard let vm = getSandbox(id: id),
              let snapshotMgr = vm.getSnapshotManager() else { return false }

        let semaphore = DispatchSemaphore(value: 0)
        let resultBox = LockedBool()

        Task {
            do {
                let ok = try await snapshotMgr.saveSnapshot(name: name)
                resultBox.setValue(ok)
            } catch {
                resultBox.setValue(false)
            }
            semaphore.signal()
        }

        semaphore.wait()
        return resultBox.value
    }

    @objc public static func restoreSnapshot(id: String, name: String) -> Bool {
        guard let vm = getSandbox(id: id),
              let snapshotMgr = vm.getSnapshotManager() else { return false }

        let semaphore = DispatchSemaphore(value: 0)
        let resultBox = LockedBool()

        Task {
            do {
                let ok = try await snapshotMgr.restoreSnapshot(name: name)
                resultBox.setValue(ok)
            } catch {
                resultBox.setValue(false)
            }
            semaphore.signal()
        }

        semaphore.wait()
        return resultBox.value
    }

    @objc public static func listSnapshots(id: String) -> [[String: Any]] {
        guard let vm = getSandbox(id: id),
              let snapshotMgr = vm.getSnapshotManager() else { return [] }

        return snapshotMgr.listSnapshots().map { info in
            return [
                "name": info.name,
                "createdAt": ISO8601DateFormatter().string(from: info.createdAt),
                "sizeBytes": info.sizeBytes,
                "description": info.description ?? NSNull(),
                "architecture": info.architecture,
                "isNative": info.isNative
            ]
        }
    }

    @objc public static func deleteSnapshot(id: String, name: String) -> Bool {
        guard let vm = getSandbox(id: id),
              let snapshotMgr = vm.getSnapshotManager() else { return false }

        do {
            return try snapshotMgr.deleteSnapshot(name: name)
        } catch {
            return false
        }
    }

    private static func getSandbox(id: String) -> DeerFlowVirtualMachine? {
        lock.lock()
        defer { lock.unlock() }
        return sandboxes[id]
    }

    private static func parseVMConfig(_ dict: [String: Any]) -> VMConfig {
        let archString = dict["architecture"] as? String ?? "apple_silicon"
        let arch: ChipArchitecture = archString == "intel" ? .intel : .appleSilicon

        return VMConfig(
            imagePath: dict["imagePath"] as? String ?? "",
            kernelPath: dict["kernelPath"] as? String,
            memoryMB: dict["memoryMB"] as? Int ?? 2048,
            cpuCount: dict["cpuCount"] as? Int ?? 2,
            workspacePath: dict["workspacePath"] as? String ?? "",
            sshPort: dict["sshPort"] as? Int ?? 22,
            architecture: arch
        )
    }
}

private final class LockedBool {
    private var _value = false
    private let lock = NSLock()

    var value: Bool {
        lock.lock()
        defer { lock.unlock() }
        return _value
    }

    func setValue(_ newValue: Bool) {
        lock.lock()
        _value = newValue
        lock.unlock()
    }
}

private final class LockedDict {
    private var _value: [String: Any] = [:]
    private let lock = NSLock()

    var value: [String: Any] {
        lock.lock()
        defer { lock.unlock() }
        return _value
    }

    func setValue(_ newValue: [String: Any]) {
        lock.lock()
        _value = newValue
        lock.unlock()
    }
}
