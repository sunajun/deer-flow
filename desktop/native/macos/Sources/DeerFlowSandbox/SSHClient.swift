import Foundation

private final class LockedBuffer {
    private var buffer = ""
    private let lock = NSLock()

    func append(_ text: String) {
        lock.lock()
        buffer += text
        lock.unlock()
    }

    func getAndReset() -> String {
        lock.lock()
        let result = buffer
        buffer = ""
        lock.unlock()
        return result
    }
}

public protocol SSHClientDelegate: AnyObject {
    func onStdout(line: String)
    func onStderr(line: String)
}

public final class SSHClient {
    private let host: String
    private let port: Int
    private let username: String
    private let privateKeyPath: String?

    public weak var delegate: SSHClientDelegate?

    private var isConnected = false
    private var keepaliveTimer: Timer?

    private let homeDir: String

    public init(
        host: String,
        port: Int = 22,
        username: String = "sandbox",
        privateKeyPath: String? = nil
    ) {
        self.host = host
        self.port = port
        self.username = username
        self.privateKeyPath = privateKeyPath
        self.homeDir = FileManager.default.homeDirectoryForCurrentUser.path
    }

    public func connect() async throws {
        let result = try await execute(command: "echo connected", timeout: 5)
        if result.exitCode == 0 {
            isConnected = true
            startKeepalive()
        } else {
            isConnected = false
            throw SSHError.connectionFailed("SSH connection failed: \(result.stderr)")
        }
    }

    public func disconnect() {
        isConnected = false
        stopKeepalive()
    }

    public func execute(
        command: String,
        timeout: TimeInterval = 300
    ) async throws -> CommandResult {
        let process = Process()
        let stdoutPipe = Pipe()
        let stderrPipe = Pipe()

        process.executableURL = URL(fileURLWithPath: "/usr/bin/ssh")

        var args: [String] = [
            "-o", "StrictHostKeyChecking=no",
            "-o", "UserKnownHostsFile=/dev/null",
            "-o", "ConnectTimeout=10",
            "-o", "ServerAliveInterval=60",
            "-o", "ServerAliveCountMax=3",
            "-p", String(port)
        ]

        if let keyPath = resolvePrivateKeyPath() {
            args += ["-i", keyPath]
        }

        args += ["\(username)@\(host)", command]

        process.arguments = args
        process.standardOutput = stdoutPipe
        process.standardError = stderrPipe

        return try await withCheckedThrowingContinuation { continuation in
            do {
                try process.run()
            } catch {
                continuation.resume(
                    returning: CommandResult(
                        exitCode: -1,
                        stdout: "",
                        stderr: "Failed to launch ssh: \(error.localizedDescription)"
                    )
                )
                return
            }

            let timeoutTimer = DispatchSource.makeTimerSource()
            timeoutTimer.schedule(
                deadline: .now() + timeout,
                repeating: .never
            )
            timeoutTimer.setEventHandler {
                if process.isRunning {
                    process.terminate()
                }
            }
            timeoutTimer.resume()

            process.waitUntilExit()

            timeoutTimer.cancel()

            let stdoutData = stdoutPipe.fileHandleForReading.readDataToEndOfFile()
            let stderrData = stderrPipe.fileHandleForReading.readDataToEndOfFile()

            let stdout = String(data: stdoutData, encoding: .utf8) ?? ""
            let stderr = String(data: stderrData, encoding: .utf8) ?? ""

            continuation.resume(
                returning: CommandResult(
                    exitCode: process.terminationStatus,
                    stdout: stdout,
                    stderr: stderr
                )
            )
        }
    }

    public func executeStreaming(
        command: String,
        timeout: TimeInterval = 300,
        onStdout: @escaping (String) -> Void,
        onStderr: @escaping (String) -> Void
    ) async throws -> CommandResult {
        let process = Process()
        let stdoutPipe = Pipe()
        let stderrPipe = Pipe()

        process.executableURL = URL(fileURLWithPath: "/usr/bin/ssh")

        var args: [String] = [
            "-o", "StrictHostKeyChecking=no",
            "-o", "UserKnownHostsFile=/dev/null",
            "-o", "ConnectTimeout=10",
            "-p", String(port)
        ]

        if let keyPath = resolvePrivateKeyPath() {
            args += ["-i", keyPath]
        }

        args += ["\(username)@\(host)", command]

        process.arguments = args
        process.standardOutput = stdoutPipe
        process.standardError = stderrPipe

        try process.run()

        let stdoutBuffer = LockedBuffer()
        let stderrBuffer = LockedBuffer()

        let stdoutFD = stdoutPipe.fileHandleForReading.fileDescriptor
        let stderrFD = stderrPipe.fileHandleForReading.fileDescriptor

        let stdoutSource = DispatchSource.makeReadSource(
            fileDescriptor: stdoutFD,
            queue: DispatchQueue.global(qos: .userInitiated)
        )
        let stderrSource = DispatchSource.makeReadSource(
            fileDescriptor: stderrFD,
            queue: DispatchQueue.global(qos: .userInitiated)
        )

        stdoutSource.setEventHandler {
            let data = stdoutPipe.fileHandleForReading.availableData
            if let text = String(data: data, encoding: .utf8), !text.isEmpty {
                stdoutBuffer.append(text)
                text.split(separator: "\n", omittingEmptySubsequences: false).forEach { line in
                    onStdout(String(line))
                }
            }
        }

        stderrSource.setEventHandler {
            let data = stderrPipe.fileHandleForReading.availableData
            if let text = String(data: data, encoding: .utf8), !text.isEmpty {
                stderrBuffer.append(text)
                text.split(separator: "\n", omittingEmptySubsequences: false).forEach { line in
                    onStderr(String(line))
                }
            }
        }

        stdoutSource.resume()
        stderrSource.resume()

        return try await withCheckedThrowingContinuation { continuation in
            let timeoutTimer = DispatchSource.makeTimerSource()
            timeoutTimer.schedule(deadline: .now() + timeout, repeating: .never)
            timeoutTimer.setEventHandler {
                if process.isRunning {
                    process.terminate()
                }
            }
            timeoutTimer.resume()

            DispatchQueue.global(qos: .utility).async {
                process.waitUntilExit()
                timeoutTimer.cancel()
                stdoutSource.cancel()
                stderrSource.cancel()

                let remainingStdout = stdoutPipe.fileHandleForReading.readDataToEndOfFile()
                let remainingStderr = stderrPipe.fileHandleForReading.readDataToEndOfFile()

                if let text = String(data: remainingStdout, encoding: .utf8), !text.isEmpty {
                    stdoutBuffer.append(text)
                }
                if let text = String(data: remainingStderr, encoding: .utf8), !text.isEmpty {
                    stderrBuffer.append(text)
                }

                let finalStdout = stdoutBuffer.getAndReset()
                let finalStderr = stderrBuffer.getAndReset()

                continuation.resume(
                    returning: CommandResult(
                        exitCode: process.terminationStatus,
                        stdout: finalStdout,
                        stderr: finalStderr
                    )
                )
            }
        }
    }

    public func upload(localPath: String, remotePath: String) async throws -> CommandResult {
        let process = Process()
        let stderrPipe = Pipe()

        process.executableURL = URL(fileURLWithPath: "/usr/bin/scp")

        var args: [String] = [
            "-o", "StrictHostKeyChecking=no",
            "-o", "UserKnownHostsFile=/dev/null",
            "-P", String(port)
        ]

        if let keyPath = resolvePrivateKeyPath() {
            args += ["-i", keyPath]
        }

        args += [localPath, "\(username)@\(host):\(remotePath)"]

        process.arguments = args
        process.standardError = stderrPipe

        try process.run()
        process.waitUntilExit()

        let stderrData = stderrPipe.fileHandleForReading.readDataToEndOfFile()
        let stderr = String(data: stderrData, encoding: .utf8) ?? ""

        return CommandResult(exitCode: process.terminationStatus, stdout: "", stderr: stderr)
    }

    public func download(remotePath: String, localPath: String) async throws -> CommandResult {
        let process = Process()
        let stderrPipe = Pipe()

        process.executableURL = URL(fileURLWithPath: "/usr/bin/scp")

        var args: [String] = [
            "-o", "StrictHostKeyChecking=no",
            "-o", "UserKnownHostsFile=/dev/null",
            "-P", String(port)
        ]

        if let keyPath = resolvePrivateKeyPath() {
            args += ["-i", keyPath]
        }

        args += ["\(username)@\(host):\(remotePath)", localPath]

        process.arguments = args
        process.standardError = stderrPipe

        try process.run()
        process.waitUntilExit()

        let stderrData = stderrPipe.fileHandleForReading.readDataToEndOfFile()
        let stderr = String(data: stderrData, encoding: .utf8) ?? ""

        return CommandResult(exitCode: process.terminationStatus, stdout: "", stderr: stderr)
    }

    private func resolvePrivateKeyPath() -> String? {
        if let keyPath = privateKeyPath {
            return keyPath
        }

        let defaultKeyPath = "\(homeDir)/DeerFlow/ssh/id_deerflow"
        if FileManager.default.fileExists(atPath: defaultKeyPath) {
            return defaultKeyPath
        }

        let homeSSHKey = "\(homeDir)/.ssh/id_ed25519"
        if FileManager.default.fileExists(atPath: homeSSHKey) {
            return homeSSHKey
        }

        let homeRSAKey = "\(homeDir)/.ssh/id_rsa"
        if FileManager.default.fileExists(atPath: homeRSAKey) {
            return homeRSAKey
        }

        return nil
    }

    private func startKeepalive() {
        stopKeepalive()
        keepaliveTimer = Timer.scheduledTimer(
            withTimeInterval: 60,
            repeats: true
        ) { [weak self] _ in
            guard let self = self, self.isConnected else { return }
            Task {
                _ = try? await self.execute(command: "true", timeout: 10)
            }
        }
    }

    private func stopKeepalive() {
        keepaliveTimer?.invalidate()
        keepaliveTimer = nil
    }
}

public enum SSHError: LocalizedError {
    case connectionFailed(String)
    case authenticationFailed(String)
    case timeout
    case disconnected

    public var errorDescription: String? {
        switch self {
        case .connectionFailed(let msg):
            return "SSH connection failed: \(msg)"
        case .authenticationFailed(let msg):
            return "SSH authentication failed: \(msg)"
        case .timeout:
            return "SSH operation timed out"
        case .disconnected:
            return "SSH connection disconnected"
        }
    }
}
