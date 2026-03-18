import abc
from typing import Any, Type


class Singleton(abc.ABCMeta, type):
    """
    单例元类，用于确保一个类只有一个实例
    """

    _instances = {}

    def __call__(cls, *args: Any, **kwargs: Any) -> Any:
        if cls not in cls._instances:
            cls._instances[cls] = super(Singleton, cls).__call__(*args, **kwargs)
        return cls._instances[cls]

    @classmethod
    def update_instance(cls, new_instance: Type["AbstractSingleton"]):
        """
        更新单例实例
        """
        cls._instances[cls.__class__] = new_instance
        # print(f"单例实例已更新: {new_instance}")


class AbstractSingleton(abc.ABC, metaclass=Singleton):
    """抽象单例类，以确保一个类只有一个实例"""

    pass
