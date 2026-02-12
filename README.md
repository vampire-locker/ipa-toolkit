# ipa-toolkit

一个用于修改和重新签名 iOS .ipa 文件的 Python 命令行工具。

## 功能特性

- ✅ **重新签名** - 使用新的代码签名身份对 iOS 应用进行签名
- ✅ **修改 Bundle ID** - 自动处理主应用和扩展的包标识符
- ✅ **更新版本信息** - 修改版本号（CFBundleShortVersionString）和构建号（CFBundleVersion）
- ✅ **更改显示名称** - 修改应用在主屏幕上显示的名称
- ✅ **嵌入描述文件** - 安装新的 provisioning profile
- ✅ **通用 Info.plist 编辑** - 支持设置、删除、数组操作等
- ✅ **嵌套键路径** - 支持 PlistBuddy 风格的路径（如 `CFBundleURLTypes:0:CFBundleURLSchemes:0`）
- ✅ **作用域控制** - 可以只针对主应用或扩展进行修改
- ✅ **完整保留** - 保留 IPA 中的所有内容（Payload、Symbols、SwiftSupport 等）
- ✅ **递归签名** - 自动处理 frameworks、extensions、XPC services

## 系统要求

- **操作系统**: macOS（依赖 macOS 的 codesign 和 security 工具）
- **Python**: 3.9 或更高版本
- **Xcode Command Line Tools**: 需要安装（提供 codesign 工具）

验证系统要求：

```bash
# 检查 Python 版本
python3 --version  # 应该 >= 3.9

# 检查 codesign 工具
which codesign  # 应该输出 /usr/bin/codesign

# 检查可用的签名身份
security find-identity -v -p codesigning
```

## 安装

```bash
# 方式 1: 直接使用
python3 ipa_toolkit.py -h

# 方式 2: 安装为命令行工具
pip install -e .
ipa-toolkit -h

# 方式 3: Python 模块方式
python3 -m ipa_toolkit -h
```

## 快速开始

只重新签名：

```bash
ipa-toolkit -i app.ipa -s "Apple Distribution: Company (TEAMID)" -p profile.mobileprovision
```

修改 Bundle ID 和版本：

```bash
ipa-toolkit -i app.ipa -o app-resigned.ipa \
  -s "Apple Distribution: Company (TEAMID)" \
  -p profile.mobileprovision \
  -b com.newcompany.app -v 2.0.0 -n 100
```

## 使用指南

### 基本用法

```bash
ipa-toolkit -i INPUT.ipa -s "SIGN_IDENTITY" [选项]
```

**必需参数：**

- `-i, --input` - 输入的 .ipa 文件路径
- `-s, --sign-identity` - 代码签名身份名称

**常用选项：**

- `-o, --output` - 输出的 .ipa 文件路径（默认：`<input>.resigned.ipa`）
- `-p, --profile` - 要嵌入的 provisioning profile 文件（.mobileprovision）
- `-e, --entitlements` - 自定义 entitlements.plist 文件（可选）
- `--main-app-name` - 当 Payload 下有多个 `.app` 时，指定主应用（如 `MyApp.app`）
- `-b, --bundle-id` - 新的 Bundle ID（会自动处理扩展）
- `-v, --version` - 新的版本号（CFBundleShortVersionString）
- `-n, --build` - 新的构建号（CFBundleVersion）
- `-d, --display-name` - 新的显示名称（CFBundleDisplayName）
- `--keep-temp` - 保留临时工作目录（用于调试）
- `--verbose` - 显示详细日志

### 高级用法 - Info.plist 编辑

设置值：

```bash
# 字符串
ipa-toolkit -i app.ipa -s "IDENTITY" \
  --set NSCameraUsageDescription="需要访问相机"

# 整数和布尔
ipa-toolkit -i app.ipa -s "IDENTITY" \
  --set-int SomeNumericKey=123 \
  --set-bool UIFileSharingEnabled=true

# 删除键
ipa-toolkit -i app.ipa -s "IDENTITY" \
  --delete NSAppTransportSecurity
```

数组和嵌套路径：

```bash
# 数组操作
ipa-toolkit -i app.ipa -s "IDENTITY" \
  --array-add LSApplicationQueriesSchemes=weixin \
  --array-remove LSApplicationQueriesSchemes=weixin

# 嵌套键路径（PlistBuddy 风格）
ipa-toolkit -i app.ipa -s "IDENTITY" \
  --set CFBundleURLTypes:0:CFBundleURLSchemes:0=myapp
```

作用域控制：

```bash
--set-main NSCameraUsageDescription="只修改主应用"
--set-ext NSExtension:SomeKey="只修改扩展"
--set NSCameraUsageDescription="修改所有 bundle（默认）"
```

主应用选择（多 `.app` 场景）：

```bash
ipa-toolkit -i app.ipa -s "IDENTITY" \
  --main-app-name MyApp.app
```

### 完整示例

企业分发：

```bash
ipa-toolkit -i MyApp.ipa -o MyApp-Enterprise.ipa \
  -s "Apple Distribution: My Company (ABC123XYZ)" \
  -p Enterprise.mobileprovision \
  -b com.mycompany.myapp.enterprise \
  -v 1.0.0 -n 1 -d "MyApp Enterprise" \
  --set NSCameraUsageDescription="需要使用相机扫描二维码" \
  --set-bool UIFileSharingEnabled=true \
  --verbose
```

测试环境：

```bash
ipa-toolkit -i Production.ipa -o Testing.ipa \
  -s "Apple Development: Developer Name (DEV123)" \
  -p Development.mobileprovision \
  -b com.mycompany.myapp.dev -d "MyApp DEV" \
  --set APIBaseURL="https://test-api.example.com" \
  --set-bool EnableDebugMode=true
```

## 前置条件

### 获取代码签名身份

```bash
security find-identity -v -p codesigning
```

输出示例：
```
1) ABC123... "Apple Distribution: Your Company (TEAMID)"
2) DEF456... "Apple Development: Your Name (DEVID)"
```

使用引号中的完整名称作为 `-s` 参数。

### Provisioning Profile

- **开发**: Development Profile（从 Xcode 或 Apple Developer 下载）
- **企业分发**: Enterprise Distribution Profile
- **Ad Hoc**: Ad Hoc Distribution Profile

Profile 通常位于 `~/Library/MobileDevice/Provisioning Profiles/`

### Bundle ID 规则

- Bundle ID 必须与 Profile 中的 App ID 匹配
- 修改主应用 Bundle ID 时，扩展会自动前缀替换：
  - `com.old.app` → `com.new.app`
  - `com.old.app.share` → `com.new.app.share`

## 工作原理

1. **解压 IPA** - 将 .ipa 文件解压到临时目录
2. **查找 Bundle** - 定位主应用和所有嵌套的 bundle（.appex、.xpc 等）
3. **修改 Info.plist** - 应用所有请求的修改（Bundle ID、版本、自定义键等）
4. **嵌入 Profile** - 将 provisioning profile 复制到主应用
5. **准备 Entitlements** - 从现有签名或 profile 中提取权限配置
6. **递归签名** - 按正确顺序签名所有组件：
   - 先签名嵌套的 frameworks 和 dylibs
   - 再签名扩展（.appex）和 XPC services
   - 最后签名主应用 bundle
7. **重新打包** - 使用 `zip -y` 保留符号链接，打包所有内容
8. **验证** - 运行 `codesign --verify` 确保签名有效

## 常见问题

### Q: 签名失败，提示 "errSecInternalComponent"

钥匙串权限问题，尝试解锁：

```bash
security unlock-keychain ~/Library/Keychains/login.keychain-db
```

### Q: 安装时提示 "无法验证应用"

可能原因：
1. Profile 与设备 UDID 不匹配
2. Bundle ID 与 Profile 的 App ID 不匹配
3. 证书过期或被撤销
4. Entitlements 配置错误

使用 `--verbose` 查看详细日志。

### Q: 应用安装后闪退

检查：
1. 所有扩展是否正确签名
2. Entitlements 是否正确（特别是 `application-identifier`）
3. 复杂扩展是否需要单独的 Profile

使用 Xcode Console 查看设备日志。

### Q: 如何验证签名？

```bash
codesign --verify --deep --strict Payload/YourApp.app
codesign -dvvv Payload/YourApp.app
codesign -d --entitlements :- Payload/YourApp.app
```

### Q: 支持哪些 IPA？

- ✅ Xcode 导出、企业分发、Ad Hoc 分发的 IPA
- ⚠️ App Store 下载的 IPA 需要先解密

### Q: 可以用于 App Store 提交吗？

**不推荐**。App Store Connect 期望 Xcode Archive 生成的标准 IPA，重签名会丢失元数据和版本历史。

正确流程：`Xcode → Archive → Organizer → Distribute App → App Store Connect`

此工具适用于：企业分发、开发测试、Ad Hoc 分发、CI/CD 自动化。

## 限制和注意事项

1. **仅限 macOS** - 依赖 macOS 系统工具（codesign、security、unzip、zip）
2. **不适合 App Store** - 仅用于企业分发、开发测试、Ad Hoc 分发。App Store 提交请使用 Xcode Archive
3. **复杂扩展** - 多个扩展可能需要独立的 Provisioning Profile
4. **加密应用** - App Store 下载的 IPA 通常已加密，需要先解密
5. **权限调整** - 修改 Bundle ID 时，entitlements 会自动调整但可能不完整
6. **兼容性** - Apple 的签名机制可能随时变化
7. **Entitlements 校验** - 工具会校验 `application-identifier` 与 `keychain-access-groups` 的关键一致性，不匹配会直接报错

## 开发

```bash
# 安装开发依赖
pip install -e ".[dev]"

# 运行测试
pytest tests/ -v

# 代码检查
ruff check src/
```

项目结构：

```
ipa-toolkit/
├── src/ipa_toolkit/
│   ├── cli.py           # 命令行接口
│   ├── ipa.py           # 主处理流程
│   ├── bundle_scan.py   # 主 app 和嵌套 bundle 发现
│   ├── codesign.py      # 代码签名
│   ├── entitlements.py  # Entitlements 调整与校验
│   ├── pipeline_utils.py # 流水线命令执行与递归签名
│   ├── plist_ops.py     # 高层 plist 操作应用
│   ├── provisioning.py  # Profile 处理
│   ├── plist_edit.py    # Plist 编辑
│   └── plist_path.py    # 键路径解析
└── tests/               # 单元测试
```

## License

MIT License - 详见 [LICENSE](LICENSE) 文件

## 贡献

欢迎提交 Issue 和 Pull Request！提交前请确保代码通过 `ruff` 检查并添加必要的测试。

## 相关资源

- [Apple Code Signing Guide](https://developer.apple.com/library/archive/documentation/Security/Conceptual/CodeSigningGuide/)
- [iOS App Distribution](https://developer.apple.com/documentation/xcode/distributing-your-app-for-beta-testing-and-releases)
- [Entitlements Documentation](https://developer.apple.com/documentation/bundleresources/entitlements)

---

## 免责声明

此工具按"原样"提供，不提供任何担保。仅用于合法的开发、测试和企业分发场景。使用者需：

- 拥有合法的代码签名证书和应用修改权限
- 遵守 Apple Developer Program License Agreement
- 遵守所有适用的法律法规

作者不对任何误用或违规使用承担责任。
