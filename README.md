# 九江学院图书馆座位预约脚本

基于 [ChaoXingReserveSeat](https://github.com/bear-zd/ChaoXingReserveSeat) 适配的纯 Python requests 版本，无需浏览器，轻量快速。

## 功能特点

- 纯 requests 实现，enc 签名用纯 Python MD5 计算，无需执行 JS
- 支持多房间、多座位、多时段自动备选
- 每天 21:30 准点抢第二天的座位
- 支持 GitHub Actions 定时托管
- 支持用户名密码登录和 Cookie 登录两种方式

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 修改配置

编辑 `config.json`：

```json
{
  "deptIdEnc": "369ce50576aa680d",
  "rooms": [
    {"id": 4597, "name": "主馆书库-1-5楼书库"},
    {"id": 8215, "name": "逸夫馆-逸夫馆108"}
  ],
  "seats": [711, 734, 700],
  "timeSlots": [
    {"start": "19:00", "end": "21:00"},
    {"start": "18:30", "end": "21:00"}
  ]
}
```

- `rooms`：按优先级排列的房间列表，脚本会依次尝试
- `seats`：按优先级排列的座位号列表
- `timeSlots`：按优先级排列的时段列表
- 脚本会按「房间 → 时段 → 座位」的顺序依次尝试，直到成功

### 3. 本地运行

**方式一：用户名密码登录（推荐）**

```bash
python main.py -m now -u 你的学号 -p 你的密码
```

**方式二：Cookie 登录**

从浏览器导出登录态为 `storage_state.json`（Playwright 格式），然后：

```bash
python main.py -m now --cookie config/storage_state.json
```

**参数说明：**

| 参数 | 说明 |
|------|------|
| `-m now` | 立即执行 |
| `-m reserve` | 等到 21:30 准点执行 |
| `-m debug` | 立即执行（调试用） |
| `-d YYYY-MM-DD` | 指定预约日期（默认明天） |
| `-u 账号` | 学习通账号 |
| `-p 密码` | 学习通密码 |
| `--cookie 路径` | Cookie 文件路径 |
| `-c 路径` | 配置文件路径（默认 config.json） |

## 房间 ID 对照表

| 房间 ID | 名称 | 座位数 |
|---------|------|--------|
| 4597 | 主馆书库-1-5楼书库 | 741 |
| 4217 | 主馆207 | 336 |
| 8215 | 逸夫馆108 | 303 |
| 12038 | 主馆407 | 278 |
| 12036 | 主馆307 | 241 |
| 5971 | 主馆507 | 228 |
| 3993 | 主馆301 | 150 |
| 1769 | 主馆107-A | 132 |
| 3984 | 主馆107-B | 132 |
| 3985 | 主馆107-C | 132 |
| 3986 | 主馆107-D | 132 |
| 8599 | 逸夫馆208 | 120 |
| 6009 | 逸夫馆105 | 98 |
| 8598 | 逸夫馆207 | 104 |
| 1768 | 主馆312 | 80 |
| 4326 | 主馆312B | 78 |
| 9674 | 逸夫大厅A | 84 |
| 9719 | 逸夫大厅B | 84 |
| 8800 | 逸夫馆208B | 62 |
| 8601 | 逸夫馆207圆厅 | 52 |

## GitHub Actions 托管

### 1. Fork 本仓库到你的 GitHub

### 2. 设置 Secrets

在仓库 `Settings → Secrets and variables → Actions` 中添加：

- `USERNAME`：你的学习通账号（学号）
- `PASSWORD`：你的学习通密码

### 3. 启用定时任务

工作流已配置为每天 **北京时间 21:29** 自动触发（UTC 13:29），脚本内部精确等待到 21:30 准点提交。

也可以在 `Actions` 页面手动触发，支持指定日期和模式。

## 技术原理

### enc 签名算法

九江学院系统的 enc 签名无需执行混淆 JS，纯 Python 即可计算：

1. 访问选座页面，从 HTML 隐藏 input 中提取 `submit_enc` 值
2. 对提交参数的键按字母排序
3. 拼接成 `[key=value][key=value]...[submit_enc值]` 格式
4. 对整体字符串做 MD5，得到最终 enc

### 登录

使用超星统一的 AES-128-CBC 加密（key=iv=`u2oh6Vu^HWe4_AES`），加密用户名密码后提交到 `passport2.chaoxing.com/fanyalogin`。

## 注意事项

- 系统页面提示"后台自动监控第三方抢座，发现立即拉黑"，使用风险自负
- 建议先用 `debug` 模式测试，确认配置正确后再正式使用
- 座位号需补零到 3 位（如 36 号 → "036"），脚本已自动处理
- GitHub Actions 的 cron 可能有几分钟延迟，脚本内部会精确等待到 21:30

## 项目结构

```
library-seat-bot/
├── main.py                  # 主程序
├── config.json              # 配置文件
├── requirements.txt         # 依赖
├── utils/
│   ├── __init__.py
│   ├── encrypt.py           # AES 加密（登录用）
│   └── enc.py               # enc 签名计算（MD5）
├── .github/workflows/
│   └── reserve.yml          # GitHub Actions 定时任务
└── README.md
```
