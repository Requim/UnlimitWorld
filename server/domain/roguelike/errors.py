"""卡牌肉鸽错误类型。"""


class RoguelikeError(Exception):
    """领域与应用错误的公共基类。"""


class InvalidAction(RoguelikeError):
    """动作不符合当前局面规则。"""


class RevisionConflict(RoguelikeError):
    """客户端版本或幂等动作内容发生冲突。"""


class Unauthorized(RoguelikeError):
    """匿名访问凭证无效或不拥有目标局面。"""


class RunNotFound(RoguelikeError):
    """目标局面不存在。"""
