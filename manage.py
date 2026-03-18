#!/usr/bin/env python
"""
Coder 管理脚本

# 启动服务器
python manage.py runserver


"""

import click


@click.group()
def cli():
    """Lowcode-Coder-Engine 管理命令行工具"""
    pass


@cli.command()
def runserver():
    """启动开发服务器"""
    click.echo("正在启动服务器...")

    # 导入模块
    from coder import run

    # 创建命令行参数字典
    server_args = {}

    # 使用命令行参数启动服务器
    run.main(cli_args=server_args)


if __name__ == "__main__":
    cli()
