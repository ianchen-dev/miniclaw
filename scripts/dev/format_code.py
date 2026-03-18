#!/usr/bin/env python3
"""
代码格式化脚本
使用Ruff对指定目录进行代码格式化和检查
"""

import argparse
import subprocess
import sys
from pathlib import Path


def run_command(cmd, description=""):
    """运行命令并处理错误"""
    if description:
        print(f"🔧 {description}...")

    try:
        result = subprocess.run(cmd, shell=True, check=True, capture_output=True, text=True)
        return True, result.stdout
    except subprocess.CalledProcessError as e:
        print(f"❌ 错误: {e}")
        if e.stderr:
            print(f"错误详情: {e.stderr}")
        return False, e.stderr


def check_project_root():
    """检查是否在项目根目录"""
    return Path("pyproject.toml").exists()


def count_python_files(path):
    """统计Python文件数量"""
    if Path(path).is_file() and path.endswith(".py"):
        return 1
    elif Path(path).is_dir():
        return len(list(Path(path).rglob("*.py")))
    return 0


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="FlyGPT 代码格式化工具")
    parser.add_argument(
        "--targets",
        nargs="*",
        default=["flygpt/", "extended/", "manage.py"],
        help="要格式化的目录和文件 (默认: flygpt/ extended/ manage.py)",
    )
    parser.add_argument("--check-only", action="store_true", help="只检查不修复")
    parser.add_argument("--format-only", action="store_true", help="只格式化不检查")

    args = parser.parse_args()

    # 检查是否在项目根目录
    if not check_project_root():
        print("❌ 错误：请在项目根目录运行此脚本")
        sys.exit(1)

    targets = args.targets

    print("🚀 开始代码格式化和检查...")
    print(f"📋 目标文件/目录: {' '.join(targets)}")
    print()

    # 检查目标是否存在
    for target in targets:
        if not Path(target).exists():
            print(f"⚠️  警告: {target} 不存在，跳过")
            targets.remove(target)

    if not targets:
        print("❌ 没有有效的目标文件或目录")
        sys.exit(1)

    success = True

    # 步骤1: 代码检查和修复
    if not args.format_only:
        print("📋 步骤 1: 检查并修复代码问题...")

        if args.check_only:
            cmd = f"uv run ruff check {' '.join(targets)}"
        else:
            cmd = f"uv run ruff check --fix {' '.join(targets)}"

        check_success, _ = run_command(cmd)
        if check_success:
            print("✅ 代码检查和修复完成")
        else:
            print("❌ 代码检查发现问题")
            if args.check_only:
                print("💡 运行 'uv run format-code' 自动修复问题")
            success = False
        print()

    # 步骤2: 代码格式化
    if not args.check_only:
        print("🎨 步骤 2: 格式化代码...")

        cmd = f"uv run ruff format {' '.join(targets)}"
        format_success, _ = run_command(cmd)
        if format_success:
            print("✅ 代码格式化完成")
        else:
            print("❌ 代码格式化失败")
            success = False
        print()

    if success:
        print("🎉 所有操作完成！代码已格式化并修复了问题。")
    else:
        print("⚠️  部分操作失败，请检查错误信息")

    # 显示统计信息
    print()
    print("📊 格式化统计:")
    print("已处理的目录和文件:")

    total_files = 0
    for target in targets:
        file_count = count_python_files(target)
        total_files += file_count

        if Path(target).is_dir():
            print(f"  📁 {target}: {file_count} 个Python文件")
        elif Path(target).is_file():
            print(f"  📄 {target}: 1 个Python文件")

    print(f"  📈 总计: {total_files} 个Python文件")

    if not success:
        sys.exit(1)


if __name__ == "__main__":
    main()
