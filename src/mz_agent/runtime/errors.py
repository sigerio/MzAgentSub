"""MzAgent 第一阶段领域异常。"""


class ContractViolationError(Exception):
    """协议对象或领域规则被破坏时抛出。"""


class TransitionViolationError(ContractViolationError):
    """状态门禁不允许当前转换时抛出。"""


class DomainValidationError(ContractViolationError):
    """领域语义不满足最小契约时抛出。"""

