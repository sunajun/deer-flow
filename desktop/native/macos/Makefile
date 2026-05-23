.PHONY: build release test clean sign cli

SIGNING_IDENTITY ?= "Developer ID Application: DeerFlow Team"
ENTITLEMENTS ?= ../../../assets/entitlements.sandbox.plist
BUILD_DIR ?= .build

build:
	swift build

release:
	swift build -c release

cli: release
	@echo "CLI built at $(BUILD_DIR)/release/DeerFlowSandboxCLI"

test:
	swift test

clean:
	swift package clean

sign: release
	codesign --force --options runtime \
		--entitlements $(ENTITLEMENTS) \
		--sign $(SIGNING_IDENTITY) \
		$(BUILD_DIR)/release/DeerFlowSandboxCLI

verify:
	codesign --verify --deep --strict --verbose=2 $(BUILD_DIR)/release/DeerFlowSandboxCLI
