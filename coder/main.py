from coder.agent import run_agent_loop
from coder.tools import TOOLS


def main():
    run_agent_loop(tools=TOOLS, enable_intelligence=True)


main()
