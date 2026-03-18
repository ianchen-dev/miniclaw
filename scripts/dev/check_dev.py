#!/usr/bin/env python3
"""
开发环境检查脚本
检查开发环境是否正确设置，包括pre-commit hooks
"""

import subprocess
import sys
from pathlib import Path


def run_command(cmd, capture_output=True):
    """运行命令"""
    try:
        result = subprocess.run(cmd, shell=True, check=True, capture_output=capture_output, text=True)
        return True, result.stdout if capture_output else ""
    except subprocess.CalledProcessError as e:
        return False, e.stderr if capture_output else ""


def check_git_repo():
    """检查是否在git仓库中"""
    return Path(".git").exists()


def check_project_root():
    """检查是否在项目根目录"""
    return Path("pyproject.toml").exists()


def check_uv_available():
    """检查uv是否可用"""
    success, _ = run_command("uv --version")
    return success


def check_pre_commit_installed():
    """检查pre-commit hooks是否已安装"""
    pre_commit_hook = Path(".git/hooks/pre-commit")
    commit_msg_hook = Path(".git/hooks/commit-msg")
    return pre_commit_hook.exists() and commit_msg_hook.exists()


def install_pre_commit_hooks():
    """安装pre-commit hooks"""
    print("🔧 正在自动安装 pre-commit hooks...")

    success1, _ = run_command("uv run pre-commit install")
    success2, _ = run_command("uv run pre-commit install --hook-type commit-msg")

    return success1 and success2


def main():
    """主函数"""
    print("🔍 检查 FlyGPT 开发环境...")

    # 检查项目根目录
    if not check_project_root():
        print("❌ 错误：请在项目根目录运行此脚本")
        sys.exit(1)

    # 检查是否在git仓库中
    if not check_git_repo():
        print("❌ 错误：当前目录不是git仓库")
        sys.exit(1)

    # 检查uv是否可用
    if not check_uv_available():
        print("❌ 错误：uv 未安装或不可用")
        print("请安装uv：")
        print("  macOS/Linux: curl -LsSf https://astral.sh/uv/install.sh | sh")
        print('  Windows: powershell -c "irm https://astral.sh/uv/install.ps1 | iex"')
        sys.exit(1)

    print("✅ uv 可用")

    # 检查pre-commit hooks
    if check_pre_commit_installed():
        print("✅ pre-commit hooks 已安装")

        # 验证hooks是否正常工作
        print("🔍 验证 pre-commit 配置...")
        success, output = run_command("uv run pre-commit run --all-files")
        if success:
            print("✅ pre-commit 配置验证成功")
        else:
            print("⚠️  pre-commit 检查发现问题")
            print("建议运行：uv run pre-commit run --all-files")
    else:
        print("❌ pre-commit hooks 未安装")

        if install_pre_commit_hooks():
            print("✅ pre-commit hooks 安装成功")
        else:
            print("❌ pre-commit hooks 安装失败")
            print("请手动运行：")
            print("  uv run pre-commit install")
            print("  uv run pre-commit install --hook-type commit-msg")
            sys.exit(1)

    print("\n🎉 开发环境检查完成！")
    print("\n💡 提示：")
    print("  - 每次 git commit 都会自动运行代码检查")
    print("  - 使用 'uv run cz commit' 进行规范化提交")
    print("  - 使用 'uv run pre-commit run --all-files' 手动检查所有文件")
    print("  - 使用 'uv run setup-dev' 重新设置开发环境")


if __name__ == "__main__":
    main()
