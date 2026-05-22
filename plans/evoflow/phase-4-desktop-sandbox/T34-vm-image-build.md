# T34 - VM 镜像构建 + 集成测试

## 元信息
- **任务ID**: T34
- **阶段**: 第4期 - 桌面客户端与SOLO沙箱
- **优先级**: P6
- **预估工期**: 6 天（增加 CI/CD 集成、版本兼容检查和体积优化）
- **依赖任务**: T30, T31, T32, T33
- **关联差距**: 差距7 - 桌面客户端 + SOLO 轻量 VM 沙箱

## 目标
构建三平台 VM 沙箱镜像（macOS .img / Windows .tar.gz / Linux rootfs），建立**自动化 CI 构建流水线**，实现**镜像版本管理和兼容性检查**，编写跨平台集成测试确保核心功能正常。

## 详细实现步骤

### 步骤1: 创建镜像构建目录结构
- **文件**: `scripts/build-vm-image/`
- **操作**: 新建
- **内容**: 创建以下文件结构：
  ```
  scripts/build-vm-image/
  ├── Dockerfile                    通用基础镜像定义
  ├── Dockerfile.firecracker        Firecracker 专用 rootfs
  ├── build-all.sh                  一键构建三平台镜像
  ├── build-macos.sh                macOS Virtualization.framework 镜像
  ├── build-wsl2.sh                 Windows WSL2 rootfs
  ├── build-firecracker.sh          Linux Firecracker rootfs
  ├── config/
  │   ├── wsl.conf                  WSL2 配置
  │   ├── sshd_config               SSH 服务器配置
  │   └── deerflow-init.sh          VM 内初始化脚本
  ├── test-image.sh                 镜像功能验证脚本
  ├── versions.env                  版本管理
  └── compatibility-check.sh        镜像兼容性检查
  ```
- **验收**: 目录结构完整，脚本可执行

### 步骤2: 通用 Dockerfile 定义
- **文件**: `scripts/build-vm-image/Dockerfile`
- **操作**: 新建
- **内容**: 定义最小 Ubuntu + 开发工具基础镜像（同原版，略）
- **验收**: `docker build -t deerflow-vm-base .` 构建成功

### 步骤3: macOS 镜像构建
- **文件**: `scripts/build-vm-image/build-macos.sh`
- **操作**: 新建
- **内容**: 构建 macOS Virtualization.framework 格式的磁盘镜像（同原版，略）
- **验收**: 构建的 .img.gz 文件可在 macOS Virtualization.framework 中加载启动

### 步骤4: Windows WSL2 镜像构建
- **文件**: `scripts/build-vm-image/build-wsl2.sh`
- **操作**: 新建
- **内容**: 构建 Windows WSL2 格式的 rootfs 压缩包（同原版，略）
- **验收**: 构建的 .tar.gz 文件可通过 `wsl --import` 成功导入

### 步骤5: Linux Firecracker 镜像构建
- **文件**: `scripts/build-vm-image/build-firecracker.sh`
- **操作**: 新建
- **内容**: 构建 Linux Firecracker 格式的 rootfs ext4 镜像（同原版，略）
- **验收**: 构建的 rootfs.ext4.gz + vmlinux 可用于 Firecracker 启动 VM

### 步骤6: 一键构建脚本
- **文件**: `scripts/build-vm-image/build-all.sh`
- **操作**: 新建
- **内容**: 一键构建三平台镜像（同原版，略）
- **验收**: `./build-all.sh` 一键构建三平台镜像，输出文件完整

### 步骤7: 镜像版本管理与兼容性检查
- **文件**: `scripts/build-vm-image/compatibility-check.sh`
- **操作**: 新建
- **内容**: **核心改进：镜像版本管理和兼容性检查**：
  1. **版本信息嵌入**：
     - 每个镜像内写入 `/etc/deerflow-version`：
       ```
       DEERFLOW_VERSION=0.1.0
       IMAGE_FORMAT=macos-img
       BUILD_DATE=2026-05-22T00:00:00Z
       COMPAT_VERSION=1
       MIN_APP_VERSION=0.1.0
       PYTHON_VERSION=3.12
       NODE_VERSION=20
       UBUNTU_VERSION=24.04
       ```
     - `COMPAT_VERSION`：镜像兼容性版本，应用检查此版本决定是否兼容
     - `MIN_APP_VERSION`：镜像要求的最低应用版本
  2. **兼容性检查逻辑**：
     ```python
     def check_image_compatibility(app_version: str, image_info: dict) -> CompatibilityResult:
         if app_version < image_info["MIN_APP_VERSION"]:
             return CompatibilityResult(
                 compatible=False,
                 reason=f"应用版本 {app_version} 低于镜像要求的最低版本 {image_info['MIN_APP_VERSION']}",
                 action="update_app",
             )
         return CompatibilityResult(compatible=True)
     ```
  3. **镜像与应用版本映射**：
     ```yaml
     # versions.env
     VERSION=0.1.0
     COMPAT_VERSION=1
     MIN_APP_VERSION=0.1.0
     FIRECRACKER_VERSION=1.7.0
     FIRECRACKER_KERNEL_VERSION=6.1
     UBUNTU_VERSION=24.04
     PYTHON_VERSION=3.12
     NODE_VERSION=20
     ```
  4. **运行时版本检查**：
     - 应用启动时检查 VM 镜像版本
     - 版本不匹配时提示更新镜像
     - `COMPAT_VERSION` 不兼容时阻止使用（必须更新）
     - `MIN_APP_VERSION` 不兼容时提示更新应用
  5. **镜像更新检查**：
     - 应用定期检查 GitHub Releases 是否有新镜像
     - 新镜像可用时提示用户更新
     - 镜像更新为可选（不影响核心功能）
- **验收**: 版本信息正确嵌入镜像；兼容性检查逻辑正确；版本不匹配时有明确提示

### 步骤8: 镜像体积优化
- **文件**: `scripts/build-vm-image/Dockerfile`（优化）
- **操作**: 改造
- **内容**: **核心改进：系统化的镜像体积优化**：
  1. **多阶段构建**：
     ```dockerfile
     FROM ubuntu:24.04 AS builder
     # 安装编译依赖，编译自定义工具
     RUN apt-get update && apt-get install -y --no-install-recommends \
         build-essential python3.12-dev

     FROM ubuntu:24.04 AS runtime
     COPY --from=builder /usr/local/bin/custom-tool /usr/local/bin/
     # 仅安装运行时依赖
     ```
  2. **包排除列表**：
     ```dockerfile
     # 排除不必要的文件
     RUN rm -rf /usr/share/doc/* /usr/share/man/* /usr/share/info/* \
         /usr/share/lintian/* /usr/share/common-licenses/* \
         /usr/share/bash-completion/* /usr/share/zsh/* \
         /var/lib/apt/lists/* /var/cache/apt/* \
         /root/.cache/pip /root/.npm \
         /tmp/* /var/tmp/*
     ```
  3. **ELF 二进制 strip**：
     ```bash
     find /usr -type f -executable -exec strip --strip-unneeded {} + 2>/dev/null || true
     find /usr -name "*.so" -exec strip --strip-unneeded {} + 2>/dev/null || true
     ```
  4. **Python 优化**：
     - 删除 `__pycache__` 和 `.pyc` 文件
     - 删除 `tests/` 和 `docs/` 目录
     - 使用 `pip install --no-cache-dir`
  5. **压缩优化**：
     - ext4 镜像使用最小块大小
     - gzip 使用最高压缩级别（`gzip -9`）
     - 考虑使用 zstd 压缩（更快的解压速度）
  6. **体积目标与监控**：
     | 平台 | 目标大小 | 最大允许 |
     |------|---------|---------|
     | macOS .img.gz | < 80MB | 100MB |
     | Windows .tar.gz | < 60MB | 80MB |
     | Linux rootfs.ext4.gz | < 25MB | 50MB |
     | Linux vmlinux | < 20MB | 30MB |
  7. **CI 体积检查**：
     - 构建后自动检查镜像大小
     - 超过最大允许值时 CI 失败
     - 体积趋势跟踪（记录每次构建的大小）
- **验收**: 三平台镜像大小在目标范围内；CI 体积检查生效

### 步骤9: 镜像功能验证脚本
- **文件**: `scripts/build-vm-image/test-image.sh`
- **操作**: 新建
- **内容**: 验证构建的镜像是否可用（同原版，增加版本检查）：
  1. 基础验证：SHA256 校验、文件大小、版本信息
  2. 平台验证：macOS/Windows/Linux 各自的功能测试
  3. **版本兼容性验证**：检查 `COMPAT_VERSION` 和 `MIN_APP_VERSION`
  4. **工具版本验证**：Python 3.12、Node.js 20、git 等
- **验收**: 在对应平台上执行验证脚本，所有检查通过

### 步骤10: CI/CD 自动化构建流水线
- **文件**: `.github/workflows/build-vm-images.yml`
- **操作**: 新建
- **内容**: **核心改进：完整的 CI/CD 自动化构建流水线**：
  1. **触发条件**：
     - `scripts/build-vm-image/` 目录变更
     - `versions.env` 变更
     - 手动触发（workflow_dispatch）
     - tag 发布时（`v*`）
     - 定时构建（每周一凌晨）
  2. **构建矩阵**：
     ```yaml
     strategy:
       matrix:
         platform: [macos, wsl2, firecracker]
     ```
  3. **构建步骤**：
     - Checkout 代码
     - 安装 Docker
     - 执行平台构建脚本
     - **运行镜像功能验证**
     - **检查镜像体积**
     - 上传构建产物
  4. **发布步骤**（仅 tag 触发）：
     - 创建 GitHub Release
     - 上传三平台镜像到 Release Assets
     - 更新 manifest.json
     - **更新 latest 指向**
  5. **测试步骤**：
     - Linux runner 上测试 Firecracker 镜像
     - macOS runner 上测试 Virtualization.framework 镜像
     - Windows runner 上测试 WSL2 镜像
  6. **缓存**：
     - Docker layer 缓存
     - 下载的内核文件缓存
  7. **通知**：
     - 构建失败通知
     - 新版本发布通知
  8. **体积趋势跟踪**：
     - 每次构建记录镜像大小
     - 存储为 CI artifact
     - 体积增长超过 10% 时报警
- **验收**: CI 流水线可自动构建并发布三平台镜像；体积检查和功能验证通过

### 步骤11: macOS 沙箱集成测试
- **文件**: `desktop/native/macos/Tests/DeerFlowSandboxTests/IntegrationTests.swift`
- **操作**: 新建
- **内容**: 编写 macOS Virtualization.framework 集成测试（同原版）
- **验收**: 所有集成测试通过

### 步骤12: Windows WSL2 集成测试
- **文件**: `desktop/native/windows/__tests__/wsl2-integration.test.ts`
- **操作**: 新建
- **内容**: 编写 Windows WSL2 集成测试（同原版）
- **验收**: 所有集成测试在 Windows 上通过

### 步骤13: Linux Firecracker 集成测试
- **文件**: `backend/tests/test_firecracker_integration.py`
- **操作**: 新建
- **内容**: 编写 Linux Firecracker 集成测试（同原版）
- **验收**: 所有集成测试在 Ubuntu 22.04/24.04 + KVM 上通过

### 步骤14: 跨平台一致性测试
- **文件**: `backend/tests/test_sandbox_consistency.py`
- **操作**: 新建
- **内容**: 验证三平台沙箱行为一致（同原版）
- **验收**: 三平台核心行为一致

## 验收标准
- [ ] 三平台镜像均可构建，大小在预期范围内
- [ ] macOS .img.gz < 100MB，可在 Virtualization.framework 中启动
- [ ] Windows .tar.gz < 80MB，可通过 wsl --import 导入
- [ ] Linux rootfs.ext4.gz < 50MB，可在 Firecracker 中启动
- [ ] manifest.json 和 SHA256 校验文件生成正确
- [ ] **CI/CD 流水线可自动构建三平台镜像**
- [ ] **镜像版本信息正确嵌入，兼容性检查逻辑正确**
- [ ] **镜像体积优化在目标范围内，CI 体积检查生效**
- [ ] 所有平台集成测试通过
- [ ] 跨平台行为一致性测试通过
- [ ] 镜像内 Python 3.12 + Node.js 20 + 基础工具可用

## 测试计划
| 测试类型 | 测试用例 | 预期结果 |
|---------|---------|---------|
| 构建测试 | build-all.sh 执行 | 三平台镜像全部构建成功 |
| 构建测试 | macOS 镜像大小 | .img.gz < 100MB |
| 构建测试 | Windows 镜像大小 | .tar.gz < 80MB |
| 构建测试 | Linux 镜像大小 | rootfs.ext4.gz < 50MB |
| 版本测试 | 版本信息嵌入 | `/etc/deerflow-version` 包含所有字段 |
| 版本测试 | 兼容性检查 | COMPAT_VERSION 不匹配时阻止使用 |
| 版本测试 | 最低应用版本检查 | MIN_APP_VERSION 不满足时提示更新 |
| 体积测试 | CI 体积检查 | 超过最大允许值时 CI 失败 |
| 体积测试 | 体积趋势 | 记录每次构建大小，增长 >10% 报警 |
| 功能测试 | macOS VM 启动 | VM 状态 running，SSH 可连接 |
| 功能测试 | Windows WSL2 导入 | 发行版列表包含 DeerFlow |
| 功能测试 | Linux Firecracker 启动 | VM 启动成功，命令执行正常 |
| 功能测试 | 三平台 Python 版本 | python3 --version 包含 3.12 |
| 功能测试 | 三平台 Node.js 版本 | node --version 包含 v20 |
| 集成测试 | macOS 快照/恢复 | 恢复后状态一致 |
| 集成测试 | Windows 文件共享 | 双向读写正常 |
| 集成测试 | Linux 多实例并行 | 互不干扰 |
| 一致性测试 | 跨平台工具可用性 | bash/git/curl/wget 全部可用 |
| CI 测试 | GitHub Actions 流水线 | 自动构建并发布成功 |
| CI 测试 | 定时构建 | 每周一自动构建 |

## 风险与缓解
| 风险 | 概率 | 缓解措施 |
|------|------|---------|
| macOS 镜像格式与 Virtualization.framework 不兼容 | 中 | 参考 Apple 官方示例；使用 raw 格式确保兼容 |
| WSL2 rootfs.tar.gz 导入失败 | 低 | 参考 Microsoft 官方文档；使用 Docker export 标准格式 |
| Firecracker 内核与 rootfs 不兼容 | 中 | 使用 Firecracker 官方推荐内核版本；CI 测试验证 |
| CI 环境无 KVM 导致 Firecracker 测试跳过 | 高 | 使用支持嵌套虚拟化的 GitHub runner；或使用 QEMU 模拟 |
| 镜像体积超出预期 | 中 | **系统化体积优化**；多阶段构建；strip 二进制；CI 体积检查 |
| 版本号不一致导致兼容性问题 | 低 | **versions.env 统一管理**；构建时注入版本号；兼容性检查 |
| macOS/Windows CI runner 难以获取 | 高 | GitHub Actions 提供 macOS/Windows runner；Docker 构建可在 Linux 上跨平台 |
| 镜像更新后与旧版应用不兼容 | 中 | **COMPAT_VERSION 兼容性检查**；强制更新提示；保留旧版镜像下载 |

## 参考文档
- EVOFLOW_IMPLEMENTATION_PLAN.md 第7节（7.6 VM 镜像构建）
- Docker 多阶段构建: https://docs.docker.com/build/building/multi-stage/
- WSL2 发行版创建: https://learn.microsoft.com/en-us/windows/wsl/build-custom-distro
- Firecracker rootfs 设置: https://github.com/firecracker-microvm/firecracker/blob/main/docs/rootfs-and-kernel-setup.md
- macOS Virtualization.framework 示例: https://developer.apple.com/documentation/virtualization/creating_and_running_a_linux_virtual_machine
