# 验证码存储与 SMS 发送/验证策略

手机验证码登录涉及三个基础选择：验证码临时存储方案、发送策略、以及自生成 vs 托管两种模式的架构设计。

## 决策背景

需要实现手机验证码登录，当前为自生成验证码模式（开发环境），未来需对接阿里云号码认证服务（生产环境）。两种模式的验证码生命周期管理方式根本不同。

## 验证码存储：自生成模式用 Redis

**Why**
- 项目已有 Redis 基础设施（redis:7-alpine，redis-py 同步 + redis.asyncio 异步双模式可用）
- Redis 原生 TTL 自动过期，天然匹配验证码 300s 生命周期
- 原子 INCR 适合失败尝试次数计数
- 无持久化需求（验证码本身是一次性用完即弃的数据）

**Rejected**: 数据库表 `verification_codes`。TTL 需定时清理逻辑，查询成本高于 Redis，增加不必要的表维护负担。

**适用范围**: 仅 `SMS_MODE=log`。`SMS_MODE=dypnsapi` 模式下验证码由阿里云持有，不使用 Redis 存储。

## 验证码托管：阿里云号码认证 (Dypnsapi)

**Why**
- 阿里云号码认证服务负责验证码生成、发送、核验全流程，应用端不持有验证码
- 调用 `SendSmsVerifyCode`（发送）和 `CheckSmsVerifyCode`（核验）两个 API
- 验证码通过 `##code##` 占位符由阿里云自动生成，应用端无感知
- 阿里云自带发送间隔控制（Interval 参数，默认 60s）、验证码有效期（ValidTime 参数，默认 300s）、QPS 限制（500/s）
- 阿里云自带预置签名和模板，无需企业资质申请

**与自生成模式的关键差异**:
- 验证码不存储在 Redis，`/api/dev/verification-code` 不可用
- Provider 的 `send()` 不生成 code，`verify()` 调用阿里云而非查 Redis
- 手机号冷却和重试限制由阿里云端控制，应用端仅保留 IP 限流

**Rejected**: 自行对接阿里云短信服务（Dysmsapi）+ 继续用 Redis 验证。虽然与当前自生成模式一致（我们生成 code，阿里云仅发送），但号码认证服务免签名模板审核，接入门槛更低。

## SMS Provider 策略模式

**Why**
- Provider 封装完整生命周期（send + verify），切换模式时行为完全替换，调用方零判断
- 单环境变量 `SMS_MODE` 控制切换，避免 Provider + Verifier 非法组合
- `SMS_MODE` 向后兼容旧的 `SMS_PROVIDER` 变量（fallback）
- 阿里云 SDK 调用通过 `asyncio.to_thread()` 包裹，避免阻塞 FastAPI 事件循环
- 环境变量注入配置（AccessKey、SignName 等），构造时不校验（允许未配置时先启动，后续切换模式）

**Rejected**: Provider 和 Verifier 分离为两个抽象。log 模式用 RedisVerifier，dypnsapi 模式用 DypnsapiVerifier，但实际不存在跨组合场景（选了 dypnsapi 就不可能用 Redis 验证），拆分增加不必要的复杂度。

**Rejected**: 启动时校验配置。不同模式可能在不同时期激活，启动时校验会阻止未配置模式的系统启动。
