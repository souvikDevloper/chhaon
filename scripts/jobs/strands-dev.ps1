# Install Strands Agents (with the OpenAI-compatible model provider) into build\winpy for local tests on this PC.
$ErrorActionPreference = 'Continue'
python -m pip install "strands-agents[openai]" --target build\winpy --upgrade --quiet 2>&1 | Select-Object -Last 3
python -c "import sys; sys.path.insert(0, r'build\winpy'); import importlib.metadata as m; print('strands', m.version('strands-agents'), 'openai', m.version('openai'), 'httpx', m.version('httpx'))" 2>&1
exit 0
