"""
主动私聊插件 (Proactive Private Chat Plugin)

让麦麦能够主动发起私聊，支持以下功能：
1. 通过命令手动触发私聊指定用户
2. 麦麦智能决策主动私聊用户
3. 可配置的问候消息模板
4. 冷却时间控制，防止过于频繁

作者: MaiBot Plugin Developer
版本: 1.0.2
"""

import random
import time
from typing import List, Tuple, Type, Optional, Dict, Any

from src.plugin_system import (
    BasePlugin,
    register_plugin,
    BaseAction,
    BaseCommand,
    ComponentInfo,
    ActionActivationType,
)
from src.plugin_system.apis import send_api, chat_api, person_api
from src.common.logger import get_logger

logger = get_logger("ProactivePrivateChat")

# 默认平台
DEFAULT_PLATFORM = "qq"


# ==================== 工具函数 ====================

class PrivateChatCooldown:
    """私聊冷却时间管理器"""
    
    _cooldowns: Dict[str, float] = {}
    
    @classmethod
    def can_send(cls, user_id: str, cooldown_seconds: int) -> bool:
        """检查是否可以向指定用户发送私聊"""
        last_time = cls._cooldowns.get(user_id, 0)
        return time.time() - last_time >= cooldown_seconds
    
    @classmethod
    def record_send(cls, user_id: str):
        """记录向指定用户发送私聊的时间"""
        cls._cooldowns[user_id] = time.time()
    
    @classmethod
    def get_remaining_time(cls, user_id: str, cooldown_seconds: int) -> int:
        """获取剩余冷却时间（秒）"""
        last_time = cls._cooldowns.get(user_id, 0)
        remaining = cooldown_seconds - (time.time() - last_time)
        return max(0, int(remaining))

async def get_user_id_by_name(platform: str, username: str) -> Optional[str]:
    """
    通过用户名查询对应的用户ID（修正版，不依赖get_person）
    Args:
        platform: 平台名称（如"qq"）
        username: 用户名（昵称）
    Returns:
        对应的用户ID（数字字符串），未找到则返回None
    """
    try:
        # 1. 先通过用户名获取person_id（使用提供的get_person_id_by_name）
        person_id = person_api.get_person_id_by_name(username)
        if not person_id:
            logger.debug(f"未找到用户名 {username} 对应的person_id")
            return None
        
        # 2. 通过person_id获取对应的user_id（使用现有get_person_value方法）
        # 假设user_id存储在person的"user_id"属性中，若实际字段名不同需调整
        user_id = await person_api.get_person_value(person_id, "user_id")
        
        if user_id is not None:
            return str(user_id)  # 确保返回字符串类型的数字ID
        else:
            logger.debug(f"用户 {username} 的person_id {person_id} 未关联user_id属性")
            return None
            
    except Exception as e:
        logger.error(f"通过用户名查询用户ID失败: {e}")
        return None

async def is_user_known(platform: str, user_id: str) -> bool:
    """
    判断用户是否是已知用户
    判定逻辑：
    1. 优先通过person_api获取person_id判断
    2. 若获取失败，检查是否存在该用户的私聊流（存在则视为已知）
    """
    try:
        # 原逻辑：检查是否有person_id
        person_id = person_api.get_person_id(platform, int(user_id))
        if person_id:
            return True
    except Exception as e:
        logger.debug(f"通过person_api检查用户 {user_id} 失败: {e}")
    
    try:
        # 新增逻辑：检查是否存在私聊流
        chat_stream = chat_api.get_stream_by_user_id(user_id, platform)
        if chat_stream is not None:
            logger.debug(f"用户 {user_id} 存在私聊流，视为已知用户")
            return True
    except Exception as e:
        logger.debug(f"检查用户 {user_id} 私聊流失败: {e}")
    
    return False


async def get_greeting_message(config_getter, nickname: str) -> str:
    """获取问候消息"""
    # 尝试从随机问候列表中选择
    random_greetings = config_getter("messages.random_greetings", [])
    if random_greetings and random.random() > 0.3:
        message = random.choice(random_greetings)
    else:
        message = config_getter("messages.default_greeting", "嗨 {nickname}，最近怎么样呀？")
    
    # 替换变量
    return message.replace("{nickname}", nickname)


async def send_private_message(
    user_id: str,
    message: str,
    platform: str = "qq",
    config_getter=None
) -> Tuple[bool, str]:
    """
    向指定用户发送私聊消息
    
    Args:
        user_id: 用户ID
        message: 要发送的消息内容
        platform: 平台名称，默认为 "qq"
        config_getter: 配置获取函数
    
    Returns:
        Tuple[bool, str]: (是否成功, 结果描述)
    """
    try:
        # 检查冷却时间
        if config_getter:
            cooldown_seconds = config_getter("general.cooldown_seconds", 300)
            if not PrivateChatCooldown.can_send(user_id, cooldown_seconds):
                remaining = PrivateChatCooldown.get_remaining_time(user_id, cooldown_seconds)
                return False, f"冷却中，还需等待 {remaining} 秒"
        
        # 获取用户的私聊流
        chat_stream = chat_api.get_stream_by_user_id(user_id, platform)
        
        if chat_stream is None:
            logger.warning(f"未找到用户 {user_id} 的私聊流，可能该用户从未与麦麦私聊过")
            return False, f"未找到用户 {user_id} 的私聊流"
        
        # 发送消息
        success = await send_api.text_to_stream(
            text=message,
            stream_id=chat_stream.stream_id,
            typing=True,  # 显示正在输入
            storage_message=True  # 存储消息到数据库
        )
        
        if success:
            # 记录发送时间
            PrivateChatCooldown.record_send(user_id)
            logger.info(f"成功向用户 {user_id} 发送私聊消息")
            return True, "私聊消息发送成功"
        else:
            logger.error(f"向用户 {user_id} 发送私聊消息失败")
            return False, "消息发送失败"
            
    except Exception as e:
        logger.error(f"发送私聊消息时出错: {e}")
        return False, f"发送出错: {str(e)}"


# ==================== Action 组件 ====================

class ProactivePrivateChatAction(BaseAction):
    """
    主动私聊 Action
    
    让麦麦能够智能决策是否主动私聊某个用户。
    基于用户的活跃度、好感度等因素决定是否触发。
    """
    
    # === 基本信息 ===
    action_name = "proactive_private_chat"
    action_description = "主动向用户发起私聊，表达关心或分享有趣的事情"
    
    # 使用随机激活，增加行为的自然性
    activation_type = ActionActivationType.ALWAYS
    
    # === 功能描述 ===
    action_parameters = {
        "target_user_id": "要私聊的目标用户ID",
        "message_content": "要发送的私聊消息内容",
        "reason": "发起私聊的原因"
    }
    
    action_require = [
        "当用户要求私聊时使用",
        "当群聊中有人提到了一些私人的事情，你想私下关心ta时使用",
        "当你想和某个用户单独聊聊群里提到的话题时使用",
        "当你觉得某个用户可能需要私下安慰或鼓励时使用",
        "当群聊中的话题不方便公开讨论，想私下继续时使用",
        "当你很久没有和某个用户聊天，想问候一下时使用"
    ]
    
    associated_types = ["text"]
    parallel_action = False  # 不与其他动作并行
    
    async def execute(self) -> Tuple[bool, str]:
        """执行主动私聊动作"""
        
        # 检查插件是否启用
        if not self.get_config("general.enabled", True):
            logger.info("主动私聊功能已禁用（通过配置）")
            return False, "主动私聊功能已禁用"
        
        # 获取目标用户ID和消息内容
        target_user_id = self.action_data.get("target_user_id", "")
        message_content = self.action_data.get("message_content", "")
        reason = self.action_data.get("reason", "想和你聊聊天")

        # 若输入为非数字（用户名），尝试转换为user_id
        if target_user_id and not target_user_id.isdigit():
            logger.debug(f"检测到用户名 {target_user_id}，尝试转换为用户ID")
            converted_user_id = await get_user_id_by_name(self.platform, target_user_id)
            if converted_user_id:
                target_user_id = converted_user_id
                logger.debug(f"用户名 {self.action_data.get('target_user_id')} 转换为用户ID: {target_user_id}")
            else:
                logger.warning(f"未找到用户名 {target_user_id} 对应的用户ID")
                return False, f"未找到用户 {target_user_id} 的ID，请检查用户名是否正确"
        
        if not target_user_id:
            # 如果没有指定用户，尝试使用当前聊天的用户
            if self.user_id:
                target_user_id = self.user_id
            else:
                logger.warning("未指定目标用户，且当前上下文无用户ID")
                return False, "未指定目标用户"
        
        # 检查是否只允许对已知用户私聊
        only_known = self.get_config("smart_chat.only_known_users", True)
        if only_known:
            # 检查用户是否是已知用户
            is_known = await is_user_known(self.platform, target_user_id)
            if not is_known:
                logger.info(f"用户 {target_user_id} 不是已知用户，跳过私聊")
                return False, "该用户不是已知用户，跳过私聊"
        
        # 获取用户昵称
        try:
            person_id = person_api.get_person_id(self.platform, int(target_user_id))
            nickname = await person_api.get_person_value(person_id, "nickname", "朋友")
        except Exception as e:
            logger.warning(f"获取用户昵称失败: {e}")
            nickname = "朋友"
        
        # 如果没有指定消息内容，使用配置的问候模板
        if not message_content:
            message_content = await get_greeting_message(self.get_config, nickname)
        else:
            # 替换消息中的变量
            message_content = message_content.replace("{nickname}", nickname)
        
        # 发送私聊消息
        success, result_msg = await send_private_message(
            user_id=target_user_id,
            message=message_content,
            platform=self.platform,
            config_getter=self.get_config
        )
        
        if success:
            logger.info(f"主动私聊成功: 用户={target_user_id}, 原因={reason}")
            return True, f"成功向 {nickname} 发送了私聊消息"
        else:
            return False, result_msg


# ==================== Command 组件 ====================

class PrivateChatCommand(BaseCommand):
    """
    私聊命令
    
    通过命令手动触发向指定用户发送私聊消息。
    命令格式: /私聊 <用户ID> [消息内容]
    """
    
    command_name = "private_chat"
    command_description = "向指定用户发送私聊消息"
    command_pattern = r"^[/／]私聊\s+(?P<target_id>\d+)(?:\s+(?P<message>.+))?$"
    
    async def execute(self) -> Tuple[bool, Optional[str], bool]:
        """
        执行私聊命令
        
        Returns:
            Tuple[bool, Optional[str], bool]: (是否成功, 回复消息, 是否阻止后续处理)
        """
        # 从匹配组获取参数
        target_user_id = self.matched_groups.get("target_id", "")
        custom_message = self.matched_groups.get("message", None)
        
        if not target_user_id:
            return False, "命令格式错误，请使用: /私聊 <用户ID> [消息内容]", True
        
        # 获取用户昵称
        try:
            person_id = person_api.get_person_id(DEFAULT_PLATFORM, int(target_user_id))
            nickname = await person_api.get_person_value(person_id, "nickname", "用户")
        except:
            nickname = "用户"
        
        # 准备消息内容
        if custom_message:
            message = custom_message.replace("{nickname}", nickname)
        else:
            message = await get_greeting_message(self.get_config, nickname)
        
        # 发送私聊
        success, result_msg = await send_private_message(
            user_id=target_user_id,
            message=message,
            platform=DEFAULT_PLATFORM,
            config_getter=self.get_config
        )
        
        if success:
            return True, f"已向 {nickname}({target_user_id}) 发送私聊消息", True
        else:
            return False, f"发送失败: {result_msg}", True


class ListPrivateStreamsCommand(BaseCommand):
    """
    列出私聊流命令
    
    查看当前所有可用的私聊流。
    命令格式: /私聊列表
    """
    
    command_name = "list_private_streams"
    command_description = "列出所有可用的私聊流"
    command_pattern = r"^[/／]私聊列表$"
    
    async def execute(self) -> Tuple[bool, Optional[str], bool]:
        """执行列出私聊流命令"""
        
        try:
            # 获取所有私聊流
            private_streams = chat_api.get_private_streams(DEFAULT_PLATFORM)
            
            if not private_streams:
                return True, "当前没有可用的私聊流", True
            
            # 构建回复消息
            lines = ["📋 可用的私聊流列表：", ""]
            
            for i, stream in enumerate(private_streams[:20], 1):  # 最多显示20个
                stream_info = chat_api.get_stream_info(stream)
                user_id = stream_info.get("user_id", "未知")
                user_name = stream_info.get("user_name", "未知用户")
                lines.append(f"{i}. {user_name} (ID: {user_id})")
            
            if len(private_streams) > 20:
                lines.append(f"... 还有 {len(private_streams) - 20} 个私聊流")
            
            return True, "\n".join(lines), True
            
        except Exception as e:
            logger.error(f"获取私聊流列表失败: {e}")
            return False, f"获取失败: {str(e)}", True


# ==================== 插件主类 ====================

@register_plugin
class ProactivePrivateChatPlugin(BasePlugin):
    """
    主动私聊插件
    
    让麦麦能够主动发起私聊，支持命令触发和智能决策触发。
    """
    
    # 插件基本信息
    plugin_name = "proactive_private_chat"
    enable_plugin = True
    dependencies = []
    python_dependencies = []
    config_file_name = "config.toml"
    
    # 配置文件模式
    config_schema = {
        "general": {
            "enabled": {"type": "bool", "default": True, "description": "是否启用主动私聊功能"},
            "cooldown_seconds": {"type": "int", "default": 300, "description": "私聊冷却时间（秒）"},
            "allowed_platforms": {"type": "list", "default": ["qq"], "description": "允许的平台列表"}
        },
        "smart_chat": {
            "trigger_probability": {"type": "float", "default": 0.3, "description": "智能私聊触发概率"},
            "only_known_users": {"type": "bool", "default": True, "description": "是否只对已知用户私聊"},
            "min_impression_threshold": {"type": "int", "default": 50, "description": "最小好感度阈值"}
        },
        "messages": {
            "default_greeting": {"type": "str", "default": "嗨 {nickname}，最近怎么样呀？", "description": "默认问候消息"},
            "random_greetings": {"type": "list", "default": [], "description": "随机问候消息列表"}
        },
        "command": {
            "require_admin": {"type": "bool", "default": False, "description": "命令是否需要管理员权限"},
            "allowed_users": {"type": "list", "default": [], "description": "允许使用命令的用户列表"}
        }
    }
    
    def get_plugin_components(self) -> List[Tuple[ComponentInfo, Type]]:
        """返回插件包含的组件列表"""
        return [
            # 主动私聊 Action
            (ProactivePrivateChatAction.get_action_info(), ProactivePrivateChatAction),
            # 私聊命令
            (PrivateChatCommand.get_command_info(), PrivateChatCommand),
            # 列出私聊流命令
            (ListPrivateStreamsCommand.get_command_info(), ListPrivateStreamsCommand),
        ]
    
    async def on_load(self):
        """插件加载时的初始化"""
        logger.info("主动私聊插件已加载")
    
    async def on_unload(self):
        """插件卸载时的清理"""
        logger.info("主动私聊插件已卸载")