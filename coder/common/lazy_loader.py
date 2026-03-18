from typing import Any, Optional


class LazyLoader:
    """
    该类包装模块。在第一次访问属性时加载真正的模块并传递所有属性。
    """

    def __init__(self, module_name: str):
        self.module_name: str = module_name
        self._module: Optional[Any] = None

    def __getattr__(self, name):
        """
        在第一次访问属性时加载真正的模块并传递所有属性。
        """

        try:
            return getattr(self._module, name)

        except Exception as e:
            if self._module is None:
                # 如果模块尚未加载，则加载它
                import importlib

                self._module = importlib.import_module(name=self.module_name)
            else:
                # 模块被设置，收到与getattr（）不同的异常。reraise它
                raise e

        # 重试getattr如果模块只是第一次加载调用这个外部异常处理程序，以防它引发新的异常
        return getattr(self._module, name)


auto_import_module: set[str] = set()
"""自动导入的模块"""


def lazy_import_batch(*module_name: str, auto: bool = False) -> tuple[Any, ...]:
    """

    Args:
        *module_name: 模块名，如：'component'
        auto: 是否自动导入，如果为True，则会在启动服务后自动导入。

    Returns:

    """
    r: list[Any] = []
    for e in module_name:
        r.append(LazyLoader(module_name=e))
        if auto:
            auto_import_module.add(e)
    return tuple(r)


def lazy_import_single(module_name: str, auto: bool = False) -> Any:
    """

    Args:
        module_name: 模块名，如：'component'
        auto: 是否自动导入，如果为True，则会在启动服务后自动导入。

    Returns:

    """

    model = LazyLoader(module_name=module_name)
    if auto:
        auto_import_module.add(module_name)
    return model
