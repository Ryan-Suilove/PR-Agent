"""
CLI适配器 - PR审查系统
功能：本地命令行接口，无需飞书配置即可使用
支持：命令行交互模式和Git钩子模式
"""

import asyncio
import json
import uuid
import os
import sys
import time
import argparse
from datetime import datetime
from typing import Dict, Optional, List

# 导入重构后的模块
from src.core.workflow import build_pr_review_graph
from src.utils.config import CONFIG
from src.utils.thread_safe_logger import log_info, log_error, log_warning


class CLIReviewManager:
    """CLI模式的PR审查管理器"""

    def __init__(self):
        self.reviews: Dict[str, Dict] = {}
        self.pr_graph = build_pr_review_graph()

    def add_review(self, review_data: Dict) -> str:
        review_id = str(uuid.uuid4())
        review_data['id'] = review_id
        review_data['created_at'] = datetime.now().isoformat()
        self.reviews[review_id] = review_data
        return review_id

    def get_review(self, review_id: str) -> Dict:
        return self.reviews.get(review_id)

    def update_review(self, review_id: str, update_data: Dict):
        if review_id in self.reviews:
            self.reviews[review_id].update(update_data)

    async def run_pr_review(self, review_id: str, initial_state: Dict) -> Dict:
        """运行PR审查工作流"""
        config = {"configurable": {"thread_id": review_id}}
        final_state = None
        try:
            async for chunk in self.pr_graph.astream(initial_state, config, stream_mode="values"):
                final_state = chunk
                log_info(f"[审查进度] {chunk.get('current_stage', 'unknown')}")
            return final_state
        except Exception as e:
            log_error(f"[错误] PR审查失败: {str(e)}")
            import traceback
            traceback.print_exc()
            return None


# 全局变量
cli_review_manager = CLIReviewManager()

# Git仓库配置
GIT_BASE_BRANCH = CONFIG['git_repo']['base_branch']
REPO_NAME = CONFIG['git_repo']['repo_name']


def print_banner():
    """打印CLI横幅"""
    print("\n" + "="*60)
    print("  PRManager - 本地代码审查系统 (CLI模式)")
    print("="*60)


def print_usage():
    """打印使用说明"""
    print("""
使用方式:
  1. 分支审查:
     python main_cli.py review <源分支> [目标分支]
     示例: python main_cli.py review feature/login main

  2. 交互模式:
     python main_cli.py interactive

  3. Git钩子模式 (post-receive):
     python main_cli.py hook

  4. 监听模式 (持续监控push):
     python main_cli.py watch

配置说明:
  - 在 config/config.yaml 中配置仓库路径和LLM设置
  - 支持 local (Ollama) 和 api (OpenRouter) 两种LLM模式
""")


async def run_review(source_branch: str, target_branch: str, user_name: str = "CLI用户") -> Dict:
    """执行PR审查

    Args:
        source_branch: 源分支名
        target_branch: 目标分支名
        user_name: 用户名

    Returns:
        审查结果字典
    """
    print(f"\n📋 审查请求:")
    print(f"   仓库: {REPO_NAME}")
    print(f"   源分支: {source_branch}")
    print(f"   目标分支: {target_branch}")
    print(f"   提交者: {user_name}")
    print()

    review_id = cli_review_manager.add_review({
        'feishu_user_id': 'cli_user',
        'feishu_message': f'{source_branch} merge {target_branch}',
        'source_branch': source_branch,
        'target_branch': target_branch,
        'repo_name': REPO_NAME
    })

    print(f"⏳ 正在审查中...")
    print("-" * 40)

    initial_state = {
        'feishu_user_id': 'cli_user',
        'feishu_user_name': user_name,
        'feishu_message': f'{source_branch} merge {target_branch}',
        'source_branch': source_branch,
        'target_branch': target_branch,
        'repo_name': REPO_NAME,
    }

    log_info(f"[信息] 开始审查分支合并: {review_id}")
    final_state = await cli_review_manager.run_pr_review(review_id, initial_state)

    return final_state


def display_result(final_state: Optional[Dict]):
    """显示审查结果"""
    print("\n" + "="*60)
    print("  审查结果")
    print("="*60 + "\n")

    if not final_state:
        print("❌ 审查过程出错，未能获取结果")
        return

    # 获取反馈信息
    submitter_feedback = final_state.get('submitter_feedback', '')
    admin_feedback = final_state.get('admin_feedback', '')
    final_decision = final_state.get('final_decision', 'unknown')

    # 显示决策结果
    if final_decision == 'approve':
        print("✅ 审查结果: 通过")
    elif final_decision == 'reject':
        print("❌ 审查结果: 未通过")
    else:
        print(f"⚠️ 审查结果: {final_decision}")

    print()

    # 显示详细反馈
    if submitter_feedback:
        print("-" * 40)
        print("📋 详细报告:")
        print("-" * 40)
        print(submitter_feedback)

    # 保存完整报告到文件
    report_dir = "logs/review_reports"
    os.makedirs(report_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_file = os.path.join(report_dir, f"review_{timestamp}.md")

    with open(report_file, 'w', encoding='utf-8') as f:
        f.write(f"# 代码审查报告\n\n")
        f.write(f"**时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write(f"**结果**: {'✅ 通过' if final_decision == 'approve' else '❌ 未通过'}\n\n")
        if admin_feedback:
            f.write("## 详细报告\n\n")
            f.write(admin_feedback)

    print(f"\n📄 完整报告已保存至: {report_file}")


async def cmd_review(args):
    """处理review命令"""
    if len(args) < 1:
        print("❌ 错误: 请指定源分支")
        print("用法: python main_cli.py review <源分支> [目标分支]")
        return

    source_branch = args[0]
    target_branch = args[1] if len(args) > 1 else GIT_BASE_BRANCH

    final_state = await run_review(source_branch, target_branch)
    display_result(final_state)


async def cmd_interactive():
    """交互模式"""
    print_banner()
    print("📝 交互模式 - 输入分支名进行审查，输入 'quit' 退出\n")

    while True:
        try:
            user_input = input("请输入命令 (或 'help' 查看帮助): ").strip()

            if not user_input:
                continue

            if user_input.lower() in ['quit', 'exit', 'q']:
                print("\n👋 再见!")
                break

            if user_input.lower() == 'help':
                print("""
命令说明:
  <源分支> [目标分支]  - 审查指定分支的合并
  branches            - 列出所有分支
  status              - 显示系统状态
  config              - 显示当前配置
  clear               - 清屏
  quit / exit / q     - 退出程序
  help                - 显示此帮助
""")
                continue

            if user_input.lower() == 'clear':
                os.system('cls' if os.name == 'nt' else 'clear')
                print_banner()
                continue

            if user_input.lower() == 'branches':
                await list_branches()
                continue

            if user_input.lower() == 'status':
                show_status()
                continue

            if user_input.lower() == 'config':
                show_config()
                continue

            # 解析分支审查命令
            parts = user_input.split()
            if len(parts) >= 1:
                source_branch = parts[0]
                target_branch = parts[1] if len(parts) > 1 else GIT_BASE_BRANCH
                final_state = await run_review(source_branch, target_branch)
                display_result(final_state)

        except KeyboardInterrupt:
            print("\n\n👋 再见!")
            break
        except Exception as e:
            print(f"❌ 错误: {str(e)}")


async def list_branches():
    """列出所有分支"""
    print("\n📋 分支列表:")
    print("-" * 40)

    try:
        from src.adapters.git_adapter import get_git_adapter
        git_adapter = get_git_adapter()
        branches = await git_adapter.list_branches()

        for branch in branches:
            marker = " *" if branch == GIT_BASE_BRANCH else ""
            print(f"  {branch}{marker}")

        print(f"\n当前基础分支: {GIT_BASE_BRANCH}")
    except Exception as e:
        print(f"❌ 获取分支列表失败: {str(e)}")


def show_status():
    """显示系统状态"""
    print("\n📊 系统状态:")
    print("-" * 40)

    # LLM状态
    llm_mode = CONFIG['llm'].get('mode', 'local')
    print(f"  LLM模式: {llm_mode}")

    if llm_mode == 'api':
        api_base = CONFIG['llm'].get('api_base_url', 'N/A')
        model = CONFIG['llm'].get('model', 'N/A')
        print(f"  API地址: {api_base}")
        print(f"  模型: {model}")
        print(f"  API密钥: {'已配置' if CONFIG['llm'].get('api_key') else '未配置'}")
    else:
        ollama_url = CONFIG['llm'].get('base_url', 'http://localhost:11434')
        model = CONFIG['llm'].get('model', 'N/A')
        print(f"  Ollama地址: {ollama_url}")
        print(f"  模型: {model}")

    # Git仓库状态
    repo_path = CONFIG['git_repo'].get('repo_path', 'N/A')
    print(f"  仓库路径: {repo_path}")
    print(f"  基础分支: {GIT_BASE_BRANCH}")

    # 检查仓库是否存在
    if os.path.exists(repo_path):
        print(f"  仓库状态: ✅ 存在")
    else:
        print(f"  仓库状态: ❌ 不存在")


def show_config():
    """显示当前配置"""
    print("\n⚙️ 当前配置:")
    print("-" * 40)

    # LLM配置
    print("\n[LLM配置]")
    for key, value in CONFIG.get('llm', {}).items():
        if key == 'api_key' and value:
            print(f"  {key}: ***已配置***")
        else:
            print(f"  {key}: {value}")

    # Git配置
    print("\n[Git仓库配置]")
    for key, value in CONFIG.get('git_repo', {}).items():
        print(f"  {key}: {value}")

    # PR审查配置
    print("\n[PR审查配置]")
    pr_config = CONFIG.get('pr_review', {})
    for key, value in pr_config.items():
        print(f"  {key}: {value}")


async def cmd_hook():
    """Git钩子模式 - 处理post-receive钩子"""
    print_banner()
    print("🔗 Git Hook 模式 (post-receive)")
    print("-" * 40)

    # 从stdin读取post-receive输入
    try:
        for line in sys.stdin:
            parts = line.strip().split()
            if len(parts) >= 3:
                old_rev, new_rev, ref_name = parts

                # 只处理分支推送
                if ref_name.startswith('refs/heads/'):
                    branch_name = ref_name.replace('refs/heads/', '')

                    # 跳过基础分支
                    if branch_name == GIT_BASE_BRANCH:
                        print(f"⏭️ 跳过基础分支: {branch_name}")
                        continue

                    print(f"\n📥 检测到分支推送: {branch_name}")

                    # 执行审查
                    final_state = await run_review(branch_name, GIT_BASE_BRANCH, "Git Hook")

                    # 显示结果
                    if final_state:
                        decision = final_state.get('final_decision', 'unknown')
                        if decision == 'reject':
                            print("\n⚠️ 警告: 代码审查未通过，建议修复后再合并!")

    except Exception as e:
        print(f"❌ Hook处理错误: {str(e)}")


async def cmd_watch():
    """监听模式 - 持续监控Git仓库的push事件"""
    print_banner()
    print("👀 监听模式 - 持续监控Git仓库push事件")
    print("-" * 40)
    print(f"仓库: {CONFIG['git_repo'].get('repo_path', 'N/A')}")
    print(f"基础分支: {GIT_BASE_BRANCH}")
    print("\n按 Ctrl+C 停止监听...\n")

    from src.adapters.git_adapter import get_git_adapter
    git_adapter = get_git_adapter()

    # 记录已知的分支提交
    known_commits = {}

    # 初始化：获取所有分支的当前提交
    try:
        branches = await git_adapter.list_branches()
        for branch in branches:
            commit_hash = git_adapter._run_git_command(["rev-parse", branch])
            known_commits[branch] = commit_hash
            print(f"  已记录分支: {branch} ({commit_hash[:8]})")
    except Exception as e:
        print(f"❌ 初始化失败: {str(e)}")
        return

    print("\n🔄 开始监听...")

    # 监听循环
    poll_interval = CONFIG.get('cli', {}).get('watch_interval', 30)

    while True:
        try:
            await asyncio.sleep(poll_interval)

            # 检查分支变化
            branches = await git_adapter.list_branches()

            for branch in branches:
                try:
                    commit_hash = git_adapter._run_git_command(["rev-parse", branch])

                    if branch not in known_commits:
                        # 新分支
                        known_commits[branch] = commit_hash
                        print(f"\n🆕 新分支: {branch} ({commit_hash[:8]})")
                    elif known_commits[branch] != commit_hash:
                        # 分支有更新
                        old_hash = known_commits[branch]
                        known_commits[branch] = commit_hash
                        print(f"\n📝 分支更新: {branch}")
                        print(f"   {old_hash[:8]} -> {commit_hash[:8]}")

                        # 如果不是基础分支，执行审查
                        if branch != GIT_BASE_BRANCH:
                            print(f"\n⏳ 自动审查分支: {branch} -> {GIT_BASE_BRANCH}")
                            final_state = await run_review(branch, GIT_BASE_BRANCH, "自动审查")
                            display_result(final_state)

                except Exception as e:
                    log_error(f"检查分支 {branch} 失败: {str(e)}")
                    continue

        except KeyboardInterrupt:
            print("\n\n👋 停止监听，再见!")
            break
        except Exception as e:
            log_error(f"监听错误: {str(e)}")
            await asyncio.sleep(5)


def start_cli():
    """启动CLI模式"""
    parser = argparse.ArgumentParser(
        description='PRManager - 本地代码审查系统 (CLI模式)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python main_cli.py review feature/login main    审查feature/login分支合并到main
  python main_cli.py interactive                   进入交互模式
  python main_cli.py hook                          作为Git post-receive钩子运行
  python main_cli.py watch                         持续监听仓库push事件
        """
    )

    subparsers = parser.add_subparsers(dest='command', help='可用命令')

    # review 命令
    review_parser = subparsers.add_parser('review', help='审查指定分支')
    review_parser.add_argument('source_branch', help='源分支名')
    review_parser.add_argument('target_branch', nargs='?', default=GIT_BASE_BRANCH, help='目标分支名 (默认为配置的基础分支)')

    # interactive 命令
    subparsers.add_parser('interactive', help='进入交互模式')

    # hook 命令
    subparsers.add_parser('hook', help='作为Git post-receive钩子运行')

    # watch 命令
    subparsers.add_parser('watch', help='持续监听仓库push事件')

    args = parser.parse_args()

    # 根据命令执行对应操作
    if args.command == 'review':
        asyncio.run(cmd_review([args.source_branch, args.target_branch]))
    elif args.command == 'interactive':
        asyncio.run(cmd_interactive())
    elif args.command == 'hook':
        asyncio.run(cmd_hook())
    elif args.command == 'watch':
        asyncio.run(cmd_watch())
    else:
        # 无命令或help
        print_banner()
        print_usage()


if __name__ == "__main__":
    start_cli()