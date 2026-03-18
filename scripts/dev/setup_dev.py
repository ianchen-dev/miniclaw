#!/usr/bin/env python3
"""
开发环境设置脚本
用于团队成员快速设置开发环境
"""

import subprocess
import sys
from pathlib import Path


def run_command(cmd, description=""):
    """运行命令并处理错误"""
    if description:
        print(f"📦 {description}...")

    try:
        result = subprocess.run(cmd, shell=True, check=True, capture_output=True, text=True)
        return True, result.stdout
    except subprocess.CalledProcessError as e:
        print(f"❌ 错误: {e}")
        if e.stderr:
            print(f"错误详情: {e.stderr}")
        return False, e.stderr


def check_requirements():
    """检查前置要求"""
    print("🔍 检查前置要求...")

    # 检查是否在项目根目录
    if not Path("pyproject.toml").exists():
        print("❌ 错误：请在项目根目录运行此脚本")
        return False

    # 检查是否在git仓库中
    if not Path(".git").exists():
        print("❌ 错误：当前目录不是git仓库")
        return False

    # 检查uv是否安装
    success, _ = run_command("uv --version")
    if not success:
        print("❌ 错误：uv 未安装")
        print("安装命令：")
        print("  macOS/Linux: curl -LsSf https://astral.sh/uv/install.sh | sh")
        print('  Windows: powershell -c "irm https://astral.sh/uv/install.ps1 | iex"')
        return False

    print("✅ 前置要求检查通过")
    return True


def install_dependencies():
    """安装项目依赖"""
    success, output = run_command("uv sync --all-extras", "安装项目依赖")
    if not success:
        print("❌ 依赖安装失败")
        return False

    print("✅ 依赖安装成功")
    return True


def install_pre_commit_hooks():
    """安装pre-commit hooks"""
    print("🔧 设置 pre-commit hooks...")

    # 安装pre-commit hook
    success, _ = run_command("uv run pre-commit install")
    if not success:
        print("❌ pre-commit hook 安装失败")
        return False

    # 安装commit-msg hook
    success, _ = run_command("uv run pre-commit install --hook-type commit-msg")
    if not success:
        print("❌ commit-msg hook 安装失败")
        return False

    print("✅ pre-commit hooks 安装成功")
    return True


def verify_setup():
    """验证设置"""
    print("✅ 验证 pre-commit 配置...")

    success, output = run_command("uv run pre-commit run --all-files")
    if success:
        print("✅ pre-commit 配置验证成功")
    else:
        print("⚠️  pre-commit 检查发现问题，已自动修复")
        print("请检查修改的文件，如有需要请重新提交")

    return True


def main():
    """主函数"""
    print("🚀 设置 FlyGPT 开发环境...")
    print()

    # 检查前置要求
    if not check_requirements():
        sys.exit(1)

    print()

    # 安装依赖
    if not install_dependencies():
        sys.exit(1)

    print()

    # 安装pre-commit hooks
    if not install_pre_commit_hooks():
        sys.exit(1)

    print()

    # 验证设置
    verify_setup()

    print()
    print("🎉 开发环境设置完成！")
    print()
    print("📋 常用命令：")
    print("  uv run python manage.py runserver    # 启动开发服务器")
    print("  uv run pre-commit run --all-files    # 手动运行代码检查")
    print("  uv run cz commit                     # 规范化提交")
    print("  uv run check-dev                     # 检查开发环境")
    print()
    print("💡 提示：现在每次 git commit 都会自动运行代码检查和格式化")


if __name__ == "__main__":
    main()
