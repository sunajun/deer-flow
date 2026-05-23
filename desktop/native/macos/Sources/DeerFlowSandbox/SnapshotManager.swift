import Foundation
import Virtualization

public struct SnapshotInfo: Codable {
    public let name: String
    public let createdAt: Date
    public let sizeBytes: Int64
    public let description: String?
    public let architecture: String
    public let isNative: Bool

    public init(
        name: String,
        createdAt: Date = Date(),
        sizeBytes: Int64 = 0,
        description: String? = nil,
        architecture: String = "unknown",
        isNative: Bool = false
    ) {
        self.name = name
        self.createdAt = createdAt
        self.sizeBytes = sizeBytes
        self.description = description
        self.architecture = architecture
        self.isNative = isNative
    }
}

public final class SnapshotManager {
    private weak var vm: VZVirtualMachine?
    private let config: VMConfig
    private let fileManager = FileManager.default
    private let homeDir: String

    private let maxAutoSnapshots = 10
    private var autoSnapshotTimer: Timer?

    public private(set) var snapshots: [SnapshotInfo] = []

    public init(vm: VZVirtualMachine, config: VMConfig) {
        self.vm = vm
        self.config = config
        self.homeDir = FileManager.default.homeDirectoryForCurrentUser.path
        loadSnapshotList()
    }

    public func saveSnapshot(name: String, description: String? = nil) async throws -> Bool {
        #if NATIVE_SNAPSHOTS
        if #available(macOS 14, *) {
            do {
                return try await performNativeSave(name: name, description: description)
            } catch {
                return try saveFileBasedSnapshot(name: name, description: description)
            }
        }
        #endif
        return try saveFileBasedSnapshot(name: name, description: description)
    }

    public func restoreSnapshot(name: String) async throws -> Bool {
        #if NATIVE_SNAPSHOTS
        if #available(macOS 14, *) {
            do {
                return try await performNativeRestore(name: name)
            } catch {
                return try restoreFileBasedSnapshot(name: name)
            }
        }
        #endif
        return try restoreFileBasedSnapshot(name: name)
    }

    public func listSnapshots() -> [SnapshotInfo] {
        return snapshots
    }

    public func deleteSnapshot(name: String) throws -> Bool {
        let snapshotDir = snapshotDirectory(for: name)

        guard fileManager.fileExists(atPath: snapshotDir) else {
            return false
        }

        try fileManager.removeItem(atPath: snapshotDir)
        snapshots.removeAll { $0.name == name }
        saveSnapshotList()

        return true
    }

    public func createBootSnapshot() async throws {
        _ = try await saveSnapshot(name: "boot", description: "Auto-created boot snapshot")
    }

    public func startAutoSnapshot(intervalMinutes: Int = 60) {
        stopAutoSnapshot()
        autoSnapshotTimer = Timer.scheduledTimer(
            withTimeInterval: TimeInterval(intervalMinutes * 60),
            repeats: true
        ) { [weak self] _ in
            guard let self = self else { return }
            Task {
                let timestamp = Int(Date().timeIntervalSince1970)
                _ = try? await self.saveSnapshot(
                    name: "auto-\(timestamp)",
                    description: "Auto snapshot"
                )
                self.pruneAutoSnapshots()
            }
        }
    }

    public func stopAutoSnapshot() {
        autoSnapshotTimer?.invalidate()
        autoSnapshotTimer = nil
    }

    #if NATIVE_SNAPSHOTS
    @available(macOS 14, *)
    private func performNativeSave(name: String, description: String?) async throws -> Bool {
        guard let vm = vm else { return false }

        try await vm.saveSnapshot(name: name)

        let snapshotDir = snapshotDirectory(for: name)
        try fileManager.createDirectory(atPath: snapshotDir, withIntermediateDirectories: true)

        let info = SnapshotInfo(
            name: name,
            description: description,
            architecture: config.architecture.rawValue,
            isNative: true
        )

        let metadataPath = "\(snapshotDir)/metadata.json"
        let data = try JSONEncoder().encode(info)
        try data.write(to: URL(fileURLWithPath: metadataPath))

        snapshots.removeAll { $0.name == name }
        snapshots.append(info)
        saveSnapshotList()

        return true
    }

    @available(macOS 14, *)
    private func performNativeRestore(name: String) async throws -> Bool {
        guard let vm = vm else { return false }

        try await vm.restoreSnapshot(name: name)
        return true
    }
    #endif

    private func saveFileBasedSnapshot(name: String, description: String?) throws -> Bool {
        let snapshotDir = snapshotDirectory(for: name)

        try fileManager.createDirectory(atPath: snapshotDir, withIntermediateDirectories: true)

        let sourceURL = URL(fileURLWithPath: config.imagePath)
        let destURL = URL(fileURLWithPath: "\(snapshotDir)/disk.img")

        try fileManager.copyItem(at: sourceURL, to: destURL)

        let configCopyPath = "\(snapshotDir)/config.json"
        let configData = try JSONEncoder().encode(config)
        try configData.write(to: URL(fileURLWithPath: configCopyPath))

        let attributes = try fileManager.attributesOfItem(atPath: "\(snapshotDir)/disk.img")
        let fileSize = (attributes[.size] as? Int64) ?? 0

        let info = SnapshotInfo(
            name: name,
            sizeBytes: fileSize,
            description: description,
            architecture: config.architecture.rawValue,
            isNative: false
        )

        let metadataPath = "\(snapshotDir)/metadata.json"
        let metadata = try JSONEncoder().encode(info)
        try metadata.write(to: URL(fileURLWithPath: metadataPath))

        snapshots.removeAll { $0.name == name }
        snapshots.append(info)
        saveSnapshotList()

        return true
    }

    private func restoreFileBasedSnapshot(name: String) throws -> Bool {
        let snapshotDir = snapshotDirectory(for: name)

        guard fileManager.fileExists(atPath: "\(snapshotDir)/disk.img") else {
            return false
        }

        let sourceURL = URL(fileURLWithPath: "\(snapshotDir)/disk.img")
        let destURL = URL(fileURLWithPath: config.imagePath)

        if fileManager.fileExists(atPath: config.imagePath) {
            try fileManager.removeItem(at: destURL)
        }

        try fileManager.copyItem(at: sourceURL, to: destURL)

        return true
    }

    private func pruneAutoSnapshots() {
        let autoSnapshots = snapshots
            .filter { $0.name.hasPrefix("auto-") }
            .sorted { $0.createdAt < $1.createdAt }

        if autoSnapshots.count > maxAutoSnapshots {
            let toDelete = autoSnapshots.prefix(autoSnapshots.count - maxAutoSnapshots)
            for snapshot in toDelete {
                _ = try? deleteSnapshot(name: snapshot.name)
            }
        }
    }

    private func snapshotDirectory(for name: String) -> String {
        return "\(homeDir)/DeerFlow/snapshots/default/\(name)"
    }

    private func snapshotsBaseDirectory() -> String {
        return "\(homeDir)/DeerFlow/snapshots/default"
    }

    private func loadSnapshotList() {
        let baseDir = snapshotsBaseDirectory()
        guard fileManager.fileExists(atPath: baseDir) else { return }

        let listPath = "\(baseDir)/snapshots.json"
        guard fileManager.fileExists(atPath: listPath) else { return }

        guard let data = fileManager.contents(atPath: listPath) else { return }
        snapshots = (try? JSONDecoder().decode([SnapshotInfo].self, from: data)) ?? []
    }

    private func saveSnapshotList() {
        let baseDir = snapshotsBaseDirectory()
        try? fileManager.createDirectory(atPath: baseDir, withIntermediateDirectories: true)

        let listPath = "\(baseDir)/snapshots.json"
        if let data = try? JSONEncoder().encode(snapshots) {
            try? data.write(to: URL(fileURLWithPath: listPath))
        }
    }
}
