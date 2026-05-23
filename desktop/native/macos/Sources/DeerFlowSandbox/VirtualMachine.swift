import Foundation
import Virtualization

public enum VMState: String, Codable {
    case stopped
    case starting
    case running
    case paused
    case error
}

public struct VMConfig: Codable {
    public var imagePath: String
    public var kernelPath: String?
    public var memoryMB: Int
    public var cpuCount: Int
    public var workspacePath: String
    public var sshPort: Int
    public var architecture: ChipArchitecture

    public init(
        imagePath: String = "",
        kernelPath: String? = nil,
        memoryMB: Int = 2048,
        cpuCount: Int = 2,
        workspacePath: String = "",
        sshPort: Int = 22,
        architecture: ChipArchitecture = .appleSilicon
    ) {
        self.imagePath = imagePath
        self.kernelPath = kernelPath
        self.memoryMB = memoryMB
        self.cpuCount = cpuCount
        self.workspacePath = workspacePath
        self.sshPort = sshPort
        self.architecture = architecture
    }

    public static func appleSiliconDefault() -> VMConfig {
        return VMConfig(
            imagePath: "",
            memoryMB: 2048,
            cpuCount: 2,
            workspacePath: "",
            architecture: .appleSilicon
        )
    }

    public static func intelDefault() -> VMConfig {
        return VMConfig(
            imagePath: "",
            memoryMB: 2048,
            cpuCount: 2,
            workspacePath: "",
            architecture: .intel
        )
    }
}

public struct CommandResult: Codable {
    public let exitCode: Int32
    public let stdout: String
    public let stderr: String

    public init(exitCode: Int32, stdout: String, stderr: String) {
        self.exitCode = exitCode
        self.stdout = stdout
        self.stderr = stderr
    }
}

public protocol DeerFlowVMDelegate: AnyObject {
    func vmStateChanged(to state: VMState)
    func vmDidStopUnexpectedly()
    func vmOutput(_ line: String)
}

public final class DeerFlowVirtualMachine: NSObject {
    public private(set) var state: VMState = .stopped {
        didSet {
            delegate?.vmStateChanged(to: state)
        }
    }
    public var config: VMConfig
    public let chipArchitecture: ChipArchitecture

    public weak var delegate: DeerFlowVMDelegate?

    private var vm: VZVirtualMachine?
    private var sshClient: SSHClient?
    private var snapshotManager: SnapshotManager?

    private let stateLock = NSLock()
    private var sleepObserver: Any?
    private var wakeObserver: Any?

    public init(config: VMConfig) {
        self.config = config
        self.chipArchitecture = config.architecture
        super.init()
        registerSleepWakeNotifications()
    }

    deinit {
        unregisterSleepWakeNotifications()
    }

    public func start() async throws {
        try preflightChecks()

        stateLock.lock()
        guard state == .stopped else {
            stateLock.unlock()
            throw VMError.alreadyRunning
        }
        state = .starting
        stateLock.unlock()

        do {
            let vzConfig = try buildVZConfiguration()

            try vzConfig.validate()

            let virtualMachine = VZVirtualMachine(configuration: vzConfig)
            virtualMachine.delegate = self
            self.vm = virtualMachine

            try await virtualMachine.start()

            state = .running

            try await mountVirtiofs()

            sshClient = SSHClient(host: "192.168.64.2", port: config.sshPort, username: "sandbox")
            try await waitForSSHReady()

            snapshotManager = SnapshotManager(vm: virtualMachine, config: config)
        } catch {
            state = .error
            throw mapVZError(error)
        }
    }

    public func preflightChecks() throws {
        let osVersion = ProcessInfo.processInfo.operatingSystemVersion
        if osVersion.majorVersion < 11 {
            throw VMError.osVersionTooLow(
                "DeerFlow 虚拟化沙箱需要 macOS 11 (Big Sur) 或更高版本。当前系统为 macOS \(osVersion.majorVersion).\(osVersion.minorVersion).\(osVersion.patchVersion)。将降级到本地模式运行。"
            )
        }

        let detector = VirtualizationDetector.shared
        let chip = detector.detectChipArchitecture()
        if chip == .intel && !detector.checkIntelVTxSupport() {
            throw VMError.intelVTxNotSupported(
                "此 Mac 的 CPU 不支持 VT-x + EPT 虚拟化扩展，无法运行虚拟机。将降级到本地模式运行。"
            )
        }

        if !config.imagePath.isEmpty {
            if !FileManager.default.fileExists(atPath: config.imagePath) {
                throw VMError.imageCorrupted
            }

            let expectedArch = chip == .appleSilicon ? "arm64" : "x86_64"
            let wrongArch = chip == .appleSilicon ? "x86_64" : "arm64"
            if config.imagePath.contains(wrongArch) && !config.imagePath.contains(expectedArch) {
                throw VMError.architectureMismatch
            }
        }

        let physicalMemory = ProcessInfo.processInfo.physicalMemory
        let requestedBytes = UInt64(config.memoryMB) * 1024 * 1024
        if requestedBytes > physicalMemory / 2 {
            config.memoryMB = max(512, Int(physicalMemory / (3 * 1024 * 1024)))
        }
    }

    public func execute(command: String, timeout: TimeInterval = 300) async throws -> CommandResult {
        guard state == .running else {
            throw VMError.notRunning
        }
        guard let sshClient = sshClient else {
            throw VMError.sshNotConnected
        }
        return try await sshClient.execute(command: command, timeout: timeout)
    }

    public func executeStreaming(
        command: String,
        timeout: TimeInterval = 300,
        onStdout: @escaping (String) -> Void,
        onStderr: @escaping (String) -> Void
    ) async throws -> CommandResult {
        guard state == .running else {
            throw VMError.notRunning
        }
        guard let sshClient = sshClient else {
            throw VMError.sshNotConnected
        }
        return try await sshClient.executeStreaming(
            command: command,
            timeout: timeout,
            onStdout: onStdout,
            onStderr: onStderr
        )
    }

    public func stop() async throws {
        stateLock.lock()
        guard state == .running || state == .paused else {
            stateLock.unlock()
            return
        }
        stateLock.unlock()

        guard let vm = vm else { return }

        sshClient?.disconnect()
        sshClient = nil

        do {
            try await vm.stop()
        } catch {
            try? await forceStop()
        }

        self.vm = nil
        snapshotManager = nil
        state = .stopped
    }

    public func pause() async throws {
        guard state == .running else {
            throw VMError.notRunning
        }
        guard let vm = vm else { return }

        try await vm.pause()
        state = .paused
    }

    public func resume() async throws {
        guard state == .paused else {
            throw VMError.notPaused
        }
        guard let vm = vm else { return }

        try await vm.resume()
        state = .running
    }

    public func getSnapshotManager() -> SnapshotManager? {
        return snapshotManager
    }

    private func buildVZConfiguration() throws -> VZVirtualMachineConfiguration {
        let vzConfig = VZVirtualMachineConfiguration()

        vzConfig.cpuCount = config.cpuCount
        vzConfig.memorySize = UInt64(config.memoryMB) * 1024 * 1024

        let diskAttachment = try VZDiskImageStorageDeviceAttachment(
            url: URL(fileURLWithPath: config.imagePath),
            readOnly: false
        )
        let diskDevice = VZVirtioBlockDeviceConfiguration(attachment: diskAttachment)
        vzConfig.storageDevices = [diskDevice]

        let networkDevice = VZVirtioNetworkDeviceConfiguration()
        let networkAttachment = VZNATNetworkDeviceAttachment()
        networkDevice.attachment = networkAttachment
        vzConfig.networkDevices = [networkDevice]

        let serialPort = VZVirtioConsoleDeviceSerialPortConfiguration()
        vzConfig.serialPorts = [serialPort]

        let sharedDirectory = VZSharedDirectory(
            url: URL(fileURLWithPath: resolveWorkspacePath()),
            readOnly: false
        )
        let directoryShare = VZSingleDirectoryShare(directory: sharedDirectory)
        let fileSystemDevice = VZVirtioFileSystemDeviceConfiguration(tag: "deerflow-workspace")
        fileSystemDevice.share = directoryShare
        vzConfig.directorySharingDevices = [fileSystemDevice]

        let bootLoader = try createBootLoader()
        vzConfig.bootLoader = bootLoader

        return vzConfig
    }

    private func createBootLoader() throws -> VZBootLoader {
        if let kernelPath = config.kernelPath, !kernelPath.isEmpty {
            let bootLoader = VZLinuxBootLoader(kernelURL: URL(fileURLWithPath: kernelPath))
            bootLoader.commandLine = "console=hvc0 root=/dev/vda1 rw"
            return bootLoader
        }

        let kernelPath = try extractKernelFromImage()
        let bootLoader = VZLinuxBootLoader(kernelURL: URL(fileURLWithPath: kernelPath))
        bootLoader.commandLine = "console=hvc0 root=/dev/vda1 rw"
        return bootLoader
    }

    private func extractKernelFromImage() throws -> String {
        let homeDir = FileManager.default.homeDirectoryForCurrentUser.path
        let kernelCacheDir = "\(homeDir)/DeerFlow/cache/kernels"
        let archSuffix = chipArchitecture == .appleSilicon ? "arm64" : "x86_64"
        let kernelCachePath = "\(kernelCacheDir)/vmlinuz-\(archSuffix)"

        if FileManager.default.fileExists(atPath: kernelCachePath) {
            return kernelCachePath
        }

        throw VMError.kernelNotFound(
            "Kernel not found at \(kernelCachePath). Please provide kernelPath in config or place kernel in cache directory."
        )
    }

    private func resolveWorkspacePath() -> String {
        if !config.workspacePath.isEmpty {
            return config.workspacePath
        }
        let homeDir = FileManager.default.homeDirectoryForCurrentUser.path
        let defaultPath = "\(homeDir)/DeerFlow/workspace"
        try? FileManager.default.createDirectory(
            atPath: defaultPath,
            withIntermediateDirectories: true
        )
        return defaultPath
    }

    private func mountVirtiofs() async throws {
        guard let sshClient = sshClient else { return }

        _ = try await sshClient.execute(command: "mkdir -p /mnt/workspace")
        _ = try? await sshClient.execute(command: "mount -t virtiofs deerflow-workspace /mnt/workspace 2>/dev/null || true")
        _ = try? await sshClient.execute(command: "chown sandbox:sandbox /mnt/workspace 2>/dev/null || true")
    }

    private func waitForSSHReady() async throws {
        guard let sshClient = sshClient else { return }

        let maxRetries = 30
        for attempt in 1...maxRetries {
            do {
                try await sshClient.connect()
                return
            } catch {
                if attempt == maxRetries {
                    throw VMError.sshTimeout
                }
                try await Task.sleep(nanoseconds: 1_000_000_000)
            }
        }
    }

    private func forceStop() async throws {
        guard let vm = vm else { return }
        try await vm.stop()
    }

    func handleGuestStop() {
        sshClient?.disconnect()
        sshClient = nil
        vm = nil
        snapshotManager = nil
        state = .stopped
        delegate?.vmDidStopUnexpectedly()
    }

    private func registerSleepWakeNotifications() {
        let nc = NSWorkspace.shared.notificationCenter
        sleepObserver = nc.addObserver(
            forName: NSWorkspace.willSleepNotification,
            object: nil,
            queue: .main
        ) { [weak self] _ in
            guard let self = self, self.state == .running else { return }
            Task {
                do {
                    try await self.pause()
                } catch {
                    self.state = .error
                }
            }
        }

        wakeObserver = nc.addObserver(
            forName: NSWorkspace.didWakeNotification,
            object: nil,
            queue: .main
        ) { [weak self] _ in
            guard let self = self, self.state == .paused else { return }
            Task {
                do {
                    try await self.resume()
                } catch {
                    do {
                        try await self.stop()
                        try await self.start()
                    } catch {
                        self.state = .error
                    }
                }
            }
        }
    }

    private func unregisterSleepWakeNotifications() {
        let nc = NSWorkspace.shared.notificationCenter
        if let observer = sleepObserver {
            nc.removeObserver(observer)
            sleepObserver = nil
        }
        if let observer = wakeObserver {
            nc.removeObserver(observer)
            wakeObserver = nil
        }
    }
}

extension DeerFlowVirtualMachine: VZVirtualMachineDelegate {
    public func guestDidStop(_ virtualMachine: VZVirtualMachine) {
        handleGuestStop()
    }

    public func virtualMachine(
        _ virtualMachine: VZVirtualMachine,
        didChangeStateTo newState: VZVirtualMachine.State
    ) {
        switch newState {
        case .running:
            if state == .starting {
                state = .running
            }
        case .paused:
            state = .paused
        case .stopping, .starting, .pausing, .resuming, .error:
            break
        case .stopped:
            handleGuestStop()
        @unknown default:
            break
        }
    }

    public func virtualMachine(
        _ virtualMachine: VZVirtualMachine,
        networkDevice: VZNetworkDevice,
        attachmentWasDisconnectedWithError error: Error
    ) {}
}

public enum VMError: LocalizedError {
    case alreadyRunning
    case notRunning
    case notPaused
    case sshNotConnected
    case sshTimeout
    case kernelNotFound(String)
    case vzError(String)
    case configurationError(String)
    case insufficientMemory
    case permissionDenied
    case imageCorrupted
    case architectureMismatch
    case osVersionTooLow(String)
    case intelVTxNotSupported(String)
    case vmAlreadyExists

    public var errorDescription: String? {
        switch self {
        case .alreadyRunning:
            return "VM is already running. Stop it first before starting a new instance."
        case .notRunning:
            return "VM is not running."
        case .notPaused:
            return "VM is not paused."
        case .sshNotConnected:
            return "SSH connection is not established."
        case .sshTimeout:
            return "SSH connection timed out after 30 seconds."
        case .kernelNotFound(let msg):
            return msg
        case .vzError(let msg):
            return "Virtualization error: \(msg)"
        case .configurationError(let msg):
            return "VM configuration error: \(msg)"
        case .insufficientMemory:
            return "Insufficient memory to start VM. Try reducing memoryMB or closing other applications."
        case .permissionDenied:
            return "Virtualization permission denied. Grant permission in System Preferences > Privacy & Security."
        case .imageCorrupted:
            return "Disk image is corrupted or invalid. Please re-download the VM image."
        case .architectureMismatch:
            return "Architecture mismatch: the VM image does not match the current CPU architecture."
        case .osVersionTooLow(let msg):
            return msg
        case .intelVTxNotSupported(let msg):
            return msg
        case .vmAlreadyExists:
            return "A VM is already running. Stop it first or reuse the existing instance."
        }
    }

    public var recoverySuggestion: String? {
        switch self {
        case .alreadyRunning, .vmAlreadyExists:
            return "Stop the current VM before starting a new one, or reuse the existing instance."
        case .insufficientMemory:
            return "Reduce the VM memory allocation or close other applications to free up RAM."
        case .permissionDenied:
            return "Open System Preferences > Privacy & Security and grant virtualization permission to DeerFlow."
        case .imageCorrupted:
            return "Delete the current VM image and re-download it from the DeerFlow server."
        case .architectureMismatch:
            return "Download the correct VM image for your CPU architecture (arm64 for Apple Silicon, x86_64 for Intel)."
        case .osVersionTooLow:
            return "Upgrade to macOS 11 (Big Sur) or later, or use DeerFlow in local mode."
        case .intelVTxNotSupported:
            return "This Mac does not support hardware virtualization. Use DeerFlow in local mode."
        case .sshTimeout:
            return "The VM may still be booting. Try again in a few seconds, or check the VM image."
        default:
            return nil
        }
    }
}

private func mapVZError(_ error: Error) -> VMError {
    if let vzError = error as? VZError {
        let code = vzError.errorCode
        switch code {
        case 1:
            return .permissionDenied
        case 2:
            return .imageCorrupted
        default:
            return .vzError(vzError.localizedDescription)
        }
    }

    if error.localizedDescription.contains("memory") {
        return .insufficientMemory
    }

    return .vzError(error.localizedDescription)
}
