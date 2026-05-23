import Foundation
import DeerFlowSandbox

struct CLI {
    static func main() async {
        let args = CommandLine.arguments

        guard args.count > 1 else {
            printUsage()
            return
        }

        let action = args[1]

        do {
            let result = try await handleAction(action, args: Array(args.dropFirst(2)))
            outputJSON(result)
        } catch {
            outputJSON([
                "success": false,
                "error": error.localizedDescription
            ])
        }
    }

    static func handleAction(_ action: String, args: [String]) async throws -> [String: Any] {
        let parsedArgs = parseArgs(args)

        switch action {
        case "detect-support":
            return [
                "success": true,
                "data": DeerFlowSandboxAPI.detectSupport()
            ]

        case "create-sandbox":
            guard let config = parsedArgs["config"] as? [String: Any] ?? parsedArgs as? [String: Any] else {
                return ["success": false, "error": "Missing config"]
            }
            let id = DeerFlowSandboxAPI.createSandbox(config: config)
            return ["success": true, "id": id]

        case "start-sandbox":
            guard let id = parsedArgs["id"] as? String else {
                return ["success": false, "error": "Missing id"]
            }
            let ok = DeerFlowSandboxAPI.startSandbox(id: id)
            return ["success": ok]

        case "stop-sandbox":
            guard let id = parsedArgs["id"] as? String else {
                return ["success": false, "error": "Missing id"]
            }
            let ok = DeerFlowSandboxAPI.stopSandbox(id: id)
            return ["success": ok]

        case "execute":
            guard let id = parsedArgs["id"] as? String,
                  let command = parsedArgs["command"] as? String else {
                return ["success": false, "error": "Missing id or command"]
            }
            let timeout = parsedArgs["timeout"] as? Int ?? 300
            let result = DeerFlowSandboxAPI.executeInSandbox(
                id: id,
                command: command,
                timeout: timeout
            )
            return ["success": true, "data": result]

        case "pause-sandbox":
            guard let id = parsedArgs["id"] as? String else {
                return ["success": false, "error": "Missing id"]
            }
            let ok = DeerFlowSandboxAPI.pauseSandbox(id: id)
            return ["success": ok]

        case "resume-sandbox":
            guard let id = parsedArgs["id"] as? String else {
                return ["success": false, "error": "Missing id"]
            }
            let ok = DeerFlowSandboxAPI.resumeSandbox(id: id)
            return ["success": ok]

        case "save-snapshot":
            guard let id = parsedArgs["id"] as? String,
                  let name = parsedArgs["name"] as? String else {
                return ["success": false, "error": "Missing id or name"]
            }
            let ok = DeerFlowSandboxAPI.saveSnapshot(id: id, name: name)
            return ["success": ok]

        case "restore-snapshot":
            guard let id = parsedArgs["id"] as? String,
                  let name = parsedArgs["name"] as? String else {
                return ["success": false, "error": "Missing id or name"]
            }
            let ok = DeerFlowSandboxAPI.restoreSnapshot(id: id, name: name)
            return ["success": ok]

        case "list-snapshots":
            guard let id = parsedArgs["id"] as? String else {
                return ["success": false, "error": "Missing id"]
            }
            let list = DeerFlowSandboxAPI.listSnapshots(id: id)
            return ["success": true, "data": list]

        case "delete-snapshot":
            guard let id = parsedArgs["id"] as? String,
                  let name = parsedArgs["name"] as? String else {
                return ["success": false, "error": "Missing id or name"]
            }
            let ok = DeerFlowSandboxAPI.deleteSnapshot(id: id, name: name)
            return ["success": ok]

        case "default-config":
            let compat = PlatformCompatibility.shared
            let config = compat.defaultVMConfig()
            return [
                "success": true,
                "data": [
                    "imagePath": config.imagePath,
                    "memoryMB": config.memoryMB,
                    "cpuCount": config.cpuCount,
                    "workspacePath": config.workspacePath,
                    "architecture": config.architecture.rawValue
                ]
            ]

        default:
            return ["success": false, "error": "Unknown action: \(action)"]
        }
    }

    static func parseArgs(_ args: [String]) -> [String: Any] {
        var result: [String: Any] = [:]
        var i = 0

        while i < args.count {
            let arg = args[i]
            if arg.hasPrefix("--") {
                let key = String(arg.dropFirst(2))
                if i + 1 < args.count {
                    let value = args[i + 1]
                    if let jsonData = value.data(using: .utf8),
                       let json = try? JSONSerialization.jsonObject(with: jsonData) {
                        result[key] = json
                    } else if let intVal = Int(value) {
                        result[key] = intVal
                    } else {
                        result[key] = value
                    }
                    i += 2
                } else {
                    i += 1
                }
            } else {
                i += 1
            }
        }

        return result
    }

    static func outputJSON(_ dict: [String: Any]) {
        if let data = try? JSONSerialization.data(
            withJSONObject: dict,
            options: [.sortedKeys]
        ) {
            print(String(data: data, encoding: .utf8) ?? "{}")
        } else {
            print("{}")
        }
    }

    static func printUsage() {
        let usage = """
        DeerFlowSandboxCLI - macOS Virtualization Sandbox Manager

        Usage: DeerFlowSandboxCLI <action> [options]

        Actions:
          detect-support              Detect virtualization support
          create-sandbox --args JSON  Create a new sandbox
          start-sandbox --id ID       Start a sandbox
          stop-sandbox --id ID        Stop a sandbox
          execute --id ID --command CMD [--timeout SEC]  Execute command
          pause-sandbox --id ID       Pause a sandbox
          resume-sandbox --id ID      Resume a sandbox
          save-snapshot --id ID --name NAME   Save snapshot
          restore-snapshot --id ID --name NAME Restore snapshot
          list-snapshots --id ID      List snapshots
          delete-snapshot --id ID --name NAME Delete snapshot
          default-config              Get default VM config

        Examples:
          DeerFlowSandboxCLI detect-support
          DeerFlowSandboxCLI create-sandbox --args '{"imagePath":"/path/to/image"}'
          DeerFlowSandboxCLI start-sandbox --id abc-123
          DeerFlowSandboxCLI execute --id abc-123 --command "uname -a"
        """
        print(usage)
    }
}

await CLI.main()
