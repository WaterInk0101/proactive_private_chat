# proactive_private_chat
麦麦主动私聊插件

---
## 功能说明

让麦麦自主决策是否要私聊别人

## 安装方法  

1.下载或克隆本仓库
```bash
https://github.com/WaterInk0101/proactive_private_chat.git
```

2.将本插件解压至插件目录`plugins`

3.重启麦麦

## 命令使用方法
```bash
/私聊 QQ号  #立即私聊指定用户 *使用随机问候消息模版*
/私聊列表   #debug·在麦麦控制台日志中输出可私聊的用户列表    
```

## 配置选项
```bash
[general]
enabled = true                                   #是否启用插件
cooldown_seconds = 300                           #私聊消息发送的冷却时间（秒），防止过于频繁

[smart_chat]
only_known_users = true                          #是否只对已知用户发起私聊（互为好友且有聊天记录）

[messages]
default_greeting = "嗨 {nickname}，最近怎么样？"  #默认问候消息模板
random_greetings = [
    "嗨 {nickname}，好久不见！",
    "{nickname}，在忙什么？",
    "想你了 {nickname}，来聊聊天~",
    "{nickname}，今天过得怎么样？",
    "嘿 {nickname}，有空吗？想和你说说话~"       #随机问候消息模版列表
]

[command]
require_admin = false                            #是否启用管理员权限
allowed_users = ["123456"]                       #管理员白名单
```
