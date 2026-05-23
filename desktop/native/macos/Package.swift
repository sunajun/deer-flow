// swift-tools-version:5.9

import PackageDescription

var swiftSettings: [SwiftSetting] = []
#if canImport(Virtualization, _version: 14)
swiftSettings.append(.define("NATIVE_SNAPSHOTS"))
#endif

let package = Package(
    name: "DeerFlowSandbox",
    platforms: [
        .macOS(.v11)
    ],
    products: [
        .executable(name: "DeerFlowSandboxCLI", targets: ["DeerFlowSandboxCLI"]),
        .library(name: "DeerFlowSandbox", targets: ["DeerFlowSandbox"])
    ],
    dependencies: [],
    targets: [
        .executableTarget(
            name: "DeerFlowSandboxCLI",
            dependencies: ["DeerFlowSandbox"],
            path: "Sources/DeerFlowSandboxCLI"
        ),
        .target(
            name: "DeerFlowSandbox",
            dependencies: [],
            path: "Sources/DeerFlowSandbox",
            swiftSettings: swiftSettings
        ),
        .testTarget(
            name: "DeerFlowSandboxTests",
            dependencies: ["DeerFlowSandbox"],
            path: "Tests/DeerFlowSandboxTests"
        )
    ]
)
